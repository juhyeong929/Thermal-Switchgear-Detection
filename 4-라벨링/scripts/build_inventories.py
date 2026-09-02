"""반별 · 클래스별 현황표를 만든다. 교수님 보고의 기본 데이터.

입력: data/metadata/image_inventory.csv        (build_image_inventory.py)
      data/labeling/reviewed/**/*.txt          (migrate_labels.py, v2 스키마)
출력: reports/data_audit/panel_inventory.csv
      reports/data_audit/class_inventory.csv

숫자는 전부 여기서 집계한다. 문서에 손으로 적지 않는다.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

PANEL_RE = re.compile(r"_(P\d+)_")
SKIP_NAMES = {"train.txt", "val.txt", "test.txt", "classes.txt", "obj.names"}


def load_images():
    p = paths.METADATA / "image_inventory.csv"
    if not p.exists():
        sys.exit("image_inventory.csv 가 없다. scripts/build_image_inventory.py 를 먼저 실행한다.")
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_v2_labels():
    """승계된 v2 라벨을 읽어 (panel_id, class_id) -> 박스수, panel -> 파일수 로 집계."""
    boxes = Counter()
    files = Counter()
    root = paths.LABELING / "reviewed"
    for f in root.rglob("*.txt"):
        if f.name in SKIP_NAMES or f.name.startswith("._"):
            continue
        m = PANEL_RE.search(f.stem)
        panel_id = m.group(1) if m else "UNKNOWN"
        n = 0
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            boxes[(panel_id, int(p[0]))] += 1
            n += 1
        if n:
            files[panel_id] += 1
    return boxes, files


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    imgs = load_images()
    boxes, lfiles = load_v2_labels()

    by_panel = defaultdict(list)
    for r in imgs:
        by_panel[r["panel_folder"]].append(r)

    # ---------------- 반별 ----------------
    panel_rows = []
    for panel in paths.PANELS:
        rows = by_panel.get(panel, [])
        pid = panel.split("-")[0]
        ir = [r for r in rows if r["kind"] == "IR"]
        rgb = [r for r in rows if r["kind"] == "RGB"]
        paired = [r for r in ir if r["has_rgb_pair"] == "1"]
        subs = sorted({r["subfolder"] for r in rows if r["subfolder"]})
        cams = Counter(r["camera"] for r in ir)
        sessions = {(r["site"], r["building"], r["date"], r["camera"], r["session"])
                    for r in ir}
        pbox = {c: n for (p, c), n in boxes.items() if p == pid}

        cand = v2.PANEL_CLASSES.get(panel, [])
        labelable = v2.labelable(panel)
        notes = []
        if panel in v2.PANEL_CLASSES_PROVISIONAL:
            notes.append("가이드에 단독 상세 없음 — 후보 클래스 잠정")
        if not labelable:
            notes.append("라벨 가능 클래스 0종 — 범위 판정 필요")
        if subs:
            notes.append("하위폴더: " + ", ".join(subs))

        panel_rows.append({
            "panel_id": pid,
            "folder_name": panel,
            "panel_priority": v2.PANEL_PRIORITY.get(panel, ""),
            "image_count": len(ir),
            "rgb_pair_count": len(rgb),
            "rgb_paired_ir_count": len(paired),
            "rgb_pair_ratio": f"{len(paired)/len(ir):.4f}" if ir else "0",
            "capture_sessions": len(sessions),
            "cameras": " ".join(f"{k}:{v}" for k, v in sorted(cams.items())),
            "existing_label_files": lfiles.get(pid, 0),
            "existing_bbox_count": sum(pbox.values()),
            "existing_class_count": len(pbox),
            "candidate_class_count": len(cand),
            "labelable_class_count": len(labelable),
            "provisional": "1" if panel in v2.PANEL_CLASSES_PROVISIONAL else "0",
            "status": "라벨 일부 존재" if pbox else "미착수",
            "notes": " / ".join(notes),
        })

    # 삭제된 반도 기록에 남긴다 (복구 가능하다는 사실 포함).
    for panel in paths.PANELS_REMOVED:
        panel_rows.append({
            "panel_id": panel.split("-")[0], "folder_name": panel,
            "panel_priority": "", "image_count": "", "rgb_pair_count": "",
            "rgb_paired_ir_count": "", "rgb_pair_ratio": "", "capture_sessions": "",
            "cameras": "", "existing_label_files": 0, "existing_bbox_count": 0,
            "existing_class_count": 0, "candidate_class_count": "",
            "labelable_class_count": "", "provisional": "",
            "status": "삭제됨(2026-08-27)",
            "notes": "3-가공.zip 에서 복구 가능",
        })

    # ---------------- 클래스별 ----------------
    class_rows = []
    for c in sorted(v2.CLASSES, key=lambda x: x.class_id):
        inst = {p: n for (p, cid), n in boxes.items() if cid == c.class_id}
        cand_panels = [p.split("-")[0] for p in v2.panels_of(c.class_name)]
        notes = list(filter(None, [c.notes]))
        if c.class_name in v2.EXCLUDED:
            notes.append("어떤 반에서도 라벨링하지 않음")
        if c.class_name in v2.RETIRED_CLASSES:
            notes.append("폐지된 클래스 — 신규 라벨 금지 (class_id 는 유지)")
        if not cand_panels and v2.is_labelable(c.class_name):
            notes.append("현존 10개 반의 후보에 없음 — 데이터 출처 확인 필요")
        class_rows.append({
            "class_id": c.class_id,
            "guide_no": c.guide_no,
            "class_name": c.class_name,
            "canonical_name": c.canonical_name,
            "label_status": c.label_status,
            "priority": v2.priority_of(c.class_name) or "",
            "existing_instance_count": sum(inst.values()),
            "panels_with_instances": " ".join(sorted(inst)),
            "candidate_panels": " ".join(cand_panels),
            "migration_required": "1" if sum(inst.values()) else "0",
            "notes": " / ".join(notes),
        })

    paths.AUDIT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("panel_inventory.csv", panel_rows),
                       ("class_inventory.csv", class_rows)):
        p = paths.AUDIT / name
        with p.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{name:<24} {len(rows)}행 -> {p}")

    live = [r for r in panel_rows if r["image_count"] != ""]
    print(f"\n현존 반 {len(live)}개 / IR {sum(r['image_count'] for r in live):,}장 "
          f"/ RGB {sum(r['rgb_pair_count'] for r in live):,}장 "
          f"/ 기존 박스 {sum(r['existing_bbox_count'] for r in live):,}개")
    print(f"라벨 실적 있는 클래스 "
          f"{sum(1 for r in class_rows if r['existing_instance_count'])}/{len(class_rows)}")


if __name__ == "__main__":
    main()
