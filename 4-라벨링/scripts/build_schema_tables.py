"""스키마 정의(파이썬)에서 보고용 CSV 를 생성한다.

문서에 숫자·표를 손으로 적지 않기 위한 장치다. 스키마를 고치면 이 스크립트를 다시
돌리는 것만으로 모든 표가 따라 바뀐다.

출력: schemas/class_migration_26_to_28.csv
      schemas/panel_class_candidates.csv
      schemas/classes_v2.csv
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import classes_v1_26 as v1  # noqa: E402


def write(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def classes_table():
    rows = []
    for c in sorted(v2.CLASSES, key=lambda x: x.class_id):
        rows.append({
            "class_id": c.class_id,
            "guide_no": c.guide_no,
            "class_name": c.class_name,
            "canonical_name": c.canonical_name,
            "label_status": c.label_status,
            "priority": v2.priority_of(c.class_name) or "",
            "description": c.description,
            "aliases": " | ".join(c.alias),
            "panel_candidates": " ".join(
                p.split("-")[0] for p in v2.panels_of(c.class_name)),
            "notes": c.notes,
        })
    return write(paths.SCHEMAS / "classes_v2.csv",
                 ["class_id", "guide_no", "class_name", "canonical_name",
                  "label_status", "priority", "description", "aliases",
                  "panel_candidates", "notes"], rows)


def migration_table():
    rows = []
    for old_id, old_key, old_ko in v1.OLD_CLASSES:
        name, kind, basis = v1.MIGRATION[old_id]
        if kind == "split":
            for panel_id, target in sorted(v1.SPLIT_BY_PANEL.items()):
                c = v2.BY_NAME[target]
                rows.append({
                    "old_class_id": old_id, "old_class_name": old_key,
                    "old_class_ko": old_ko,
                    "new_class_id": c.class_id, "new_class_name": c.class_name,
                    "new_class_ko": c.canonical_name, "new_guide_no": c.guide_no,
                    "migration_type": "split",
                    "applies_to_panel": panel_id,
                    "basis": basis,
                })
            rows.append({
                "old_class_id": old_id, "old_class_name": old_key,
                "old_class_ko": old_ko,
                "new_class_id": "", "new_class_name": "", "new_class_ko": "",
                "new_guide_no": "", "migration_type": "split-unresolved",
                "applies_to_panel": "그 밖의 반",
                "basis": "가이드에 대응 항목 없음 — 자동 변환하지 않고 사람이 판정",
            })
        else:
            c = v2.BY_NAME[name]
            rows.append({
                "old_class_id": old_id, "old_class_name": old_key,
                "old_class_ko": old_ko,
                "new_class_id": c.class_id, "new_class_name": c.class_name,
                "new_class_ko": c.canonical_name, "new_guide_no": c.guide_no,
                "migration_type": kind, "applies_to_panel": "전체",
                "basis": basis,
            })
    for name in v1.NEW_IN_V2:
        c = v2.BY_NAME[name]
        rows.append({
            "old_class_id": "", "old_class_name": "", "old_class_ko": "",
            "new_class_id": c.class_id, "new_class_name": c.class_name,
            "new_class_ko": c.canonical_name, "new_guide_no": c.guide_no,
            "migration_type": "new", "applies_to_panel": " ".join(
                p.split("-")[0] for p in v2.panels_of(name)),
            "basis": "v2 신규 항목 — 구 스키마에 대응 없음, 전량 신규 라벨링",
        })
    return write(paths.SCHEMAS / "class_migration_26_to_28.csv",
                 ["old_class_id", "old_class_name", "old_class_ko",
                  "new_class_id", "new_class_name", "new_class_ko", "new_guide_no",
                  "migration_type", "applies_to_panel", "basis"], rows)


def panel_candidates_table():
    rows = []
    for panel, names in v2.PANEL_CLASSES.items():
        for order, n in enumerate(names, 1):
            c = v2.BY_NAME[n]
            rows.append({
                "panel_id": panel.split("-")[0],
                "panel_folder": panel,
                "panel_priority": v2.PANEL_PRIORITY[panel],
                "order": order,
                "class_id": c.class_id,
                "guide_no": c.guide_no,
                "class_name": c.class_name,
                "canonical_name": c.canonical_name,
                "label_status": c.label_status,
                "provisional": "1" if panel in v2.PANEL_CLASSES_PROVISIONAL else "0",
            })
    return write(paths.SCHEMAS / "panel_class_candidates.csv",
                 ["panel_id", "panel_folder", "panel_priority", "order",
                  "class_id", "guide_no", "class_name", "canonical_name",
                  "label_status", "provisional"], rows)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for p in (classes_table(), migration_table(), panel_candidates_table()):
        n = sum(1 for _ in p.open(encoding="utf-8-sig")) - 1
        print(f"{p.name:<34} {n}행")
