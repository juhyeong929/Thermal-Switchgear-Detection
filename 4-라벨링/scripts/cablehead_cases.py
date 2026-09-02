"""OQ-006 / 케이블헤드 경계 — 사례 후보를 추출한다.

**원본과 기존 라벨을 수정하지 않는다.** 읽기만 하고, 시각 자료는 experiments 아래에 새로 만든다.

기존 P6 라벨(구 class 15 분기 접촉부 387개)은 **참고 사례**이지 정답이 아니다(DEC-011).
여기서는 "기존 라벨이 어디까지 잡았는가"를 측정만 하고 옳고 그름을 판정하지 않는다.

사례 유형은 측정 가능한 신호로 1차 분류한 뒤, 육안으로 확정한다.
    한 이미지 안의 15번 박스 개수
    박스끼리의 수직 인접 / 포함(nesting) 관계
    프레임 상단 접촉 여부
    종횡비와 면적

출력: reports/data_audit/cablehead_candidates.csv
      experiments/.../cable_head_boundary/_pool/*.png   후보 확대 렌더
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

SRC = paths.PILOT / "6ban_existing_labels" / "obj_train_data"
OUT = paths.PROJECT / "experiments" / "seed_selection" / "newlabel_probe" / "cable_head_boundary"
CID_CABLEHEAD_OLD = 15          # 구 스키마 분기 접촉부
CID_VCB_OLD = 17
EDGE_EPS = 0.004
SCALE = 3                        # 320x240 -> 960x720 확대 렌더


def read_boxes(stem):
    out = []
    for line in (SRC / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        out.append((int(float(p[0])), *[float(x) for x in p[1:5]]))
    return out


def xyxy(b):
    _, cx, cy, w, h = b
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def contains(a, b, tol=0.01):
    """a 가 b 를 (거의) 포함하는가."""
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    return (ax0 - tol <= bx0 and ay0 - tol <= by0
            and ax1 + tol >= bx1 and ay1 + tol >= by1)


def x_overlap(a, b):
    ax0, _, ax1, _ = xyxy(a)
    bx0, _, bx1, _ = xyxy(b)
    ov = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    return ov / max(1e-9, min(ax1 - ax0, bx1 - bx0))


def render(stem, boxes, path, highlight=None):
    """확대 렌더. 원본 파일은 열어서 읽기만 한다."""
    im = cv2.imdecode(np.frombuffer((SRC / f"{stem}.jpg").read_bytes(), np.uint8),
                      cv2.IMREAD_COLOR)
    if im is None:
        return False
    im = cv2.resize(im, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    H, W = im.shape[:2]
    for i, b in enumerate(boxes):
        x0, y0, x1, y1 = xyxy(b)
        col = (0, 255, 255) if b[0] == CID_CABLEHEAD_OLD else (0, 140, 255)
        th = 3 if (highlight is not None and i == highlight) else 2
        cv2.rectangle(im, (int(x0 * W), int(y0 * H)), (int(x1 * W), int(y1 * H)), col, th)
        cv2.putText(im, str(i), (int(x0 * W) + 3, int(y0 * H) + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", im)[1].tofile(str(path))
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    with (paths.DEDUP / "dedup_metadata.csv").open(encoding="utf-8-sig") as fh:
        dd = {Path(r["rel_path"]).stem: r for r in csv.DictReader(fh)}

    stems = sorted(f.stem for f in SRC.glob("*.txt"))
    rows = []
    for s in stems:
        bs = read_boxes(s)
        heads = [b for b in bs if b[0] == CID_CABLEHEAD_OLD]
        if not heads:
            continue
        n_head = len(heads)
        for i, b in enumerate(heads):
            x0, y0, x1, y1 = xyxy(b)
            # 같은 이미지 안의 다른 케이블헤드 박스와의 관계
            nested_in = any(contains(o, b) for j, o in enumerate(heads) if j != i)
            contains_other = any(contains(b, o) for j, o in enumerate(heads) if j != i)
            # 바로 위에 붙어 있는 박스 (수직 인접) — 몸통/상부 분리 사례 신호
            above = None
            for j, o in enumerate(heads):
                if j == i:
                    continue
                ox0, oy0, ox1, oy1 = xyxy(o)
                if oy1 <= y0 + 0.06 and x_overlap(b, o) > 0.4:
                    above = j
            m = dd.get(s, {})
            rows.append({
                "image_id": m.get("image_id", s), "stem": s,
                "rel_path": m.get("rel_path", ""),
                "panel": "P6-VCB반", "camera": "IR1",
                "session": m.get("session_key", ""),
                "cluster_id": m.get("cluster_id", ""),
                "original_class_id": CID_CABLEHEAD_OLD,
                "v2_class_id": 13,
                "box_index": i, "boxes_in_image": n_head,
                "bbox_xyxy": f"{x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f}",
                "bbox_area_ratio": round(b[3] * b[4], 5),
                "aspect_w_over_h": round(b[3] / max(b[4], 1e-9), 3),
                "top_at_frame": int(y0 <= EDGE_EPS),
                "bottom_at_frame": int(y1 >= 1 - EDGE_EPS),
                "nested_in_other": int(nested_in),
                "contains_other": int(contains_other),
                "has_box_directly_above": int(above is not None),
            })

    # ---- 유형 1차 분류 (측정 신호 기준. 육안으로 확정한다) ----
    for r in rows:
        if r["nested_in_other"] or r["contains_other"]:
            r["case_type_hint"] = "E_중첩"
        elif r["has_box_directly_above"]:
            r["case_type_hint"] = "D_몸통상부분리"
        elif r["top_at_frame"]:
            r["case_type_hint"] = "F_상단잘림"
        elif r["boxes_in_image"] == 1 and 0.15 <= r["aspect_w_over_h"] <= 0.25:
            r["case_type_hint"] = "A_전형"
        elif r["aspect_w_over_h"] > 0.30:
            r["case_type_hint"] = "B_넓음"
        elif r["aspect_w_over_h"] < 0.13:
            r["case_type_hint"] = "C_매우김"
        else:
            r["case_type_hint"] = "A_전형"

    OUT.mkdir(parents=True, exist_ok=True)
    cpath = paths.AUDIT / "cablehead_candidates.csv"
    with cpath.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"케이블헤드 박스 {len(rows)}개 / 이미지 {len({r['stem'] for r in rows})}장")
    print(f"세션 {len({r['session'] for r in rows})}개  "
          f"클러스터 {len({r['cluster_id'] for r in rows})}개\n")
    print("유형 1차 분류 (측정 신호)")
    for k, n in Counter(r["case_type_hint"] for r in rows).most_common():
        print(f"  {k:<16}{n:>5}")
    print(f"\n한 이미지당 박스 수: {dict(Counter(r['boxes_in_image'] for r in rows))}")
    print(f"상단 프레임 접촉 {sum(r['top_at_frame'] for r in rows)}  "
          f"하단 접촉 {sum(r['bottom_at_frame'] for r in rows)}")
    print(f"중첩(포함관계) {sum(r['nested_in_other'] or r['contains_other'] for r in rows)}  "
          f"바로 위 박스 있음 {sum(r['has_box_directly_above'] for r in rows)}")

    # ---- 후보 풀 렌더: 유형별로 세션이 겹치지 않게 고른다 ----
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["case_type_hint"]].append(r)
    pool, used_clusters = [], set()
    for t in ["E_중첩", "D_몸통상부분리", "B_넓음", "C_매우김", "F_상단잘림", "A_전형"]:
        cand = sorted(by_type.get(t, []), key=lambda r: (r["session"], -r["bbox_area_ratio"]))
        picked_sessions = set()
        for r in cand:
            if r["cluster_id"] in used_clusters:
                continue
            if r["session"] in picked_sessions and len(pool) > 6:
                continue
            pool.append(r)
            used_clusters.add(r["cluster_id"])
            picked_sessions.add(r["session"])
            if sum(1 for p in pool if p["case_type_hint"] == t) >= 4:
                break

    pdir = OUT / "_pool"
    pdir.mkdir(parents=True, exist_ok=True)
    seen = set()
    for r in pool:
        if r["stem"] in seen:
            continue
        seen.add(r["stem"])
        render(r["stem"], read_boxes(r["stem"]),
               pdir / f"{r['case_type_hint']}__{r['stem']}.png")
    print(f"\n후보 풀 {len(seen)}장 렌더 -> {pdir}")
    for r in pool:
        if r["stem"] in seen:
            print(f"  {r['case_type_hint']:<16}{r['stem']:<34}"
                  f"박스{r['boxes_in_image']} 종횡비{r['aspect_w_over_h']:.2f} "
                  f"면적{r['bbox_area_ratio']:.4f}")
    print(f"\n-> {cpath.name}")


if __name__ == "__main__":
    main()
