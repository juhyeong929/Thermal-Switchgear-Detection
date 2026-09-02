"""고정 스케일의 온도 창(window)을 최적화한다.

고정 스케일은 밝기->온도 사상이 정확히 알려져 있다:  T = lo + g/255*(hi-lo)
따라서 적합(fit) 없이 실제 오차를 직접 잴 수 있다. 오차원은 둘뿐이다.

  양자화 오차  창이 넓을수록 커진다      (hi-lo)/255
  포화 오차    창이 좁을수록 커진다      창 밖으로 잘린 화소

  python scale_window.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402

HERE = Path(__file__).parent
TEMPD = HERE / "data" / "temp_all"
SKIP = {"P11", "P12", "P13"}

WINDOWS = [(20, 120), (20, 90), (15, 60), (15, 45), (18, 40), (15, 35)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    mask = osd_mask() > 0

    files = sorted(p for p in TEMPD.glob("*.npy") if p.stem.split("_")[2] not in SKIP)
    if args.limit:
        files = files[:args.limit]

    # 전 화소 온도 분포부터
    samp = []
    rng = np.random.default_rng(0)
    for f in files:
        t = np.load(f)[mask]
        samp.append(rng.choice(t, size=min(400, t.size), replace=False))
    v = np.concatenate(samp)
    print(f"화소 표본 {len(v):,}개 · 온도맵 {len(files)}장\n")
    print("전체 화소 온도 분포")
    for p in (0.1, 1, 5, 25, 50, 75, 95, 99, 99.9):
        print(f"  p{p:<5} {np.percentile(v, p):7.1f}C")
    print(f"  최고   {v.max():7.1f}C")

    print(f"\n\n고정 창별 온도 복원 오차  (밝기 -> 온도, 적합 없이 직접 환산)")
    print(f"{'창':<14}{'양자화 step':>12}{'포화 화소':>11}{'RMSE':>9}"
          f"{'p95 오차':>10}{'최대':>9}")
    best = None
    for lo, hi in WINDOWS:
        g = np.clip((v - lo) / (hi - lo) * 255, 0, 255)
        g = np.round(g)                       # 8bit 저장
        est = lo + g / 255 * (hi - lo)
        err = np.abs(est - v)
        sat = ((v < lo) | (v > hi)).mean() * 100
        rmse = float(np.sqrt((err ** 2).mean()))
        row = (f"{f'{lo}~{hi}°C':<14}{(hi-lo)/255:>11.3f}K{sat:>10.1f}%"
               f"{rmse:>8.2f}K{np.percentile(err,95):>9.2f}K{err.max():>8.2f}K")
        print(row)
        if best is None or rmse < best[0]:
            best = (rmse, lo, hi)

    print(f"\n권장 창: {best[1]}~{best[2]}°C  (RMSE {best[0]:.2f}K)")

    # 판정 임계 관점: 5K/15K/40K 를 구분할 수 있는가
    print(f"\n\n판정 임계 해상도  (상간 비교 임계 5K / 15K / 40K)")
    print(f"{'창':<14}{'5K 를 몇 계단으로 표현':>26}")
    for lo, hi in WINDOWS:
        step = (hi - lo) / 255
        print(f"{f'{lo}~{hi}°C':<14}{5/step:>22.0f}계단")


if __name__ == "__main__":
    main()
