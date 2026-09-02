"""OQ-016 — 근접 미달 쌍의 **층화 표본**을 뽑고 육안 검증 자료를 만든다.

무엇을 검증하나
    DEC-008 은 과소병합을 택했다(오병합보다 안전). 그 대가로 **병합 기준을 아슬아슬하게
    못 넘은 쌍**(해밍<=22 · 코사인 0.90~0.93)이 남고, 그중 41,184쌍이 split 을 가로지른다.
    이 쌍들이 실제로 같은 장면이면 val/test 지표가 부풀고, 다른 장면이면 아무 문제 없다.
    **지금까지 육안 확인은 4건뿐이다.**

이 스크립트가 하는 것 / 하지 않는 것
    한다:   교차 쌍을 다시 세고 · 층화 표본을 뽑고 · 나란히 볼 이미지를 만든다
    안 한다: **판정하지 않는다.** clustering 을 다시 만들지 않는다. split 을 바꾸지 않는다.
            원본 이미지와 cluster_id 를 건드리지 않는다.

    목적은 새 알고리즘이 아니라 **현재 채택된 cluster 방식이 근접 미달 구간에서도
    동일 시야를 충분히 분리하고 있는지** 확인하는 것이다.

층화 축 (임의 균등표본을 쓰지 않는다)
    panel · camera · 세션 관계(same/diff) · 코사인 구간
    코사인 구간은 **실제 분포를 보고** 정한다 (`--explore`).

출력
    reports/data_audit/oq016/sample_pairs.csv    뽑은 쌍과 그 근거
    reports/data_audit/oq016/visual_review.csv   사람이 verdict 를 채우는 표
    reports/data_audit/oq016/summary.csv         층별 표본 수와 모집단 비중
    experiments/data_audit/oq016/pair_0001.png…  나란히 본 이미지

사용
    python scripts/oq016_sample.py --explore     # 분포만 보고 bin 을 정한다
    python scripts/oq016_sample.py --n 100
"""

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

OUT = paths.AUDIT / "oq016"
IMGDIR = paths.PROJECT / "experiments" / "data_audit" / "oq016"
HAMMING_MAX = 22          # DEC-008 의 후보 기준
COS_LO, COS_HI = 0.90, 0.93   # 병합 기준(0.93) 바로 아래 구간
SEED = 20260831

VERDICTS = ["SAME_SCENE", "NEAR_DUPLICATE", "DIFFERENT_SCENE", "UNCERTAIN"]


def load_meta():
    """rel_path -> (image_id, panel, camera, session, cluster_id, split)"""
    inv = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] != "IR":
                continue
            inv[r["rel_path"]] = {"image_id": r["image_id"], "panel": r["panel_id"],
                                  "camera": r["camera"], "session": r["session"]}
    with (paths.PROJECT / "data" / "splits" / "image_split.csv").open(
            encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            m = inv.get(r["rel_path"])
            if m is not None:
                m["split"] = r["split"]
                m["cluster_id"] = r["cluster_id"]
    return inv


def crossing_pairs(inv):
    """교차 쌍을 다시 센다. build_splits.py 와 같은 기준을 쓴다."""
    emb = np.load(paths.DEDUP / "embeddings.npy").astype(np.float32)
    with (paths.DEDUP / "embeddings_index.csv").open(encoding="utf-8-sig") as fh:
        row_of = {r["rel_path"]: int(r["row"]) for r in csv.DictReader(fh)}

    near, cross = 0, []
    with (paths.DEDUP / "candidate_pairs.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if int(r["hamming"]) > HAMMING_MAX:
                continue
            ra, rb = row_of.get(r["rel_a"]), row_of.get(r["rel_b"])
            if ra is None or rb is None:
                continue
            cos = float(emb[ra] @ emb[rb])
            if not (COS_LO <= cos < COS_HI):
                continue
            near += 1
            ma, mb = inv.get(r["rel_a"]), inv.get(r["rel_b"])
            if not ma or not mb or "split" not in ma or "split" not in mb:
                continue
            if ma["split"] == mb["split"]:
                continue
            cross.append({
                "rel_a": r["rel_a"], "rel_b": r["rel_b"],
                "hamming": int(r["hamming"]), "cosine": round(cos, 4),
                "panel": ma["panel"], "camera_a": ma["camera"], "camera_b": mb["camera"],
                "session_a": ma["session"], "session_b": mb["session"],
                "same_session": int(ma["session"] == mb["session"]),
                "cluster_a": ma["cluster_id"], "cluster_b": mb["cluster_id"],
                "same_cluster": int(ma["cluster_id"] == mb["cluster_id"]),
                "split_a": ma["split"], "split_b": mb["split"],
                "image_id_a": ma["image_id"], "image_id_b": mb["image_id"],
            })
    return near, cross


def bins_from(cross):
    """코사인 구간은 **실제 분포에서** 정한다. 균등 분위 4구간."""
    v = np.array([c["cosine"] for c in cross])
    edges = [COS_LO] + [round(float(np.percentile(v, q)), 4) for q in (25, 50, 75)] + [COS_HI]
    edges = sorted(set(edges))
    return edges


def bin_of(cos, edges):
    for i in range(len(edges) - 1):
        if edges[i] <= cos < edges[i + 1] or (i == len(edges) - 2 and cos <= edges[-1]):
            return f"{edges[i]:.4f}~{edges[i+1]:.4f}"
    return f"{edges[-2]:.4f}~{edges[-1]:.4f}"


def render(pair, idx, inv):
    import cv2
    out = IMGDIR / f"pair_{idx:04d}.png"
    ims = []
    for side in ("a", "b"):
        p = paths.PROCESSED / pair[f"rel_{side}"]
        if not p.exists():
            return None
        im = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
        if im is None:
            return None
        im = cv2.resize(im, (640, 480), interpolation=cv2.INTER_NEAREST)
        ims.append(im)

    gap = np.full((480, 6, 3), 60, np.uint8)
    body = np.hstack([ims[0], gap, ims[1]])
    band = np.full((86, body.shape[1], 3), 245, np.uint8)
    f, sc, th = cv2.FONT_HERSHEY_SIMPLEX, .48, 1
    cv2.putText(band, f"pair_{idx:04d}   cos {pair['cosine']:.4f}   hamming {pair['hamming']}"
                      f"   same_session={pair['same_session']}"
                      f"   same_cluster={pair['same_cluster']}",
                (10, 22), f, .55, (25, 25, 25), th, cv2.LINE_AA)
    cv2.putText(band, f"A  {pair['image_id_a']}", (10, 46), f, sc, (150, 60, 20), th, cv2.LINE_AA)
    cv2.putText(band, f"   {pair['camera_a']} | {pair['session_a'][:44]} | "
                      f"cl {pair['cluster_a']} | split {pair['split_a']}",
                (10, 64), f, .42, (110, 60, 40), th, cv2.LINE_AA)
    cv2.putText(band, f"B  {pair['image_id_b']}", (660, 46), f, sc, (20, 60, 150), th, cv2.LINE_AA)
    cv2.putText(band, f"   {pair['camera_b']} | {pair['session_b'][:44]} | "
                      f"cl {pair['cluster_b']} | split {pair['split_b']}",
                (660, 64), f, .42, (40, 60, 110), th, cv2.LINE_AA)
    IMGDIR.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", np.vstack([band, body]))[1].tofile(str(out))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=100, help="목표 표본 수 (80~150 권장)")
    ap.add_argument("--explore", action="store_true", help="분포만 보고 끝낸다")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    inv = load_meta()
    near, cross = crossing_pairs(inv)
    print(f"근접 미달 쌍 {near:,}  ·  split 교차 {len(cross):,} "
          f"({len(cross)/near:.1%})")

    v = np.array([c["cosine"] for c in cross])
    print(f"\n코사인 분포 (교차 쌍): 최소 {v.min():.4f} · p25 {np.percentile(v,25):.4f} "
          f"· 중앙 {np.median(v):.4f} · p75 {np.percentile(v,75):.4f} · 최대 {v.max():.4f}")
    print(f"세션 관계: 같은 세션 {sum(c['same_session'] for c in cross):,} "
          f"/ 다른 세션 {sum(1-c['same_session'] for c in cross):,}")
    print(f"같은 cluster 인데 split 이 다른 쌍: "
          f"{sum(c['same_cluster'] for c in cross):,}  <- 0 이 아니면 명백한 누수")
    print("\n반별:", dict(Counter(c["panel"] for c in cross).most_common()))
    print("카메라(A):", dict(Counter(c["camera_a"] for c in cross).most_common()))
    if a.explore:
        return 0

    edges = bins_from(cross)
    print(f"\n코사인 구간(실제 분포 4분위): {edges}")

    # ---- 층화 ----
    for c in cross:
        c["cos_bin"] = bin_of(c["cosine"], edges)
        c["cell"] = f"{c['panel']}|{c['camera_a']}|{'same' if c['same_session'] else 'diff'}" \
                    f"|{c['cos_bin']}"
    cells = defaultdict(list)
    for c in cross:
        cells[c["cell"]].append(c)

    rng = random.Random(SEED)
    total = len(cross)

    # **비례 배분이지 균등 배분이 아니다.** 층이 139개나 되면 전 층에 1개씩 주는 순간
    # 5.7% 층과 0.01% 층이 같은 무게를 갖는다 — 그건 층화가 아니다.
    #
    #   주요 층 (모집단의 MAJOR_MIN 이상)  -> 비례 배분, 최소 1
    #   나머지 잔층                        -> 하나로 묶어 비례 몫만큼 무작위 추출
    #
    # 잔층을 버리지 않는 이유: 드문 조합에서만 같은 장면이 나올 수도 있기 때문이다.
    MAJOR_MIN = 0.005                      # 0.5%
    major = {c: v for c, v in cells.items() if len(v) / total >= MAJOR_MIN}
    minor = {c: v for c, v in cells.items() if c not in major}
    pop_major = sum(len(v) for v in major.values())
    pop_minor = total - pop_major

    n_minor = round(a.n * pop_minor / total)
    n_major = a.n - n_minor

    alloc = {}
    for cell, items in major.items():
        alloc[cell] = max(1, round(n_major * len(items) / pop_major))
    # 반올림 오차를 큰 층에서 조정한다
    while sum(alloc.values()) > n_major and len(alloc) > 0:
        big = max(alloc, key=lambda k: alloc[k])
        if alloc[big] <= 1:
            break
        alloc[big] -= 1

    sample, srows = [], []
    for cell, items in sorted(major.items()):
        k = min(alloc[cell], len(items))
        sample += rng.sample(items, k)
        srows.append({"cell": cell, "population": len(items),
                      "population_pct": round(len(items) / total * 100, 3),
                      "sampled": k})

    # 잔층 — 반별로 비례해 뽑아 한쪽 반에 몰리지 않게 한다
    if minor and n_minor > 0:
        by_panel = defaultdict(list)
        for items in minor.values():
            for c in items:
                by_panel[c["panel"]].append(c)
        picked_minor = []
        for pn, items in sorted(by_panel.items()):
            k = min(len(items), max(1, round(n_minor * len(items) / pop_minor)))
            picked_minor += rng.sample(items, k)
        sample += picked_minor
        srows.append({"cell": f"(잔층 {len(minor)}개 묶음)", "population": pop_minor,
                      "population_pct": round(pop_minor / total * 100, 3),
                      "sampled": len(picked_minor)})
    rng.shuffle(sample)

    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["pair_id", "rel_a", "rel_b", "image_id_a", "image_id_b", "panel",
              "camera_a", "camera_b", "session_a", "session_b", "same_session",
              "cluster_a", "cluster_b", "same_cluster", "split_a", "split_b",
              "hamming", "cosine", "cos_bin", "cell"]
    for i, c in enumerate(sample, 1):
        c["pair_id"] = f"pair_{i:04d}"
    with (OUT / "sample_pairs.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(sample)

    with (OUT / "visual_review.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["pair_id", "verdict", "note", "image", "cosine",
                    "same_session", "same_cluster", "panel", "camera_a", "camera_b"])
        w.writerow([f"# verdict 는 넷 중 하나: {' / '.join(VERDICTS)}",
                    "", "", "", "", "", "", "", "", ""])
        w.writerow(["# SAME_SCENE=사실상 같은 시야(미세 이동만) · "
                    "NEAR_DUPLICATE=같은 대상 거의 같은 구도지만 명백히 다른 프레임",
                    "", "", "", "", "", "", "", "", ""])
        w.writerow(["# DIFFERENT_SCENE=시야·대상·구성이 실질적으로 다름 · "
                    "UNCERTAIN=두 장만으로 판정 불가", "", "", "", "", "", "", "", "", ""])
        for c in sample:
            w.writerow([c["pair_id"], "", "", f"{c['pair_id']}.png", c["cosine"],
                        c["same_session"], c["same_cluster"], c["panel"],
                        c["camera_a"], c["camera_b"]])

    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["cell", "population", "population_pct", "sampled"])
        w.writeheader()
        w.writerows(sorted(srows, key=lambda r: -r["population"]))

    print(f"\n층 {len(cells)}개 · 표본 {len(sample)}쌍 "
          f"(모집단 {total:,} 의 {len(sample)/total:.3%})")
    print(f"  같은 세션 {sum(c['same_session'] for c in sample)} / "
          f"다른 세션 {sum(1-c['same_session'] for c in sample)}")
    print(f"  상위 층 (모집단 비중):")
    for r in sorted(srows, key=lambda r: -r["population"])[:6]:
        print(f"    {r['cell']:<44}{r['population']:>7,} ({r['population_pct']:>5.2f}%)"
              f"  표본 {r['sampled']}")

    if not a.no_render:
        ok = 0
        for i, c in enumerate(sample, 1):
            if render(c, i, inv):
                ok += 1
        print(f"\n검토용 이미지 {ok}/{len(sample)}장 -> {IMGDIR}")

    print(f"\n-> {OUT}")
    print("판정은 사람이 한다. visual_review.csv 의 verdict 칸을 채운다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
