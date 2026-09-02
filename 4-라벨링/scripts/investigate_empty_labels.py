"""NQ-1 조사 — 빈 라벨 파일이 '대상 없음'인가 '미작업'인가.

**분석 전용. 라벨을 수정하지 않는다.**

빈 라벨은 두 가지 뜻일 수 있고, 둘은 정반대다.
    (a) 정상 음성  — 그 프레임에 라벨 대상이 실제로 없다
    (b) 미작업     — 대상이 있는데 사람이 아직 안 그렸다
(b) 를 정본으로 올리면 모델에게 "이건 배경"이라고 가르치게 된다.

육안 판단은 표본에 그친다. 여기서는 **중복 클러스터를 판정 근거로 쓴다.**

  근거 1  같은 클러스터 동거
          STEP 08 에서 같은 클러스터로 묶였다는 것은 사실상 같은 장면이라는 뜻이다
          (해밍<=22 이고 코사인>=0.93, 오병합률 0.5%).
          같은 클러스터 안에 '박스가 있는 이미지'와 '빈 이미지'가 함께 있다면,
          그 빈 이미지는 대상이 있는데 안 그린 것일 가능성이 매우 높다.

  근거 2  최근접 이웃 유사도
          클러스터가 다르더라도, 빈 이미지의 임베딩 최근접 이웃(같은 반)이
          박스를 가진 이미지이고 유사도가 높다면 같은 정황이다.

  근거 3  세션 단위 공백
          한 세션이 통째로 미라벨이면 개별 판단이 아니라 작업 누락이다.

출력: reports/data_audit/nq1_empty_label_verdict.csv   빈 이미지 1장 = 1행
      reports/data_audit/nq1_session_summary.csv       세션별 요약
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

SOURCES = [("6ban", "6ban_existing_labels", "P6"),
           ("9ban", "9ban_existing_labels", "P9")]
SKIP = {"train.txt", "val.txt", "classes.txt", "obj.names"}
NEIGHBOR_HIGH = 0.93     # STEP 08 의 병합 기준과 같은 값
NEIGHBOR_MID = 0.88


def load_labels(rel):
    d = paths.PILOT / rel / "obj_train_data"
    out = {}
    for f in sorted(d.glob("*.txt")):
        if f.name in SKIP:
            continue
        n = sum(1 for line in f.read_text(encoding="utf-8").splitlines()
                if len(line.split()) >= 5)
        out[f.stem] = n
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    with (paths.DEDUP / "dedup_metadata.csv").open(encoding="utf-8-sig") as fh:
        dd = {Path(r["rel_path"]).stem: r for r in csv.DictReader(fh)}
    with (paths.DEDUP / "embeddings_index.csv").open(encoding="utf-8-sig") as fh:
        idx = list(csv.DictReader(fh))
    emb = np.load(paths.DEDUP / "embeddings.npy").astype(np.float32)
    row_of = {Path(r["rel_path"]).stem: int(r["row"]) for r in idx}
    stem_of = {int(r["row"]): Path(r["rel_path"]).stem for r in idx}
    panel_rows = defaultdict(list)
    for r in idx:
        panel_rows[r["panel_id"]].append(int(r["row"]))

    verdicts, sess_rows = [], []

    for tag, rel, pid in SOURCES:
        labels = load_labels(rel)
        empty = [s for s, n in labels.items() if n == 0]
        filled = {s for s, n in labels.items() if n > 0}

        # 근거 1 — 클러스터 동거
        cluster_members = defaultdict(list)
        for s in labels:
            if s in dd:
                cluster_members[dd[s]["cluster_id"]].append(s)

        # 근거 2 — 반 전체를 대상으로 한 최근접 이웃
        rows = np.array(panel_rows[pid])
        X = emb[rows]

        for s in empty:
            cid = dd.get(s, {}).get("cluster_id", "")
            mates = [m for m in cluster_members.get(cid, []) if m != s]
            labeled_mates = [m for m in mates if m in filled]

            nn_stem, nn_sim, nn_labeled = "", 0.0, ""
            if s in row_of:
                v = emb[row_of[s]]
                sims = X @ v
                order = np.argsort(-sims)
                for oi in order:
                    cand = stem_of[int(rows[oi])]
                    if cand == s:
                        continue
                    nn_stem, nn_sim = cand, float(sims[oi])
                    nn_labeled = ("1" if cand in filled
                                  else "0" if cand in labels else "")
                    break

            if labeled_mates:
                verdict = "미작업 강함 — 같은 클러스터에 라벨된 이미지 있음"
            elif nn_labeled == "1" and nn_sim >= NEIGHBOR_HIGH:
                verdict = "미작업 의심 — 최근접 이웃이 라벨됨(유사도 높음)"
            elif nn_labeled == "1" and nn_sim >= NEIGHBOR_MID:
                verdict = "판단 보류 — 최근접 이웃이 라벨됨(유사도 중간)"
            else:
                verdict = "정상 음성 가능 — 유사한 라벨 이미지 없음"

            verdicts.append({
                "source": tag, "panel_id": pid, "image": s,
                "session": dd.get(s, {}).get("session_key", ""),
                "cluster_id": cid,
                "cluster_size": dd.get(s, {}).get("cluster_size", ""),
                "labeled_cluster_mates": len(labeled_mates),
                "cluster_mate_example": labeled_mates[0] if labeled_mates else "",
                "nearest_neighbor": nn_stem,
                "nn_similarity": round(nn_sim, 4),
                "nn_is_labeled": nn_labeled,
                "verdict": verdict,
            })

        # 근거 3 — 세션 단위
        per = defaultdict(lambda: [0, 0])
        for s, n in labels.items():
            k = dd.get(s, {}).get("session_key", "?")
            per[k][0 if n > 0 else 1] += 1
        for k, (lab, emp) in sorted(per.items()):
            sess_rows.append({
                "source": tag, "panel_id": pid, "session": k,
                "labeled_images": lab, "empty_images": emp,
                "empty_ratio": f"{emp/(lab+emp):.3f}",
                "note": "세션 전체 미라벨" if lab == 0 else "",
            })

    def dump(name, rows):
        p = paths.AUDIT / name
        with p.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return p

    dump("nq1_empty_label_verdict.csv", verdicts)
    dump("nq1_session_summary.csv", sess_rows)

    # ---------------- 리포트 ----------------
    from collections import Counter
    print("=" * 72)
    print("NQ-1  빈 라벨 파일 판정")
    print("=" * 72)
    for tag, _, pid in SOURCES:
        sub = [v for v in verdicts if v["source"] == tag]
        print(f"\n[{tag} / {pid}]  빈 라벨 {len(sub)}장")
        c = Counter(v["verdict"] for v in sub)
        for k, n in c.most_common():
            print(f"  {n:>4}장 ({n/len(sub):>5.1%})  {k}")
        strong = [v for v in sub if v["verdict"].startswith("미작업 강함")]
        if strong:
            print(f"  -- 클러스터 동거 사례 (최대 5건)")
            for v in strong[:5]:
                print(f"     {v['image']}  <-> 라벨된 {v['cluster_mate_example']}  "
                      f"(클러스터 {v['cluster_id']}, 크기 {v['cluster_size']})")

    print("\n" + "=" * 72)
    print("세션별 공백")
    print("=" * 72)
    print(f"{'src':<6}{'세션':<32}{'라벨':>6}{'빈':>5}{'빈비율':>8}  비고")
    for r in sess_rows:
        print(f"{r['source']:<6}{r['session']:<32}{r['labeled_images']:>6}"
              f"{r['empty_images']:>5}{float(r['empty_ratio'])*100:>7.0f}%  {r['note']}")

    print("\n-> nq1_empty_label_verdict.csv, nq1_session_summary.csv")


if __name__ == "__main__":
    main()
