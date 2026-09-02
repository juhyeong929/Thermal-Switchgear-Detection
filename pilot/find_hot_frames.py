"""특정 반의 IR3 프레임을 전부 매칭한 뒤 발열이 큰 순으로 골라 본다.

Lepton 은 온도차가 작으면 형태가 안 드러난다 (P6 VCB반 표본 10장이 전부 2~3°C
범위였고 판독이 어려웠다). 발열이 있는 프레임만 추리면 판독성이 달라질 수 있으므로,
실제 온도로 순위를 매겨 확인한다.

발열 지표 = 프레임 최고온도 − 대기온도 추정(최저 10% 화소 평균)
analyze.py 와 같은 방식이다.

  python find_hot_frames.py --panel P6 --date 2022-07-11 --top 10
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from match_ir3_lepton import ir3_descriptor, load_bank  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out" / "lepton_view"


def to_c(tif: Path) -> np.ndarray:
    return np.asarray(Image.open(tif)).astype(np.float32) / 100.0 - 273.15


def ambient(t: np.ndarray) -> float:
    v = t.ravel()
    return float(v[v <= np.percentile(v, 10)].mean())


def stretch(t, lo_p=1, hi_p=99):
    lo, hi = np.percentile(t, (lo_p, hi_p))
    return cv2.normalize(np.clip(t, lo, hi), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default="P6")
    ap.add_argument("--date", default="2022-07-11")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--batch", type=int, default=512)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    folder = next((d for d in (ROOT / "3-가공").iterdir()
                   if d.is_dir() and d.name.split("-")[0] == args.panel), None)
    if folder is None:
        raise SystemExit(f"{args.panel} 폴더 없음")
    ir3 = sorted(p for p in folder.rglob(f"*_{args.date}_IR3_*.jpg")
                 if not p.name.startswith("._"))
    print(f"{folder.name} · {args.date} · IR3 {len(ir3)}장")
    if not ir3:
        raise SystemExit("대상 없음")

    M, tifs = load_bank(args.date)
    rows = []
    t0 = time.time()
    for s in range(0, len(ir3), args.batch):
        chunk = ir3[s:s+args.batch]
        Q = np.stack([ir3_descriptor(p) for p in chunk])
        sims = (Q @ M.T) / Q.shape[1]
        best = sims.argmax(1)
        top = sims[np.arange(len(chunk)), best]
        for p, bi, tv in zip(chunk, best, top):
            if tv < 0.95:
                continue
            t = to_c(tifs[bi])
            amb = ambient(t)
            rows.append({"ir3": p, "tiff": tifs[bi], "ncc": float(tv),
                         "amb": amb, "tmax": float(t.max()),
                         "dT": float(t.max() - amb),
                         "p99": float(np.percentile(t, 99))})
        print(f"  매칭 {s+len(chunk)}/{len(ir3)}  {time.time()-t0:.0f}s", end="\r")
    print()
    if not rows:
        raise SystemExit("매칭된 프레임 없음")

    rows.sort(key=lambda r: -r["dT"])
    dt = np.array([r["dT"] for r in rows])
    print(f"\n매칭 {len(rows)}장 (NCC>=0.95)")
    print(f"  발열폭 dT  중앙 {np.median(dt):.1f}K · p90 {np.percentile(dt,90):.1f}K "
          f"· 최대 {dt.max():.1f}K")
    for th in (3, 5, 10, 15):
        n = int((dt >= th).sum())
        print(f"    dT >= {th:2d}K : {n:4d}장 ({n/len(dt)*100:4.1f}%)")

    with open(OUT / f"hot_{args.panel}_{args.date}.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["ir3", "tiff", "ncc", "amb", "tmax", "dT", "p99"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "ir3": r["ir3"].name, "tiff": r["tiff"].name})

    pick = rows[:args.top]
    CW, CH = 340, 255
    head = 26
    rn = (len(pick) + 1) // 2
    img = Image.new("RGB", (CW*4, head + CH*rn), "#0e1116")
    d = ImageDraw.Draw(img)
    for i, lab in enumerate(["IR3 jpg", "CLAHE 2.0/8", "IR3 jpg", "CLAHE 2.0/8"]):
        d.text((i*CW + 8, 8), lab, fill="#e8edf3")
    print(f"\n{'순위':>4} {'dT':>7} {'최고':>8} {'대기':>8}  파일")
    for k, r in enumerate(pick):
        t = to_c(r["tiff"])
        cl = cv2.cvtColor(cv2.createCLAHE(2.0, (8, 8)).apply(stretch(t)), cv2.COLOR_GRAY2RGB)
        a = cv2.imdecode(np.fromfile(str(r["ir3"]), np.uint8), cv2.IMREAD_COLOR)
        a = cv2.cvtColor(a, cv2.COLOR_BGR2RGB) if a is not None else np.zeros_like(cl)
        rr, cc = k // 2, (k % 2) * 2
        for j, pane in enumerate((a, cl)):
            img.paste(Image.fromarray(cv2.resize(pane, (CW, CH), interpolation=cv2.INTER_NEAREST)),
                      ((cc+j)*CW, head + rr*CH))
        d.text((cc*CW + 6, head + rr*CH + 6),
               f"#{k:02d}  dT {r['dT']:.1f}K  max {r['tmax']:.1f}C", fill="#ffd479")
        print(f"{k:>4} {r['dT']:>6.1f}K {r['tmax']:>7.1f}C {r['amb']:>7.1f}C  {r['ir3'].name[:34]}")
    p = OUT / f"hot_{args.panel}_{args.date}.png"
    img.save(p)
    print(f"\n-> {p}")
    print(f"-> {OUT / f'hot_{args.panel}_{args.date}.csv'}")


if __name__ == "__main__":
    main()
