"""P1~P10 전 반의 IR1 에서 온도맵을 추출해 data/temp_all 에 저장한다.

원본(3-가공)은 읽기만 한다. 결과는 pilot/data/temp_all/<stem>.npy (float32 240x320).

  python extract_all_temp.py
"""
from __future__ import annotations

import argparse
import collections
import sys
import time
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import flir  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "data" / "temp_all"
SKIP_PANELS = {"P11", "P12", "P13"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    files = []
    for p in (ROOT / "3-가공").rglob("*_IR1_*.jpg"):
        if p.name.startswith("._") or "rgb" in p.name.lower():
            continue
        q = p.name.split("_")
        if len(q) > 3 and q[2] not in SKIP_PANELS:
            files.append(p)
    files.sort()
    print(f"대상 {len(files)}장  ->  {OUT}")

    ok = skip = fail = 0
    errs = collections.Counter()
    t0 = time.time()
    for i, p in enumerate(files, 1):
        dst = OUT / f"{p.stem}.npy"
        if dst.exists() and not args.force:
            skip += 1
            continue
        try:
            temp, _rgb, _meta = flir.read(p)
            np.save(dst, temp.astype(np.float32))
            ok += 1
        except Exception as e:                     # noqa: BLE001
            fail += 1
            errs[type(e).__name__] += 1
        if i % 100 == 0 or i == len(files):
            el = time.time() - t0
            print(f"  {i}/{len(files)}  성공{ok} 건너뜀{skip} 실패{fail}  "
                  f"{el:.0f}s", end="\r")
    print()
    print(f"\n성공 {ok} · 건너뜀 {skip} · 실패 {fail}  ({time.time()-t0:.0f}s)")
    if errs:
        print("실패 사유:", dict(errs))

    c = collections.Counter(f.stem.split("_")[2] for f in OUT.glob("*.npy"))
    print(f"\n{'반':<6}{'온도맵':>8}")
    for k in sorted(c, key=lambda x: int(x[1:]) if x[1:].isdigit() else 99):
        print(f"{k:<6}{c[k]:>8}")
    print(f"{'합계':<6}{sum(c.values()):>8}")


if __name__ == "__main__":
    main()
