"""3-가공 IR3 jpg 를 1-수집 Lepton TIFF 로 역매칭해 절대온도를 되살린다.

IR3 는 컬러 JPEG 이라 온도가 없다고 알려졌으나, 원본인 Lepton TIFF(centi-Kelvin
16비트)가 1-수집 에 남아 있다. 두 파일을 화소 상관으로 대응시키면 IR3 에 절대온도를
붙일 수 있다.

검증 근거 — 표본 3장 전수 탐색에서 NCC 0.993~0.998 로 대응 확인 (2026-08-20).

방법
  1) TIFF 를 80x60 저해상도 서술자로 만들어 뱅크 구성 (날짜별, 디스크 캐시)
  2) IR3 는 아이언보우 LUT 역변환으로 온도 순서를 복원한 뒤 같은 서술자로 변환
     (단순 그레이 변환은 아이언보우에서 순위상관 0.83 까지 떨어짐 — 실측)
  3) 일괄 행렬곱으로 NCC 최댓값 탐색
  4) NCC 임계 이상만 채택하고 매핑을 CSV 로 남긴다

원본은 읽기만 한다.

  python match_ir3_lepton.py --date 2022-07-11 --limit 300     # 표본 검증
  python match_ir3_lepton.py --date 2022-07-11                 # 전량
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out" / "ir3_match"
CACHE = HERE / "cache"
DW, DH = 80, 60                 # 서술자 해상도
NCC_ACCEPT = 0.95

IRONBOW = [(0,0,0),(20,11,52),(65,10,104),(120,14,108),(171,35,85),
           (211,66,53),(239,110,25),(253,163,7),(255,211,55),(255,255,255)]


def build_rgb_lut(bins=32):
    """RGB -> 팔레트 인덱스 조회표. cKDTree 보다 훨씬 빠르다."""
    a = np.array(IRONBOW, float)
    t = np.linspace(0, len(a)-1, 256)
    pal = np.stack([np.interp(t, np.arange(len(a)), a[:, c]) for c in range(3)], 1)
    grid = (np.arange(bins) + 0.5) * (256.0 / bins)
    R, G, B = np.meshgrid(grid, grid, grid, indexing="ij")
    q = np.stack([R.ravel(), G.ravel(), B.ravel()], 1)
    d = ((q[:, None, :] - pal[None, :, :]) ** 2).sum(2)
    return d.argmin(1).astype(np.uint8).reshape(bins, bins, bins), bins


_LUT, _BINS = build_rgb_lut()


def ir3_descriptor(path: Path) -> np.ndarray:
    im = Image.open(path).convert("RGB").resize((DW, DH), Image.BOX)
    a = np.asarray(im)
    idx = (a.astype(np.int32) * _BINS // 256).clip(0, _BINS-1)
    v = _LUT[idx[:, :, 0], idx[:, :, 1], idx[:, :, 2]].astype(np.float32)
    return _z(v.ravel())


def tiff_descriptor(path: Path) -> np.ndarray:
    a = np.asarray(Image.open(path).resize((DW, DH), Image.BOX)).astype(np.float32)
    return _z(a.ravel())


def _z(v):
    return (v - v.mean()) / (v.std() + 1e-6)


def load_bank(date: str):
    CACHE.mkdir(exist_ok=True)
    npy = CACHE / f"lepton_{date}_{DW}x{DH}.npy"
    lst = CACHE / f"lepton_{date}_paths.txt"
    tifs = sorted(p for p in (ROOT / "1-수집").rglob("*.tiff") if p.name[:10] == date)
    if npy.exists() and lst.exists():
        paths = lst.read_text(encoding="utf-8").splitlines()
        if len(paths) == len(tifs):
            print(f"  캐시 사용: {npy.name}")
            return np.load(npy), [Path(p) for p in paths]
    print(f"  TIFF {len(tifs)}장 서술자 생성 중...")
    t0 = time.time()
    M = np.empty((len(tifs), DW*DH), np.float32)
    for i, p in enumerate(tifs):
        M[i] = tiff_descriptor(p)
        if (i+1) % 5000 == 0:
            print(f"    {i+1}/{len(tifs)}  {time.time()-t0:.0f}s", end="\r")
    np.save(npy, M)
    lst.write_text("\n".join(str(p) for p in tifs), encoding="utf-8")
    print(f"\n  완료 {time.time()-t0:.0f}s -> 캐시 저장")
    return M, tifs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2022-07-11")
    ap.add_argument("--limit", type=int, default=0, help="IR3 표본 수 (0=전량)")
    ap.add_argument("--batch", type=int, default=512)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"날짜 {args.date}")
    M, tifs = load_bank(args.date)

    ir3 = sorted(p for p in (ROOT / "3-가공").rglob(f"*_{args.date}_IR3_*.jpg")
                 if not p.name.startswith("._"))
    if args.limit:
        step = max(1, len(ir3) // args.limit)
        ir3 = ir3[::step][:args.limit]
    print(f"  IR3 {len(ir3)}장 매칭 시작")

    rows = []
    t0 = time.time()
    for s in range(0, len(ir3), args.batch):
        chunk = ir3[s:s+args.batch]
        Q = np.stack([ir3_descriptor(p) for p in chunk])
        sims = (Q @ M.T) / Q.shape[1]
        best = sims.argmax(1)
        top = sims[np.arange(len(chunk)), best]
        sims[np.arange(len(chunk)), best] = -2
        second = sims.max(1)
        for p, bi, tv, sv in zip(chunk, best, top, second):
            rows.append({"ir3": str(p.relative_to(ROOT)),
                         "tiff": str(tifs[bi].relative_to(ROOT)),
                         "ncc": round(float(tv), 4),
                         "ncc2": round(float(sv), 4),
                         "accept": int(tv >= NCC_ACCEPT)})
        print(f"    {s+len(chunk)}/{len(ir3)}  {time.time()-t0:.0f}s", end="\r")
    print()

    p = OUT / f"match_{args.date}.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["ir3", "tiff", "ncc", "ncc2", "accept"])
        w.writeheader()
        w.writerows(rows)

    ncc = np.array([r["ncc"] for r in rows])
    acc = int(sum(r["accept"] for r in rows))
    el = time.time() - t0
    print(f"\n매칭 {len(rows)}장 · 소요 {el:.0f}s ({el/max(len(rows),1)*1000:.0f}ms/장)")
    print(f"  NCC  중앙 {np.median(ncc):.3f} · p10 {np.percentile(ncc,10):.3f} · 최소 {ncc.min():.3f}")
    print(f"  채택(NCC>={NCC_ACCEPT})  {acc}/{len(rows)} ({acc/len(rows)*100:.1f}%)")
    for th in (0.99, 0.98, 0.95, 0.90):
        print(f"    NCC >= {th}: {int((ncc>=th).sum())}장 ({(ncc>=th).mean()*100:.1f}%)")
    full = len(list((ROOT/"3-가공").rglob(f"*_{args.date}_IR3_*.jpg")))
    print(f"\n  이 날짜 IR3 전량 {full}장 기준 예상 소요 "
          f"{el/max(len(rows),1)*full/60:.0f}분")
    print(f"-> {p}")


if __name__ == "__main__":
    main()
