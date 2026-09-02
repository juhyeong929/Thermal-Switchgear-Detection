"""클래스별 정상 온도 프로파일을 만든다.

정상 설비만 찍힌 데이터라도 '이 부품은 보통 몇 도이고, 상(相) 간 편차는 얼마인가'는
뽑을 수 있다. 이것이 판정 임계값의 근거가 된다. NETA 계열의 관용 임계(5/15/40 K)가
이 설비·이 카메라에서 실제로 맞는지 확인하는 용도이기도 하다.

  python profile_class.py                    전체
  python profile_class.py --panel P3-MOF반    특정 반만
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from analyze import box_temperature  # noqa: E402
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID  # noqa: E402
from transfer import label_files  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"
W, H = 320, 240


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=None)
    ap.add_argument("--labels", default=str(DATA / "labels_ir"))
    args = ap.parse_args()

    index = {r["stem"]: r for r in json.loads((DATA / "index.json").read_text(encoding="utf-8"))}
    mask = osd_mask() > 0

    per_cls = collections.defaultdict(list)     # 절대온도
    per_cls_dt_amb = collections.defaultdict(list)
    phase_spread = collections.defaultdict(list)   # 한 프레임 내 동종 부품 최대-최소
    n_img = 0

    for f in label_files(Path(args.labels)):
        rec = index.get(f.stem)
        if not rec or (args.panel and rec["panel"] != args.panel):
            continue
        tp = DATA / "temp" / f"{f.stem}.npy"
        if not tp.exists():
            continue
        temp = np.load(tp)
        ref = float(np.median(temp[mask & np.isfinite(temp)]))
        n_img += 1
        frame = collections.defaultdict(list)
        for ln in f.read_text(encoding="utf-8").splitlines():
            p = ln.split()
            if len(p) < 5:
                continue
            c = int(p[0])
            cx, cy, w, h = map(float, p[1:5])
            st = box_temperature(temp, mask, [(cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H])
            if not st:
                continue
            per_cls[c].append(st["t_p99"])
            per_cls_dt_amb[c].append(st["t_p99"] - ref)
            frame[c].append(st["t_p99"])
        for c, vals in frame.items():
            if len(vals) >= 2:
                phase_spread[c].append(max(vals) - min(vals))

    if not per_cls:
        raise SystemExit("해당 조건의 라벨이 없습니다")

    title = f"[{args.panel}] " if args.panel else "[전체] "
    print(f"{title}{n_img}장 기준 클래스별 온도 프로파일\n")
    print(f"{'클래스':<20}{'박스':>5}{'절대온도 중앙':>13}{'p95':>7}{'최대':>7}"
          f"{'주변대비 중앙':>13}{'p95':>7}")
    rows = []
    for c in sorted(per_cls, key=lambda c: -len(per_cls[c])):
        t = np.array(per_cls[c])
        d = np.array(per_cls_dt_amb[c])
        print(f"{KOREAN_BY_ID[c]:<20}{len(t):>5}{np.median(t):>12.1f}C{np.percentile(t,95):>7.1f}"
              f"{t.max():>7.1f}{np.median(d):>12.1f}K{np.percentile(d,95):>7.1f}")
        rows.append({"class": KOREAN_BY_ID[c], "n": len(t),
                     "t_median": round(float(np.median(t)), 2),
                     "t_p95": round(float(np.percentile(t, 95)), 2),
                     "t_max": round(float(t.max()), 2),
                     "dT_amb_median": round(float(np.median(d)), 2),
                     "dT_amb_p95": round(float(np.percentile(d, 95)), 2)})

    print(f"\n상(相) 간 편차 — 한 프레임 안 동종 부품의 최대-최소")
    print(f"{'클래스':<20}{'프레임':>7}{'중앙':>8}{'p90':>8}{'p99':>8}{'최대':>8}"
          f"{'  5K 초과':>10}{'15K 초과':>10}")
    for c in sorted(phase_spread, key=lambda c: -len(phase_spread[c])):
        s = np.array(phase_spread[c])
        over5 = int((s > 5).sum())
        over15 = int((s > 15).sum())
        print(f"{KOREAN_BY_ID[c]:<20}{len(s):>7}{np.median(s):>7.1f}K{np.percentile(s,90):>7.1f}"
              f"{np.percentile(s,99):>8.1f}{s.max():>8.1f}"
              f"{over5:>8}건{over15:>9}건")
        for r in rows:
            if r["class"] == KOREAN_BY_ID[c]:
                r.update(phase_frames=len(s),
                         phase_median=round(float(np.median(s)), 2),
                         phase_p90=round(float(np.percentile(s, 90)), 2),
                         phase_max=round(float(s.max()), 2))

    OUT.mkdir(exist_ok=True)
    tag = f"_{args.panel}" if args.panel else ""
    p = OUT / f"class_profile{tag}.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        keys = sorted({k for r in rows for k in r})
        wr = csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        wr.writerows(rows)
    print(f"\n-> {p}")
    print("\n상 간 편차의 p90 이 판정 임계(5K)보다 크면, 그 부품에는 관용 임계가 맞지 않는다.")
    print("정상 설비에서 나온 편차이므로 이 분포가 곧 '정상 범위'다.")


if __name__ == "__main__":
    main()
