"""OQ-016 판정을 빠르게 하기 위한 **묶음 시트**를 만든다. 101쌍을 한 장씩 열지 않아도 되게.

왜 필요한가
    REV-005 는 101쌍 판정이다. 한 장씩 열면 오래 걸리고, 대부분은 한눈에
    `DIFFERENT_SCENE` 임을 알 수 있다. 훑어보고 **애매한 것만 원본 이미지를 여는** 순서가 빠르다.

    이 스크립트는 새 판정을 하지 않는다. **보기 편하게 다시 배치할 뿐이다.**

순서
    위험이 큰 것부터 낸다 — 코사인이 높고 같은 세션인 쌍.
    도중에 멈춰도 **가장 중요한 층은 이미 본 상태**가 되게 하려는 것이다.

출력
    experiments/data_audit/oq016/sheets/sheet_01.png …   한 장에 6쌍
    reports/data_audit/oq016/review_order.csv            시트별 수록 순서

사용
    python scripts/oq016_contact_sheet.py
"""

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

BASE = paths.AUDIT / "oq016"
IMGDIR = paths.PROJECT / "experiments" / "data_audit" / "oq016"
SHEETS = IMGDIR / "sheets"
PER_SHEET = 6
THUMB_W = 560          # 쌍 하나(두 장 나란히)의 너비


def risk_key(r):
    """위험이 큰 것 먼저 — 코사인 높고 같은 세션. 같으면 pair_id 순."""
    return (-float(r["cosine"]), -int(r["same_session"]), r["pair_id"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import cv2

    with (BASE / "sample_pairs.csv").open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=risk_key)

    SHEETS.mkdir(parents=True, exist_ok=True)
    order, made = [], 0

    for si in range(0, len(rows), PER_SHEET):
        chunk = rows[si:si + PER_SHEET]
        tiles = []
        for r in chunk:
            src = IMGDIR / f"{r['pair_id']}.png"
            if not src.exists():
                continue
            im = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
            if im is None:
                continue
            h = int(im.shape[0] * THUMB_W / im.shape[1])
            im = cv2.resize(im, (THUMB_W, h), interpolation=cv2.INTER_AREA)
            # 판정 시 눈이 가야 할 정보만 큰 글씨로 다시 얹는다
            band = np.full((30, THUMB_W, 3), 250, np.uint8)
            same = "SAME session" if r["same_session"] == "1" else "diff session"
            cv2.putText(band, f"{r['pair_id']}   cos {r['cosine']}   {same}   {r['panel']}",
                        (8, 21), cv2.FONT_HERSHEY_SIMPLEX, .52, (20, 20, 20), 1, cv2.LINE_AA)
            tiles.append(np.vstack([band, im]))
            order.append({"sheet": f"sheet_{si//PER_SHEET+1:02d}",
                          "pair_id": r["pair_id"], "cosine": r["cosine"],
                          "same_session": r["same_session"], "panel": r["panel"],
                          "cos_bin": r["cos_bin"]})
        if not tiles:
            continue

        hmax = max(t.shape[0] for t in tiles)
        tiles = [np.vstack([t, np.full((hmax - t.shape[0], THUMB_W, 3), 250, np.uint8)])
                 if t.shape[0] < hmax else t for t in tiles]
        while len(tiles) % 2:
            tiles.append(np.full((hmax, THUMB_W, 3), 250, np.uint8))
        gap_v = np.full((hmax, 8, 3), 200, np.uint8)
        rowsimg = []
        for i in range(0, len(tiles), 2):
            rowsimg.append(np.hstack([tiles[i], gap_v, tiles[i + 1]]))
        gap_h = np.full((8, rowsimg[0].shape[1], 3), 200, np.uint8)
        body = rowsimg[0]
        for rr in rowsimg[1:]:
            body = np.vstack([body, gap_h, rr])

        n = si // PER_SHEET + 1
        head = np.full((44, body.shape[1], 3), 240, np.uint8)
        cv2.putText(head, f"OQ-016 review  sheet {n}/{(len(rows)+PER_SHEET-1)//PER_SHEET}"
                          f"   (risk order: high cosine + same session first)",
                    (10, 29), cv2.FONT_HERSHEY_SIMPLEX, .6, (25, 25, 25), 1, cv2.LINE_AA)
        out = SHEETS / f"sheet_{n:02d}.png"
        cv2.imencode(".png", np.vstack([head, body]))[1].tofile(str(out))
        made += 1

    with (BASE / "review_order.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(order[0]))
        w.writeheader(); w.writerows(order)

    print(f"묶음 시트 {made}장 (한 장에 {PER_SHEET}쌍) -> {SHEETS}")
    print(f"  순서: 코사인 높은 것 · 같은 세션 먼저 — 도중에 멈춰도 위험한 층은 본 상태가 된다")
    print(f"  sheet_01 은 {order[0]['pair_id']} (cos {order[0]['cosine']}) 부터")
    print(f"-> {BASE / 'review_order.csv'}")
    print("\n판정은 visual_review.csv 에 적는다. 이 시트는 보기용이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
