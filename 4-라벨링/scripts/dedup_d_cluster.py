"""STEP 08 Stage E — 후보쌍을 판정해 클러스터를 만들고 대표 이미지를 고른다.

판정 규칙은 손으로 정하지 않고 **pHash·임베딩과 무관한 정답셋**으로 보정한다.
정답은 파일명 메타데이터에서만 나오므로 두 지문 어느 쪽과도 독립이다.

  POSITIVE   같은 반·같은 세션의 연속 프레임 (seq 차이 1)      -> 같은 장면
  NEG-hard   같은 반·같은 세션이지만 seq 가 1000 이상 떨어짐   -> 같은 회차의 다른 구간
  NEG-easy   같은 반이지만 다른 건물                            -> 다른 설비

NEG-hard 가 핵심이다. 다른 건물끼리만 음성으로 쓰면 임계값이 한없이 느슨해진다.
실제 위험은 "같은 회차에 찍은 다른 부위"를 같은 장면으로 잘못 묶는 것이다.

클러스터링은 **리더(대표) 방식**을 쓴다. union-find 단일연결은
A~B, B~C, C~D 로 이어붙어 전혀 다른 장면까지 한 덩어리로 만든다
(실측: P1 45,721장 중 41,063장이 한 클러스터로 뭉쳤다).
리더 방식은 '이미 정해진 대표와 직접 비슷한가'만 보므로 연쇄가 생기지 않는다.

원본 이미지는 삭제하지 않는다. 이 단계의 결과물은 메타데이터뿐이다.

출력: data/dedup/dedup_metadata.csv           이미지 1장 = 1행
      data/dedup/cluster_summary.csv          클러스터 1개 = 1행
      reports/data_audit/dedup_calibration.csv 임계값 탐색 전 과정
      reports/data_audit/dedup_summary.csv     반별 축소 결과
"""

import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

HAM_GRID = [8, 10, 12, 14, 16, 18, 20, 22]
COS_GRID = [0.90, 0.92, 0.93, 0.94, 0.95, 0.96, 0.97]
GT_N = 600
FAR_SEQ = 1000          # NEG-hard 로 인정할 세션 내 seq 간격
MIN_SESSION = 1200      # NEG-hard 를 뽑을 수 있는 최소 세션 길이


def load():
    with (paths.DEDUP / "embeddings_index.csv").open(encoding="utf-8-sig") as fh:
        idx = list(csv.DictReader(fh))
    emb = np.load(paths.DEDUP / "embeddings.npy").astype(np.float32)
    row_of = {r["rel_path"]: int(r["row"]) for r in idx}
    with (paths.DEDUP / "fingerprints.csv").open(encoding="utf-8-sig") as fh:
        fp = {r["rel_path"]: r for r in csv.DictReader(fh) if not r["error"]}
    for r in fp.values():
        r["_seq"] = int(r["rel_path"].rsplit("_", 1)[1].split(".")[0])
        r["_skey"] = r["panel_id"] + "|" + r["session_key"]
        r["_bld"] = Path(r["rel_path"]).name.split("_")[1]
    with (paths.DEDUP / "candidate_pairs.csv").open(encoding="utf-8-sig") as fh:
        pairs = [(r["rel_a"], r["rel_b"], int(r["hamming"]))
                 for r in csv.DictReader(fh)]
    return idx, emb, row_of, fp, pairs


def ground_truth(fp):
    by_s = defaultdict(list)
    for r in fp.values():
        by_s[r["_skey"]].append(r)

    pos, hard = [], []
    for v in by_s.values():
        v.sort(key=lambda x: x["_seq"])
        pos += [(a, b) for a, b in zip(v, v[1:]) if b["_seq"] - a["_seq"] == 1]
        if len(v) > MIN_SESSION:
            for _ in range(300):
                i = random.randrange(len(v) - FAR_SEQ)
                j = random.randrange(i + FAR_SEQ, len(v))
                hard.append((v[i], v[j]))

    by_pb = defaultdict(list)
    for r in fp.values():
        by_pb[(r["panel_id"], r["_bld"])].append(r)
    panels = defaultdict(list)
    for (p, b), v in by_pb.items():
        panels[p].append(v)
    easy = []
    for bs in panels.values():
        if len(bs) < 2:
            continue
        for _ in range(200):
            v1, v2 = random.sample(bs, 2)
            easy.append((random.choice(v1), random.choice(v2)))

    for lst in (pos, hard, easy):
        random.shuffle(lst)
    return pos[:GT_N], hard[:GT_N], easy[:GT_N]


def feats(pairs, emb, row_of):
    h, c = [], []
    for a, b in pairs:
        ra, rb = row_of.get(a["rel_path"]), row_of.get(b["rel_path"])
        if ra is None or rb is None:
            continue
        h.append(bin(int(a["phash"], 16) ^ int(b["phash"], 16)).count("1"))
        c.append(float(emb[ra] @ emb[rb]))
    return np.array(h), np.array(c)


def calibrate(pos, hard, easy, emb, row_of):
    """규칙: 해밍 <= H 이고 코사인 >= C. 두 지문을 동시에 만족해야 병합한다."""
    hp, cp = feats(pos, emb, row_of)
    hh, ch = feats(hard, emb, row_of)
    he, ce = feats(easy, emb, row_of)
    trials = []
    for H in HAM_GRID:
        for C in COS_GRID:
            mp = (hp <= H) & (cp >= C)
            mh = (hh <= H) & (ch >= C)
            me = (he <= H) & (ce >= C)
            rec = float(mp.mean())
            fm_h, fm_e = float(mh.mean()), float(me.mean())
            tp = mp.sum()
            fp_ = mh.sum() + me.sum()
            prec = tp / (tp + fp_) if tp + fp_ else 0.0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            trials.append({"ham_max": H, "cos_min": C,
                           "recall": round(rec, 4),
                           "precision": round(float(prec), 4),
                           "f1": round(float(f1), 4),
                           "false_merge_hard": round(fm_h, 4),
                           "false_merge_easy": round(fm_e, 4)})
    # 오병합이 곧 데이터 손실이다. 같은 F1 이면 어려운 음성의 오병합이 낮은 쪽을 고른다.
    trials.sort(key=lambda t: (-t["f1"], t["false_merge_hard"]))
    return trials[0], trials


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(5)
    if not (paths.DEDUP / "embeddings.npy").exists():
        sys.exit("embeddings.npy 가 없다. scripts/dedup_c_embed.py 를 먼저 실행한다.")

    idx, emb, row_of, fp, pairs = load()
    print(f"이미지 {len(idx):,} / 후보쌍 {len(pairs):,}")

    pos, hard, easy = ground_truth(fp)
    best, trials = calibrate(pos, hard, easy, emb, row_of)
    print(f"\n정답셋 POS {len(pos)} / NEG-hard {len(hard)} / NEG-easy {len(easy)}")
    print(f"선택 규칙  해밍 <= {best['ham_max']}  이고  코사인 >= {best['cos_min']}")
    print(f"  재현율 {best['recall']:.1%}  정밀도 {best['precision']:.1%}  "
          f"F1 {best['f1']:.3f}")
    print(f"  오병합  어려운음성 {best['false_merge_hard']:.1%}  "
          f"쉬운음성 {best['false_merge_easy']:.1%}")

    with (paths.AUDIT / "dedup_calibration.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trials[0]))
        w.writeheader()
        w.writerows(trials)

    # --- 리더 방식 클러스터링 ------------------------------------------------
    H, C = best["ham_max"], best["cos_min"]
    adj = defaultdict(list)
    kept = 0
    for a, b, h in pairs:
        if h > H:
            continue
        ra, rb = row_of.get(a), row_of.get(b)
        if ra is None or rb is None:
            continue
        cos = float(emb[ra] @ emb[rb])
        if cos < C:
            continue
        adj[ra].append((rb, cos))
        adj[rb].append((ra, cos))
        kept += 1
    print(f"\n규칙을 통과한 쌍 {kept:,} / 후보 {len(pairs):,}")

    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        has_rgb = {r["rel_path"]: r["has_rgb_pair"] == "1"
                   for r in csv.DictReader(fh) if r["kind"] == "IR"}

    # 촬영 순서대로 훑으며 리더를 세운다. 뒤에 오는 프레임은 '리더와 직접 비슷할 때만'
    # 그 리더에 붙는다. 멤버끼리 이어붙지 않으므로 연쇄 병합이 생기지 않는다.
    #
    # 세션 안에서는 RGB 페어가 있는 프레임을 먼저 훑는다. 그러면 그 프레임이 리더가 되고,
    # 대표 이미지에 실화상이 딸려 온다 — 경계 판단과 교차 검증에 쓸 수 있다.
    order = sorted(range(len(idx)),
                   key=lambda i: (idx[i]["panel_id"],
                                  fp[idx[i]["rel_path"]]["_skey"],
                                  0 if has_rgb.get(idx[i]["rel_path"]) else 1,
                                  fp[idx[i]["rel_path"]]["_seq"]))
    leader_of = {}
    is_leader = [False] * len(idx)
    sim_of = {}
    for i in order:
        bestj, bestc = None, -1.0
        for j, cos in adj.get(i, ()):
            if is_leader[j] and cos > bestc:
                bestj, bestc = j, cos
        if bestj is None:
            is_leader[i] = True
            leader_of[i] = i
            sim_of[i] = 1.0
        else:
            leader_of[i] = bestj
            sim_of[i] = bestc

    groups = defaultdict(list)
    for i, lead in leader_of.items():
        groups[lead].append(i)

    # --- 산출물 -------------------------------------------------------------
    out = paths.DEDUP / "dedup_metadata.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["image_id", "panel_id", "session_key", "rel_path", "cluster_id",
                    "cluster_size", "is_representative", "is_duplicate",
                    "representative_id", "similarity_score", "has_rgb_pair"])
        for lead, members in groups.items():
            cid = f"{idx[lead]['panel_id']}-C{lead}"
            for m in members:
                r = idx[m]
                w.writerow([r["image_id"], r["panel_id"],
                            fp[r["rel_path"]]["_skey"], r["rel_path"], cid,
                            len(members), int(m == lead), int(m != lead),
                            idx[lead]["image_id"], f"{sim_of[m]:.4f}",
                            int(bool(has_rgb.get(r["rel_path"])))])

    with (paths.DEDUP / "cluster_summary.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["cluster_id", "panel_id", "size", "representative_id",
                    "rep_has_rgb_pair"])
        for lead, members in sorted(groups.items(), key=lambda x: -len(x[1])):
            w.writerow([f"{idx[lead]['panel_id']}-C{lead}", idx[lead]["panel_id"],
                        len(members), idx[lead]["image_id"],
                        int(bool(has_rgb.get(idx[lead]["rel_path"])))])

    per = defaultdict(lambda: [0, 0])
    for lead, members in groups.items():
        p = idx[lead]["panel_id"]
        per[p][0] += len(members)
        per[p][1] += 1
    with (paths.AUDIT / "dedup_summary.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["panel_id", "images", "clusters", "reduction_rate"])
        for p, (n, c) in sorted(per.items(), key=lambda x: -x[1][0]):
            w.writerow([p, n, c, f"{1 - c / n:.4f}"])
        tn = sum(v[0] for v in per.values())
        tc = sum(v[1] for v in per.values())
        w.writerow(["TOTAL", tn, tc, f"{1 - tc / tn:.4f}"])

    # 카메라별 축소율 — 촬영 방식(단발 vs 연속)에 따라 성격이 갈린다
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        cam_of = {r["rel_path"]: r["camera"] for r in csv.DictReader(fh)
                  if r["kind"] == "IR"}
    cam_all, cam_rep = defaultdict(int), defaultdict(int)
    for lead, members in groups.items():
        for m in members:
            cam_all[cam_of.get(idx[m]["rel_path"], "?")] += 1
        cam_rep[cam_of.get(idx[lead]["rel_path"], "?")] += 1
    with (paths.AUDIT / "dedup_camera_summary.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["camera", "images", "representatives", "reduction_rate"])
        for c in sorted(cam_all):
            w.writerow([c, cam_all[c], cam_rep[c],
                        f"{1 - cam_rep[c] / cam_all[c]:.4f}"])

    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    print(f"\n{'반':<6}{'이미지':>9}{'클러스터':>10}{'축소율':>9}")
    for p, (n, c) in sorted(per.items(), key=lambda x: -x[1][0]):
        print(f"{p:<6}{n:>9,}{c:>10,}{1 - c/n:>8.1%}")
    print(f"{'합계':<6}{tn:>9,}{tc:>10,}{1 - tc/tn:>8.1%}")
    print(f"\n최대 클러스터 {sizes[0]:,}  상위10 합 {sum(sizes[:10]):,} "
          f"({sum(sizes[:10])/tn:.1%})")
    print(f"실질 독립 이미지 {tc:,}장  <- STEP 09 라벨링 물량의 기준")


if __name__ == "__main__":
    main()
