"""극단 고온 프레임이 진짜 발열인지 반사/외광인지 확인한다.

271°C 같은 값은 수배전반 정상 운전에서 나올 수 없다. 후보 원인:
  - 태양광/조명 반사 (금속면)
  - 촬영자 반사
  - 창문 밖 외부 장면이 프레임에 들어옴
  - 실제 심각 발열

실화상을 나란히 놓으면 대부분 구분된다.

  python check_outliers.py --top 12
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import flir  # noqa: E402
from calibrate import osd_mask  # noqa: E402
from scale_compare import render  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
TEMPD = HERE / "data" / "temp_all"
OUT = HERE / "out"
SKIP = {"P11", "P12", "P13"}


def find_src(stem):
    hits = list((ROOT / "3-가공").rglob(f"{stem}.jpg"))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--min-c", type=float, default=100.0)
    args = ap.parse_args()
    mask = osd_mask() > 0

    cand = []
    for f in sorted(TEMPD.glob("*.npy")):
        if f.stem.split("_")[2] in SKIP:
            continue
        t = np.load(f)
        tm = t[mask]
        mx = float(tm.max())
        if mx >= args.min_c:
            hot = tm >= mx - 5
            cand.append({"stem": f.stem, "tmax": mx, "p999": float(np.percentile(tm, 99.9)),
                         "hot_px": int(hot.sum()), "hot_pct": float(hot.mean() * 100),
                         "med": float(np.median(tm))})
    cand.sort(key=lambda r: -r["tmax"])
    print(f"{args.min_c:.0f}°C 이상 프레임 {len(cand)}장\n")
    print(f"{'반':<5}{'최고':>8}{'p99.9':>9}{'장면중앙':>9}{'최고부 화소':>10}{'비율':>7}  파일")
    for r in cand[:40]:
        pan = r["stem"].split("_")[2]
        print(f"{pan:<5}{r['tmax']:>7.1f}C{r['p999']:>8.1f}C{r['med']:>8.1f}C"
              f"{r['hot_px']:>10}{r['hot_pct']:>6.2f}%  {r['stem'][:34]}")

    pick = cand[:args.top]
    CW, CH, head = 300, 225, 28
    img = Image.new("RGB", (CW * 4, head + CH * len(pick)), "#0e1116")
    d = ImageDraw.Draw(img)
    for i, lab in enumerate(["실화상", "열화상 오토", "절대 20~120°C", "최고온부 위치"]):
        d.text((i * CW + 8, 8), lab, fill="#e8edf3")

    print()
    for r, c in enumerate(pick):
        src = find_src(c["stem"])
        t = np.load(TEMPD / f"{c['stem']}.npy")
        y = head + r * CH
        rgb = None
        if src:
            try:
                _t2, rgb, _m = flir.read(src)
            except Exception as e:                     # noqa: BLE001
                print(f"  실화상 실패 {c['stem']}: {e}")
        panes = [rgb if rgb is not None else np.zeros((240, 320, 3), np.uint8),
                 cv2.cvtColor(render(t, mask, "auto"), cv2.COLOR_GRAY2RGB),
                 cv2.cvtColor(render(t, mask, "abs"), cv2.COLOR_GRAY2RGB)]
        # 최고온부 위치 표시
        loc = cv2.cvtColor(render(t, mask, "auto"), cv2.COLOR_GRAY2RGB)
        hot = (t >= t[mask].max() - 5) & mask
        loc[hot] = (255, 60, 60)
        panes.append(loc)
        for i, p in enumerate(panes):
            img.paste(Image.fromarray(cv2.resize(p, (CW, CH), interpolation=cv2.INTER_AREA)),
                      (i * CW, y))
        d.text((6, y + 6), f"{c['stem'].split('_')[2]}  {c['tmax']:.0f}C", fill="#ff6b6b")
        d.text((6, y + 24), f"화소 {c['hot_px']}", fill="#ffd479")
        d.text((6, y + CH - 16), c["stem"][:30], fill="#9aa5b1")
    p = OUT / "outliers.png"
    img.save(p)
    img.save(OUT / "outliers.jpg", quality=88)
    print(f"-> {p}")


if __name__ == "__main__":
    main()
