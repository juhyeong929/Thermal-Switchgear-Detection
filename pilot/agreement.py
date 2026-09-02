"""여러 라벨러의 결과를 비교해 일치도를 측정한다 (교차검증).

이 프로젝트의 합격 기준은 IoU 가 아니라 **판정 일치율**이다. 박스 안 화소에서 온도를
집계해 등급(정상/주의/이상/심각)을 내므로, 경계가 조금 달라도 등급이 같으면 문제없고
반대로 IoU 가 높아도 박스가 발열부 경계를 물었는지에 따라 등급이 갈릴 수 있다.

  python agreement.py annot/A annot/B annot/C annot/D annot/E

권장 합격선
  판정 일치율 >= 90%   (주 기준)
  matched IoU 중앙값 >= 0.70
  박스 개수 차이 <= 10%
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from analyze import box_temperature, judge  # noqa: E402
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID, NAMES  # noqa: E402
from transfer import label_files  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"
W, H = 320, 240
IOU_MATCH = 0.5


def load_dir(d: Path) -> dict[str, list]:
    out = {}
    for f in label_files(d):
        boxes = []
        for ln in f.read_text(encoding="utf-8").splitlines():
            p = ln.split()
            if len(p) < 5:
                continue
            c = int(p[0])
            cx, cy, w, h = map(float, p[1:5])
            boxes.append((c, (cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H))
        out[f.stem] = boxes
    return out


def iou(a, b) -> float:
    x1, y1 = max(a[1], b[1]), max(a[2], b[2])
    x2, y2 = min(a[3], b[3]), min(a[4], b[4])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2-x1)*(y2-y1)
    ua = (a[3]-a[1])*(a[4]-a[2]) + (b[3]-b[1])*(b[4]-b[2]) - inter
    return inter/max(ua, 1e-9)


def match(ref, hyp):
    """클래스가 같고 IoU >= 0.5 인 쌍을 그리디로 맞춘다."""
    pairs, used = [], set()
    for i, r in enumerate(ref):
        best, bj = 0.0, None
        for j, h in enumerate(hyp):
            if j in used or h[0] != r[0]:
                continue
            v = iou(r, h)
            if v > best:
                best, bj = v, j
        if bj is not None and best >= IOU_MATCH:
            used.add(bj)
            pairs.append((i, bj, best))
    return pairs, used


def verdicts(stem: str, boxes, temp_cache) -> dict:
    """라벨 한 세트에서 이 사진의 최종 판정을 계산한다."""
    if stem not in temp_cache:
        p = DATA / "temp" / f"{stem}.npy"
        temp_cache[stem] = np.load(p) if p.exists() else None
    temp = temp_cache[stem]
    if temp is None or not boxes:
        return {"verdict": "탐지없음", "parts": {}}
    mask = temp_cache["_mask"]
    valid = temp[mask & np.isfinite(temp)]
    ref = float(np.median(valid))
    stats = []
    for c, *bx in boxes:
        s = box_temperature(temp, mask, bx)
        if s:
            stats.append((c, s["t_p99"]))
    if not stats:
        return {"verdict": "탐지없음", "parts": {}}
    by_cls = collections.defaultdict(list)
    for c, t in stats:
        by_cls[c].append(t)
    worst, parts = "정상", {}
    order = ["정상", "주의", "이상", "심각"]
    for c, t in stats:
        same = by_cls[c]
        dt_phase = t - float(np.median(same)) if len(same) >= 2 else None
        v, _ = judge(dt_phase, t - ref)
        parts[NAMES[c]] = max(parts.get(NAMES[c], "정상"), v, key=order.index)
        if order.index(v) > order.index(worst):
            worst = v
    return {"verdict": worst, "parts": parts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", help="라벨러별 라벨 디렉터리")
    ap.add_argument("--names", default=None, help="쉼표로 구분한 라벨러 이름")
    args = ap.parse_args()

    dirs = [Path(d) for d in args.dirs]
    for d in dirs:
        if not d.is_dir():
            raise SystemExit(f"디렉터리가 없습니다: {d}")
    names = args.names.split(",") if args.names else [d.name for d in dirs]
    if len(names) != len(dirs):
        raise SystemExit("이름 개수와 디렉터리 개수가 다릅니다")

    sets = {n: load_dir(d) for n, d in zip(names, dirs)}
    common = set.intersection(*(set(v) for v in sets.values()))
    if not common:
        raise SystemExit("모든 라벨러가 공통으로 작업한 사진이 없습니다")
    print(f"라벨러 {len(names)}명: {', '.join(names)}")
    print(f"공통 사진 {len(common)}장\n")

    # --- 1. 박스 개수 ---
    print("1. 작업량")
    print(f"   {'라벨러':<10}{'박스':>7}{'장당':>7}")
    counts = {}
    for n in names:
        tot = sum(len(sets[n][s]) for s in common)
        counts[n] = tot
        print(f"   {n:<10}{tot:>7}{tot/len(common):>7.1f}")
    lo, hi = min(counts.values()), max(counts.values())
    print(f"   최대-최소 차이 {hi-lo}개 ({(hi-lo)/max(hi,1)*100:.0f}%)"
          f"{'  <- 10% 초과, 기준 불일치 의심' if (hi-lo)/max(hi,1) > 0.10 else '  OK'}")

    # --- 2. 쌍별 일치도 ---
    print("\n2. 쌍별 일치도 (클래스 동일 + IoU >= 0.5 를 일치로 봄)")
    print(f"   {'쌍':<12}{'일치':>6}{'A만':>6}{'B만':>6}{'F1':>7}{'IoU중앙':>9}")
    ious_all = []
    for a, b in itertools.combinations(names, 2):
        m = only_a = only_b = 0
        ious = []
        for s in common:
            pairs, used = match(sets[a][s], sets[b][s])
            m += len(pairs)
            only_a += len(sets[a][s]) - len(pairs)
            only_b += len(sets[b][s]) - len(used)
            ious += [p[2] for p in pairs]
        f1 = 2*m/max(2*m + only_a + only_b, 1)
        med = float(np.median(ious)) if ious else 0.0
        ious_all += ious
        flag = "" if (f1 >= 0.8 and med >= 0.70) else "  <-"
        print(f"   {a+'-'+b:<12}{m:>6}{only_a:>6}{only_b:>6}{f1:>7.3f}{med:>9.3f}{flag}")
    if ious_all:
        print(f"   전체 matched IoU 중앙값 {np.median(ious_all):.3f}"
              f"{'  OK' if np.median(ious_all) >= 0.70 else '  <- 0.70 미만, 경계 관습 합의 필요'}")

    # --- 3. 클래스 혼동 ---
    print("\n3. 클래스 불일치 (같은 자리를 다른 클래스로 본 경우, IoU >= 0.5)")
    conf = collections.Counter()
    for a, b in itertools.combinations(names, 2):
        for s in common:
            for r in sets[a][s]:
                for h in sets[b][s]:
                    if r[0] != h[0] and iou(r, h) >= IOU_MATCH:
                        conf[tuple(sorted((KOREAN_BY_ID[r[0]], KOREAN_BY_ID[h[0]])))] += 1
    if conf:
        for (x, y), n in conf.most_common(10):
            print(f"   {x} <-> {y}: {n}건")
    else:
        print("   없음")

    # --- 4. 판정 일치율 (주 기준) ---
    print("\n4. 판정 일치율 — 주 기준")
    cache = {"_mask": osd_mask() > 0}
    per = {n: {s: verdicts(s, sets[n][s], cache) for s in common} for n in names}
    same = sum(1 for s in common if len({per[n][s]["verdict"] for n in names}) == 1)
    rate = same/len(common)
    print(f"   전원 동일 등급 {same}/{len(common)}장 = {rate:.1%}"
          f"{'  OK' if rate >= 0.90 else '  <- 90% 미만'}")
    print(f"\n   {'쌍':<12}{'일치율':>8}")
    for a, b in itertools.combinations(names, 2):
        n_ok = sum(1 for s in common if per[a][s]["verdict"] == per[b][s]["verdict"])
        print(f"   {a+'-'+b:<12}{n_ok/len(common):>8.1%}")

    dis = [s for s in common if len({per[n][s]["verdict"] for n in names}) > 1]
    if dis:
        print(f"\n   등급이 갈린 사진 {len(dis)}장 (조정 필요, 상위 10장)")
        for s in sorted(dis)[:10]:
            v = "  ".join(f"{n}:{per[n][s]['verdict']}" for n in names)
            print(f"     {s}  {v}")

    OUT.mkdir(exist_ok=True)
    (OUT / "agreement.json").write_text(json.dumps(
        {"names": names, "n_common": len(common), "verdict_agreement": rate,
         "iou_median": float(np.median(ious_all)) if ious_all else None,
         "box_counts": counts, "disagreed": sorted(dis)},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {OUT/'agreement.json'}")
    print("\n등급이 갈린 사진은 다섯이 같이 보고 규칙으로 정한 뒤, 그 규칙을 이미 작업한")
    print("분량에도 소급 적용해야 한다. 규칙 없이 개별 조정만 하면 다시 갈린다.")


if __name__ == "__main__":
    main()
