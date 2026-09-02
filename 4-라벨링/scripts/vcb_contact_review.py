"""VCB 접촉부 annotation unit 판정용 육안 확인 자료를 만든다.

왜 좌표만으로 못 정하는가
    크기는 `CONTACT_POINT` 를 가리킨다 — 접촉부/케이블헤드 높이비 중앙 0.246 으로,
    CONTACT_POINT 로 확정된 두 클래스(0.462 · 0.379)보다도 작다.
    그런데 **개수가 반대로 간다** — 장당 1개가 74/111 로 지배적이다.
    3상 설비라면 접속점 단위일 때 장당 3개 안팎이 나와야 한다(몰드변압기 접촉부는 중앙 3).

    좌표만으로는 다음 셋을 가를 수 없다.
      (a) 클로즈업이라 접속점이 하나만 보였다        -> CONTACT_POINT 와 모순 없음
      (b) 여러 접속점을 하나로 묶어 그렸다            -> TERMINAL_GROUP 에 가까움
      (c) 보이는 것만 골라 그렸다                    -> 근거로 쓰지 않는다

    DEC-016 이 CONTACT_POINT 준수 여부에 대해 같은 한계를 이미 기록했다 —
    "좌표만으로는 하나의 물리적 접속점마다 박스 하나인가를 확정할 수 없다".

무엇을 만드는가
    표본 이미지에 박스를 그려 저장하고, 판정표(CSV)를 만든다.
    **판정은 사람이 verdict 열에 적는다.** 이 스크립트는 판정하지 않는다.
    quarantine_review.csv 와 같은 방식이다 (사람 판정 원천을 파일 하나로 둔다).

표본 설계
    개수 판단이 갈리는 지점을 보려면 **1개짜리와 2개 이상짜리를 모두** 봐야 한다.
    1개짜리만 보면 (a)(b)(c) 를 가를 수 없고, 2개 이상짜리만 보면 편향된다.

출력
    experiments/data_audit/vcb_contact/VC01.png ...      박스를 그린 표본
    reports/labeling/vcb_contact_review.csv              판정표 (verdict 열 비어 있음)

사용:
    python scripts/vcb_contact_review.py [--n-multi 5] [--n-single 10]
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

SRC_LABELS = paths.BACKUP / "P6_6ban"
OUT_IMG = paths.PROJECT / "experiments" / "data_audit" / "vcb_contact"
OUT_CSV = paths.REPORTS / "labeling" / "vcb_contact_review.csv"

OLD_CABLE_HEAD = 15      # P6 에서 old 15 = 케이블헤드 (class_migration split)
OLD_VCB_CONTACT = 17
SEED = 6                 # 표본이 재현되어야 한다

# 이미지 원본 후보 — 참고 라벨은 pilot 에서 왔다
IMG_ROOTS = [paths.PILOT / "6ban_existing_labels" / "obj_train_data",
             paths.PROCESSED / "P6-VCB반"]


def find_image(stem):
    for root in IMG_ROOTS:
        if not root.is_dir():
            continue
        for ext in (".jpg", ".JPG", ".png", ".PNG"):
            p = root / (stem + ext)
            if p.exists():
                return p
        hit = next(root.rglob(stem + ".jpg"), None)
        if hit:
            return hit
    return None


def load():
    per = defaultdict(lambda: {"body": [], "con": []})
    for p in SRC_LABELS.rglob("*.txt"):
        if p.name in ("classes.txt", "obj.names", "train.txt"):
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.split()
            if len(s) < 5:
                continue
            b = tuple(float(x) for x in s[1:5])
            cid = int(float(s[0]))
            if cid == OLD_CABLE_HEAD:
                per[p.stem]["body"].append(b)
            elif cid == OLD_VCB_CONTACT:
                per[p.stem]["con"].append(b)
    return per


def draw(img, boxes, color, label):
    h, w = img.shape[:2]
    for i, (cx, cy, bw, bh) in enumerate(boxes, 1):
        x0, y0 = int((cx - bw/2) * w), int((cy - bh/2) * h)
        x1, y1 = int((cx + bw/2) * w), int((cy + bh/2) * h)
        cv2.rectangle(img, (x0, y0), (x1, y1), color, 2)
        cv2.putText(img, f"{label}{i}", (x0, max(12, y0 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-multi", type=int, default=5)
    ap.add_argument("--n-single", type=int, default=10)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    per = load()

    have = {k: v for k, v in per.items() if v["con"]}
    multi = sorted(k for k, v in have.items() if len(v["con"]) >= 2)
    single = sorted(k for k, v in have.items() if len(v["con"]) == 1)
    print(f"VCB 접촉부 보유 이미지 {len(have)}장 "
          f"(2개 이상 {len(multi)} · 1개 {len(single)})")

    rng = np.random.default_rng(SEED)
    pick = ([multi[i] for i in rng.permutation(len(multi))[:a.n_multi]]
            + [single[i] for i in rng.permutation(len(single))[:a.n_single]])
    pick.sort()

    OUT_IMG.mkdir(parents=True, exist_ok=True)
    rows, missing = [], []
    for i, stem in enumerate(pick, 1):
        cid = f"VC{i:02d}"
        src = find_image(stem)
        d = per[stem]
        if src is None:
            missing.append(stem)
        else:
            img = cv2.imdecode(np.fromfile(str(src), np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                if img.shape[1] < 900:      # 작은 열화상은 확대해야 접속점이 보인다
                    img = cv2.resize(img, None, fx=3, fy=3,
                                     interpolation=cv2.INTER_NEAREST)
                draw(img, d["body"], (255, 160, 0), "H")    # 케이블헤드
                draw(img, d["con"], (0, 0, 255), "C")       # VCB 접촉부
                cv2.imencode(".png", img)[1].tofile(
                    str(OUT_IMG / f"{cid}.png"))
        rows.append({
            "case_id": cid, "image": stem,
            "n_vcb_contact": len(d["con"]), "n_cable_head": len(d["body"]),
            "image_file": f"{cid}.png" if src else "(원본 이미지 없음)",
            "visible_contact_points": "", "verdict": "", "note": "",
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["# VCB 접촉부 annotation unit 판정표 — 사람이 채운다"])
        w.writerow(["# 이미지: experiments/data_audit/vcb_contact/<case_id>.png"])
        w.writerow(["#   빨강 C = 기존 VCB 접촉부 박스 · 주황 H = 케이블헤드 박스"])
        w.writerow(["# visible_contact_points: 눈으로 세어 실제 보이는 접속점 개수"])
        w.writerow(["# verdict: CONTACT_POINT / TERMINAL_GROUP / "
                    "PARTIAL_LABELING / 판단불가"])
        w.writerow(["#   CONTACT_POINT    박스 1개 = 접속점 1개. 보이는 수와 박스 수가 같다"])
        w.writerow(["#   TERMINAL_GROUP   박스 1개가 여러 접속점을 묶고 있다"])
        w.writerow(["#   PARTIAL_LABELING 보이는 것보다 박스가 적다 (미작업 의심 · 근거로 쓰지 않는다)"])
        w.writerow(["#   판단불가          이미지로 셀 수 없다"])
        ww = csv.DictWriter(fh, fieldnames=list(rows[0]))
        ww.writeheader()
        ww.writerows(rows)

    print(f"\n표본 {len(rows)}장 (2개 이상 {a.n_multi} · 1개 {a.n_single}) · seed {SEED}")
    for r in rows:
        print(f"  {r['case_id']}  접촉부 {r['n_vcb_contact']} · 케이블헤드 "
              f"{r['n_cable_head']}   {r['image']}")
    if missing:
        print(f"\n[주의] 원본 이미지를 못 찾은 것 {len(missing)}장: "
              f"{', '.join(missing[:5])}")
        print("       라벨 좌표만으로는 판정할 수 없다. 이미지 경로를 확인할 것.")
    print(f"\n-> {OUT_IMG}")
    print(f"-> {OUT_CSV}")
    print("\n판정 후 할 일 — reports/decisions/drafts/vcb-contact-annotation-unit.md 참조")
    print("  CONTACT_POINT 다수     -> classes_v2.ANNOTATION_UNIT 에 CONTACT_POINT")
    print("  TERMINAL_GROUP 다수    -> TERMINAL_GROUP")
    print("  PARTIAL_LABELING 다수  -> 참고 라벨을 근거로 쓰지 않는다. UNKNOWN 유지")
    return 0


if __name__ == "__main__":
    sys.exit(main())
