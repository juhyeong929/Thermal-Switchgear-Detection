"""라벨 없이 도는 이상 발열 탐지 (기준선).

부품 라벨이 없어도 온도맵만으로 여기까지는 지금 당장 된다. 이 결과가 YOLO 단계의
비교 기준선이 되고, "탐지 모델이 실제로 무엇을 더 해주는가"를 정량적으로 보여준다.

판정은 NETA/KEPCO 계열 관행을 따라 장면 기준온도 대비 상승폭(dT)으로 한다.
  dT <  5 K   정상
  dT  5~15 K  주의 관찰
  dT 15~40 K  이상, 조치 권고
  dT >= 40 K  심각, 즉시 조치
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"

T_RANGE_MAX = 250.0        # FLIR E8 측정 상한. 초과분은 외삽이므로 측정값 아님
MIN_BLOB_PX = 12           # 노이즈 제거 (320x240 기준)
LEVELS = [(40, "심각"), (15, "이상"), (5, "주의"), (-1e9, "정상")]


def verdict(dt: float) -> str:
    for thr, name in LEVELS:
        if dt >= thr:
            return name
    return "정상"


def _label_blobs(binary: np.ndarray) -> tuple[np.ndarray, int]:
    """4-이웃 연결요소 라벨링 (scipy 없이 union-find)."""
    h, w = binary.shape
    lab = np.zeros((h, w), np.int32)
    parent = [0]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    nxt = 1
    for y in range(h):
        for x in range(w):
            if not binary[y, x]:
                continue
            up = lab[y - 1, x] if y else 0
            left = lab[y, x - 1] if x else 0
            if up and left:
                lab[y, x] = min(up, left)
                union(up, left)
            elif up or left:
                lab[y, x] = up or left
            else:
                lab[y, x] = nxt
                parent.append(nxt)
                nxt += 1
    if nxt == 1:
        return lab, 0
    remap, count = {}, 0
    for i in range(1, nxt):
        r = find(i)
        if r not in remap:
            count += 1
            remap[r] = count
    out = np.zeros_like(lab)
    nz = lab > 0
    out[nz] = [remap[find(v)] for v in lab[nz]]
    return out, count


def analyze_frame(temp: np.ndarray, mask: np.ndarray, dt_thresh=5.0):
    valid = mask & np.isfinite(temp)
    t = temp[valid]
    ref = float(np.median(t))                       # 장면 기준온도 = 배경 대표값
    hot = valid & (temp >= ref + dt_thresh)
    lab, n = _label_blobs(hot)

    blobs = []
    for i in range(1, n + 1):
        sel = lab == i
        px = int(sel.sum())
        if px < MIN_BLOB_PX:
            continue
        ys, xs = np.nonzero(sel)
        vals = temp[sel]
        peak = float(vals.max())
        blobs.append({
            "x1": int(xs.min()), "y1": int(ys.min()),
            "x2": int(xs.max()) + 1, "y2": int(ys.max()) + 1,
            "px": px, "t_peak": round(peak, 1), "t_mean": round(float(vals.mean()), 1),
            "dT": round(peak - ref, 1), "verdict": verdict(peak - ref),
            "over_range": bool(peak > T_RANGE_MAX),
        })
    blobs.sort(key=lambda b: -b["dT"])
    return ref, blobs


def main(dt_thresh=5.0, top=15):
    OUT.mkdir(exist_ok=True)
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    mask = osd_mask() > 0

    rows = []
    for rec in index:
        temp = np.load(DATA / "temp" / f"{rec['stem']}.npy")
        ref, blobs = analyze_frame(temp, mask, dt_thresh)
        worst = blobs[0] if blobs else None
        rows.append({
            "stem": rec["stem"], "panel": rec["panel"], "date": rec["date"],
            "t_ref": round(ref, 1),
            "n_hotspots": len(blobs),
            "t_peak": worst["t_peak"] if worst else round(ref, 1),
            "dT": worst["dT"] if worst else 0.0,
            "verdict": worst["verdict"] if worst else "정상",
            "over_range": worst["over_range"] if worst else False,
            "blobs": blobs,
        })

    with open(OUT / "hotspots.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in rows[0] if k != "blobs"])
        w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k != "blobs"})
    (OUT / "hotspots.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"100쌍 라벨 없는 이상 발열 판정 (기준선)  임계 dT >= {dt_thresh} K\n")
    order = {"심각": 0, "이상": 1, "주의": 2, "정상": 3}
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for v in sorted(counts, key=lambda v: order[v]):
        print(f"  {v:<4} {counts[v]:3d}장")
    n_over = sum(1 for r in rows if r["over_range"])
    print(f"\n측정범위 초과(>{T_RANGE_MAX:.0f}도) 포함: {n_over}장 "
          f"- 램프/히터 등 설비 외 발열체 가능성, 온도값 신뢰 불가")

    print(f"\n{'':2}{'파일':<44}{'반':<16}{'기준':>6}{'피크':>8}{'dT':>7}  판정")
    for r in sorted(rows, key=lambda r: -r["dT"])[:top]:
        flag = " *범위초과" if r["over_range"] else ""
        print(f"  {r['stem']:<44}{r['panel']:<16}{r['t_ref']:6.1f}{r['t_peak']:8.1f}"
              f"{r['dT']:7.1f}  {r['verdict']}{flag}")

    print("\n반별 이상+심각 비율")
    for panel in sorted({r["panel"] for r in rows}):
        sub = [r for r in rows if r["panel"] == panel]
        bad = sum(1 for r in sub if r["verdict"] in ("이상", "심각"))
        print(f"  {panel:<16} {bad:2d}/{len(sub):2d}")
    print(f"\n-> {OUT/'hotspots.csv'}")
    print("주의: 이 단계는 '뜨거운 영역'만 찾는다. 그것이 설비인지 조명·히터인지는 "
          "구분하지 못한다. 그 구분이 YOLO 부품 탐지 단계의 역할이다.")


if __name__ == "__main__":
    main()
