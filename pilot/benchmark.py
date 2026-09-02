"""모델 계열 비교 실험.

조건을 전부 고정하고 모델만 바꾼다: 같은 데이터·분할·epochs·imgsz·batch·seed,
검증 시 같은 conf/IoU.

측정 항목
  mAP50 / mAP50-95   정확도
  Precision          오검출이 적은지
  Recall             누락이 적은지
  CPU 추론시간        이미지 1장당 (엣지 배포 대상이 CPU 이므로 중요)
  가중치 파일 크기      배포 부담

  python benchmark.py                       실험 A (11n, 11s, 26n, 26s)
  python benchmark.py --stage B --add yolo11m.pt yolo26m.pt
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

HERE = Path(__file__).parent
OUT = HERE / "out"

STAGE_A = ["yolo11n.pt", "yolo11s.pt", "yolo26n.pt", "yolo26s.pt"]

# 전 모델 공통 고정 조건
FIXED = dict(epochs=60, imgsz=320, batch=8, seed=0)
VAL_CONF, VAL_IOU = 0.001, 0.7      # mAP 산출용 표준값 (모든 모델 동일)
SPEED_CONF = 0.25                    # 실사용 추론시간 측정용


def best_from_csv(p: Path):
    rows = list(csv.DictReader(p.open()))
    if not rows:
        return None
    k = next(c for c in rows[0] if "mAP50(B)" in c)
    b = max(rows, key=lambda r: float(r[k]))
    g = lambda pat: float(b[next(c for c in b if pat in c)])  # noqa: E731
    return dict(best_epoch=int(float(b["epoch"])), mAP50=g("mAP50(B)"),
                mAP50_95=g("mAP50-95(B)"), P=g("precision"), R=g("recall"))


def measure_speed(weights: Path, imgs: list[Path], n=30) -> float:
    """CPU 이미지 1장당 추론시간(ms). 워밍업 후 중앙값."""
    from ultralytics import YOLO
    m = YOLO(str(weights))
    for p in imgs[:3]:
        m.predict(str(p), conf=SPEED_CONF, imgsz=FIXED["imgsz"], device="cpu", verbose=False)
    ts = []
    for p in (imgs * ((n // len(imgs)) + 1))[:n]:
        t0 = time.perf_counter()
        m.predict(str(p), conf=SPEED_CONF, imgsz=FIXED["imgsz"], device="cpu", verbose=False)
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return ts[len(ts) // 2]


def run_one(model: str, tag: str) -> dict | None:
    name = f"bm_{tag}"
    print(f"\n{'='*72}\n{model}  (epochs={FIXED['epochs']}, imgsz={FIXED['imgsz']}, "
          f"batch={FIXED['batch']}, seed={FIXED['seed']})\n{'='*72}")
    r = subprocess.run(
        [sys.executable, "train.py", "--modality", "ir", "--model", model,
         "--imgsz", str(FIXED["imgsz"]), "--epochs", str(FIXED["epochs"]),
         "--batch", str(FIXED["batch"]), "--name", name],
        cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("학습 실패:", (r.stderr or "")[-600:])
        return None
    for ln in (r.stdout or "").splitlines():
        if "학습" in ln and "검증" in ln:
            print(" ", ln.strip())

    run = HERE / "runs" / name
    m = best_from_csv(run / "results.csv")
    w = run / "weights" / "best.pt"
    if not m or not w.exists():
        return None

    imgs = sorted((HERE / "dataset" / "ir" / "images" / "val").glob("*.jpg"))
    ms = measure_speed(w, imgs)
    m.update(model=model, tag=tag, size_mb=round(w.stat().st_size / 1e6, 1), ms_per_img=round(ms, 1))
    print(f"  mAP50 {m['mAP50']:.3f}  mAP50-95 {m['mAP50_95']:.3f}  "
          f"P {m['P']:.3f}  R {m['R']:.3f}  |  {ms:.0f} ms/장  {m['size_mb']} MB")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="A")
    ap.add_argument("--models", nargs="*", default=None)
    args = ap.parse_args()
    models = args.models or STAGE_A

    OUT.mkdir(exist_ok=True)
    results = []
    for mdl in models:
        tag = Path(mdl).stem
        got = run_one(mdl, tag)
        if got:
            results.append(got)

    if not results:
        raise SystemExit("성공한 실험이 없습니다")

    results.sort(key=lambda r: -r["mAP50"])
    print(f"\n{'='*84}")
    print(f"실험 {args.stage} 결과  (동일 데이터·분할·epochs·imgsz·batch·seed)")
    print(f"{'='*84}")
    print(f"{'모델':<14}{'mAP50':>8}{'mAP50-95':>10}{'P':>8}{'R':>8}"
          f"{'ms/장':>9}{'MB':>7}{'best ep':>9}")
    for r in results:
        print(f"{r['tag']:<14}{r['mAP50']:>8.3f}{r['mAP50_95']:>10.3f}{r['P']:>8.3f}"
              f"{r['R']:>8.3f}{r['ms_per_img']:>9.1f}{r['size_mb']:>7.1f}{r['best_epoch']:>9}")

    p = OUT / f"benchmark_{args.stage}.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=["tag", "model", "mAP50", "mAP50_95", "P", "R",
                                            "ms_per_img", "size_mb", "best_epoch"])
        wr.writeheader()
        wr.writerows(results)
    (OUT / f"benchmark_{args.stage}.json").write_text(
        json.dumps({"fixed": FIXED, "val_conf": VAL_CONF, "val_iou": VAL_IOU,
                    "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {p}")


if __name__ == "__main__":
    main()
