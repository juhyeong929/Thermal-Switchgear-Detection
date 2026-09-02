"""train / val / test 분할 — 정책 + 재현 가능한 생성기 + 누수 감사.

**이것은 최종 학습셋 확정이 아니다.** 라벨링이 끝나지 않았으므로 지금은
`분할 정책` 과 `그 정책을 실행하는 도구` 와 `누수를 검사하는 방법` 까지만 만든다.
최종 분할은 라벨이 모인 뒤 같은 도구로 다시 돌려 고정한다.

---
분할 단위 = cluster_id (기본) 또는 session_key (--unit session)
    근거: 파이프라인 Step 03 Note — 같은 클러스터가 train/val 에 나뉘면 검증 지표가
          부풀려진다(data leakage). DEC-008 에서 클러스터를 "분할의 최소 단위"로 정했다.
    실측 근거: 정본 라벨 1,036장 중 63장이 비대표다. 이미지 단위로 나누면 이 63장이
          자기 대표와 다른 split 으로 갈릴 수 있다. 클러스터 단위면 그런 일이 없다.

    왜 "연결요소로 더 느슨하게 묶기"를 쓰지 않는가 (실측):
          병합 기준을 낮춰 union-find 로 묶어 보면 덩어리가 폭주한다.
              h22 c0.93(현 기준)  그룹 19,394  최대  12,289장  상위10 32.8%
              h22 c0.90           그룹 16,220  최대  17,494장  상위10 46.8%
              h22 c0.88           그룹 14,725  최대  19,370장  상위10 53.2%
          DEC-008 에서 단일연결 연쇄로 41,063장 덩어리가 생겨 폐기했던 문제가
          그대로 재현된다. 12,289장(11.5%)짜리 그룹은 통째로 한 split 에 들어가므로
          비율을 맞출 수 없다. -> 채택하지 않는다.

    세션 단위가 더 엄격한 대안인 이유 (실측):
          근접 미달 쌍 96,292 중 46,801(48.6%)이 같은 세션 안에 있다.
          세션 단위로 나누면 이 48.6% 는 정의상 같은 split 에 남는다.
          세션 175개 · 최대 6,016장(5.6%) · 반을 넘나드는 세션 0개 이므로
          반별 층화도 그대로 가능하다. 대신 층화 granularity 가 거칠어진다.
          어느 쪽을 최종으로 쓸지는 사람 판단이다 -> OQ-016

층화 축 = 반(panel) × 카메라(camera)
    근거(반):     DEC-002 — 반은 독립 데이터 도메인이다. 한 반이 test 에만 몰리면
                  그 반의 성능을 학습에서 전혀 배우지 못한다.
    근거(카메라): DEC-008 실측 — 축소율이 IR1 6.6% / IR2 72.2% / IR3 56.8% 로 갈린다.
                  단발 촬영과 연속 촬영은 성격이 다르므로 한쪽에 몰리면 안 된다.

비율 = 기본 70 / 15 / 15
    **근거 없음.** 프로젝트 문서 어디에도 지정이 없다. 관례값을 기본으로 두고
    인자로 바꿀 수 있게 했다. 확정은 사람 판단이다 -> OQ-015

무작위 시드 고정
    근거: 같은 입력에 같은 분할이 나와야 보고서의 수치를 재현할 수 있다.

출력(--unit session 으로 돌리면 파일명에 `_session` 이 붙어 비교용으로 따로 남는다):
      data/splits/group_split.csv           분할 그룹 -> split
      data/splits/image_split.csv           이미지 -> split (그룹에서 상속)
      reports/data_audit/split_leakage.csv  누수 감사
      reports/data_audit/split_balance.csv  분포 균형
"""

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

DEFAULT_RATIO = (0.70, 0.15, 0.15)   # 근거 없음. OQ-015 참조
SPLITS = ("train", "val", "test")
GROUP_KEY = {"cluster": "cluster_id", "session": "session_key"}


def load():
    with (paths.DEDUP / "dedup_metadata.csv").open(encoding="utf-8-sig") as fh:
        dd = list(csv.DictReader(fh))
    cam = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "IR":
                cam[r["rel_path"]] = r["camera"]
    return dd, cam


def assign(dd, cam, ratio, seed, unit="cluster"):
    """분할 단위로 묶은 뒤 (반 × 카메라) 층 안에서 비율대로 나눈다.

    unit="cluster"  같은 클러스터는 절대 갈리지 않는다 (기본)
    unit="session"  같은 촬영 회차가 통째로 한 split 에 간다 (더 엄격, OQ-016)

    그룹의 카메라는 그 대표 이미지의 카메라로 잡는다. 한 그룹이 여러 카메라를
    섞는 경우가 있어(연속 촬영에서 기기가 바뀜) 대표를 기준으로 하나만 정한다.
    """
    key = GROUP_KEY[unit]
    rng = random.Random(seed)
    cl = defaultdict(list)
    rep_cam = {}
    for r in dd:
        cl[r[key]].append(r)
        if r["is_representative"] == "1" and r[key] not in rep_cam:
            rep_cam[r[key]] = cam.get(r["rel_path"], "?")

    strata = defaultdict(list)
    for gid, members in cl.items():
        strata[(members[0]["panel_id"], rep_cam.get(gid, "?"))].append(gid)

    out = {}
    for _key, gids in sorted(strata.items()):
        # 큰 그룹이 한쪽에 몰리지 않도록 크기 순으로 정렬한 뒤 섞어 배분한다
        gids = sorted(gids, key=lambda g: (-len(cl[g]), g))
        rng.shuffle(gids)
        n = len(gids)
        n_tr = round(n * ratio[0])
        n_va = round(n * ratio[1])
        for i, g in enumerate(gids):
            out[g] = ("train" if i < n_tr else
                      "val" if i < n_tr + n_va else "test")
    return cl, out


def audit_leakage(cl, split_of, dd, unit="cluster"):
    """누수 감사 세 가지. 각각 무엇을 잡는지 다르다."""
    key = GROUP_KEY[unit]
    rows = []
    split_img = {r["rel_path"]: split_of[r[key]] for r in dd}

    # 1. 클러스터 교차 — 이미지에서 되짚어 실제로 검사한다.
    #    cluster 단위면 설계상 0. session 단위면 세션을 넘나드는 클러스터(1.8%)가
    #    갈릴 수 있으므로 0 이 아닐 수 있다 — 그것이 세션 단위의 대가다.
    per_cluster = defaultdict(set)
    for r in dd:
        per_cluster[r["cluster_id"]].add(split_img[r["rel_path"]])
    cross = sum(1 for v in per_cluster.values() if len(v) > 1)
    rows.append({
        "check": "클러스터 교차", "count": cross, "denominator": len(per_cluster),
        "expected": "0" if unit == "cluster" else "0 이 아닐 수 있음",
        "status": ("PASS" if cross == 0 else
                   "FAIL" if unit == "cluster" else "WARN"),
        "meaning": ("같은 클러스터가 두 split 에 걸침. cluster 단위에서는 설계상 불가능하므로 "
                    "0 이 아니면 구현 버그. session 단위에서는 세션을 넘나드는 클러스터가 "
                    "갈린 것이며 실제 누수다"),
    })

    # 2. 근접 미달 쌍 교차 — 잔여 위험. 병합 기준을 아슬아슬하게 통과 못 한 쌍
    #    DEC-008 은 과소병합을 택했다(오병합보다 안전). 그 대가가 여기서 드러난다
    near_cross = near_tot = 0
    cp = paths.DEDUP / "candidate_pairs.csv"
    if cp.exists():
        import numpy as np
        idxp = paths.DEDUP / "embeddings_index.csv"
        emb = np.load(paths.DEDUP / "embeddings.npy").astype(np.float32)
        with idxp.open(encoding="utf-8-sig") as fh:
            row_of = {r["rel_path"]: int(r["row"]) for r in csv.DictReader(fh)}
        with cp.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if int(r["hamming"]) > 22:
                    continue
                ra, rb = row_of.get(r["rel_a"]), row_of.get(r["rel_b"])
                if ra is None or rb is None:
                    continue
                cos = float(emb[ra] @ emb[rb])
                if not (0.90 <= cos < 0.93):      # 병합 기준 바로 아래 구간
                    continue
                near_tot += 1
                if split_img.get(r["rel_a"]) != split_img.get(r["rel_b"]):
                    near_cross += 1
    rows.append({
        "check": "근접 미달 쌍 교차", "count": near_cross, "denominator": near_tot,
        "expected": "낮을수록 좋음",
        "status": "INFO",
        "meaning": "병합 기준(코사인 0.93)을 아슬아슬하게 못 넘은 쌍이 split 을 가로지름. "
                   "과소병합을 택한 대가이며 잔여 누수 위험이다",
    })

    # 3. 세션 교차 — 정보용. 같은 회차가 갈리는 것 자체는 금지가 아니다
    ses = defaultdict(set)
    for r in dd:
        ses[r["session_key"]].add(split_img[r["rel_path"]])
    ses_cross = sum(1 for v in ses.values() if len(v) > 1)
    rows.append({
        "check": "촬영 세션 교차", "count": ses_cross, "denominator": len(ses),
        "expected": "정책상 허용" if unit == "cluster" else "0",
        "status": "INFO" if unit == "cluster" else
                  ("PASS" if ses_cross == 0 else "FAIL"),
        "meaning": "같은 회차가 여러 split 에 걸침. 클러스터가 다르면 다른 장면이므로 "
                   "금지하지 않는다. 더 엄격히 가려면 세션 단위 분할로 바꿔야 한다",
    })
    return rows, split_img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", default="70,15,15",
                    help="train,val,test 비율 (기본 70,15,15 — 근거 없음, OQ-015)")
    ap.add_argument("--seed", type=int, default=20260828)
    ap.add_argument("--unit", choices=("cluster", "session"), default="cluster",
                    help="분할 단위 (기본 cluster. session 은 더 엄격 — OQ-016)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    ratio = tuple(float(x) / 100 for x in a.ratio.split(","))
    if abs(sum(ratio) - 1) > 1e-6:
        sys.exit("비율 합이 100 이 아니다")

    dd, cam = load()
    cl, split_of = assign(dd, cam, ratio, a.seed, a.unit)
    leak, split_img = audit_leakage(cl, split_of, dd, a.unit)
    key = GROUP_KEY[a.unit]
    sfx = "" if a.unit == "cluster" else f"_{a.unit}"

    paths.SPLITS.mkdir(parents=True, exist_ok=True)
    with (paths.SPLITS / f"group_split{sfx}.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["group_unit", "group_id", "split", "panel_id", "group_size"])
        for gid, sp in sorted(split_of.items()):
            w.writerow([a.unit, gid, sp, cl[gid][0]["panel_id"], len(cl[gid])])
    with (paths.SPLITS / f"image_split{sfx}.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["image_id", "rel_path", "cluster_id", "session_key",
                    "group_unit", "split", "panel_id", "camera",
                    "is_representative"])
        for r in dd:
            w.writerow([r["image_id"], r["rel_path"], r["cluster_id"],
                        r["session_key"], a.unit, split_of[r[key]],
                        r["panel_id"], cam.get(r["rel_path"], "?"),
                        r["is_representative"]])

    # 분포 균형
    bal = []
    for axis, getter in (("panel", lambda r: r["panel_id"]),
                         ("camera", lambda r: cam.get(r["rel_path"], "?"))):
        agg = defaultdict(Counter)
        for r in dd:
            agg[getter(r)][split_of[r[key]]] += 1
        for k, c in sorted(agg.items()):
            tot = sum(c.values())
            bal.append({"axis": axis, "value": k, "total": tot,
                        **{sp: c[sp] for sp in SPLITS},
                        **{f"{sp}_pct": f"{c[sp]/tot:.4f}" for sp in SPLITS}})
    with (paths.AUDIT / f"split_balance{sfx}.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(bal[0]))
        w.writeheader()
        w.writerows(bal)
    with (paths.AUDIT / f"split_leakage{sfx}.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(leak[0]))
        w.writeheader()
        w.writerows(leak)

    # ---- 콘솔 ----
    n_img = Counter(split_of[r[key]] for r in dd)
    n_grp = Counter(split_of.values())
    n_rep = Counter(split_of[r[key]] for r in dd
                    if r["is_representative"] == "1")
    print(f"분할 단위 = {key} · 층화 = 반 × 카메라 · "
          f"비율 {a.ratio} · seed {a.seed}")
    print()
    print(f"{'split':<8}{'그룹':>10}{'대표':>10}{'전체 이미지':>12}")
    for sp in SPLITS:
        print(f"{sp:<8}{n_grp[sp]:>10,}{n_rep[sp]:>10,}{n_img[sp]:>12,}")
    print(f"{'합계':<8}{sum(n_grp.values()):>10,}{sum(n_rep.values()):>10,}"
          f"{sum(n_img.values()):>12,}")

    print()
    print("누수 감사")
    for r in leak:
        print(f"  [{r['status']}] {r['check']:<16}{r['count']:,} / "
              f"{r['denominator']:,}")

    print()
    print(f"분포 균형 (대표 기준 목표 "
          f"{ratio[0]:.0%}/{ratio[1]:.0%}/{ratio[2]:.0%})")
    print(f"  {'축':<8}{'값':<8}{'train':>9}{'val':>8}{'test':>8}")
    for r in bal:
        print(f"  {r['axis']:<8}{r['value']:<8}"
              f"{float(r['train_pct'])*100:>8.1f}%{float(r['val_pct'])*100:>7.1f}%"
              f"{float(r['test_pct'])*100:>7.1f}%")

    print()
    print("**이것은 최종 학습셋이 아니다.** 정책·도구·감사까지만 만들었다.")
    print("라벨이 모이면 같은 명령으로 다시 돌려 고정한다.")


if __name__ == "__main__":
    main()
