"""NQ-11 — MCCB 접촉부(#28)의 annotation unit 검증.

**원본과 기존 라벨을 수정하지 않는다.** 읽기만 한다.
P9 참고 라벨을 정답으로 가정하지 않는다. "어떻게 그려졌는가"를 측정할 뿐이다.

검증 축
  1. 본체(MCCB #19) 대비 접촉부(#28)의 개수비 — 기기당 2개인가
  2. 접촉부가 본체의 좌/우에 놓이는가 — 단자군이라면 좌우 대칭이어야 한다
  3. 접촉부 박스가 본체 박스와 겹치는가 — 단자군은 기기 외곽 안쪽/경계에 붙는다
  4. 세션·건물이 달라도 같은 관행인가 — 한 작업자의 습관인지 구조적 패턴인지

출력: reports/data_audit/nq11_mccb_unit.csv          이미지 1장 = 1행
      reports/data_audit/nq11_mccb_summary.csv       세션별 요약
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v1_26 as v1  # noqa: E402

SRC = paths.PILOT / "9ban_existing_labels" / "obj_train_data"
BODY, CONTACT = 18, 27          # v2 class_id: MCCB, MCCB 접촉부
SKIP = {"train.txt", "classes.txt", "obj.names"}


def xyxy(b):
    _, cx, cy, w, h = b
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def overlap_ratio(a, b):
    """a 가 b 와 겹치는 면적 / a 의 면적."""
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    aa = (ax1 - ax0) * (ay1 - ay0)
    return (ix * iy) / aa if aa > 0 else 0.0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with (paths.DEDUP / "dedup_metadata.csv").open(encoding="utf-8-sig") as fh:
        dd = {Path(r["rel_path"]).stem: r for r in csv.DictReader(fh)}

    rows = []
    for f in sorted(SRC.glob("*.txt")):
        if f.name in SKIP:
            continue
        boxes = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            new = v1.new_id(int(float(p[0])), "P9")
            if new is not None:
                boxes.append((new, *[float(x) for x in p[1:5]]))
        bodies = [b for b in boxes if b[0] == BODY]
        conts = [b for b in boxes if b[0] == CONTACT]
        if not conts:
            continue

        # 각 접촉부를 가장 많이 겹치는(또는 가장 가까운) 본체에 배정
        left = right = inside = unmatched = 0
        for c in conts:
            if not bodies:
                unmatched += 1
                continue
            cx = c[1]
            best = max(bodies, key=lambda b: overlap_ratio(c, b))
            ov = overlap_ratio(c, best)
            if ov < 0.10:
                # 겹치지 않으면 가로 거리로 가장 가까운 본체
                best = min(bodies, key=lambda b: abs(b[1] - cx))
                ov = 0.0
            bx0, _, bx1, _ = xyxy(best)
            bcx = (bx0 + bx1) / 2
            if ov >= 0.85:
                inside += 1
            if cx < bcx:
                left += 1
            else:
                right += 1

        m = dd.get(f.stem, {})
        rows.append({
            "image": f.stem,
            "session": m.get("session_key", ""),
            "building": f.stem.split("_")[1],
            "bodies": len(bodies), "contacts": len(conts),
            "contacts_per_body": round(len(conts) / len(bodies), 2) if bodies else "",
            "left_of_body": left, "right_of_body": right,
            "lr_balance": round(min(left, right) / max(left, right), 2) if max(left, right) else "",
            "fully_inside_body": inside,
            "unmatched": unmatched,
        })

    with (paths.AUDIT / "nq11_mccb_unit.csv").open("w", newline="",
                                                   encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    withbody = [r for r in rows if r["bodies"] > 0]
    cpb = np.array([r["contacts"] / r["bodies"] for r in withbody])
    bal = np.array([float(r["lr_balance"]) for r in withbody if r["lr_balance"] != ""])

    print(f"접촉부가 있는 이미지 {len(rows)}장 (그중 본체도 있는 장 {len(withbody)})")
    print(f"\n1. 기기당 접촉부 개수")
    print(f"   중앙 {np.median(cpb):.2f}  평균 {cpb.mean():.2f}  "
          f"p25 {np.percentile(cpb,25):.2f}  p75 {np.percentile(cpb,75):.2f}")
    print(f"   정확히 2.0 인 장: {(np.abs(cpb-2.0)<1e-9).sum()} "
          f"({(np.abs(cpb-2.0)<1e-9).mean():.0%})")
    print(f"   1.5~2.5 구간    : {((cpb>=1.5)&(cpb<=2.5)).sum()} "
          f"({((cpb>=1.5)&(cpb<=2.5)).mean():.0%})")

    print(f"\n2. 좌우 배치 균형 (1.0 = 좌우 같은 개수)")
    print(f"   중앙 {np.median(bal):.2f}  >=0.8 인 장 {(bal>=0.8).sum()} "
          f"({(bal>=0.8).mean():.0%})")
    tl = sum(r["left_of_body"] for r in withbody)
    tr = sum(r["right_of_body"] for r in withbody)
    print(f"   전체 접촉부 좌 {tl} / 우 {tr}  (비 {min(tl,tr)/max(tl,tr):.2f})")

    ins = sum(r["fully_inside_body"] for r in withbody)
    tot = sum(r["contacts"] for r in withbody)
    print(f"\n3. 본체 박스 안에 완전히 들어간 접촉부: {ins}/{tot} ({ins/tot:.0%})")
    print(f"   -> 접촉부가 본체 외곽 안쪽에 붙어 있는지 여부")

    print(f"\n4. 세션·건물별 일관성")
    per = defaultdict(list)
    for r in withbody:
        per[(r["building"], r["session"][:24])].append(r["contacts"] / r["bodies"])
    print(f"   {'건물':<5}{'세션':<26}{'장수':>5}{'기기당중앙':>10}")
    for (b, s), v in sorted(per.items()):
        print(f"   {b:<5}{s:<26}{len(v):>5}{np.median(v):>10.2f}")

    with (paths.AUDIT / "nq11_mccb_summary.csv").open("w", newline="",
                                                      encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["building", "session", "images", "contacts_per_body_median"])
        for (b, s), v in sorted(per.items()):
            w.writerow([b, s, len(v), round(float(np.median(v)), 2)])
    print("\n-> nq11_mccb_unit.csv, nq11_mccb_summary.csv")


if __name__ == "__main__":
    main()
