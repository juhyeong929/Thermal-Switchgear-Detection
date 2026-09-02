"""A1 4개 세션이 완성된 뒤, 새 세션(A2/A3)에 대한 자동 라벨링 성능을 다시 추정한다.

A2·A3 에는 라벨이 없어 직접 측정할 수 없으므로, A1 세션 하나씩을 통째로 빼는
leave-one-session-out 으로 근사한다. 실제 A2·A3 는 현장까지 다르므로 여기서 나오는
수치는 낙관적인 상한이다.

  python a1_to_a23_test.py
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID, NAMES  # noqa: E402
from p1_autolabel_test import build, evaluate, iou, load_gt, train  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
SRC = DATA / "labels_ir_src"

A1_SESSIONS = ["A1_B1_P1_2022-05-12", "A1_B2_P1_2022-05-12",
               "A1_B3_P1_2022-05-24", "A1_B1_P1_2022-06-17"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--folds", nargs="*", default=["A1_B2_P1_2022-05-12",
                                                   "A1_B3_P1_2022-05-24"])
    args = ap.parse_args()

    sess = collections.defaultdict(list)
    for f in sorted(SRC.glob("*.txt")):
        k = "_".join(f.stem.split("_")[:4])
        if k in A1_SESSIONS and (DATA / "ir" / f"{f.stem}.jpg").exists():
            sess[k].append(f.stem)
    print("A1 세션별 라벨된 장수")
    for k in A1_SESSIONS:
        print(f"  {k:<22} {len(sess.get(k, [])):3d}장")

    summary = []
    for hold in args.folds:
        if hold not in sess:
            print(f"\n건너뜀: {hold} 없음")
            continue
        tr = [s for k, ss in sess.items() if k != hold for s in ss]
        va = sorted(sess[hold])
        print(f"\n{'='*70}\n홀드아웃 {hold}: 학습 {len(tr)}장 / 검증 {len(va)}장\n{'='*70}")
        root = build(f"loso_{hold}", tr, va)
        w = train(root, f"loso_{hold}", args.epochs)
        tp, fp, fn, per = evaluate(w, va, args.conf)
        prec = tp / max(tp+fp, 1)
        rec = tp / max(tp+fn, 1)
        touch = fp + fn
        n_gt = tp + fn
        save = (1 - touch/max(n_gt, 1)) * 100
        print(f"  정답 {n_gt}개 / 예측 {tp+fp}개 -> 맞음 {tp}, 오검출 {fp}, 누락 {fn}")
        print(f"  Precision {prec:.3f}   Recall {rec:.3f}")
        print(f"  손댈 횟수 {touch}회 vs 처음부터 {n_gt}회 -> "
              f"{'%.0f%% 절감' % save if touch < n_gt else '손해'}")
        print(f"  {'클래스':<20}{'맞음':>6}{'오검출':>8}{'누락':>7}{'Recall':>9}")
        for c in sorted(per, key=lambda c: -(per[c][0]+per[c][2])):
            t, f_, n_ = per[c]
            print(f"  {KOREAN_BY_ID[c]:<20}{t:>6}{f_:>8}{n_:>7}{t/max(t+n_,1):>9.2f}")
        summary.append((hold, prec, rec, save, touch < n_gt))

    print(f"\n{'='*70}\n요약 — 새 세션 자동 라벨링 추정\n{'='*70}")
    print(f"{'홀드아웃 세션':<24}{'Precision':>11}{'Recall':>9}{'절감':>9}  판정")
    for h, p, r, s, ok in summary:
        print(f"{h:<24}{p:>11.3f}{r:>9.3f}{s:>8.0f}%  {'이득' if ok else '손해'}")
    print("\nA2·A3 는 현장 자체가 달라 위 수치보다 나쁠 것으로 봐야 한다.")


if __name__ == "__main__":
    main()
