"""반별 CVAT task 정의를 만든다 (A-1 · NQ-15 결정 반영).

결정 (A-1) — 반 정보를 라벨러에게 **공개한다**
    이전 정책은 반을 감췄다. 그 결과 지침서 §1("자기 반의 목록에 없는 클래스는
    그리지 않습니다")이 **적용 수단 없이 배포**됐고, 시험에서 3/3 재현됐다 —
    `A09` 에서 세 사람이 비한류형 전력퓨즈 / 한류형 전력퓨즈 / LA 로 갈렸다.

    반을 알려주는 것은 **모델의 의미 분류 성능을 시험하는 것이 아니라 실제 라벨링
    운영 조건을 맞추는 것**이다. 본작업에서 라벨러는 당연히 자기 반을 안다.

무엇을 만드는가
    반마다 CVAT task 를 따로 만든다. task 이름에 panel_id / panel_name 을 박고,
    라벨 목록을 그 반의 **배포 대상 클래스로만** 제한한다. 그러면 후보 밖 클래스는
    화면에 나타나지 않으므로 §1 을 지키는 것이 라벨러의 기억력에 의존하지 않는다.

    클래스 목록은 `classes_v2.deployable(panel)` 하나에서 나온다 (A-2).
    속성 정의(truncated / ignore / 촬영유형)는 `cvat_labels_json.py` 와 같은 규칙을
    쓰되, 여기서는 반별로 잘라 낸다.

주의 — class_id 는 여전히 복원해야 한다
    반별로 라벨 목록이 다르므로 CVAT 의 YOLO export 는 반마다 **다른 순서**로
    class_id 를 매긴다. `trial_ingest.py` 의 `obj.names` 복원이 더 중요해졌다.
    이 스크립트가 반별 `obj.names` 기대값을 함께 내보내 회수 때 대조할 수 있게 한다.

출력
    reports/labeling/generated/cvat_tasks.csv          반별 task 이름·클래스·장수
    reports/labeling/generated/cvat_labels/<PID>.json  반별 CVAT Raw 붙여넣기용
    reports/labeling/generated/cvat_labels/<PID>.names 반별 obj.names 기대값

사용:
    python scripts/build_cvat_tasks.py
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import labeling_rules as rules  # noqa: E402

OUT = paths.REPORTS / "labeling" / "generated"
LABELS = OUT / "cvat_labels"

BOX_ATTRS = ["truncated", "ignore"]      # occluded 는 CVAT 내장이라 정의하지 않는다
PALETTE = ["#ff5555", "#ffaa00", "#ffee33", "#66dd44", "#33ccaa", "#33aaff",
           "#5566ff", "#aa66ff", "#ff66cc", "#cc8855", "#88aa99", "#dd4477"]


def checkbox(name):
    return {"name": name, "mutable": True, "input_type": "checkbox",
            "default_value": "false", "values": ["false", "true"],
            "description": rules.ATTRIBUTES[name]}


def shot_tag():
    return {"name": "촬영유형", "color": "#888888", "type": "tag",
            "attributes": [{"name": "shot_type", "mutable": False,
                            "input_type": "select",
                            "default_value": rules.SHOT_TYPES[0],
                            "values": list(rules.SHOT_TYPES),
                            "description": "이미지 단위 메타데이터"}]}


def labels_for(panel):
    out = []
    for cname in v2.deployable(panel):
        c = v2.BY_NAME[cname]
        out.append({"name": c.canonical_name,
                    "color": PALETTE[c.class_id % len(PALETTE)],
                    "type": "rectangle",
                    "attributes": [checkbox(a) for a in BOX_ATTRS]})
    out.append(shot_tag())
    return out


def seed_counts():
    f = paths.LABELING / "seed" / "seed_candidates.csv"
    if not f.exists():
        return Counter()
    with f.open(encoding="utf-8-sig") as fh:
        return Counter(r["panel"] for r in csv.DictReader(fh))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    LABELS.mkdir(parents=True, exist_ok=True)
    seed = seed_counts()

    rows = []
    for panel in v2.PANEL_CLASSES:
        pid = v2.panel_id(panel)
        dep = v2.deployable(panel)
        held = [c for c in v2.labelable(panel) if c not in dep]
        labs = labels_for(panel)

        (LABELS / f"{pid}.json").write_text(
            json.dumps(labs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # CVAT 이 YOLO export 에서 매길 순서 = 라벨 정의 순서 중 rectangle 만
        names = [x["name"] for x in labs if x["type"] == "rectangle"]
        (LABELS / f"{pid}.names").write_text("\n".join(names) + "\n", encoding="utf-8")

        rows.append({
            "panel_id": pid,
            "panel_name": panel,
            "cvat_task_name": f"{pid} · {panel}",
            "seed_images": seed.get(panel, 0),
            "deployable_n": len(dep),
            "deployable": " · ".join(v2.BY_NAME[c].canonical_name for c in dep),
            "caution": " · ".join(v2.BY_NAME[c].canonical_name for c in dep
                                  if v2.BY_NAME[c].label_status == v2.CAUTION),
            "held_unit_unknown": " · ".join(v2.BY_NAME[c].canonical_name
                                            for c in held),
            "provisional_panel": int(panel in v2.PANEL_CLASSES_PROVISIONAL),
            "labels_json": f"generated/cvat_labels/{pid}.json",
            "expected_obj_names": f"generated/cvat_labels/{pid}.names",
        })

    f = OUT / "cvat_tasks.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("반별 CVAT task 정의 — A-1(반 정보 공개) 반영\n")
    print(f"  {'task 이름':<26}{'시드':>5}{'클래스':>5}  배포 목록")
    for r in rows:
        print(f"  {r['cvat_task_name']:<26}{r['seed_images']:>5}"
              f"{r['deployable_n']:>5}  {r['deployable'] or '— 없음 —'}")
        if r["held_unit_unknown"]:
            print(f"  {'':<26}{'':>10}  (이번 판 제외: {r['held_unit_unknown']})")

    thin = [r for r in rows if r["deployable_n"] <= 2]
    if thin:
        print("\n[주의] 배포 클래스가 2종 이하인 반 — 이 반의 Kappa 는 별도로 읽는다")
        for r in thin:
            print(f"  {r['panel_name']:<16}{r['deployable_n']}종  "
                  f"({r['deployable']})")
        print("  이유: 후보가 좁으면 클래스 일치가 쉬워져 전체 평균을 밀어 올린다.")
        print("  -> agreement.py 가 반별 지표를 따로 낸다 (agreement_by_panel_*.csv)")

    print(f"\n  라벨 정의 {len(rows)}개 -> {LABELS}")
    print(f"  -> {f}")
    print("\nCVAT 프로젝트 생성 시 반별로 해당 <PID>.json 을 Raw 탭에 붙여넣는다.")
    print("반마다 라벨 목록이 다르므로 class_id 는 반마다 다르게 매겨진다 —")
    print("회수 때 obj.names 복원(trial_ingest.py)이 필수다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
