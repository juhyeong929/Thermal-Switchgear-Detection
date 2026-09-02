"""반 x 프레임 전수 발열 통계.

묻는 것: 이 데이터셋은 '객체탐지 문제'인가, '이상탐지 데이터 부족 문제'인가.

ΔT 정의를 셋 다 낸다. 앞선 조사에서 미지근한 반은 대기추정(최저10% 평균)이
장면중앙과 겹쳐 무너지는 것을 확인했기 때문이다.
  dT_amb = Tmax - 대기추정(최저10% 평균)     analyze.py 와 동일
  dT_med = Tmax - 장면중앙                  대기추정이 못 미더울 때
  Tmax   = 절대 최고온도                     기준 없는 값

출력
  1) 반별 요약 (프레임수 / dT 분위수 / 임계초과 / 최대)
  2) 임계 초과 프레임의 반별 분포
  3) 객체별 Tmax (사람 라벨이 있는 프레임만)
  4) 시간적 지속성 (연속 프레임에서 발열이 이어지는가)
  5) out/heat_census.csv  프레임 전수

  python heat_census.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID  # noqa: E402
from scale_compare import load_boxes, crop  # noqa: E402

HERE = Path(__file__).parent
TEMPD = HERE / "data" / "temp_all"
LABD = HERE / "data" / "labels_ir"
OUT = HERE / "out"
SKIP = {"P11", "P12", "P13"}
PNAME = {"P1": "TR반", "P2": "LBS&LA반", "P3": "MOF반", "P4": "MOF&PT반",
         "P5": "PF&PT반", "P6": "VCB반", "P7": "VCB&CT반", "P8": "ACB반",
         "P9": "MCCB반", "P10": "ACB&MCCB반"}
THS = (5, 10, 20, 40)


def parse(stem):
    """A1_B2_P1_2022-05-12_IR1_00068 -> (session, panel, date, frame_no)"""
    q = stem.split("_")
    fn = re.sub(r"\D", "", q[-1])
    return "_".join(q[:4]), q[2], q[3], int(fn) if fn else -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hot", type=float, default=5.0, help="이상 후보 임계 K")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mask = osd_mask() > 0

    files = sorted(p for p in TEMPD.glob("*.npy") if p.stem.split("_")[2] not in SKIP)
    rows = []
    percls = collections.defaultdict(list)      # cls -> [Tmax]
    percls_pan = collections.defaultdict(set)   # cls -> {panel}
    hot_cls = collections.Counter()             # 임계 초과 프레임에 등장한 클래스

    for f in files:
        t = np.load(f)
        # 조명기구/반사는 1~15화소짜리 초고온 점으로 나타난다. 5x5 중앙값 필터로
        # 그런 소면적 점을 제거한 뒤 최고온도를 잰다. 실제 부품 발열은 면적이 있어 살아남는다.
        tmed = cv2.medianBlur(t.astype(np.float32), 5)
        tm = t[mask]
        tmr = tmed[mask]
        v = np.sort(tm)
        amb = float(v[:max(1, int(len(v) * .1))].mean())
        med = float(np.median(tm))
        tmax = float(tmr.max())          # 잡음 제거 후 최고온도
        tmax_raw = float(v[-1])
        p99 = float(np.percentile(tm, 99))
        sess, pan, date, fno = parse(f.stem)
        r = {"stem": f.stem, "panel": pan, "session": sess, "date": date, "frame": fno,
             "amb": round(amb, 2), "median": round(med, 2), "mean": round(float(tm.mean()), 2),
             "p95": round(float(np.percentile(tm, 95)), 2), "p99": round(p99, 2),
             "tmax": round(tmax, 2), "tmax_raw": round(tmax_raw, 2),
             "spike": round(tmax_raw - tmax, 2),
             "dT_amb": round(tmax - amb, 2), "dT_med": round(tmax - med, 2)}

        lp = LABD / f"{f.stem}.txt"
        r["labeled"] = int(lp.exists())
        if lp.exists():
            for c, bn in load_boxes(lp):
                ct = crop(tmed, bn)
                if ct is None or ct.size < 4:
                    continue
                cmax = float(np.percentile(ct, 99))
                percls[c].append(cmax)
                percls_pan[c].add(pan)
                if tmax - amb >= args.hot:
                    hot_cls[c] += 1
        rows.append(r)

    with open(OUT / "heat_census.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by = collections.defaultdict(list)
    for r in rows:
        by[r["panel"]].append(r)
    pans = sorted(by, key=lambda x: int(x[1:]))

    def q(a, p):
        return float(np.percentile(a, p))

    print(f"온도맵 {len(rows):,}장 · 반 {len(pans)}개\n")
    print("=" * 104)
    print("1) 반별 발열폭 dT_amb = 최고온도 - 대기추정(최저10% 평균)")
    print("=" * 104)
    print(f"{'반':<14}{'프레임':>7}{'중앙':>8}{'p90':>8}{'p95':>8}{'p99':>8}"
          f"{'최대':>9}{'최고온도':>10}")
    for p in pans:
        a = np.array([r["dT_amb"] for r in by[p]])
        tx = max(r["tmax"] for r in by[p])
        print(f"{p+' '+PNAME.get(p,''):<14}{len(a):>7}{np.median(a):>7.1f}K{q(a,90):>7.1f}K"
              f"{q(a,95):>7.1f}K{q(a,99):>7.1f}K{a.max():>8.1f}K{tx:>9.1f}C")
    a = np.array([r["dT_amb"] for r in rows])
    print(f"{'전체':<14}{len(a):>7}{np.median(a):>7.1f}K{q(a,90):>7.1f}K"
          f"{q(a,95):>7.1f}K{q(a,99):>7.1f}K{a.max():>8.1f}K"
          f"{max(r['tmax'] for r in rows):>9.1f}C")

    print(f"\n{'='*104}")
    print("   참고 · 같은 표를 dT_med = 최고온도 - 장면중앙 으로 다시 계산")
    print("=" * 104)
    print(f"{'반':<14}{'중앙':>8}{'p90':>8}{'p95':>8}{'p99':>8}{'최대':>9}")
    for p in pans:
        a = np.array([r["dT_med"] for r in by[p]])
        print(f"{p+' '+PNAME.get(p,''):<14}{np.median(a):>7.1f}K{q(a,90):>7.1f}K"
              f"{q(a,95):>7.1f}K{q(a,99):>7.1f}K{a.max():>8.1f}K")

    print(f"\n{'='*104}")
    print("2) 임계 초과 프레임 수  (dT_amb 기준)")
    print("=" * 104)
    hdr = f"{'반':<14}{'프레임':>7}" + "".join(f"{'≥'+str(t)+'K':>11}" for t in THS)
    print(hdr)
    for p in pans:
        a = np.array([r["dT_amb"] for r in by[p]])
        row = f"{p+' '+PNAME.get(p,''):<14}{len(a):>7}"
        for t in THS:
            n = int((a >= t).sum())
            row += f"{n:>6} {n/len(a)*100:>3.0f}%"
        print(row)
    row = f"{'전체':<14}{len(rows):>7}"
    a = np.array([r["dT_amb"] for r in rows])
    for t in THS:
        n = int((a >= t).sum())
        row += f"{n:>6} {n/len(a)*100:>3.0f}%"
    print(row)

    print(f"\n{'='*104}")
    print(f"3) 객체별 최고온도  (사람 라벨 프레임만 · 박스내 p99)")
    print("=" * 104)
    lab_n = sum(r["labeled"] for r in rows)
    print(f"   라벨 있는 프레임 {lab_n}/{len(rows)} ({lab_n/len(rows)*100:.0f}%)\n")
    print(f"{'클래스':<20}{'박스':>7}{'중앙':>8}{'p90':>8}{'p99':>8}{'최대':>9}"
          f"{'≥60C':>8}  등장 반")
    for c in sorted(percls, key=lambda c: -np.percentile(percls[c], 99)):
        v = np.array(percls[c])
        if len(v) < 5:
            continue
        pans_s = ",".join(sorted(percls_pan[c], key=lambda x: int(x[1:])))
        print(f"{KOREAN_BY_ID[c]:<20}{len(v):>7}{np.median(v):>7.1f}C{q(v,90):>7.1f}C"
              f"{q(v,99):>7.1f}C{v.max():>8.1f}C{int((v>=60).sum()):>8}  {pans_s}")

    if hot_cls:
        print(f"\n   dT_amb ≥ {args.hot:.0f}K 프레임에 등장한 클래스")
        for c, n in hot_cls.most_common():
            print(f"     {KOREAN_BY_ID[c]:<20}{n:>6}회")

    print(f"\n{'='*104}")
    print(f"4) 시간적 지속성  (촬영 세션 내 연속 프레임에서 dT_amb ≥ {args.hot:.0f}K 가 이어지는가)")
    print("=" * 104)
    bysess = collections.defaultdict(list)
    for r in rows:
        bysess[r["session"]].append(r)
    runs = []
    single = 0
    for s, rs in bysess.items():
        rs.sort(key=lambda r: r["frame"])
        cur = 0
        for r in rs:
            if r["dT_amb"] >= args.hot:
                cur += 1
            elif cur:
                runs.append(cur); single += (cur == 1); cur = 0
        if cur:
            runs.append(cur); single += (cur == 1)
    if runs:
        rr = np.array(runs)
        print(f"   세션 {len(bysess)}개 · 발열 구간 {len(rr)}개")
        print(f"   구간 길이  중앙 {np.median(rr):.0f}프레임 · 평균 {rr.mean():.1f} · 최대 {rr.max()}")
        print(f"   1프레임짜리 단발 구간 {single}개 ({single/len(rr)*100:.0f}%)")
        print(f"   -> 단발 비율이 높으면 '지속 발열'이 아니라 촬영 각도/반사일 가능성")
    else:
        print("   해당 없음")
    print(f"\n-> {OUT / 'heat_census.csv'}")


if __name__ == "__main__":
    main()
