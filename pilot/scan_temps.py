"""IR1 2,606쌍 전체의 온도 통계를 훑어 인덱스를 만든다.

라벨이 없어도 지금 당장 답할 수 있는 질문: 이 데이터셋에 실제로 이상 발열이 찍혀 있는가.
장면 중앙값 대비 상승폭(dT)이 열화 판정의 기본 지표이므로 함께 계산한다.

원본은 읽기만 한다. 결과는 out/temp_index.csv.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import flir  # noqa: E402
from calibrate import osd_mask  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).parent / "out"

# FLIR E8 측정 범위는 -20 ~ +250 °C. 이를 넘는 값은 외삽이라 측정값으로 쓰면 안 된다.
T_RANGE_MAX = 250.0


def main():
    OUT.mkdir(exist_ok=True)
    mask = osd_mask() > 0
    files = sorted(p for p in ROOT.glob("3-가공/**/*_IR1_*.jpg")
                   if not p.name.endswith("_rgb_image.jpg"))
    print(f"IR1 열화상 {len(files)}장 스캔")

    rows, failed = [], 0
    for i, p in enumerate(files, 1):
        try:
            temp, _vis, _meta = flir.read(p)
        except Exception:
            failed += 1
            continue
        t = temp[mask]
        t = t[np.isfinite(t)]
        if t.size == 0:
            failed += 1
            continue
        med = float(np.median(t))
        rows.append({
            "stem": p.stem,
            "panel": p.parts[-2] if p.parts[-2].startswith("P") else p.parts[-3],
            "site": p.stem.split("_")[0], "date": p.stem.split("_")[3],
            "t_med": round(med, 2), "t_mean": round(float(t.mean()), 2),
            "t_p99": round(float(np.percentile(t, 99)), 2),
            "t_max": round(float(t.max()), 2),
            "dT_p99": round(float(np.percentile(t, 99)) - med, 2),
            "dT_max": round(float(t.max()) - med, 2),
            "saturated_px": int((t > T_RANGE_MAX).sum()),   # 측정범위 초과 화소수
            "path": str(p.relative_to(ROOT)),
        })
        if i % 400 == 0:
            print(f"  {i}/{len(files)}")

    out = OUT / "temp_index.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    dt = np.array([r["dT_max"] for r in rows])
    tmax = np.array([r["t_max"] for r in rows])
    print(f"\n성공 {len(rows)}장 / 실패 {failed}장  -> {out}")
    print("\n장면 중앙값 대비 최대 상승폭 dT_max 분포")
    for q in (50, 75, 90, 95, 99):
        print(f"  p{q:<3d} {np.percentile(dt, q):6.1f} K")
    print(f"  최대 {dt.max():.1f} K")
    print("\nNETA/KEPCO 계열 열화 판정 구간별 장수")
    for lo, hi, label in [(0, 5, "정상"), (5, 15, "주의 관찰"),
                          (15, 40, "이상, 조치 권고"), (40, 999, "심각, 즉시 조치")]:
        n = int(((dt >= lo) & (dt < hi)).sum())
        hi_s = str(hi) if hi < 999 else "inf"
        print(f"  dT {lo:>2}~{hi_s:>3} K  {label:<16} {n:5d}장 ({n/len(dt)*100:5.1f}%)")
    print(f"\n절대 최고온도 60도 이상: {int((tmax >= 60).sum())}장, "
          f"80도 이상: {int((tmax >= 80).sum())}장")
    sat = np.array([r["saturated_px"] for r in rows])
    print(f"측정범위({T_RANGE_MAX:.0f}도) 초과 화소를 포함한 장: {int((sat > 0).sum())}장 "
          f"- 램프/히터 등 설비 외 발열체이거나 외삽값이므로 측정값으로 쓰지 말 것")


if __name__ == "__main__":
    main()
