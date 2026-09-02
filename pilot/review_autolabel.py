"""자동 라벨링 결과를 사람이 검수하고, 그 차이로 자동화 정확도를 측정한다.

sample_autolabel/<IR2|IR3>/labels 의 예측을 review/ 로 복사해 사람이 고치게 하고,
고친 결과(정답)와 원래 예측을 비교해 precision/recall 을 낸다.

  python review_autolabel.py prepare      검수용 사본 생성 + 실행 명령 안내
  python review_autolabel.py score        검수 완료 후 자동화 정확도 산출

원본 예측(labels/)은 보존한다. 사람은 review/ 만 고친다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID, NAMES  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE / "sample_autolabel"
KINDS = ("IR2", "IR3")
W, H = 320, 240
IOU_T = 0.5


def load(f: Path):
    out = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        p = ln.split()
        if len(p) < 5:
            continue
        c = int(p[0])
        cx, cy, w, h = map(float, p[1:5])
        out.append((c, (cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H))
    return out


def iou(a, b):
    x1, y1 = max(a[1], b[1]), max(a[2], b[2])
    x2, y2 = min(a[3], b[3]), min(a[4], b[4])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2-x1)*(y2-y1)
    return inter / max((a[3]-a[1])*(a[4]-a[2]) + (b[3]-b[1])*(b[4]-b[2]) - inter, 1e-9)


def prepare():
    cls_file = HERE / "data" / "classes_autolabel.txt"
    cls_file.write_text("\n".join(NAMES) + "\n", encoding="utf-8")
    for k in KINDS:
        src = ROOT / k / "labels"
        dst = ROOT / "review" / k
        if dst.exists():
            print(f"  {dst} 는 이미 있습니다 (덮어쓰지 않음)")
            continue
        dst.mkdir(parents=True)
        n = 0
        for f in src.glob("*.txt"):
            if f.name == "classes.txt":
                continue
            shutil.copy2(f, dst / f.name)
            n += 1
        print(f"  {k}: 예측 {n}개 -> {dst}")
    print("\n검수 방법 (예측 박스가 그려진 상태로 열립니다)")
    for k in KINDS:
        print(f"  python -m labelImg.labelImg sample_autolabel/{k}/images "
              f"data/classes_autolabel.txt sample_autolabel/review/{k}")
    print("\n  틀린 박스는 지우고, 빠진 부품은 새로 그린 뒤 저장하세요.")
    print("  저장 포맷은 YOLO 로 두어야 합니다.")
    print("\n검수가 끝나면:  python review_autolabel.py score")


def score():
    print("자동 라벨링 정확도 — 사람이 검수한 결과를 정답으로 봄\n")
    for k in KINDS:
        pred_dir, gt_dir = ROOT / k / "labels", ROOT / "review" / k
        if not gt_dir.is_dir():
            print(f"  {k}: 검수 결과 없음 (prepare 후 작업 필요)")
            continue
        tp = fp = fn = 0
        ious = []
        per_cls = {}
        for gf in sorted(gt_dir.glob("*.txt")):
            if gf.name == "classes.txt":
                continue
            gt = load(gf)
            pf = pred_dir / gf.name
            pred = load(pf) if pf.exists() else []
            used = set()
            for p in pred:
                best, bj = 0.0, None
                for j, g in enumerate(gt):
                    if j in used or g[0] != p[0]:
                        continue
                    v = iou(p, g)
                    if v > best:
                        best, bj = v, j
                if bj is not None and best >= IOU_T:
                    used.add(bj); tp += 1; ious.append(best)
                    per_cls.setdefault(p[0], [0, 0, 0])[0] += 1
                else:
                    fp += 1
                    per_cls.setdefault(p[0], [0, 0, 0])[1] += 1
            for j, g in enumerate(gt):
                if j not in used:
                    fn += 1
                    per_cls.setdefault(g[0], [0, 0, 0])[2] += 1
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        print(f"  [{k}]  정답 {tp+fn}개 / 예측 {tp+fp}개")
        print(f"     맞음 {tp}  오검출 {fp}  누락 {fn}")
        print(f"     Precision {prec:.3f}  Recall {rec:.3f}  F1 {f1:.3f}"
              f"  matched IoU 중앙 {np.median(ious):.3f}" if ious else
              f"     Precision {prec:.3f}  Recall {rec:.3f}  F1 {f1:.3f}")
        for c, (t, f_, n_) in sorted(per_cls.items()):
            print(f"       {KOREAN_BY_ID[c]:<20} 맞음 {t:3d}  오검출 {f_:3d}  누락 {n_:3d}")
        need = fn + fp
        print(f"     사람이 손댈 횟수 {need}회 vs 처음부터 그리기 {tp+fn}회 "
              f"-> {'이득' if need < tp+fn else '손해'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "score"])
    a = ap.parse_args()
    (prepare if a.cmd == "prepare" else score)()
