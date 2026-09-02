"""OQ-016 후속 — **split 단계 제약**을 걸면 분포가 얼마나 왜곡되는지 시뮬레이션한다.

배경
    임계값 보정 실험에서 0.91~0.93 어디에도 더 나은 trade-off 가 없었다.
    문제는 임계값이 아니라 리더 방식의 성질이었다. 그래서 방향을 바꾼다 —
    **클러스터링은 그대로 두고, 분할 단계에서만 근접 후보쌍을 같은 split 에 두는 제약.**

이 실험의 성격
    **READ-ONLY · SIMULATION ONLY.** 실제 split 파일을 만들지 않는다.
    `cluster_id` · `dedup_metadata.csv` · `cluster_summary.csv` · `group_split.csv` ·
    `image_split.csv` · 임계값 0.93 · 기존 분할 정책 **전부 무수정.**

방법
    노드는 **cluster_id** 다 (이미지가 아니다). 제약 간선이 서로 다른 클러스터를 이으면
    그 클러스터들이 한 덩어리(super-group)가 되어 같은 split 으로 간다.
    **클러스터를 다시 만들지 않는다** — 기존 cluster_id 를 노드로 쓸 뿐이다.

    분할은 `build_splits.assign` 과 같은 규칙을 쓴다: (반 × 카메라) 층 안에서
    그룹 수 기준 70/15/15, 크기 정렬 후 같은 seed 로 셔플.

false merge 의 의미가 다르다
    클러스터 병합에서는 다른 장면을 하나로 묶는 것이 곧 오류다.
    **split 제약에서는 다르다** — 다른 장면이라도 근접 유사하면 train/val/test 에
    비슷한 데이터가 걸치는 위험이 생기므로, 같은 split 에 두는 것 자체는 문제가 아니다.
    비용은 오직 **분포 왜곡**(비율·반별 고갈·이동량)으로 나타난다.

출력
    experiments/dedup/split_constraint_sim/scenarios.csv   시나리오별 지표
    experiments/dedup/split_constraint_sim/<S>/panel_camera.csv  층별 분포

사용
    python scripts/split_constraint_sim.py
"""

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from schemas import paths  # noqa: E402

OUT = paths.PROJECT / "experiments" / "dedup" / "split_constraint_sim"
OQ016 = paths.AUDIT / "oq016"
RATIO = (0.70, 0.15, 0.15)
SEED = 20260828          # build_splits 기본값과 같게
HAM_MAX = 22


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def load():
    with (paths.DEDUP / "dedup_metadata.csv").open(encoding="utf-8-sig") as fh:
        dd = list(csv.DictReader(fh))
    cam = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "IR":
                cam[r["rel_path"]] = r["camera"]
    base = {}
    with (paths.PROJECT / "data" / "splits" / "image_split.csv").open(
            encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            base[r["rel_path"]] = r["split"]
    return dd, cam, base


def edges_for(scenario, cos_min, row_of, emb, pairs, cl_of):
    """제약 간선 — **서로 다른 클러스터를 잇는 것만** 의미가 있다."""
    if scenario == "S1":
        # 사람이 SAME/NEAR 로 판정한 쌍만
        sample = {r["pair_id"]: r for r in csv.DictReader(
            (OQ016 / "sample_pairs.csv").open(encoding="utf-8-sig"))}
        out = []
        with (OQ016 / "visual_review.csv").open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r["pair_id"].startswith("#"):
                    continue
                if r["verdict"].strip() in ("SAME_SCENE", "NEAR_DUPLICATE"):
                    s = sample.get(r["pair_id"])
                    if s:
                        out.append((s["rel_a"], s["rel_b"]))
        return out
    out = []
    for a, b, h in pairs:
        if h > HAM_MAX:
            continue
        ra, rb = row_of.get(a), row_of.get(b)
        if ra is None or rb is None:
            continue
        if float(emb[ra] @ emb[rb]) >= cos_min:
            out.append((a, b))
    return out


def assign(groups, panel_of, cam_of, seed=SEED):
    """build_splits.assign 과 같은 규칙 — (반 × 카메라) 층 · 그룹 수 기준 · 같은 seed."""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for gid, members in groups.items():
        strata[(panel_of[gid], cam_of[gid])].append(gid)
    out = {}
    for _k, gids in sorted(strata.items()):
        gids = sorted(gids, key=lambda g: (-len(groups[g]), str(g)))
        rng.shuffle(gids)
        n = len(gids)
        n_tr = round(n * RATIO[0])
        n_va = round(n * RATIO[1])
        for i, g in enumerate(gids):
            out[g] = "train" if i < n_tr else "val" if i < n_tr + n_va else "test"
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    dd, cam, base = load()
    cl_of = {r["rel_path"]: r["cluster_id"] for r in dd}
    panel_img = {r["rel_path"]: r["panel_id"] for r in dd}
    sess_img = {r["rel_path"]: r["session_key"] for r in dd}

    # 클러스터의 반·카메라는 대표 이미지 기준 (build_splits 와 같다)
    cl_panel, cl_cam, cl_imgs = {}, {}, defaultdict(list)
    for r in dd:
        c = r["cluster_id"]
        cl_imgs[c].append(r["rel_path"])
        cl_panel.setdefault(c, r["panel_id"])
        if r["is_representative"] == "1":
            cl_cam.setdefault(c, cam.get(r["rel_path"], "?"))
    for c in cl_imgs:
        cl_cam.setdefault(c, "?")

    import dedup_d_cluster as D
    idx, emb, row_of, fp, pairs = D.load()

    scenarios = [("S0", "제약 없음 (현행)", None),
                 ("S1", "REV-005 human SAME/NEAR 22쌍만", None),
                 ("S2", "코사인 >= 0.9155 후보 전체", 0.9155),
                 ("S3", "코사인 >= 0.920 후보 전체", 0.920),
                 ("S4", "코사인 >= 0.925 후보 전체", 0.925)]

    rows = []
    n_img = len(dd)
    for sid, desc, cmin in scenarios:
        uf = UF()
        for c in cl_imgs:
            uf.find(c)
        n_edge = n_cross = 0
        if sid != "S0":
            for a, b in edges_for(sid, cmin, row_of, emb, pairs, cl_of):
                ca, cb = cl_of.get(a), cl_of.get(b)
                if ca is None or cb is None:
                    continue
                n_edge += 1
                if uf.find(ca) != uf.find(cb):
                    n_cross += 1
                uf.union(ca, cb)

        groups = defaultdict(list)
        for c, imgs in cl_imgs.items():
            groups[uf.find(c)] += imgs
        # 슈퍼그룹의 반·카메라 = 가장 큰 구성 클러스터 기준
        g_panel, g_cam, g_mixed = {}, {}, 0
        members_by_g = defaultdict(list)
        for c in cl_imgs:
            members_by_g[uf.find(c)].append(c)
        for g, cs in members_by_g.items():
            big = max(cs, key=lambda c: len(cl_imgs[c]))
            g_panel[g] = cl_panel[big]
            g_cam[g] = cl_cam[big]
            if len({cl_panel[c] for c in cs}) > 1:
                g_mixed += 1

        split_of_g = assign(groups, g_panel, g_cam)
        split_img = {}
        for g, imgs in groups.items():
            for p in imgs:
                split_img[p] = split_of_g[g]

        cnt = Counter(split_img.values())
        # 재배정 무작위성 때문에 옮겨진 것까지 세면 제약의 비용을 과대평가한다.
        # 그룹 수가 바뀌면 층 안의 셔플 결과가 통째로 달라지기 때문이다.
        # 그래서 두 가지를 따로 낸다.
        #   moved_images  이번 시뮬레이션 배정 vs 현행 배정의 단순 차이 (무작위성 포함)
        #   forced_moves  **제약이 강제하는 최소 이동** — 한 덩어리 안에서 현행 split 이
        #                 갈려 있을 때 소수파가 다수파로 옮겨져야 하는 양
        moved = sum(1 for p, s in split_img.items() if base.get(p) not in (None, s))
        forced = 0
        for g, imgs in groups.items():
            c = Counter(base[p] for p in imgs if p in base)
            if len(c) > 1:
                forced += sum(c.values()) - max(c.values())
        sizes = sorted((len(v) for v in groups.values()), reverse=True)

        # 반별 val/test 최소치
        pv = Counter((panel_img[p], s) for p, s in split_img.items())
        panels = sorted({panel_img[p] for p in split_img})
        min_val = min(pv.get((pn, "val"), 0) for pn in panels)
        min_test = min(pv.get((pn, "test"), 0) for pn in panels)
        zero_val = [pn for pn in panels if pv.get((pn, "val"), 0) == 0]
        zero_test = [pn for pn in panels if pv.get((pn, "test"), 0) == 0]

        # 세션이 여러 split 에 걸치는 수 (제약이 줄여 주는지 본다)
        sess = defaultdict(set)
        for p, s in split_img.items():
            sess[sess_img[p]].add(s)
        sess_viol = sum(1 for v in sess.values() if len(v) > 1)

        m = {
            "scenario": sid, "edge_rule": desc,
            "edges": n_edge, "cross_cluster_edges": n_cross,
            "components": len(groups),
            "largest_component": sizes[0],
            "largest_share": round(sizes[0] / n_img, 5),
            "p99_component": int(np.percentile(sizes, 99)),
            "cross_panel_components": g_mixed,
            "moved_images": moved, "moved_ratio": round(moved / n_img, 5),
            "forced_moves": forced, "forced_ratio": round(forced / n_img, 5),
            "train_ratio": round(cnt["train"] / n_img, 4),
            "val_ratio": round(cnt["val"] / n_img, 4),
            "test_ratio": round(cnt["test"] / n_img, 4),
            "panel_min_val": min_val, "panel_min_test": min_test,
            "panels_zero_val": ",".join(zero_val), "panels_zero_test": ",".join(zero_test),
            "session_multi_split": sess_viol,
        }
        # feasible 의 정의를 드러내 둔다. 판정이 아니라 표시다.
        m["feasible"] = ("YES" if (not zero_val and not zero_test
                                   and m["largest_share"] < 0.05
                                   and abs(m["train_ratio"] - 0.70) < 0.03) else "확인")
        rows.append(m)

        d = OUT / sid
        d.mkdir(parents=True, exist_ok=True)
        pc = Counter((panel_img[p], cam.get(p, "?"), s) for p, s in split_img.items())
        with (d / "panel_camera.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["panel_id", "camera", "split", "images"])
            for (pn, cm, s), v in sorted(pc.items()):
                w.writerow([pn, cm, s, v])
        (d / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

        print(f"{sid}  {desc}")
        print(f"    간선 {n_edge:>8,} (클러스터 교차 {n_cross:>6,}) · "
              f"덩어리 {m['components']:>7,} · 최대 {m['largest_component']:>6,} "
              f"({m['largest_share']:.2%})")
        print(f"    비율 {m['train_ratio']:.1%}/{m['val_ratio']:.1%}/{m['test_ratio']:.1%} · "
              f"강제이동 {forced:>6,} ({m['forced_ratio']:.2%}) · "
              f"반별 최소 val {min_val:,} test {min_test:,} · "
              f"세션 교차 {sess_viol:,}")
        if zero_val or zero_test:
            print(f"    [경고] val 0장 반 {zero_val} · test 0장 반 {zero_test}")

    with (OUT / "scenarios.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"\n-> {OUT}")
    print("**실제 split 파일은 만들지 않았다.** 판정은 사람이 한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
