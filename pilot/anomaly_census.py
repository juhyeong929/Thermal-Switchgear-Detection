"""라벨된 부품 전수에 판정 규칙을 적용해 '실제 이상이 몇 건인가'를 센다.

heat_census 는 프레임 최고온도를 봤는데, 그 값은 조명기구 반사에 오염돼 있었다
(1~171화소짜리 250°C 점). 부품 박스 안에서만 재면 그 오염이 대부분 빠진다.

  - 조명 오염 판정: 박스 안 고온부의 연결성분 면적이 작으면 제외
  - 판정: thresholds.judge (부품별 절대/상간/대기차 기준)

  python anomaly_census.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID  # noqa: E402
from thresholds import judge as judge_rule  # noqa: E402
from scale_compare import load_boxes  # noqa: E402

HERE = Path(__file__).parent
TEMPD = HERE / "data" / "temp_all"
LABD = HERE / "data" / "labels_ir"
OUT = HERE / "out"
LEVELS = ["정상", "주의", "이상", "심각"]


def box_px(shape, bn):
    h, w = shape
    cx, cy, bw, bh = bn
    x1, y1 = max(0, int((cx - bw / 2) * w)), max(0, int((cy - bh / 2) * h))
    x2, y2 = min(w, int((cx + bw / 2) * w)), min(h, int((cy + bh / 2) * h))
    return x1, y1, x2, y2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-hot-px", type=int, default=12,
                    help="박스내 고온 연결성분 최소 면적. 미만이면 조명/반사로 본다")
    args = ap.parse_args()
    mask = osd_mask() > 0

    labs = sorted(LABD.glob("*.txt"))
    rows = []
    per = collections.defaultdict(lambda: collections.Counter())
    spike_drop = collections.Counter()

    for lp in labs:
        tp = TEMPD / f"{lp.stem}.npy"
        if not tp.exists():
            continue
        t = np.load(tp)
        pan = lp.stem.split("_")[2]
        v = np.sort(t[mask])
        amb = float(v[:max(1, int(len(v) * .1))].mean())

        boxes = load_boxes(lp)
        stats = []
        for c, bn in boxes:
            x1, y1, x2, y2 = box_px(t.shape, bn)
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            sub = t[y1:y2, x1:x2]
            sm = mask[y1:y2, x1:x2]
            if not sm.any():
                continue
            vals = sub[sm]
            p99 = float(np.percentile(vals, 99))

            # 조명/반사 배제: 고온부(최고-3K 이상)의 최대 연결성분 면적
            hot = ((sub >= sub.max() - 3) & sm).astype(np.uint8)
            n, _lbl, st, _ct = cv2.connectedComponentsWithStats(hot, 8)
            area = int(st[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
            spike = area < args.min_hot_px and float(sub.max()) - p99 > 10
            if spike:
                spike_drop[c] += 1
            stats.append((c, p99, area, spike))

        peers = collections.defaultdict(list)
        for c, p99, _a, sp in stats:
            if not sp:
                peers[c].append(p99)
        for c, p99, area, sp in stats:
            same = peers[c]
            peer = float(np.median(same)) if len(same) >= 2 else None
            verdict, basis = judge_rule(KOREAN_BY_ID[c], p99, amb, peer)
            per[c][verdict] += 1
            rows.append({"stem": lp.stem, "panel": pan, "cls": KOREAN_BY_ID[c],
                         "t_p99": round(p99, 2), "amb": round(amb, 2),
                         "peer": round(peer, 2) if peer else "", "hot_px": area,
                         "spike": int(sp), "verdict": verdict, "basis": basis})

    with open(OUT / "anomaly_census.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    tot = collections.Counter(r["verdict"] for r in rows)
    print(f"라벨 프레임 {len(labs)}장 · 부품 박스 {len(rows):,}개\n")
    print("=" * 92)
    print("1) 전체 판정 분포")
    print("=" * 92)
    for lv in LEVELS:
        n = tot.get(lv, 0)
        bar = "█" * int(n / max(tot.values()) * 46)
        print(f"  {lv:<5}{n:>7}  {n/len(rows)*100:>5.1f}%  {bar}")

    print(f"\n{'='*92}")
    print("2) 클래스별 판정")
    print("=" * 92)
    print(f"{'클래스':<20}{'박스':>7}" + "".join(f"{lv:>9}" for lv in LEVELS)
          + f"{'이상+심각':>11}")
    for c in sorted(per, key=lambda c: -(per[c]['이상'] + per[c]['심각'])):
        cc = per[c]
        n = sum(cc.values())
        bad = cc['이상'] + cc['심각']
        print(f"{KOREAN_BY_ID[c]:<20}{n:>7}" + "".join(f"{cc.get(lv,0):>9}" for lv in LEVELS)
              + f"{bad/n*100:>10.1f}%")

    print(f"\n{'='*92}")
    print("3) 반별 판정")
    print("=" * 92)
    bypan = collections.defaultdict(collections.Counter)
    for r in rows:
        bypan[r["panel"]][r["verdict"]] += 1
    print(f"{'반':<8}{'박스':>7}" + "".join(f"{lv:>9}" for lv in LEVELS))
    for p in sorted(bypan, key=lambda x: int(x[1:])):
        cc = bypan[p]
        print(f"{p:<8}{sum(cc.values()):>7}" + "".join(f"{cc.get(lv,0):>9}" for lv in LEVELS))

    print(f"\n{'='*92}")
    print(f"4) 조명/반사로 배제한 박스  (고온 연결성분 < {args.min_hot_px}화소)")
    print("=" * 92)
    if spike_drop:
        for c, n in spike_drop.most_common():
            print(f"  {KOREAN_BY_ID[c]:<20}{n:>6}개")
        print(f"  {'합계':<20}{sum(spike_drop.values()):>6}개 "
              f"({sum(spike_drop.values())/len(rows)*100:.1f}%)")
    else:
        print("  없음")

    bad = [r for r in rows if r["verdict"] in ("이상", "심각")]
    if bad:
        print(f"\n{'='*92}")
        print(f"5) 이상/심각 판정 박스 (상위 20건)")
        print("=" * 92)
        bad.sort(key=lambda r: -r["t_p99"])
        print(f"{'반':<5}{'클래스':<18}{'온도':>8}{'대기':>7}{'동종':>8}{'화소':>7}"
              f"  {'판정':<5}{'근거'}")
        for r in bad[:20]:
            print(f"{r['panel']:<5}{r['cls']:<18}{r['t_p99']:>7.1f}C{r['amb']:>6.1f}C"
                  f"{str(r['peer']):>8}{r['hot_px']:>7}  {r['verdict']:<5}{r['basis']}")
    print(f"\n-> {OUT / 'anomaly_census.csv'}")


if __name__ == "__main__":
    main()
