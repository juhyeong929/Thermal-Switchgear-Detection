"""Lepton 원본 TIFF 를 여러 방식으로 렌더링해 '부품이 구분되는가'를 눈으로 판정한다.

라벨링 대상을 Lepton 으로 옮길지 정하려면, 160x120 원본에서 부품이 실제로 보이는지
확인해야 한다. 지금까지 본 IR3 jpg 는 아이언보우로 칠해진 결과물이고 오토스케일이
적용돼 있어, 원본을 다르게 렌더링하면 더 잘 보일 수 있다.

각 행에 같은 프레임을 5가지로 렌더링한다.
  1) IR3 jpg 원본            지금까지 보던 것
  2) 온도 그대로 (선형)        p1~p99 클리핑
  3) CLAHE                  국소 대비 강화 (실행 가이드 STEP 3 의 핵심 채널)
  4) CLAHE + 4배 확대         라벨링 화면에서 보게 될 모습
  5) 온도 등고선             구조 경계 강조

  python lepton_view.py --date 2022-07-11 --n 6
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out" / "lepton_view"


def to_c(tif: Path) -> np.ndarray:
    return np.asarray(Image.open(tif)).astype(np.float32) / 100.0 - 273.15


def stretch(t: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(t, (1, 99))
    g = np.clip(t, lo, hi)
    return cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def render(tif: Path, ir3: Path | None, cell=(320, 240)):
    t = to_c(tif)
    g = stretch(t)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
    big = cv2.resize(clahe, (clahe.shape[1]*4, clahe.shape[0]*4), interpolation=cv2.INTER_CUBIC)
    # 등고선: 온도 구간을 나눠 경계를 그린다
    q = np.digitize(t, np.percentile(t, np.linspace(2, 98, 9))).astype(np.uint8)
    edge = cv2.Canny((q * 28).astype(np.uint8), 30, 90)
    cont = cv2.addWeighted(clahe, 0.75, edge, 0.9, 0)

    panes = []
    if ir3 and ir3.exists():
        a = cv2.imdecode(np.fromfile(str(ir3), np.uint8), cv2.IMREAD_COLOR)
        panes.append(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
    else:
        panes.append(np.zeros((120, 160, 3), np.uint8))
    for im in (g, clahe, big, cont):
        panes.append(cv2.cvtColor(im, cv2.COLOR_GRAY2RGB))
    return [cv2.resize(p, cell, interpolation=cv2.INTER_NEAREST) for p in panes], t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2022-07-11")
    ap.add_argument("--n", type=int, default=6)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(0)

    import csv
    mp = HERE / "out" / "ir3_match" / f"match_{args.date}.csv"
    pairs = []
    if mp.exists():
        rows = [r for r in csv.DictReader(mp.open(encoding="utf-8-sig")) if r["accept"] == "1"]
        for r in random.sample(rows, min(args.n, len(rows))):
            pairs.append((ROOT / r["tiff"], ROOT / r["ir3"]))
        print(f"매칭 결과 사용: {mp.name} ({len(rows)}건 중 {len(pairs)}장)")
    else:
        tifs = sorted(p for p in (ROOT/"1-수집").rglob("*.tiff") if p.name[:10] == args.date)
        for p in random.sample(tifs, min(args.n, len(tifs))):
            pairs.append((p, None))
        print(f"매칭 결과 없음 — TIFF 무작위 {len(pairs)}장")

    CW, CH = 320, 240
    LABELS = ["IR3 jpg (기존)", "온도 선형", "CLAHE", "CLAHE 4배확대", "온도 등고선"]
    sheet = Image.new("RGB", (CW*5, CH*len(pairs) + 26), "#0e1116")
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for i, lab in enumerate(LABELS):
        d.text((i*CW + 8, 8), lab, fill="#e8edf3")

    print(f"\n{'파일':<44}{'최저':>8}{'중앙':>8}{'최고':>8}")
    for r, (tif, ir3) in enumerate(pairs):
        panes, t = render(tif, ir3, (CW, CH))
        for c, p in enumerate(panes):
            sheet.paste(Image.fromarray(p), (c*CW, 26 + r*CH))
        d.text((6, 26 + r*CH + CH - 16), tif.name[:26], fill="#9aa5b1")
        print(f"{tif.name[:42]:<44}{t.min():>7.1f}C{np.median(t):>7.1f}C{t.max():>7.1f}C")

    p = OUT / f"lepton_render_{args.date}.png"
    sheet.save(p)
    print(f"\n-> {p}")
    print("   판정 기준: 이 화면에서 부품(부싱·접촉부·차단기)을 구분할 수 있는가?")


if __name__ == "__main__":
    main()
