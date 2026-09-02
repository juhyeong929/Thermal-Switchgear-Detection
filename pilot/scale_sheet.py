"""반별 대표 프레임을 4가지 렌더링으로 나란히 본다. (scale_compare_all 의 시각판)

  python scale_sheet.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from scale_compare import MODES, render, ambient  # noqa: E402

HERE = Path(__file__).parent
TEMPD = HERE / "data" / "temp_all"
OUT = HERE / "out"
PNAME = {"P1": "TR반", "P2": "LBS&LA반", "P3": "MOF반", "P4": "MOF&PT반",
         "P5": "PF&PT반", "P6": "VCB반", "P7": "VCB&CT반", "P8": "ACB반",
         "P9": "MCCB반", "P10": "ACB&MCCB반"}


def main():
    mask = osd_mask() > 0
    rng = np.random.default_rng(3)
    by = {}
    for f in sorted(TEMPD.glob("*.npy")):
        by.setdefault(f.stem.split("_")[2], []).append(f)

    pans = sorted(by, key=lambda x: int(x[1:]))
    picks = []
    for p in pans:
        # 그 반의 중앙 정도 발열을 가진 프레임을 고른다
        cand = list(rng.choice(by[p], size=min(40, len(by[p])), replace=False))
        sc = []
        for f in cand:
            t = np.load(f)
            sc.append((float(np.percentile(t[mask], 99) - ambient(t, mask)), f))
        sc.sort()
        picks.append((p, sc[len(sc) // 2][1], sc[len(sc) // 2][0]))

    CW, CH, head, LW = 268, 201, 30, 150
    img = Image.new("RGB", (LW + CW * len(MODES), head + CH * len(picks)), "#0e1116")
    d = ImageDraw.Draw(img)
    d.text((10, 9), "반 / 발열폭", fill="#e8edf3")
    for i, (_m, n) in enumerate(MODES):
        d.text((LW + i * CW + 8, 9), n, fill="#e8edf3")

    print(f"{'반':<14}{'dT':>8}{'대기':>8}{'최고':>8}")
    for r, (p, f, dT) in enumerate(picks):
        t = np.load(f)
        amb = ambient(t, mask)
        y = head + r * CH
        d.text((10, y + 12), f"{p} {PNAME.get(p,'')}", fill="#ffd479")
        d.text((10, y + 34), f"dT {dT:.1f}K", fill="#e8edf3")
        d.text((10, y + 52), f"대기 {amb:.1f}C", fill="#9aa5b1")
        d.text((10, y + 68), f"최고 {t[mask].max():.1f}C", fill="#9aa5b1")
        for i, (m, _n) in enumerate(MODES):
            g = cv2.cvtColor(render(t, mask, m), cv2.COLOR_GRAY2RGB)
            img.paste(Image.fromarray(cv2.resize(g, (CW, CH), interpolation=cv2.INTER_NEAREST)),
                      (LW + i * CW, y))
        print(f"{p+' '+PNAME.get(p,''):<14}{dT:>7.1f}K{amb:>7.1f}C{t[mask].max():>7.1f}C")

    img.save(OUT / "scale_sheet_all.png")
    img.save(OUT / "scale_sheet_all.jpg", quality=88)
    print(f"\n-> {OUT / 'scale_sheet_all.png'}")


if __name__ == "__main__":
    main()
