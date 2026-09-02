"""CVAT 프로젝트 라벨 정의(JSON)를 만든다. **속성이 저장되게 하려면 이게 먼저다.**

발견한 사실
    `pilot/cvat_prep.py` 는 라벨을 `"attributes": []` 로 만든다. 즉 지금 구조로
    CVAT 프로젝트를 만들면 라벨러 화면에 **truncated 를 입력할 칸 자체가 없고**,
    XML 로 export 해도 그 속성은 나오지 않는다. 없는 것을 나중에 복원할 수는 없다.

    occluded 는 다르다. CVAT **내장 필드**라 정의하지 않아도 항상 저장된다
    (박스 선택 후 단축키 Q, XML 에서는 `<box occluded="1">`).
    그래서 여기서는 occluded 를 다시 정의하지 않는다 — 내장 필드를 쓰는 편이
    라벨러에게도 익숙하고 export 에서도 확실하다.

만드는 것
    data/labeling/draft/trial/cvat_labels.json
      · 라벨 대상 클래스 (rectangle) + 속성 truncated / ignore
      · 촬영유형 (tag) — 이미지 단위 메타데이터

    CVAT 프로젝트 생성 화면의 `Raw` 탭에 통째로 붙여넣는다.

원본은 `schemas/classes_v2.py` · `schemas/labeling_rules.py` 하나뿐이다.
클래스 이름과 순서는 `classes.txt` 와 같은 규칙으로 뽑으므로 서로 어긋나지 않는다.

사용:
    python scripts/cvat_labels_json.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import labeling_rules as rules  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"

# 라벨러가 박스마다 켜는 체크박스. occluded 는 CVAT 내장이라 여기 넣지 않는다.
BOX_ATTRS = ["truncated", "ignore"]

# 색은 class_id 로 정한다. 무작위로 뽑으면 다시 만들 때마다 달라진다.
PALETTE = ["#ff5555", "#ffaa00", "#ffee33", "#66dd44", "#33ccaa", "#33aaff",
           "#5566ff", "#aa66ff", "#ff66cc", "#cc8855", "#88aa99", "#dd4477"]


def checkbox(name, why):
    return {"name": name, "mutable": True, "input_type": "checkbox",
            "default_value": "false", "values": ["false", "true"],
            "description": why}


def build():
    labels = []
    for c in sorted(v2.CLASSES, key=lambda x: x.class_id):
        # classes.txt 와 같은 조건 — 라벨 대상이 아닌 것(제외·폐지)과
        # 단위 미확정 클래스는 쓰지 않는다
        if not v2.is_labelable(c.class_name) or not v2.unit_confirmed(c.class_name):
            continue
        labels.append({
            "name": c.canonical_name,
            "color": PALETTE[c.class_id % len(PALETTE)],
            "type": "rectangle",
            "attributes": [checkbox(a, rules.ATTRIBUTES[a]) for a in BOX_ATTRS],
        })

    labels.append({
        "name": "촬영유형",
        "color": "#999999",
        "type": "tag",
        "attributes": [{
            "name": "shot_type", "mutable": True, "input_type": "select",
            "default_value": rules.SHOT_TYPES[0], "values": list(rules.SHOT_TYPES),
            "description": "이미지 단위 메타데이터 — 샷 타입별 성능 편차를 보려면 필요하다",
        }],
    })
    return labels


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    labels = build()
    out = TRIAL / "cvat_labels.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    rect = [l for l in labels if l["type"] == "rectangle"]
    print(f"라벨 정의 {len(labels)}개 (rectangle {len(rect)} + tag 1) -> {out}")
    print(f"  박스 속성: {', '.join(BOX_ATTRS)}")
    print(f"  occluded 는 CVAT 내장 필드라 정의하지 않는다 (단축키 Q · "
          f"XML 에는 <box occluded=\"1\"> 로 저장된다)")
    print(f"  이미지 태그: 촬영유형 {rules.SHOT_TYPES}")

    # classes.txt 와 어긋나지 않는지 그 자리에서 확인한다
    ctxt = TRIAL / "classes.txt"
    if ctxt.exists():
        names = [n.strip() for n in ctxt.read_text(encoding="utf-8").splitlines()]
        used = [n for n in names if n and not n.startswith("__사용안함")]
        same = used == [l["name"] for l in rect]
        print(f"  classes.txt 사용 클래스 {len(used)}종과 일치: "
              f"{'예' if same else '아니오 — 확인 필요'}")
        if not same:
            return 1
    print("\nCVAT 프로젝트 생성 화면의 Raw 탭에 이 파일 내용을 붙여넣는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
