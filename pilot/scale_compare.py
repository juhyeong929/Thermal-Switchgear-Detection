"""오토스케일 vs 고정스케일 렌더링 비교.

문제
  IR3 jpg 는 사진마다 최저~최고 온도를 0~255 로 늘려 칠한다(오토스케일).
  그래서 흰색이 어떤 사진에선 25°C, 어떤 사진에선 96°C 를 뜻한다.
  모델은 "밝다=뜨겁다"를 배우려는데 그 관계가 사진마다 달라진다.

비교 대상
  A 오토스케일        각 사진의 p1~p99          ← 현재 IR3 jpg 방식
  B 절대 고정         20~120°C 고정
  C 대기차분 고정      (온도-대기) 0~60K 고정   ← 회의 판정기준과 같은 논리
  D C + CLAHE        저ΔT 장면 대비 보강

판정 지표
  1) 밝기↔온도 상관   같은 밝기가 항상 같은 온도를 뜻하는가 (높을수록 좋음)
  2) 클래스내 밝기 편차 같은 부품이 사진마다 같은 밝기로 보이는가 (낮을수록 좋음)

  python scale_compare.py
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"

ABS_LO, ABS_HI = 20.0, 120.0    # B: 절대 고정 창
DIF_LO, DIF_HI = 0.0, 60.0      # C: 대기차분 고정 창


def ambient(t: np.ndarray, mask: np.ndarray) -> float:
    v = t[mask & np.isfinite(t)]
    return float(v[v <= np.percentile(v, 10)].mean())


def to_u8(x, lo, hi):
    return np.clip((x - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)


def render(t: np.ndarray, mask: np.ndarray, mode: str) -> np.ndarray:
    """온도맵 -> 8bit 그레이. mode: auto | abs | dif | difc"""
    if mode == "auto":
        lo, hi = np.percentile(t[mask], (1, 99))
        return to_u8(t, lo, hi)
    if mode == "abs":
        return to_u8(t, ABS_LO, ABS_HI)
    d = t - ambient(t, mask)
    g = to_u8(d, DIF_LO, DIF_HI)
    if mode == "difc":
        g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
    return g


MODES = [("auto", "A 오토스케일 (현재)"),
         ("abs",  "B 절대 20~120°C"),
         ("dif",  "C 대기차분 0~60K"),
         ("difc", "D 대기차분+CLAHE")]


def load_boxes(p: Path):
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        q = ln.split()
        if len(q) == 5:
            out.append((int(q[0]), tuple(map(float, q[1:]))))
    return out


def crop(a, bn):
    h, w = a.shape[:2]
    cx, cy, bw, bh = bn
    x1, y1 = max(0, int((cx-bw/2)*w)), max(0, int((cy-bh/2)*h))
    x2, y2 = min(w, int((cx+bw/2)*w)), min(h, int((cy+bh/2)*h))
    return a[y1:y2, x1:x2] if (x2 > x1 and y2 > y1) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(HERE / "_p1only" / "labels"))
    ap.add_argument("--limit", type=int, default=400)
    args = ap.parse_args()

    mask = osd_mask() > 0
    lab_dir = Path(args.labels)
    stems = sorted(f.stem for f in lab_dir.glob("*.txt")
                   if (DATA / "temp" / f"{f.stem}.npy").exists())[:args.limit]
    print(f"대상 {len(stems)}장\n")

    # ---- 정량 지표 ----
    # 박스마다 (실제 p99 온도, 렌더 밝기 평균) 을 모아 상관과 편차를 본다
    pts = {m: [] for m, _ in MODES}
    percls = {m: collections.defaultdict(list) for m, _ in MODES}
    sheets = []       # (dT, stem, temp) 시각화 후보

    for stem in stems:
        t = np.load(DATA / "temp" / f"{stem}.npy")
        boxes = load_boxes(lab_dir / f"{stem}.txt")
        if not boxes:
            continue
        amb = ambient(t, mask)
        sheets.append((float(np.percentile(t[mask], 99) - amb), stem))
        rend = {m: render(t, mask, m) for m, _ in MODES}
        for c, bn in boxes:
            ct = crop(t, bn)
            if ct is None or ct.size < 4:
                continue
            temp99 = float(np.percentile(ct, 99))
            for m, _ in MODES:
                g = crop(rend[m], bn)
                bright = float(g.mean())
                pts[m].append((temp99, bright))
                percls[m][c].append(bright)

    print("지표 1 · 밝기 ↔ 실제온도 상관계수  (1.0 이면 밝기만 보고 온도를 알 수 있음)")
    print(f"{'렌더 방식':<22}{'상관 r':>10}{'설명력 r²':>12}")
    for m, name in MODES:
        a = np.array(pts[m])
        r = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
        print(f"{name:<22}{r:>10.3f}{r*r*100:>11.1f}%")

    print(f"\n지표 2 · 같은 부품의 사진간 밝기 편차 (0~255 중 표준편차, 낮을수록 일관)")
    classes = sorted({c for m, _ in MODES for c in percls[m]
                      if len(percls[m][c]) >= 20})
    hdr = f"{'클래스':<18}" + "".join(f"{n.split()[0]:>10}" for _m, n in MODES)
    print(hdr + f"{'n':>8}")
    tot = {m: [] for m, _ in MODES}
    for c in classes:
        row = f"{KOREAN_BY_ID[c]:<18}"
        n = 0
        for m, _ in MODES:
            v = np.array(percls[m][c]); n = len(v)
            row += f"{v.std():>10.1f}"
            tot[m].append(v.std())
        print(row + f"{n:>8}")
    row = f"{'평균':<18}"
    for m, _ in MODES:
        row += f"{np.mean(tot[m]):>10.1f}"
    print(row)

    # ---- 시각 비교 ----
    sheets.sort()
    pick = [sheets[1], sheets[len(sheets)//8], sheets[len(sheets)//2],
            sheets[-len(sheets)//8], sheets[-2]]
    CW, CH, head = 300, 225, 30
    img = Image.new("RGB", (CW*(len(MODES)+1), head + CH*len(pick)), "#0e1116")
    d = ImageDraw.Draw(img)
    for i, lab in enumerate(["실제 온도폭"] + [n for _m, n in MODES]):
        d.text((i*CW + 8, 9), lab, fill="#e8edf3")
    print(f"\n시각 비교 대상 (프레임 발열폭 dT 순)")
    for r, (dT, stem) in enumerate(pick):
        t = np.load(DATA / "temp" / f"{stem}.npy")
        amb = ambient(t, mask)
        info = Image.new("RGB", (CW, CH), "#0e1116")
        di = ImageDraw.Draw(info)
        di.text((10, 60), f"dT {dT:.1f}K", fill="#ffd479")
        di.text((10, 82), f"대기 {amb:.1f}C", fill="#9aa5b1")
        di.text((10, 100), f"최고 {t[mask].max():.1f}C", fill="#9aa5b1")
        di.text((10, 128), stem[:24], fill="#69717b")
        img.paste(info, (0, head + r*CH))
        for i, (m, _n) in enumerate(MODES):
            g = cv2.cvtColor(render(t, mask, m), cv2.COLOR_GRAY2RGB)
            img.paste(Image.fromarray(cv2.resize(g, (CW, CH), interpolation=cv2.INTER_NEAREST)),
                      ((i+1)*CW, head + r*CH))
        print(f"  dT {dT:5.1f}K  대기 {amb:5.1f}C  최고 {t[mask].max():5.1f}C  {stem}")
    p = OUT / "scale_compare.png"
    img.save(p)
    img.convert("RGB").save(OUT / "scale_compare.jpg", quality=88)
    print(f"\n-> {p}")


if __name__ == "__main__":
    main()
