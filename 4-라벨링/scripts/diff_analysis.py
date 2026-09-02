"""라벨러와 기존 라벨의 **차이를 원인별로 분해**한다. "10개 덜 그렸다" 로 끝내지 않는다.

왜 필요한가
    A vs 기존 대조에서 MCCB 접촉부가 48 vs 58 · mIoU 0.700 으로 가장 크게 갈렸다.
    이 10개가 **누락인지 단위 해석인지**에 따라 할 일이 정반대다 —
    누락이면 지침서의 Skip 정책을 손봐야 하고, 단위 해석이면 `TERMINAL_GROUP` 정의를 손봐야 한다.

무엇을 자동으로 판정하나
    기하로 판정할 수 있는 것만 판정한다. **나머지는 사람 몫으로 비워 둔다.**

      A_SPLIT        기존 1개를 A 가 2개 이상으로 나눔      -> 단위 해석
      A_MERGE        기존 2개 이상을 A 가 1개로 묶음        -> 단위 해석
      BOUNDARY_DIFF  같은 물체인데 경계만 다름 (0<IoU<0.5)  -> 경계 규칙
      A_MISSING      기존 박스 자리에 A 박스가 전혀 없음     -> 누락 또는 정당한 Skip
      A_EXTRA        A 박스 자리에 기존 박스가 전혀 없음     -> 기존의 누락 또는 A 의 과대
      MATCHED_LOW    짝은 지어졌으나 IoU 가 낮음            -> 경계 규칙

    `A_MISSING` 과 `A_EXTRA` 는 **원인을 기하로 알 수 없다.** 사람이 이미지를 봐야 한다.
    그래서 판정표의 `verdict` 칸을 비워 두고 근거가 될 측정값만 채운다.

출력
    reports/labeling/diff_<클래스>_<날짜>.csv        박스별 판정표 (verdict 칸은 사람이 채운다)
    experiments/labeling_review/<클래스>/*.png       A(파랑) vs 기존(주황) 겹쳐 그린 검토용 이미지

사용
    python scripts/diff_analysis.py <라벨러 폴더> --class "MCCB 접촉부"
    python scripts/diff_analysis.py <라벨러 폴더> --class 전체
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
EXISTING = TRIAL / "_existing"
IOU_MATCH = 0.5          # agreement.py 와 같은 값
IOU_LOW = 0.75           # 짝은 지었으나 경계가 갈린다고 볼 선
EDGE = 0.01              # 프레임 가장자리 접촉 판정


def load(folder, only_cls=None):
    d = Path(folder)
    ydir = d / "yolo" if (d / "yolo").is_dir() else d
    out = {}
    for f in sorted(ydir.glob("*.txt")):
        if f.name in ("classes.txt", "obj.names", "train.txt"):
            continue
        bs = []
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            t = line.split()
            if len(t) < 5:
                continue
            cid = int(float(t[0]))
            if only_cls is not None and cid != only_cls:
                continue
            bs.append((i, cid, *[float(x) for x in t[1:5]]))
        out[f.stem] = bs
    return out


def xyxy(b):
    _, _, cx, cy, w, h = b
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def iou(a, b):
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def overlap_frac(inner, outer):
    """inner 가 outer 에 얼마나 들어가 있나 (inner 면적 기준)."""
    ax0, ay0, ax1, ay1 = xyxy(inner)
    bx0, by0, bx1, by1 = xyxy(outer)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    a = (ax1 - ax0) * (ay1 - ay0)
    return (ix * iy / a) if a > 0 else 0.0


def edges_touched(b):
    x0, y0, x1, y1 = xyxy(b)
    return sum([x0 <= EDGE, y0 <= EDGE, x1 >= 1 - EDGE, y1 >= 1 - EDGE])


def greedy(A, B):
    pairs = sorted(((iou(a, b), i, j) for i, a in enumerate(A) for j, b in enumerate(B)),
                   reverse=True)
    ua, ub, out = set(), set(), []
    for v, i, j in pairs:
        if v < IOU_MATCH or i in ua or j in ub:
            continue
        ua.add(i); ub.add(j); out.append((i, j, v))
    return out, [i for i in range(len(A)) if i not in ua], \
        [j for j in range(len(B)) if j not in ub]


def classify(stem, A, E):
    """돌려주는 것: [행]. 기하로 알 수 있는 것만 채우고 나머지는 비운다."""
    m, only_a, only_e = greedy(A, E)
    rows = []

    for i, j, v in m:
        rows.append({
            "image": stem, "kind": "MATCHED_LOW" if v < IOU_LOW else "MATCHED",
            "auto_cause": "경계 규칙" if v < IOU_LOW else "",
            "a_box": i, "e_box": j, "iou": round(v, 3),
            "a_area": round(A[i][4] * A[i][5], 5), "e_area": round(E[j][4] * E[j][5], 5),
            "a_edges": edges_touched(A[i]), "e_edges": edges_touched(E[j]),
            "note_auto": "", "verdict": "", "note_human": "",
        })

    for j in only_e:
        # 기존 1개를 A 가 여러 개로 나눴나
        parts = [i for i in range(len(A)) if overlap_frac(A[i], E[j]) >= 0.6]
        best = max((iou(A[i], E[j]), i) for i in range(len(A))) if A else (0.0, None)
        if len(parts) >= 2:
            kind, cause = "A_SPLIT", "단위 해석 (기존 1 -> A %d)" % len(parts)
        elif best[0] > 0:
            kind, cause = "BOUNDARY_DIFF", "경계 규칙 (겹치되 IoU<0.5)"
        else:
            kind, cause = "A_MISSING", ""      # 기하로 알 수 없다 — 사람 판정
        rows.append({
            "image": stem, "kind": kind, "auto_cause": cause,
            "a_box": ";".join(map(str, parts)) if parts else "",
            "e_box": j, "iou": round(best[0], 3),
            "a_area": "", "e_area": round(E[j][4] * E[j][5], 5),
            "a_edges": "", "e_edges": edges_touched(E[j]),
            "note_auto": "프레임 접촉" if edges_touched(E[j]) else "",
            "verdict": "", "note_human": "",
        })

    for i in only_a:
        parts = [j for j in range(len(E)) if overlap_frac(E[j], A[i]) >= 0.6]
        best = max((iou(A[i], E[j]), j) for j in range(len(E))) if E else (0.0, None)
        if len(parts) >= 2:
            kind, cause = "A_MERGE", "단위 해석 (기존 %d -> A 1)" % len(parts)
        elif best[0] > 0:
            kind, cause = "BOUNDARY_DIFF", "경계 규칙 (겹치되 IoU<0.5)"
        else:
            kind, cause = "A_EXTRA", ""
        rows.append({
            "image": stem, "kind": kind, "auto_cause": cause,
            "a_box": i, "e_box": ";".join(map(str, parts)) if parts else "",
            "iou": round(best[0], 3),
            "a_area": round(A[i][4] * A[i][5], 5), "e_area": "",
            "a_edges": edges_touched(A[i]), "e_edges": "",
            "note_auto": "프레임 접촉" if edges_touched(A[i]) else "",
            "verdict": "", "note_human": "",
        })
    return rows


def render(stem, A, E, out_png, title):
    """A(파랑) vs 기존(주황). 열화상 위에 겹쳐 그린다. 판정은 사람이 한다."""
    import cv2
    import numpy as np
    src = TRIAL / "images" / f"{stem}.jpg"
    if not src.exists():
        return False
    img = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return False
    img = cv2.resize(img, (img.shape[1] * 3, img.shape[0] * 3),
                     interpolation=cv2.INTER_NEAREST)
    h, w = img.shape[:2]
    band = np.full((34, w, 3), 245, np.uint8)

    def draw(boxes, color, tag):
        for b in boxes:
            x0, y0, x1, y1 = xyxy(b)
            p0 = (int(x0 * w), int(y0 * h))
            p1 = (int(x1 * w), int(y1 * h))
            cv2.rectangle(img, p0, p1, color, 2)
            cv2.putText(img, f"{tag}{b[0]}", (p0[0] + 2, max(12, p0[1] - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, .42, color, 1, cv2.LINE_AA)

    draw(E, (40, 130, 245), "E")      # 주황 (BGR)
    draw(A, (230, 130, 40), "A")      # 파랑
    cv2.putText(band, f"{title}   A(blue)={len(A)}  Existing(orange)={len(E)}",
                (10, 23), cv2.FONT_HERSHEY_SIMPLEX, .55, (30, 30, 30), 1, cv2.LINE_AA)
    out = np.vstack([band, img])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", out)[1].tofile(str(out_png))
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("annotator_dir")
    ap.add_argument("--class", dest="cls", default="MCCB 접촉부",
                    help='클래스 이름 또는 "전체"')
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    cid = None
    if a.cls != "전체":
        hit = [c for c in v2.CLASSES if c.canonical_name == a.cls]
        if not hit:
            sys.exit(f"그런 클래스가 없다: {a.cls}")
        cid = hit[0].class_id

    A_all = load(a.annotator_dir, cid)
    E_all = load(EXISTING, cid)

    # 라벨러가 Skip 한 장은 비교하지 않는다 (agreement.py 와 같은 규칙)
    skips = set()
    sl = Path(a.annotator_dir) / "skip_log.csv"
    if sl.exists():
        with sl.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                who = (r.get("annotator") or "").strip()
                if who.startswith("#") or not (r.get("case_id") or "").strip():
                    continue
                if (r.get("scope") or "image").strip() == "image":
                    skips.add(r["case_id"].strip())

    stems = sorted(set(A_all) & set(E_all) - skips)
    rows = []
    for s in stems:
        rows += classify(s, A_all[s], E_all[s])

    tag = "all" if cid is None else v2.BY_ID[cid].canonical_name.replace(" ", "")
    out = paths.REPORTS / "labeling" / f"diff_{tag}_{date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["image", "kind", "auto_cause", "a_box", "e_box", "iou",
              "a_area", "e_area", "a_edges", "e_edges", "note_auto",
              "verdict", "note_human"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerow({"image": "# verdict 칸을 사람이 채운다 — "
                             "규칙문제 / 단위해석 / 보수적판단 / 기존과대 / 경계가림 / 판단불가",
                    **{k: "" for k in fields[1:]}})
        w.writerows(rows)

    # ---- 보고 ----
    from collections import Counter
    kinds = Counter(r["kind"] for r in rows)
    n_a = sum(len(A_all[s]) for s in stems)
    n_e = sum(len(E_all[s]) for s in stems)
    print(f"대상 클래스: {a.cls}   비교 이미지 {len(stems)}장 (Skip 제외 {len(skips)})")
    print(f"A {n_a} vs 기존 {n_e}   차이 {n_a - n_e:+d}\n")
    print(f"  {'유형':<16}{'건수':>5}  무엇을 뜻하나")
    MEAN = {
        "MATCHED": "짝이 맞고 경계도 비슷하다",
        "MATCHED_LOW": "같은 물체인데 경계가 갈린다 -> 경계 규칙",
        "A_SPLIT": "기존 1개를 A 가 나눴다 -> 단위 해석",
        "A_MERGE": "기존 여러 개를 A 가 묶었다 -> 단위 해석",
        "BOUNDARY_DIFF": "겹치지만 IoU<0.5 -> 경계 규칙",
        "A_MISSING": "A 박스가 전혀 없다 -> **사람이 봐야 한다**",
        "A_EXTRA": "기존 박스가 전혀 없다 -> **사람이 봐야 한다**",
    }
    for k, n in kinds.most_common():
        print(f"  {k:<16}{n:>5}  {MEAN.get(k,'')}")

    need = [r for r in rows if r["kind"] in ("A_MISSING", "A_EXTRA")]
    print(f"\n기하로 판정되지 않는 것 {len(need)}건 — verdict 칸을 채워야 한다")
    for r in need:
        side = "기존에만" if r["kind"] == "A_MISSING" else "A 에만"
        print(f"  {r['image']:<22}{r['kind']:<12}{side} 있음  "
              f"면적 {r['e_area'] or r['a_area']}  "
              f"{'프레임 접촉' if r['note_auto'] else ''}")

    if not a.no_render:
        d = paths.PROJECT / "experiments" / "labeling_review" / tag
        n = 0
        for s in stems:
            if render(s, A_all[s], E_all[s], d / f"{s}.png",
                      f"{s}  [{a.cls}]"):
                n += 1
        print(f"\n검토용 이미지 {n}장 -> {d}")
        print("  파랑 = 라벨러 · 주황 = 기존 라벨 · 번호는 판정표의 a_box / e_box")

    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
