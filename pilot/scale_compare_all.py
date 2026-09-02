"""P1~P10 전 반으로 오토스케일 vs 고정스케일 비교.

scale_compare.py 는 P1(단일 반·좁은 대기온도 범위)만 봤다.
여기서는 현장 10곳 · 촬영일 4일이 섞였을 때 순위가 바뀌는지 확인한다.

지표 1 은 라벨 없이 계산한다 — 이미지마다 무작위 패치를 뽑아
(패치 실제온도, 패치 렌더밝기) 쌍을 모으면 전 반을 다 쓸 수 있다.

  지표 1a  밝기 -> 온도 상관 r
  지표 1b  밝기로 온도를 추정했을 때 오차 (K)   ← 가장 해석하기 쉬움
  지표 2   같은 부품의 사진간 밝기 편차 (라벨 있는 것만)

  python scale_compare_all.py
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID  # noqa: E402
from scale_compare import MODES, render, ambient, crop, load_boxes  # noqa: E402

HERE = Path(__file__).parent
TEMPD = HERE / "data" / "temp_all"
LABD = HERE / "data" / "labels_ir"
SKIP = {"P11", "P12", "P13"}


def panel(stem):
    q = stem.split("_")
    return q[2] if len(q) > 2 else "?"


def date(stem):
    q = stem.split("_")
    return q[3] if len(q) > 3 else "?"


def fit_rmse(temp, bright):
    """밝기->온도 최적 선형사상의 잔차 RMSE (K). 낮을수록 밝기가 온도를 잘 대변."""
    A = np.vstack([bright, np.ones_like(bright)]).T
    coef, *_ = np.linalg.lstsq(A, temp, rcond=None)
    return float(np.sqrt(np.mean((A @ coef - temp) ** 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patches", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    mask = osd_mask() > 0
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    rng = np.random.default_rng(0)

    files = sorted(p for p in TEMPD.glob("*.npy") if panel(p.stem) not in SKIP)
    if args.limit:
        files = files[:args.limit]
    print(f"온도맵 {len(files)}장 · 반 {len(set(panel(f.stem) for f in files))}개 "
          f"· 촬영일 {len(set(date(f.stem) for f in files))}일\n")

    pool = {m: {"t": [], "g": []} for m, _ in MODES}
    perpan = collections.defaultdict(lambda: {m: {"t": [], "g": []} for m, _ in MODES})
    percls = {m: collections.defaultdict(list) for m, _ in MODES}
    ambs = []

    for k, f in enumerate(files, 1):
        t = np.load(f)
        if not np.isfinite(t).all():
            t = np.nan_to_num(t, nan=float(np.nanmedian(t)))
        amb = ambient(t, mask)
        ambs.append(amb)
        rend = {m: render(t, mask, m) for m, _ in MODES}
        pan = panel(f.stem)

        # --- 지표 1: 무작위 패치 ---
        for _ in range(args.patches):
            bw = int(rng.integers(12, 70)); bh = int(rng.integers(12, 70))
            px = int(rng.integers(x0, max(x1 - bw, x0 + 1)))
            py = int(rng.integers(y0, max(y1 - bh, y0 + 1)))
            sl = (slice(py, py + bh), slice(px, px + bw))
            if not mask[sl].all():
                continue
            tv = float(np.percentile(t[sl], 99))
            for m, _ in MODES:
                gv = float(rend[m][sl].mean())
                pool[m]["t"].append(tv); pool[m]["g"].append(gv)
                perpan[pan][m]["t"].append(tv); perpan[pan][m]["g"].append(gv)

        # --- 지표 2: 라벨 있는 것만 ---
        lp = LABD / f"{f.stem}.txt"
        if lp.exists():
            for c, bn in load_boxes(lp):
                for m, _ in MODES:
                    g = crop(rend[m], bn)
                    if g is not None and g.size >= 4:
                        percls[m][c].append(float(g.mean()))
        if k % 200 == 0 or k == len(files):
            print(f"  처리 {k}/{len(files)}", end="\r")
    print()

    a = np.array(ambs)
    print(f"\n대기온도 분포  최저{a.min():.1f}  중앙{np.median(a):.1f}  "
          f"최고{a.max():.1f}  (범위 {a.max()-a.min():.1f}K)")

    print(f"\n\n지표 1 · 전 반 통합  (패치 {len(pool['auto']['t']):,}개)")
    print(f"{'렌더 방식':<22}{'상관 r':>10}{'설명력':>10}{'온도추정 오차':>14}")
    for m, name in MODES:
        t = np.array(pool[m]["t"]); g = np.array(pool[m]["g"])
        r = float(np.corrcoef(t, g)[0, 1])
        print(f"{name:<22}{r:>10.3f}{r*r*100:>9.1f}%{fit_rmse(t, g):>12.2f}K")

    print(f"\n\n지표 1 · 반별 상관 r")
    pans = sorted(perpan, key=lambda x: int(x[1:]) if x[1:].isdigit() else 99)
    print(f"{'반':<6}" + "".join(f"{n.split()[0]:>9}" for _m, n in MODES) + f"{'n':>9}")
    for p in pans:
        row = f"{p:<6}"
        n = 0
        for m, _ in MODES:
            t = np.array(perpan[p][m]["t"]); g = np.array(perpan[p][m]["g"])
            n = len(t)
            row += f"{np.corrcoef(t, g)[0,1]:>9.3f}" if n > 10 else f"{'-':>9}"
        print(row + f"{n:>9,}")

    print(f"\n\n지표 2 · 같은 부품의 사진간 밝기 편차 (낮을수록 일관)")
    classes = sorted({c for m, _ in MODES for c in percls[m] if len(percls[m][c]) >= 20},
                     key=lambda c: -len(percls["auto"][c]))
    print(f"{'클래스':<20}" + "".join(f"{n.split()[0]:>9}" for _m, n in MODES) + f"{'n':>8}")
    tot = {m: [] for m, _ in MODES}
    for c in classes:
        row = f"{KOREAN_BY_ID[c]:<20}"
        n = 0
        for m, _ in MODES:
            v = np.array(percls[m][c]); n = len(v)
            row += f"{v.std():>9.1f}"
            tot[m].append(v.std())
        print(row + f"{n:>8}")
    print(f"{'평균':<20}" + "".join(f"{np.mean(tot[m]):>9.1f}" for m, _ in MODES))


if __name__ == "__main__":
    main()
