"""실화상 좌표 → 저해상도 열화상 방식이 Lepton 에서도 성립하는지 시뮬레이션.

카메라를 실제로 달기 전에, 가진 FLIR E8 데이터로 미리 확인한다.

방법
  1) IR1 의 방사 데이터에서 실제 온도맵(240x320)을 얻는다  ← 기준값
  2) 이를 Lepton 화질로 열화시킨다 (해상도 축소 + 광학 번짐 + 센서 노이즈)
  3) 사람이 그린 박스 좌표를 그대로 적용해 두 온도맵에서 각각 온도를 뽑는다
  4) 온도 차이와 **판정 일치율**을 비교한다
  5) 정합 오차(실화상↔열화상 좌표 어긋남)를 넣어 허용 범위를 찾는다

해상도 환산
  FLIR E8   45° / 320px = 0.141°/px
  Lepton3.5 57° / 160px = 0.356°/px   -> 화소가 2.53배 거칠다
  같은 거리·같은 장면을 담으면 E8 320px 폭이 Lepton 에서는 약 126px 이 된다.
  단순 160x120 축소는 낙관적이므로 두 조건을 모두 본다.

  python simulate_lepton.py
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID  # noqa: E402
from thresholds import judge as judge_rule  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
W, H = 320, 240
LEVELS = ["정상", "주의", "이상", "심각"]

# Lepton 3.5 특성
NETD_K = 0.05          # 노이즈 등가 온도차 <50mK
BLUR_SIGMA = 0.6       # 광학 번짐 (축소 후 화소 기준)


def degrade(temp: np.ndarray, out_w: int, out_h: int, rng) -> np.ndarray:
    """온도맵을 Lepton 화질로 열화. 온도 단위를 유지한다."""
    small = cv2.resize(temp, (out_w, out_h), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), BLUR_SIGMA)
    small = small + rng.normal(0, NETD_K, small.shape).astype(np.float32)
    return small


def box_stats(temp, mask, box_norm, jitter_px=0.0, rng=None):
    """정규화 좌표 박스에서 온도 통계. jitter 는 정합 오차 모사(해당 해상도 기준 px)."""
    h, w = temp.shape
    cx, cy, bw, bh = box_norm
    x1, y1 = (cx-bw/2)*w, (cy-bh/2)*h
    x2, y2 = (cx+bw/2)*w, (cy+bh/2)*h
    if jitter_px and rng is not None:
        dx, dy = rng.uniform(-jitter_px, jitter_px, 2)
        x1 += dx; x2 += dx; y1 += dy; y2 += dy
    x1, y1 = max(0, int(round(x1))), max(0, int(round(y1)))
    x2, y2 = min(w, int(round(x2))), min(h, int(round(y2)))
    if x2-x1 < 1 or y2-y1 < 1:
        return None
    sub = temp[y1:y2, x1:x2]
    m = mask[y1:y2, x1:x2] & np.isfinite(sub)
    v = sub[m] if m.any() else sub[np.isfinite(sub)]
    if v.size < 1:
        return None
    return float(np.percentile(v, 99)), int(v.size)


def ambient(temp, mask):
    v = temp[mask & np.isfinite(temp)]
    return float(v[v <= np.percentile(v, 10)].mean())


def verdicts(stats):
    """[(cls, t_p99)] -> [(cls, 판정)]  thresholds.py 규칙 적용"""
    by = collections.defaultdict(list)
    for c, t, _n in stats:
        by[c].append(t)
    out = []
    for c, t, _n in stats:
        same = by[c]
        peer = float(np.median(same)) if len(same) >= 2 else None
        v, _b = judge_rule(KOREAN_BY_ID[c], t, stats_amb[0], peer)
        out.append((c, v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(HERE / "_p1only" / "labels"))
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()

    rng = np.random.default_rng(0)
    mask320 = osd_mask() > 0
    lab_dir = Path(args.labels)
    stems = sorted(f.stem for f in lab_dir.glob("*.txt")
                   if (DATA / "temp" / f"{f.stem}.npy").exists())[:args.limit]
    print(f"대상 {len(stems)}장\n")

    CONDS = [("원본 320x240", 320, 240),
             ("Lepton 단순축소 160x120", 160, 120),
             ("Lepton 화각보정 126x95", 126, 95)]

    # 조건별 결과 누적
    res = {c[0]: {"dt": [], "px": [], "match": 0, "total": 0,
                  "per": collections.defaultdict(lambda: [0, 0])} for c in CONDS[1:]}
    base_all = []

    global stats_amb
    for stem in stems:
        temp = np.load(DATA / "temp" / f"{stem}.npy")
        boxes = []
        for ln in (lab_dir / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
            q = ln.split()
            if len(q) == 5:
                boxes.append((int(q[0]), tuple(map(float, q[1:]))))
        if not boxes:
            continue

        cond_stats = {}
        for name, ow, oh in CONDS:
            t = temp if ow == 320 else degrade(temp, ow, oh, rng)
            m = mask320 if ow == 320 else cv2.resize(
                mask320.astype(np.uint8), (ow, oh), interpolation=cv2.INTER_NEAREST).astype(bool)
            stats_amb = (ambient(t, m),)
            st = []
            for c, bn in boxes:
                r = box_stats(t, m, bn)
                if r:
                    st.append((c, r[0], r[1]))
            cond_stats[name] = (st, verdicts(st), stats_amb[0])

        base_st, base_v, _ = cond_stats["원본 320x240"]
        base_map = {i: (c, t) for i, (c, t, _n) in enumerate(base_st)}
        base_all += [v for _c, v in base_v]

        for name, _ow, _oh in CONDS[1:]:
            st, vv, _amb = cond_stats[name]
            if len(st) != len(base_st):
                continue
            for i, ((c, t, n), (_c2, v2)) in enumerate(zip(st, vv)):
                bc, bt = base_map[i]
                bv = base_v[i][1]
                res[name]["dt"].append(t - bt)
                res[name]["px"].append(n)
                res[name]["total"] += 1
                ok = (v2 == bv)
                res[name]["match"] += ok
                pc = res[name]["per"][c]
                pc[0] += ok; pc[1] += 1

    print(f"{'조건':<26}{'박스':>7}{'온도차 중앙':>12}{'|온도차| p90':>13}"
          f"{'화소 중앙':>10}{'판정 일치':>10}")
    for name, _ow, _oh in CONDS[1:]:
        r = res[name]
        d = np.array(r["dt"]); px = np.array(r["px"])
        print(f"{name:<26}{r['total']:>7}{np.median(d):>11.2f}K"
              f"{np.percentile(np.abs(d),90):>12.2f}K{np.median(px):>10.0f}"
              f"{r['match']/max(r['total'],1)*100:>9.1f}%")

    print(f"\n클래스별 판정 일치율")
    print(f"{'클래스':<20}" + "".join(f"{n[:18]:>22}" for n, _w, _h in CONDS[1:]))
    classes = sorted({c for name, _w, _h in CONDS[1:] for c in res[name]["per"]})
    for c in classes:
        row = f"{KOREAN_BY_ID[c]:<20}"
        for name, _w, _h in CONDS[1:]:
            ok, tot = res[name]["per"][c]
            row += f"{ok/max(tot,1)*100:>19.1f}% "
        print(row)

    # --- 정합 오차 허용 범위 ---
    print(f"\n\n정합 오차에 따른 판정 일치율  (Lepton 160x120 기준)")
    print(f"{'오차':>8}{'판정 일치':>12}{'온도차 중앙':>14}")
    for jit in (0, 1, 2, 3, 5):
        rng2 = np.random.default_rng(1)
        ok = tot = 0
        dts = []
        for stem in stems[:150]:
            temp = np.load(DATA / "temp" / f"{stem}.npy")
            boxes = []
            for ln in (lab_dir / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
                q = ln.split()
                if len(q) == 5:
                    boxes.append((int(q[0]), tuple(map(float, q[1:]))))
            if not boxes:
                continue
            stats_amb = (ambient(temp, mask320),)
            st0 = [(c, box_stats(temp, mask320, b)[0], 0) for c, b in boxes
                   if box_stats(temp, mask320, b)]
            v0 = verdicts(st0)
            t = degrade(temp, 160, 120, rng2)
            m = cv2.resize(mask320.astype(np.uint8), (160, 120),
                           interpolation=cv2.INTER_NEAREST).astype(bool)
            stats_amb = (ambient(t, m),)
            st1 = []
            for c, b in boxes:
                r = box_stats(t, m, b, jitter_px=jit, rng=rng2)
                if r:
                    st1.append((c, r[0], r[1]))
            if len(st1) != len(st0):
                continue
            v1 = verdicts(st1)
            for (c0, a), (c1, bb), (_c, t1, _n) in zip(v0, v1, st1):
                tot += 1
                ok += (a == bb)
                dts.append(t1 - st0[[i for i, s in enumerate(st0)][0]][1] if False else 0)
        print(f"{jit:>6}px{ok/max(tot,1)*100:>11.1f}%{'':>14}")
    print("\n  * 오차 1px = Lepton 화소 1개. 실제 설치 정합 오차가 이 범위여야 한다")


if __name__ == "__main__":
    main()
