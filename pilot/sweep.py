"""모델·입력해상도 조합을 같은 분할로 비교한다.

데이터가 114박스뿐이라 모델 크기보다 데이터가 병목일 가능성이 크다. 그걸 확인하고
현 시점 최선의 조합을 근거로 고르기 위한 스크립트다.

  python sweep.py

비교 대상은 Ultralytics 계열 표준 모델이다. YOLO11 은 v8 의 후속으로 같은 크기에서
정확도가 더 높다고 보고된 현재 기본 계열이고, s(small) 는 n(nano) 보다 4배 크다.
입력 640 은 원본 320 을 업스케일하는 것으로, MCCB 처럼 작은 부품에서 효과가 크다.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PY = sys.executable

CONFIGS = [
    ("yolov8n.pt", 320, "v8n_320"),      # 현재 기준선
    ("yolo11n.pt", 320, "v11n_320"),
    ("yolo11s.pt", 320, "v11s_320"),
    ("yolo11s.pt", 640, "v11s_640"),
]
EPOCHS = 60


def best_row(csv_path: Path):
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        return None
    key = next(c for c in rows[0] if "mAP50(B)" in c)
    best = max(rows, key=lambda r: float(r[key]))

    def g(pat):
        return float(best[next(c for c in best if pat in c)])
    return {"epoch": int(float(best["epoch"])), "P": g("precision"), "R": g("recall"),
            "mAP50": g("mAP50(B)"), "mAP50_95": g("mAP50-95(B)")}


def main():
    results = []
    for model, imgsz, name in CONFIGS:
        print(f"\n{'='*70}\n{name}  ({model}, imgsz={imgsz}, epochs={EPOCHS})\n{'='*70}")
        r = subprocess.run(
            [PY, "train.py", "--modality", "ir", "--model", model, "--imgsz", str(imgsz),
             "--epochs", str(EPOCHS), "--name", name, "--batch", "8"],
            cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("실패:", (r.stderr or "")[-800:])
            continue
        b = best_row(HERE / "runs" / name / "results.csv")
        if b:
            b["name"] = name
            b["model"] = model
            b["imgsz"] = imgsz
            results.append(b)
            print(f"  최고 mAP50 {b['mAP50']:.3f} (epoch {b['epoch']})  "
                  f"P {b['P']:.3f}  R {b['R']:.3f}  mAP50-95 {b['mAP50_95']:.3f}")

    print(f"\n{'='*70}\n비교 결과 (동일 분할: train 36 / val 11, 세션 겹침 없음)\n{'='*70}")
    print(f"{'조합':<12}{'모델':<13}{'입력':>5}{'mAP50':>8}{'mAP50-95':>10}{'P':>7}{'R':>7}{'best ep':>9}")
    for b in sorted(results, key=lambda x: -x["mAP50"]):
        print(f"{b['name']:<12}{b['model']:<13}{b['imgsz']:>5}{b['mAP50']:>8.3f}"
              f"{b['mAP50_95']:>10.3f}{b['P']:>7.3f}{b['R']:>7.3f}{b['epoch']:>9}")
    if results:
        top = max(results, key=lambda x: x["mAP50"])
        print(f"\n최선: {top['name']}  ->  가중치 runs/{top['name']}/weights/best.pt")


if __name__ == "__main__":
    main()
