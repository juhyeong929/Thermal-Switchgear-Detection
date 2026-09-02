"""OQ-006 / 케이블헤드 — 최종 대표 사례의 시각 자료를 만든다.

**원본과 기존 라벨을 수정하지 않는다.** 원본 이미지를 읽어 메모리에서 그린 뒤
`experiments/.../cable_head_boundary/case_XX/` 에 새 파일로 저장한다.

기존 bbox 를 정답으로 취급하지 않는다(DEC-011). 각 사례에 다음을 만든다.

    original.png        박스 없는 원본 확대본
    reference.png       기존 참고 라벨 (노랑) — 정답 아님. 관행 관찰용
    variants.png        해석/오답 후보를 한 장에 나란히
    notes.md            선정 근거와 관찰 내용

오답 후보는 기준 박스를 **기계적으로 변형**해 만든다. 좌표를 손으로 지어내지 않기 위함이다.
    too_wide    가로·세로 1.45배 확대  (인접 구조물까지 삼키는 오류)
    too_narrow  가로·세로 0.55배 축소  (일부만 잡는 오류)
    split       세로로 2등분          (한 객체를 임의로 쪼개는 오류)
"""

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

SRC = paths.PILOT / "6ban_existing_labels" / "obj_train_data"
OUT = (paths.PROJECT / "experiments" / "seed_selection" / "newlabel_probe"
       / "cable_head_boundary")
SCALE = 3
YELLOW, RED, GREEN, CYAN = (0, 255, 255), (0, 0, 255), (0, 200, 0), (255, 200, 0)

# 최종 대표 사례 — 유형·세션·클러스터가 겹치지 않게 고름
CASES = [
    ("case_01", "A1_B2_P6_2022-05-12_IR1_00024", "A_전형",
     "단일 박스. 리브 적층부와 그 위 수직 도체를 함께 감쌌다. "
     "상부 도체 포함 관행의 대표 사례."),
    ("case_02", "A2_B1_P6_2022-06-03_IR1_00079", "A_전형·상단잘림",
     "좌우 두 개가 같은 방식으로 잡혔다. 리브 적층부와 상부 캡까지 포함하고 "
     "하부 도체는 제외했다. 둘 다 상단이 프레임에 잘렸다."),
    ("case_03", "A1_B3_P6_2022-05-24_IR1_00041", "E_경계불일치",
     "같은 프레임·같은 종류인데 왼쪽은 리브 적층부만(높이 0.141), "
     "가운데는 상부 도체까지(높이 0.347). 높이비 2.47 로 387개 중 최대 편차."),
    ("case_04", "A1_B1_P6_2022-05-12_IR1_00048", "E_중첩·불일치",
     "왼쪽은 리브 적층부만 1개. 오른쪽은 상부까지 큰 박스 1개 + 엘보에 작은 박스 1개. "
     "같은 구성에 박스 개수와 범위가 다르다."),
    ("case_05", "A2_B1_P6_2022-06-03_IR1_00062", "E_중복박스",
     "세 조 중 오른쪽 한 조에만 박스가 두 개 겹쳐 있다(box0 이 box3 안에 들어감). "
     "같은 인스턴스 이중 라벨."),
    ("case_06", "A1_B1_P6_2022-06-17_IR1_00017", "F_반대사례",
     "작고 가로로 넓은 박스 하나가 OSD 컬러바에 겹쳐 있다. 종횡비 1.27 로 "
     "케이블헤드 전형(0.19)에서 크게 벗어난다. 화면의 다른 애자들은 미라벨."),
]


def read_boxes(stem):
    out = []
    for line in (SRC / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) >= 5:
            out.append((int(float(p[0])), *[float(x) for x in p[1:5]]))
    return out


def load(stem):
    im = cv2.imdecode(np.frombuffer((SRC / f"{stem}.jpg").read_bytes(), np.uint8),
                      cv2.IMREAD_COLOR)
    return cv2.resize(im, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)


def draw(im, b, col, th=2, tag=""):
    H, W = im.shape[:2]
    _, cx, cy, w, h = b
    x0, y0 = int((cx - w / 2) * W), int((cy - h / 2) * H)
    x1, y1 = int((cx + w / 2) * W), int((cy + h / 2) * H)
    cv2.rectangle(im, (x0, y0), (x1, y1), col, th)
    if tag:
        cv2.putText(im, tag, (max(2, x0) + 3, max(16, y0) + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)
    return im


def scaled(b, f):
    c, cx, cy, w, h = b
    return (c, cx, cy, min(w * f, 1.0), min(h * f, 1.0))


def split_v(b):
    c, cx, cy, w, h = b
    return [(c, cx, cy - h / 4, w, h / 2), (c, cx, cy + h / 4, w, h / 2)]


def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", im)[1].tofile(str(path))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with (paths.AUDIT / "cablehead_candidates.csv").open(encoding="utf-8-sig") as fh:
        cand = list(csv.DictReader(fh))
    meta = {}
    for r in cand:
        meta.setdefault(r["stem"], r)

    index = []
    for cid, stem, ctype, why in CASES:
        d = OUT / cid
        boxes = read_boxes(stem)
        heads = [b for b in boxes if b[0] == 15]
        if not heads:
            print(f"  [건너뜀] {stem} 케이블헤드 박스 없음")
            continue

        save(load(stem), d / "original.png")

        ref = load(stem)
        for i, b in enumerate(boxes):
            draw(ref, b, YELLOW if b[0] == 15 else (0, 140, 255), 2, str(i))
        save(ref, d / "reference.png")

        # 가장 큰 케이블헤드 박스를 변형 기준으로 삼는다
        base = max(heads, key=lambda b: b[3] * b[4])
        panels = []
        for label, bs, col in [
            ("reference", [base], YELLOW),
            ("too_wide x1.45", [scaled(base, 1.45)], RED),
            ("too_narrow x0.55", [scaled(base, 0.55)], RED),
            ("wrong_split", split_v(base), RED),
        ]:
            im = load(stem)
            for b in bs:
                draw(im, b, col, 2)
            cv2.rectangle(im, (0, 0), (im.shape[1] - 1, 26), (0, 0, 0), -1)
            cv2.putText(im, label, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 1, cv2.LINE_AA)
            panels.append(im)
        grid = np.vstack([np.hstack(panels[:2]), np.hstack(panels[2:])])
        save(grid, d / "variants.png")

        m = meta.get(stem, {})
        (d / "notes.md").write_text(f"""# {cid} — {stem}

| 항목 | 값 |
|---|---|
| case_type | {ctype} |
| image_id | {m.get('image_id', '')} |
| image_path | `3-가공/{m.get('rel_path', '')}` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | {m.get('session', '')} |
| cluster_id | {m.get('cluster_id', '')} |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | {len(heads)} |
| 기준 박스 bbox_xyxy | {m.get('bbox_xyxy', '')} |
| 기준 박스 면적비 | {m.get('bbox_area_ratio', '')} |

## selection_reason
{why}

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
""", encoding="utf-8")

        index.append({"case_id": cid, "stem": stem, "case_type": ctype,
                      "session": m.get("session", ""),
                      "cluster_id": m.get("cluster_id", ""),
                      "heads_in_image": len(heads),
                      "bbox_xyxy": m.get("bbox_xyxy", ""),
                      "bbox_area_ratio": m.get("bbox_area_ratio", ""),
                      "selection_reason": why})
        print(f"  {cid}  {ctype:<16}{stem}  박스 {len(heads)}")

    ipath = paths.AUDIT / "cablehead_case_index.csv"
    with ipath.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(index[0]))
        w.writeheader()
        w.writerows(index)
    print(f"\n사례 {len(index)}건 -> {OUT}")
    print(f"색인 -> {ipath.name}")


if __name__ == "__main__":
    main()
