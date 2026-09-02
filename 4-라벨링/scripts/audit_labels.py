"""pilot 에 남아 있는 기존 라벨을 전수 조사한다.

pilot 에는 같은 이미지를 여러 번 담은 폴더가 섞여 있다 (1차 작업본 / A1·A2 검수본 /
검수완료본 / 실험용 재인코딩본). 어느 것이 정본인지는 이 스크립트가 정하지 않는다.
소스별로 따로 세고 서로 얼마나 다른지를 수치로 남긴 뒤, 정본 판정은 사람이 한다.
-> reports/decisions/DEC-005-existing-label-provenance.md 의 OPEN QUESTION

출력: reports/data_audit/label_source_inventory.csv   소스별 요약
      reports/data_audit/label_instance_inventory.csv 소스x반x클래스 박스 수
      reports/data_audit/label_source_overlap.csv      소스 간 중복 이미지/불일치

원본은 읽기만 한다.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas.classes_v2 import KOREAN, NAMES  # noqa: E402

# pilot/classes.py 의 26개 스키마 (구 스키마). 순서를 바꾸지 않는다.
OLD26 = [
    "core_iron", "epoxy_surface", "mold_tr_contact", "power_fuse", "lbs",
    "lbs_primary", "lbs_secondary", "cl_power_fuse", "la", "transformer",
    "transformer_contact", "ct_transformer", "mof_fuse", "ct_transformer_contact",
    "pt", "branch_contact", "incoming_contact", "vcb_contact", "ct", "ct_contact",
    "capacitor", "mccb", "mccb_contact", "acb_contact", "busbar", "cable",
]
OLD26_KO = {
    0: "철심부", 1: "에폭시 표면", 2: "몰드변압기 접촉부", 3: "전력퓨즈", 4: "LBS",
    5: "LBS 1차측 접촉부", 6: "LBS 2차측 접촉부", 7: "한류형 전력퓨즈", 8: "LA",
    9: "변압기", 10: "변압기 접촉부", 11: "변류기", 12: "MOF 1차측 전력퓨즈",
    13: "변류기 접촉부", 14: "PT", 15: "분기 접촉부", 16: "인입선로 접촉부",
    17: "VCB 접촉부", 18: "CT", 19: "CT 접촉부", 20: "콘덴서", 21: "MCCB",
    22: "MCCB 접촉부", 23: "ACB 접촉부", 24: "부스바", 25: "케이블",
}

# (소스명, 상대경로, 스키마, 역할)
#   role=primary  사람이 직접 그린 라벨. 승계 대상.
#   role=derived  실험용으로 재인코딩·병합된 사본. 승계 대상 아님.
SOURCES = [
    ("IR1_1반_1차",      "IR1_1반",            "26", "primary"),
    ("IR1_1반_A1검수",   "IR1_1반_A1검수",     "26", "primary"),
    ("IR1_1반_A2검수",   "IR1_1반_A2검수",     "26", "primary"),
    ("A3검수완료",       "A3 검수완료",        "26", "primary"),
    ("_p1only",          "_p1only",            "26", "primary"),
    ("_p3",              "_p3",                "26", "primary"),
    ("_p4",              "_p4",                "26", "primary"),
    ("IR1_3반",          "IR1_3반",            "26", "primary"),
    ("data_labels_ir",   "data/labels_ir",     "26", "derived"),
    ("data_labels_rgb",  "data/labels_rgb",    "26", "derived"),
    ("data_labels_pred", "data/labels_pred",   "26", "derived"),
    ("dataset_contact1", "dataset/contact_stage1", "nc1", "derived"),
    ("dataset_contact2", "dataset/contact_stage2", "nc1", "derived"),
]

SKIP_NAMES = {"train.txt", "val.txt", "test.txt", "classes.txt", "obj.names"}
PANEL_RE = re.compile(r"_(P\d+)_")


def read_labels(root):
    """소스 폴더 아래 모든 YOLO txt 를 {stem: [(cls, cx, cy, w, h), ...]} 로 읽는다."""
    out = {}
    if not root.exists():
        return out
    for f in root.rglob("*.txt"):
        if f.name in SKIP_NAMES or f.name.startswith("._"):
            continue
        boxes = []
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                p = line.split()
                if len(p) < 5:
                    continue
                try:
                    boxes.append((int(float(p[0])), *[float(x) for x in p[1:5]]))
                except ValueError:
                    continue
        except OSError:
            continue
        out[f.stem] = boxes
    return out


def panel_of(stem):
    m = PANEL_RE.search(stem)
    return m.group(1) if m else "UNKNOWN"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    paths.AUDIT.mkdir(parents=True, exist_ok=True)

    loaded = {}
    src_rows, inst_rows = [], []

    for name, rel, schema, role in SOURCES:
        labels = read_labels(paths.PILOT / rel)
        loaded[name] = labels
        n_box = sum(len(v) for v in labels.values())
        n_empty = sum(1 for v in labels.values() if not v)
        panels = Counter(panel_of(s) for s in labels)
        classes = Counter(b[0] for v in labels.values() for b in v)
        src_rows.append({
            "source": name, "rel_path": rel, "schema": schema, "role": role,
            "exists": "1" if (paths.PILOT / rel).exists() else "0",
            "label_files": len(labels), "empty_files": n_empty, "boxes": n_box,
            "panels": " ".join(f"{k}:{v}" for k, v in sorted(panels.items())),
            "distinct_classes": len(classes),
        })
        for (pan, cls), n in Counter(
            (panel_of(s), b[0]) for s, v in labels.items() for b in v
        ).items():
            inst_rows.append({
                "source": name, "role": role, "panel_id": pan,
                "old_class_id": cls,
                "old_class_name": OLD26[cls] if schema == "26" and cls < 26 else "",
                "old_class_ko": OLD26_KO.get(cls, "") if schema == "26" else "(단일클래스)",
                "boxes": n,
            })

    # --- 소스 간 겹침: 같은 stem 을 여러 소스가 들고 있는가, 내용은 같은가 -------
    ov_rows = []
    prim = [s for s in SOURCES if s[3] == "primary"]
    for i, (a, *_rest_a) in enumerate(prim):
        for (b, *_rest_b) in prim[i + 1:]:
            A, B = loaded[a], loaded[b]
            shared = set(A) & set(B)
            if not shared:
                continue
            same = sum(1 for s in shared if A[s] == B[s])
            ov_rows.append({
                "source_a": a, "source_b": b,
                "a_files": len(A), "b_files": len(B),
                "shared_files": len(shared),
                "identical_labels": same,
                "differing_labels": len(shared) - same,
                "shared_ratio_a": f"{len(shared)/len(A):.3f}" if A else "",
            })

    def dump(path, rows, fields):
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        return path

    p1 = dump(paths.AUDIT / "label_source_inventory.csv", src_rows, list(src_rows[0]))
    p2 = dump(paths.AUDIT / "label_instance_inventory.csv", inst_rows,
              ["source", "role", "panel_id", "old_class_id", "old_class_name",
               "old_class_ko", "boxes"])
    p3 = dump(paths.AUDIT / "label_source_overlap.csv", ov_rows,
              ["source_a", "source_b", "a_files", "b_files", "shared_files",
               "identical_labels", "differing_labels", "shared_ratio_a"])

    print("소스별 라벨 현황")
    for r in src_rows:
        flag = "" if r["exists"] == "1" else "  [경로 없음]"
        print(f"  {r['source']:<18} {r['role']:<8} 파일 {r['label_files']:>5} "
              f"박스 {r['boxes']:>6}  {r['panels']}{flag}")
    prim_boxes = sum(r["boxes"] for r in src_rows if r["role"] == "primary")
    print(f"\nprimary 소스 박스 합계(중복 포함) {prim_boxes}")
    print(f"\n-> {p1.name} / {p2.name} / {p3.name}")


if __name__ == "__main__":
    main()
