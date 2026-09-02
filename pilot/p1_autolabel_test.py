"""P1-TR반 나머지를 자동 라벨링할 수 있는지 두 시나리오로 측정한다.

  (A) 같은 세션의 미라벨 프레임 182장
      -> 세션 내부에서 프레임을 나눠 학습/검증. 연속 촬영이라 거의 같은 장면이므로
         낙관적이지만, 실제 상황도 똑같이 '거의 같은 장면'이라 이 수치가 현실에 가깝다.

  (B) 전량 미착수 세션 425장 (A2/A3 현장)
      -> 세션 하나를 통째로 빼고 학습해 그 세션으로 검증. 본 적 없는 장면에 대한 추정치.
         단 A2/A3 는 라벨이 없어 실제 측정은 불가능하고, A1 내 다른 세션으로 근사한다.

검수 관점 지표(사람이 손댈 횟수)까지 낸다. 그게 '자동 라벨링을 쓸 것인가'의 실제 기준이다.
"""
from __future__ import annotations

import argparse
import collections
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
SRC = DATA / "labels_ir_src"
W, H = 320, 240
PY = sys.executable

P1_SESSIONS = ["A1_B1_P1_2022-05-12", "A1_B2_P1_2022-05-12",
               "A1_B3_P1_2022-05-24", "A1_B1_P1_2022-06-17"]


def p1_stems():
    out = collections.defaultdict(list)
    for f in sorted(SRC.glob("*.txt")):
        k = "_".join(f.stem.split("_")[:4])
        if k in P1_SESSIONS and (DATA / "ir" / f"{f.stem}.jpg").exists():
            out[k].append(f.stem)
    return out


def build(tag: str, train_stems, val_stems):
    root = HERE / "dataset" / tag
    if root.exists():
        shutil.rmtree(root)
    for sp, ss in (("train", train_stems), ("val", val_stems)):
        (root / "images" / sp).mkdir(parents=True)
        (root / "labels" / sp).mkdir(parents=True)
        for s in ss:
            shutil.copy2(DATA / "ir" / f"{s}.jpg", root / "images" / sp / f"{s}.jpg")
            shutil.copy2(SRC / f"{s}.txt", root / "labels" / sp / f"{s}.txt")
    from classes import NAMES
    (root / "data.yaml").write_text(
        f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\n\n"
        f"nc: {len(NAMES)}\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(NAMES)),
        encoding="utf-8")
    return root


def train(root: Path, name: str, epochs: int):
    from ultralytics import YOLO
    m = YOLO("yolo11s.pt")
    m.train(data=str(root / "data.yaml"), epochs=epochs, imgsz=320, batch=8,
            project=str(HERE / "runs"), name=name, device="cpu", workers=0, seed=0,
            val=True, plots=False, verbose=False,
            hsv_h=0.0, hsv_s=0.3, hsv_v=0.4, degrees=5.0, translate=0.1,
            scale=0.4, fliplr=0.5, flipud=0.0, mosaic=0.5, erasing=0.0)
    return HERE / "runs" / name / "weights" / "best.pt"


def load_gt(stem):
    out = []
    for ln in (SRC / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
        p = ln.split()
        if len(p) >= 5:
            c = int(p[0]); cx, cy, w, h = map(float, p[1:5])
            out.append((c, (cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H))
    return out


def iou(a, b):
    x1, y1 = max(a[1], b[1]), max(a[2], b[2])
    x2, y2 = min(a[3], b[3]), min(a[4], b[4])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    i = (x2-x1)*(y2-y1)
    return i / max((a[3]-a[1])*(a[4]-a[2]) + (b[3]-b[1])*(b[4]-b[2]) - i, 1e-9)


def evaluate(weights: Path, stems, conf):
    from ultralytics import YOLO
    m = YOLO(str(weights))
    tp = fp = fn = 0
    per = collections.defaultdict(lambda: [0, 0, 0])
    for s in stems:
        gt = load_gt(s)
        r = m.predict(str(DATA / "ir" / f"{s}.jpg"), conf=conf, imgsz=320,
                      device="cpu", verbose=False)[0]
        pred = [(int(b.cls.item()), *b.xyxy[0].tolist()) for b in r.boxes]
        used = set()
        for p in pred:
            best, bj = 0.0, None
            for j, g in enumerate(gt):
                if j in used or g[0] != p[0]:
                    continue
                v = iou(p, g)
                if v > best:
                    best, bj = v, j
            if bj is not None and best >= 0.5:
                used.add(bj); tp += 1; per[p[0]][0] += 1
            else:
                fp += 1; per[p[0]][1] += 1
        for j, g in enumerate(gt):
            if j not in used:
                fn += 1; per[g[0]][2] += 1
    return tp, fp, fn, per


def report(title, tp, fp, fn, per, conf):
    prec = tp / max(tp+fp, 1)
    rec = tp / max(tp+fn, 1)
    n_gt = tp + fn
    touch = fp + fn
    print(f"\n  [{title}]  conf {conf}")
    print(f"    정답 {n_gt}개 / 예측 {tp+fp}개 -> 맞음 {tp}, 오검출 {fp}, 누락 {fn}")
    print(f"    Precision {prec:.3f}   Recall {rec:.3f}")
    print(f"    사람이 손댈 횟수 {touch}회  vs  처음부터 {n_gt}회  "
          f"-> {'이득 %.0f%% 절감' % ((1-touch/max(n_gt,1))*100) if touch < n_gt else '손해'}")
    for c in sorted(per, key=lambda c: -(per[c][0]+per[c][2])):
        t, f_, n_ = per[c]
        r_ = t/max(t+n_, 1)
        print(f"      {KOREAN_BY_ID[c]:<18} 맞음 {t:3d} 오검출 {f_:3d} 누락 {n_:3d}  R {r_:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--conf", type=float, nargs="*", default=[0.25, 0.10])
    args = ap.parse_args()

    sess = p1_stems()
    print("P1 라벨된 세션")
    for k in P1_SESSIONS:
        print(f"  {k}  {len(sess.get(k, []))}장")

    # (A) 세션 내부 분할 — 같은 세션 미라벨 프레임 시나리오
    tr, va = [], []
    for k, ss in sess.items():
        ss = sorted(ss)
        for i, s in enumerate(ss):
            (va if i % 5 == 0 else tr).append(s)
    print(f"\n(A) 같은 세션 시나리오: 학습 {len(tr)}장 / 검증 {len(va)}장")
    root = build("p1_A", tr, va)
    w = train(root, "p1_scenarioA", args.epochs)
    for c in args.conf:
        report("A: 같은 세션 미라벨 프레임", *evaluate(w, va, c), c)

    # (B) 세션 통째로 홀드아웃 — 미착수 세션 시나리오
    hold = "A1_B2_P1_2022-05-12"
    tr = [s for k, ss in sess.items() if k != hold for s in ss]
    va = sorted(sess[hold])
    print(f"\n(B) 새 세션 시나리오: 학습 {len(tr)}장 / 검증 {len(va)}장 (홀드아웃 {hold})")
    root = build("p1_B", tr, va)
    w = train(root, "p1_scenarioB", args.epochs)
    for c in args.conf:
        report("B: 본 적 없는 세션", *evaluate(w, va, c), c)

    print("\n주의: (B) 는 같은 현장(A1) 안의 다른 세션이다. 실제 미착수분은 A2·A3 현장이라")
    print("      현장 자체가 다르고, 그쪽에는 라벨이 없어 직접 측정이 불가능하다.")
    print("      따라서 (B) 수치는 A2·A3 에 대해서는 낙관적인 상한으로 봐야 한다.")


if __name__ == "__main__":
    main()
