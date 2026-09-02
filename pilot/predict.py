"""학습된 모델로 라벨 없는 사진에 박스를 자동 예측한다 (사전 라벨링).

사람은 처음부터 그리지 않고 예측된 박스를 검수·수정만 한다.

정합된 실화상(3-가공 rgb_image)을 쓰는 경우 실화상과 열화상의 정규화 좌표가 같으므로,
열화상에 예측한 결과를 그대로 실화상 라벨로 열어 수정할 수 있다.

  python predict.py                          data/ir 중 라벨 없는 것 전부 예측
  python predict.py --all                    라벨 있는 것까지 전부 (비교 목적)
  python predict.py --source <dir>           임의 디렉터리
  python predict.py --no-panel-filter        반별 후보 클래스 필터 해제

출력: data/labels_pred/*.txt  (YOLO 포맷)  +  out/pred_report.csv
원본 데이터는 읽기만 한다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID, NAMES, PANEL_CLASSES  # noqa: E402
from calibrate import OSD_BOXES  # noqa: E402
from transfer import label_files  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"


def osd_overlap_ratio(box, w, h) -> float:
    """박스가 FLIR 오버레이(컬러바·온도수치·로고) 영역과 겹치는 비율."""
    x1, y1, x2, y2 = box
    area = max((x2 - x1) * (y2 - y1), 1e-6)
    covered = 0.0
    for ox1, oy1, ox2, oy2 in OSD_BOXES:
        ix1, iy1 = max(x1, ox1 * w / 320), max(y1, oy1 * h / 240)
        ix2, iy2 = min(x2, ox2 * w / 320), min(y2, oy2 * h / 240)
        if ix2 > ix1 and iy2 > iy1:
            covered += (ix2 - ix1) * (iy2 - iy1)
    return covered / area


def panel_of(stem: str) -> str | None:
    """파일명의 P번호로 반을 알아낸다 (A1_B1_P9_... -> P9)."""
    parts = stem.split("_")
    if len(parts) < 3 or not parts[2].startswith("P"):
        return None
    for panel in PANEL_CLASSES:
        if panel.split("-")[0] == parts[2]:
            return panel
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(HERE / "runs" / "v11n_320" / "weights" / "best.pt"))
    ap.add_argument("--source", default=str(DATA / "ir"))
    ap.add_argument("--out", default=str(DATA / "labels_pred"))
    ap.add_argument("--conf", type=float, default=0.10)  # 검수 손익이 가장 좋은 값
    ap.add_argument("--all", action="store_true", help="이미 라벨된 것도 포함")
    ap.add_argument("--no-panel-filter", action="store_true")
    ap.add_argument("--osd-max", type=float, default=0.4,
                    help="오버레이와 이 비율 이상 겹치는 박스는 버린다")
    args = ap.parse_args()

    weights = Path(args.weights)
    if not weights.exists():
        raise SystemExit(f"가중치가 없습니다: {weights}\n먼저 train.py 를 실행하세요.")

    src = Path(args.source)
    imgs = sorted(src.glob("*.jpg"))
    done = {f.stem for f in label_files(DATA / "labels_rgb")}
    targets = imgs if args.all else [p for p in imgs if p.stem not in done]
    if not targets:
        print("예측할 대상이 없습니다 (모두 라벨 완료).")
        return

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)

    from ultralytics import YOLO
    model = YOLO(str(weights))

    rows = []
    cls_count = collections.Counter()
    dropped_panel = dropped_osd = 0
    n_with = 0

    for p in targets:
        res = model.predict(str(p), conf=args.conf, verbose=False)[0]
        h, w = res.orig_shape
        panel = panel_of(p.stem)
        allowed = None
        if not args.no_panel_filter and panel:
            allowed = {NAMES.index(c) for c in PANEL_CLASSES.get(panel, []) if c in NAMES}

        lines, kept = [], []
        for b in res.boxes:
            cid = int(b.cls.item())
            box = b.xyxy[0].tolist()
            if allowed is not None and cid not in allowed:
                dropped_panel += 1
                continue
            if osd_overlap_ratio(box, w, h) >= args.osd_max:
                dropped_osd += 1
                continue
            x1, y1, x2, y2 = box
            lines.append(f"{cid} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} "
                         f"{(x2-x1)/w:.6f} {(y2-y1)/h:.6f}")
            kept.append((cid, float(b.conf.item())))
            cls_count[cid] += 1

        (out_dir / f"{p.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""),
                                               encoding="utf-8")
        if lines:
            n_with += 1
        rows.append({"stem": p.stem, "panel": panel or "", "n_box": len(kept),
                     "classes": " ".join(sorted({NAMES[c] for c, _ in kept})),
                     "max_conf": round(max((c for _, c in kept), default=0.0), 3)})

    # labelImg 가 클래스명을 읽을 수 있게 같이 둔다
    (out_dir / "classes.txt").write_text("\n".join(NAMES) + "\n", encoding="utf-8")

    with open(OUT / "pred_report.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    print(f"자동 예측 대상 {len(targets)}장 (conf >= {args.conf})\n")
    print(f"  박스가 나온 사진      {n_with}장 ({n_with/len(targets)*100:.1f}%)")
    print(f"  박스 없음(수작업 필요) {len(targets)-n_with}장")
    print(f"  총 박스              {sum(cls_count.values())}개")
    print(f"  반 후보와 달라 버림    {dropped_panel}개")
    print(f"  오버레이와 겹쳐 버림   {dropped_osd}개")
    if cls_count:
        print("\n  클래스별")
        for cid, n in cls_count.most_common():
            print(f"    {KOREAN_BY_ID[cid]:<18} {n:4d}")
    print(f"\n-> {out_dir}")
    print(f"-> {OUT/'pred_report.csv'}")
    print("\n검수는 이렇게 엽니다 (예측 박스가 미리 그려진 상태로 열림):")
    print(f"  python -m labelImg.labelImg data/rgb data/classes_labelimg.txt {out_dir.name and 'data/labels_pred'}")
    print("  틀린 박스는 지우고, 빠진 것만 새로 그린 뒤 저장하면 됩니다.")


if __name__ == "__main__":
    main()
