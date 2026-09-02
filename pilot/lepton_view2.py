"""Lepton 원본 렌더링 — 반별 비교와 CLAHE 설정 비교.

  python lepton_view2.py panels     반별로 1~2장씩, 동일 설정
  python lepton_view2.py settings   대표 프레임을 여러 CLAHE 설정으로

판정 기준은 하나다: **이 화면에서 부품 이름을 확신을 갖고 붙일 수 있는가.**
"""
from __future__ import annotations

import argparse
import collections
import csv
import random
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out" / "lepton_view"
MATCH = HERE / "out" / "ir3_match" / "match_2022-07-11.csv"

PANEL_NAME = {
    "P1": "TR반", "P2": "LBS&LA반", "P3": "MOF반", "P5": "PF&PT반",
    "P6": "VCB반", "P8": "ACB반", "P9": "MCCB반", "P10": "ACB&MCCB반",
    "P12": "배선반", "P13": "기타",
}


def to_c(tif: Path) -> np.ndarray:
    return np.asarray(Image.open(tif)).astype(np.float32) / 100.0 - 273.15


def stretch(t, lo_p=1, hi_p=99):
    lo, hi = np.percentile(t, (lo_p, hi_p))
    return cv2.normalize(np.clip(t, lo, hi), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def clahe(g, clip, tile):
    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile)).apply(g)


def ir3_rgb(p: Path):
    a = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    return cv2.cvtColor(a, cv2.COLOR_BGR2RGB) if a is not None else None


def load_pairs():
    rows = [r for r in csv.DictReader(MATCH.open(encoding="utf-8-sig")) if r["accept"] == "1"]
    by = collections.defaultdict(list)
    for r in rows:
        by[Path(r["ir3"]).stem.split("_")[2]].append((ROOT / r["tiff"], ROOT / r["ir3"]))
    return by


def sheet(rows, cols, labels, path, cw=300, ch=225, row_label=None):
    head = 26
    img = Image.new("RGB", (cw*cols, head + ch*len(rows)), "#0e1116")
    d = ImageDraw.Draw(img)
    for i, lab in enumerate(labels):
        d.text((i*cw + 8, 8), lab, fill="#e8edf3")
    for r, panes in enumerate(rows):
        for c, p in enumerate(panes):
            if p is None:
                continue
            img.paste(Image.fromarray(cv2.resize(p, (cw, ch), interpolation=cv2.INTER_NEAREST)),
                      (c*cw, head + r*ch))
        if row_label:
            d.text((6, head + r*ch + 6), row_label[r], fill="#ffd479")
    img.save(path)
    return path


def mode_panels(args):
    by = load_pairs()
    random.seed(args.seed)
    order = ["P1", "P2", "P3", "P5", "P6", "P8", "P9", "P10", "P12", "P13"]
    rows, tags = [], []
    print(f"{'반':<16}{'최저':>8}{'중앙':>8}{'최고':>8}  파일")
    for pan in order:
        if pan not in by:
            continue
        for tif, ir3 in random.sample(by[pan], min(args.per, len(by[pan]))):
            t = to_c(tif)
            g = stretch(t)
            rows.append([ir3_rgb(ir3),
                         cv2.cvtColor(g, cv2.COLOR_GRAY2RGB),
                         cv2.cvtColor(clahe(g, 2.0, 8), cv2.COLOR_GRAY2RGB),
                         cv2.cvtColor(clahe(stretch(t, 2, 98), 3.0, 4), cv2.COLOR_GRAY2RGB)])
            tags.append(f"{pan} {PANEL_NAME.get(pan,'')}")
            print(f"{pan+' '+PANEL_NAME.get(pan,''):<16}{t.min():>7.1f}C{np.median(t):>7.1f}C"
                  f"{t.max():>7.1f}C  {tif.name[:30]}")
    p = sheet(rows, 4,
              ["IR3 jpg (기존)", "온도 선형", "CLAHE 2.0 / 8x8", "CLAHE 3.0 / 4x4"],
              OUT / "lepton_by_panel.png", row_label=tags)
    print(f"\n-> {p}")


def mode_settings(args):
    by = load_pairs()
    random.seed(args.seed)
    picks = []
    for pan in ("P1", "P6", "P9", "P8"):
        if pan in by:
            picks.append((pan, *random.choice(by[pan])))
    SET = [("원본 IR3", None),
           ("선형만", ("lin", 0, 0)),
           ("CLAHE 1.0/8", ("cl", 1.0, 8)),
           ("CLAHE 2.0/8", ("cl", 2.0, 8)),
           ("CLAHE 4.0/8", ("cl", 4.0, 8)),
           ("CLAHE 3.0/4", ("cl", 3.0, 4)),
           ("CLAHE 3.0/16", ("cl", 3.0, 16))]
    rows, tags = [], []
    for pan, tif, ir3 in picks:
        t = to_c(tif)
        g = stretch(t)
        panes = []
        for _lab, cfg in SET:
            if cfg is None:
                panes.append(ir3_rgb(ir3))
            elif cfg[0] == "lin":
                panes.append(cv2.cvtColor(g, cv2.COLOR_GRAY2RGB))
            else:
                panes.append(cv2.cvtColor(clahe(g, cfg[1], cfg[2]), cv2.COLOR_GRAY2RGB))
        rows.append(panes)
        tags.append(f"{pan} {PANEL_NAME.get(pan,'')}")
        print(f"{pan} {PANEL_NAME.get(pan,''):<12} {tif.name[:34]}  "
              f"{t.min():.1f}~{t.max():.1f}C")
    p = sheet(rows, len(SET), [s[0] for s in SET],
              OUT / "lepton_by_setting.png", cw=260, ch=195, row_label=tags)
    print(f"\n-> {p}")
    print("   clipLimit 이 클수록 대비가 강해지지만 노이즈도 같이 커집니다.")
    print("   tile 이 작을수록(4x4) 국소적으로, 클수록(16x16) 전역적으로 조정됩니다.")


def mode_one(args):
    """한 반을 여러 장 뽑아 IR3 와 CLAHE 를 나란히 본다."""
    by = load_pairs()
    pan = args.panel
    if pan not in by:
        raise SystemExit(f"{pan} 매칭 결과 없음. 있는 반: {sorted(by)}")
    random.seed(args.seed)
    pick = random.sample(by[pan], min(args.n, len(by[pan])))
    print(f"{pan} {PANEL_NAME.get(pan,'')} — {len(by[pan])}장 중 {len(pick)}장\n")
    print(f"{'파일':<38}{'최저':>8}{'중앙':>8}{'최고':>8}")
    CW, CH = 340, 255
    cols = 4                      # (IR3, CLAHE) 쌍 2개씩
    rows_n = (len(pick) + 1) // 2
    head = 26
    img = Image.new("RGB", (CW*cols, head + CH*rows_n), "#0e1116")
    d = ImageDraw.Draw(img)
    for i, lab in enumerate(["IR3 jpg", "CLAHE 2.0/8", "IR3 jpg", "CLAHE 2.0/8"]):
        d.text((i*CW + 8, 8), lab, fill="#e8edf3")
    for k, (tif, ir3) in enumerate(pick):
        t = to_c(tif); g = stretch(t)
        cl = cv2.cvtColor(clahe(g, 2.0, 8), cv2.COLOR_GRAY2RGB)
        a = ir3_rgb(ir3)
        r, c = k // 2, (k % 2) * 2
        for j, pane in enumerate((a, cl)):
            if pane is None: continue
            img.paste(Image.fromarray(cv2.resize(pane, (CW, CH), interpolation=cv2.INTER_NEAREST)),
                      ((c+j)*CW, head + r*CH))
        d.text((c*CW + 6, head + r*CH + 6), f"#{k:02d}", fill="#ffd479")
        d.text((c*CW + 6, head + r*CH + CH - 16), tif.name[11:23], fill="#9aa5b1")
        print(f"{tif.name[:36]:<38}{t.min():>7.1f}C{np.median(t):>7.1f}C{t.max():>7.1f}C")
    out = OUT / f"lepton_{pan}_{len(pick)}.png"
    img.save(out)
    print(f"\n-> {out}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["panels", "settings", "one"])
    ap.add_argument("--panel", default="P9")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--per", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    {"panels": mode_panels, "settings": mode_settings, "one": mode_one}[a.mode](a)
