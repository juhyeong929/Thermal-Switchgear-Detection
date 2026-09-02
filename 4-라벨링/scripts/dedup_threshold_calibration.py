"""OQ-016 후속 — 병합 임계값(코사인)을 바꾸면 클러스터가 어떻게 되는지 **측정만** 한다.

왜
    REV-005 육안 판정 101쌍에서 **0.9155 를 경계로 위험이 0~4% 와 37~44% 로 갈렸다.**
    DEC-008 은 0.93 을 골랐고 0.90 은 폭주해 기각했지만 **그 사이는 시험하지 않았다.**

무엇을 바꾸고 무엇을 고정하나
    바꾸는 것: **코사인 임계값 하나뿐이다.**
    고정: 임베딩 · 해밍 조건(<=22) · 리더 방식 · 후보쌍 · 인벤토리 · 반 · 세션 · 카메라 ·
          정렬 순서(리더 선정 순서) · 동점 처리.
    `dedup_d_cluster` 의 함수와 순서 규칙을 그대로 불러 쓴다. 새 알고리즘을 만들지 않는다.

절대 하지 않는 것
    **기존 `cluster_id` · `dedup_metadata.csv` · `cluster_summary.csv` · `group_split.csv` ·
    train/val/test 를 수정하지 않는다.** 결과는 별도 폴더에만 쓴다.
    임계값 선택 규칙을 코드에 넣지 않는다 — 결과·trade-off·경고만 낸다. 결정은 사람이 한다.

출력
    experiments/dedup/threshold_calibration/<임계값>/cluster_summary.csv · metrics.json
    experiments/dedup/threshold_calibration/pair_projection.csv   REV-005 101쌍의 동거 여부
    experiments/dedup/threshold_calibration/tradeoff.csv          한눈에 보는 비교표

사용
    python scripts/dedup_threshold_calibration.py
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import dedup_d_cluster as D  # noqa: E402
from schemas import paths  # noqa: E402

OUT = paths.PROJECT / "experiments" / "dedup" / "threshold_calibration"
OQ016 = paths.AUDIT / "oq016"

HAM_MAX = 22          # DEC-008 이 고른 값. 이번 실험에서 고정한다
BASELINE = 0.93       # 현재 채택된 값
GRID = [0.930, 0.925, 0.920, 0.9175, 0.9155, 0.9125, 0.910]
RISK = {"SAME_SCENE", "NEAR_DUPLICATE"}


def leader_cluster(order, adj, n):
    """`dedup_d_cluster` 의 리더 방식 그대로. 순서와 동점 처리를 바꾸지 않는다."""
    leader_of, is_leader = {}, [False] * n
    for i in order:
        bestj, bestc = None, -1.0
        for j, cos in adj.get(i, ()):
            if is_leader[j] and cos > bestc:
                bestj, bestc = j, cos
        if bestj is None:
            is_leader[i] = True
            leader_of[i] = i
        else:
            leader_of[i] = bestj
    return leader_of


def metrics(groups):
    sz = np.array(sorted((len(v) for v in groups.values()), reverse=True))
    tot = int(sz.sum())
    return {
        "cluster_count": int(len(sz)),
        "singleton_count": int((sz == 1).sum()),
        "largest_cluster_size": int(sz[0]),
        "p95_cluster_size": int(np.percentile(sz, 95)),
        "p99_cluster_size": int(np.percentile(sz, 99)),
        "top10_cluster_share": round(float(sz[:10].sum() / tot), 5),
        "mean_cluster_size": round(float(sz.mean()), 4),
        "median_cluster_size": float(np.median(sz)),
        "images": tot,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    idx, emb, row_of, fp, pairs = D.load()
    n = len(idx)
    print(f"이미지 {n:,} · 후보쌍 {len(pairs):,} · 해밍 <= {HAM_MAX} 고정")

    # 코사인은 한 번만 계산한다. 임계값마다 다시 재지 않는다.
    edges = []
    for a, b, h in pairs:
        if h > HAM_MAX:
            continue
        ra, rb = row_of.get(a), row_of.get(b)
        if ra is None or rb is None:
            continue
        edges.append((ra, rb, float(emb[ra] @ emb[rb])))
    print(f"해밍 통과 쌍 {len(edges):,}")

    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        has_rgb = {r["rel_path"]: r["has_rgb_pair"] == "1"
                   for r in csv.DictReader(fh) if r["kind"] == "IR"}
    order = sorted(range(n),
                   key=lambda i: (idx[i]["panel_id"],
                                  fp[idx[i]["rel_path"]]["_skey"],
                                  0 if has_rgb.get(idx[i]["rel_path"]) else 1,
                                  fp[idx[i]["rel_path"]]["_seq"]))

    # REV-005 판정 쌍
    proj_rows = []
    sample = {r["pair_id"]: r for r in D.csv.DictReader(
        (OQ016 / "sample_pairs.csv").open(encoding="utf-8-sig"))}
    rev = {r["pair_id"]: r["verdict"].strip() for r in D.csv.DictReader(
        (OQ016 / "visual_review.csv").open(encoding="utf-8-sig"))
        if not r["pair_id"].startswith("#") and r["verdict"].strip()}
    pair_rows = []
    for pid, v in rev.items():
        s = sample.get(pid)
        if not s:
            continue
        ra, rb = row_of.get(s["rel_a"]), row_of.get(s["rel_b"])
        if ra is None or rb is None:
            continue
        pair_rows.append({"pair_id": pid, "cosine": s["cosine"],
                          "human_verdict": v, "ra": ra, "rb": rb,
                          "same_session": s["same_session"], "panel": s["panel"]})
    print(f"REV-005 판정 쌍 {len(pair_rows)} 개를 각 임계값에 투영한다\n")

    trade, projections = [], {r["pair_id"]: dict(r) for r in pair_rows}
    for C in GRID:
        adj = defaultdict(list)
        kept = 0
        for ra, rb, cos in edges:
            if cos < C:
                continue
            adj[ra].append((rb, cos))
            adj[rb].append((ra, cos))
            kept += 1
        leader_of = leader_cluster(order, adj, n)
        groups = defaultdict(list)
        for i, lead in leader_of.items():
            groups[lead].append(i)
        m = metrics(groups)
        m["cos_min"] = C
        m["ham_max"] = HAM_MAX
        m["edges_kept"] = kept

        # REV-005 투영 — 두 이미지가 같은 클러스터인가
        col = f"cluster_same_at_{C:g}"
        cap = mrg = npos = nneg = 0
        for r in pair_rows:
            same = leader_of.get(r["ra"]) == leader_of.get(r["rb"])
            projections[r["pair_id"]][col] = int(same)
            if r["human_verdict"] in RISK:
                npos += 1; cap += same
            elif r["human_verdict"] == "DIFFERENT_SCENE":
                nneg += 1; mrg += same
        m["human_positive_n"] = npos
        m["human_positive_capture"] = round(cap / npos, 4) if npos else None
        m["human_negative_n"] = nneg
        m["human_negative_merge"] = round(mrg / nneg, 4) if nneg else None

        d = OUT / f"{C:g}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "metrics.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        with (d / "cluster_summary.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["cluster_id", "panel_id", "size", "representative_rel_path"])
            for lead, mem in sorted(groups.items(), key=lambda x: -len(x[1])):
                w.writerow([f"C{lead}", idx[lead]["panel_id"], len(mem),
                            idx[lead]["rel_path"]])
        trade.append(m)
        print(f"cos >= {C:<7g} 클러스터 {m['cluster_count']:>7,} · "
              f"singleton {m['singleton_count']:>7,} · 최대 {m['largest_cluster_size']:>6,} · "
              f"top10 {m['top10_cluster_share']:>6.2%} · "
              f"capture {m['human_positive_capture']:.1%} · "
              f"false-merge {m['human_negative_merge']:.1%}")

    with (OUT / "tradeoff.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trade[0]))
        w.writeheader(); w.writerows(trade)
    cols = ["pair_id", "cosine", "human_verdict", "same_session", "panel"] + \
           [f"cluster_same_at_{c:g}" for c in GRID]
    with (OUT / "pair_projection.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(projections.values(), key=lambda r: -float(r["cosine"])))

    # ---- 기준선 재현 검증 — 이게 안 맞으면 비교 자체가 성립하지 않는다 ----
    base = next(m for m in trade if m["cos_min"] == BASELINE)
    with (paths.DEDUP / "cluster_summary.csv").open(encoding="utf-8-sig") as fh:
        existing = list(csv.DictReader(fh))
    same = base["cluster_count"] == len(existing)
    print(f"\n[기준선 재현] cos {BASELINE} 클러스터 {base['cluster_count']:,} vs "
          f"기존 {len(existing):,} -> {'일치' if same else '불일치'}")
    if not same:
        print("  **불일치 — DEC-008 수치와 직접 비교 불가**로 기록해야 한다")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
