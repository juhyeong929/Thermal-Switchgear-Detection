"""REV-003 — 격리된 정본 중복 20쌍을 육안 판정할 자료를 만든다.

무엇을 판정하나
    DEC-016 감사에서 **같은 클래스의 박스 두 개가 같은 인스턴스를 가리키는 것으로 보이는**
    20쌍이 나왔다. DEC-017 은 정본을 고치지 않고 격리 목록에만 등재했다 —
    어느 쪽이 옳은지 모르는 상태에서 한쪽을 고르지 않기 위해서다.

    이제 사람이 이미지를 보고 정한다. 판정이 끝나야 인증 C-4(검수 이력)의
    REV-003 이 `PENDING` 을 벗어난다.

이 스크립트가 하는 것 / 하지 않는 것
    한다:   쌍마다 두 박스를 강조한 검토 이미지를 만들고 판정표를 낸다
    안 한다: **정본 라벨을 수정하지 않는다.** 격리 목록도 고치지 않는다.
            판정 결과를 적용하는 것은 별도 단계다 (`--apply` 는 만들지 않았다).

읽는 법
    빨강 = 격리된 박스 두 개 (번호는 원본 파일의 줄 번호)
    회색 = 같은 이미지의 다른 박스 (맥락용)

출력
    reports/labeling/quarantine_review.csv        판정표 (verdict 는 사람이 채운다)
    experiments/data_audit/quarantine/*.png       쌍별 검토 이미지

사용
    python scripts/quarantine_review.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

QUAR = paths.LABELING / "quarantine" / "canonical_quarantine.csv"
OUT = paths.REPORTS / "labeling" / "quarantine_review.csv"
IMGDIR = paths.PROJECT / "experiments" / "data_audit" / "quarantine"

# 정본 라벨 위치 (이미 v2 class_id 로 승계된 것)
CANON = {
    "P1": paths.LABELING / "reviewed" / "P1_A3검수완료",
    "P3": paths.LABELING / "reviewed" / "P3__p3",
    "P4": paths.LABELING / "reviewed" / "P4__p4",
}

VERDICTS = ["작은쪽_유지", "큰쪽_유지", "둘다_유효", "둘다_제외", "판단불가"]


def label_path(stem, panel_id):
    d = CANON.get(panel_id)
    if not d or not d.is_dir():
        return None
    for p in d.rglob(f"{stem}.txt"):
        return p
    return None


def image_path(stem):
    """정본 이미지는 3-가공 에 있다. 인벤토리로 찾는다."""
    global _IDX
    try:
        _IDX
    except NameError:
        _IDX = {}
        with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r["kind"] == "IR":
                    _IDX[Path(r["rel_path"]).stem] = paths.PROCESSED / r["rel_path"]
    p = _IDX.get(stem)
    return p if p and p.exists() else None


def render(stem, boxes, hi, out_png, title):
    import cv2
    src = image_path(stem)
    if src is None:
        return False
    img = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False
    S = 3
    img = cv2.resize(img, (img.shape[1] * S, img.shape[0] * S),
                     interpolation=cv2.INTER_NEAREST)
    h, w = img.shape[:2]

    for i, (cid, cx, cy, bw, bh) in enumerate(boxes):
        x0, y0 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
        x1, y1 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
        on = i in hi
        color = (40, 40, 230) if on else (150, 150, 150)     # BGR
        cv2.rectangle(img, (x0, y0), (x1, y1), color, 3 if on else 1)
        if on:
            cv2.putText(img, f"#{i}", (x0 + 3, max(14, y0 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2, cv2.LINE_AA)

    band = np.full((60, w, 3), 245, np.uint8)
    cv2.putText(band, title, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, .55,
                (25, 25, 25), 1, cv2.LINE_AA)
    cv2.putText(band, "red = quarantined pair   gray = other boxes in the image",
                (10, 46), cv2.FONT_HERSHEY_SIMPLEX, .45, (110, 110, 110), 1, cv2.LINE_AA)
    IMGDIR.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", np.vstack([band, img]))[1].tofile(str(out_png))
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with QUAR.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    # (이미지, pair_with) 가 하나의 쌍이다
    pairs = defaultdict(list)
    for r in rows:
        pairs[(r["image"], r["pair_with"])].append(r)

    out_rows, made, missing = [], 0, []
    for i, ((stem, pw), rs) in enumerate(sorted(pairs.items()), 1):
        pid = rs[0]["panel_id"]
        lp = label_path(stem, pid)
        boxes = []
        if lp:
            for line in lp.read_text(encoding="utf-8").splitlines():
                t = line.split()
                if len(t) >= 5:
                    boxes.append((int(float(t[0])), *[float(x) for x in t[1:5]]))
        idxs = sorted(int(r["box_index"]) for r in rs)
        areas = {}
        for j in idxs:
            if j < len(boxes):
                areas[j] = boxes[j][3] * boxes[j][4]

        pid_str = f"Q{i:02d}"
        ok = False
        if boxes and all(j < len(boxes) for j in idxs):
            ok = render(stem, boxes, set(idxs), IMGDIR / f"{pid_str}.png",
                        f"{pid_str}  {stem}  [{rs[0]['class_name']}]  boxes {pw}")
        if ok:
            made += 1
        else:
            missing.append(pid_str)

        small = min(areas, key=areas.get) if len(areas) == 2 else ""
        big = max(areas, key=areas.get) if len(areas) == 2 else ""
        out_rows.append({
            "pair_id": pid_str, "image": stem, "panel": pid,
            "class_name": rs[0]["class_name"], "boxes": pw,
            "small_box": small, "big_box": big,
            "small_area": round(areas[small], 5) if small != "" else "",
            "big_area": round(areas[big], 5) if big != "" else "",
            "detail": rs[0]["detail"], "image_file": f"{pid_str}.png",
            "verdict": "", "note": "",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerow({k: "" for k in out_rows[0]} |
                   {"pair_id": "# verdict: " + " / ".join(VERDICTS)})
        w.writerow({k: "" for k in out_rows[0]} |
                   {"pair_id": "# 작은쪽/큰쪽 = small_box/big_box 열의 번호가 가리키는 박스"})
        w.writerows(out_rows)

    print(f"격리 쌍 {len(pairs)}개 · 이미지 {made}장 생성"
          + (f" · 실패 {len(missing)}: {', '.join(missing)}" if missing else ""))
    print(f"  {'ID':<6}{'클래스':<16}{'작은박스':>9}{'큰박스':>9}  이미지")
    for r in out_rows:
        print(f"  {r['pair_id']:<6}{r['class_name']:<16}"
              f"{str(r['small_area']):>9}{str(r['big_area']):>9}  {r['image']}")
    print(f"\n판정 값: {' / '.join(VERDICTS)}")
    print("  작은쪽_유지 / 큰쪽_유지 — 같은 인스턴스이므로 하나만 남긴다")
    print("  둘다_유효               — 실제로 다른 인스턴스다 (감사 오탐)")
    print("  둘다_제외               — 둘 다 잘못 그려졌다")
    print(f"\n-> {OUT}")
    print(f"-> {IMGDIR}")
    print("**정본 라벨은 수정하지 않았다.** 판정 적용은 별도 단계다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
