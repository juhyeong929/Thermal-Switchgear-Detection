"""프레임에 가려 두 개로 갈라져 예측된 박스를 하나로 병합한다.

몰드변압기의 에폭시 표면은 구조 프레임이 앞을 가로질러 시각적으로 끊긴다. 사람은
프레임을 포함해 한 박스로 그리지만, 모델은 끊긴 곳에서 두 박스로 나눠 찍는다. 그러면
두 반쪽이 정답 한 박스와 IoU 0.5 를 못 넘겨 둘 다 오검출로 계산된다.
(A2 실측: 오검출 163개 중 107개가 에폭시 표면)

같은 클래스이면서 한 축으로 크게 겹치고 다른 축 간격이 작은 쌍을 합친다.

  python merge_split.py --validate      A2 정답으로 병합 효과 검증
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID  # noqa: E402

HERE = Path(__file__).parent
W, H = 320, 240

# 병합 대상 클래스: 프레임에 갈리는 것이 확인된 것만. 접촉부처럼 상별로 여러 개가
# 정상인 클래스를 합치면 상간 비교가 망가진다.
MERGE_CLASSES = {1}          # 에폭시 표면
OVERLAP_MIN = 0.60          # 한 축에서 짧은 변 대비 겹침 비율
GAP_MAX = 40.0              # 다른 축 간격(px) 상한


def _pair_mergeable(a, b) -> bool:
    if a[0] != b[0] or a[0] not in MERGE_CLASSES:
        return False
    ax1, ay1, ax2, ay2 = a[1:5]
    bx1, by1, bx2, by2 = b[1:5]
    ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    oy = max(0.0, min(ay2, by2) - max(ay1, by1))
    minw = min(ax2-ax1, bx2-bx1)
    minh = min(ay2-ay1, by2-by1)
    # 세로로 갈린 경우: 가로가 크게 겹치고 세로 간격이 작다
    if minw > 0 and ox/minw >= OVERLAP_MIN:
        gap = max(ay1, by1) - min(ay2, by2)
        if gap <= GAP_MAX:
            return True
    # 좌우 병합은 하지 않는다. 3상이 나란히 배치되므로 상끼리 합쳐져 버린다
    # (검증 결과 에폭시 Recall 0.91 -> 0.09).
    return False


def merge(boxes: list[tuple]) -> tuple[list[tuple], int]:
    """boxes: [(cls, x1, y1, x2, y2), ...] -> 병합된 리스트, 병합 횟수"""
    cur = list(boxes)
    merged = 0
    changed = True
    while changed:
        changed = False
        for i in range(len(cur)):
            for j in range(i+1, len(cur)):
                if _pair_mergeable(cur[i], cur[j]):
                    a, b = cur[i], cur[j]
                    new = (a[0], min(a[1], b[1]), min(a[2], b[2]),
                           max(a[3], b[3]), max(a[4], b[4]))
                    cur = [c for k, c in enumerate(cur) if k not in (i, j)] + [new]
                    merged += 1
                    changed = True
                    break
            if changed:
                break
    return cur, merged


def iou(a, b):
    x1, y1 = max(a[1], b[1]), max(a[2], b[2])
    x2, y2 = min(a[3], b[3]), min(a[4], b[4])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    i = (x2-x1)*(y2-y1)
    return i/max((a[3]-a[1])*(a[4]-a[2])+(b[3]-b[1])*(b[4]-b[2])-i, 1e-9)


def score(pred_by, gt_by):
    tp = fp = fn = 0
    per = collections.defaultdict(lambda: [0, 0, 0])
    for s, gt in gt_by.items():
        pr = pred_by.get(s, [])
        used = set()
        for p in pr:
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


def validate():
    import xml.etree.ElementTree as ET
    N4 = ["철심부", "에폭시 표면", "몰드변압기 접촉부", "전력퓨즈"]
    task = HERE / "IR1_1반_A2검수"
    cands = [d for d in task.rglob("obj_train_data") if d.is_dir() and any(d.glob("*.jpg"))]
    rev = max(cands, key=lambda d: len(list(d.glob("*.jpg"))))

    root = ET.parse(HERE / "out" / "cvat" / "A2_preannot_all4.xml").getroot()
    name2id = {n: i for i, n in enumerate(N4)}
    pred = {}
    for im in root.findall("image"):
        st = Path(im.get("name")).stem
        if not st.startswith("A2"):
            continue
        pred[st] = [(name2id[b.get("label")], float(b.get("xtl")), float(b.get("ytl")),
                     float(b.get("xbr")), float(b.get("ybr"))) for b in im.findall("box")]
    gt = {}
    for s in pred:
        f = rev / f"{s}.txt"
        bs = []
        if f.exists():
            for ln in f.read_text(encoding="utf-8").splitlines():
                q = ln.split()
                if len(q) >= 5:
                    c = int(q[0]); cx, cy, w, h = map(float, q[1:5])
                    bs.append((c, (cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H))
        gt[s] = bs

    merged_pred, n_merge = {}, 0
    for s, bs in pred.items():
        m, k = merge(bs)
        merged_pred[s] = m
        n_merge += k

    print(f"A2 {len(pred)}장 · 병합 {n_merge}건 발생\n")
    print(f"{'':12}{'맞음':>6}{'오검출':>8}{'누락':>7}{'Prec':>8}{'Recall':>8}"
          f"{'작업량':>8}{'가중':>8}")
    for tag, pb in (("병합 전", pred), ("병합 후", merged_pred)):
        tp, fp, fn, per = score(pb, gt)
        n_gt = tp+fn
        print(f"{tag:<12}{tp:>6}{fp:>8}{fn:>7}{tp/max(tp+fp,1):>8.3f}"
              f"{tp/max(n_gt,1):>8.3f}{fp+fn:>8}{fp*0.3+fn:>8.0f}")
    print()
    for tag, pb in (("병합 전", pred), ("병합 후", merged_pred)):
        tp, fp, fn, per = score(pb, gt)
        print(f"  [{tag}] 클래스별")
        for c in sorted(per, key=lambda c: -(per[c][0]+per[c][2])):
            t, f_, n_ = per[c]
            print(f"    {KOREAN_BY_ID[c]:<18} 맞음 {t:4d} 오검출 {f_:4d} 누락 {n_:3d}"
                  f"  R {t/max(t+n_,1):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    if a.validate:
        validate()
    else:
        print("사용: python merge_split.py --validate")
