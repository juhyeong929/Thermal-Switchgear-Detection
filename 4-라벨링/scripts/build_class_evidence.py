"""클래스별 **존재 근거**를 집계한다 (A-4).

왜 필요한가
    "현재 0개" 와 "실제로 존재하지 않음" 은 다르다. 초판 감사가 이 둘을 뭉쳐
    "21종 미검증" 으로 보고했고, 2차 감사에서 실측하니 존재 자체가 미확인인 것은
    **1종뿐**이었다. 그 구분을 문서가 아니라 **스크립트가** 유지하게 한다.

    특히 `vcb_contact` 는 `annotation_unit_basis` 에 "라벨 실적 0건" 이라고 적혀 있었으나
    참고 등급 P6 에 159박스가 실재했다. 손으로 적은 근거 문구는 이렇게 썩는다.

A-4 정책 — 존재 근거와 단위 확정을 분리한다
    이 표는 **존재 근거만** 집계한다. `annotation_unit` 을 바꾸지 않는다.
    UNKNOWN -> CONFIRMED 승격은 사람의 판정으로만 이루어진다.

등급
    CONFIRMED_PRESENT   정본 또는 참고 라벨에 박스가 실재한다
    LIKELY_PRESENT      시험에서 라벨러가 실제로 그렸다 (박스 실적은 없음)
    NOT_YET_OBSERVED    반 후보이고 가이드 참조 카드에 있으나 어디에도 박스가 없다
    UNKNOWN             후보 반이 없거나 근거가 전혀 없다
    (배포 여부는 별도 열 deployable 로 표시한다 — 등급과 섞지 않는다)

출력
    reports/data_audit/class_evidence.csv

사용:
    python scripts/build_class_evidence.py
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
SKIP_TXT = {"classes.txt", "obj.names", "train.txt", "val.txt"}

# 참고(reference) 등급 라벨의 구 class_id -> v2 class_name. 반마다 뜻이 다르다.
# 근거: schemas/class_migration_26_to_28.csv (old 15 는 반에 따라 split)
REF_SOURCES = {
    "P6_6ban": ("P6", {15: "cable_head", 17: "vcb_contact"}),
    "P9_9ban": ("P9", {20: "capacitor", 21: "mccb", 22: "mccb_contact",
                       23: "acb_contact"}),
}


def canonical_counts():
    f = paths.AUDIT / "class_inventory.csv"
    with f.open(encoding="utf-8-sig") as fh:
        return {r["class_name"]: int(r["existing_instance_count"])
                for r in csv.DictReader(fh)}


def reference_counts():
    """참고 등급 박스 수를 원본 스냅샷에서 직접 센다. 손으로 적지 않는다."""
    out = Counter()
    for folder, (_, mapping) in REF_SOURCES.items():
        d = paths.BACKUP / folder
        if not d.is_dir():
            continue
        for p in d.rglob("*.txt"):
            if p.name in SKIP_TXT:
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.split()
                if len(s) >= 5:
                    name = mapping.get(int(float(s[0])))
                    if name:
                        out[name] += 1
    return out


def trial_counts():
    """라벨러별 박스 수. 시험에서 '실제로 그렸는가' 의 근거."""
    per = defaultdict(Counter)
    for d in sorted(TRIAL.glob("annotator_*")):
        y = d / "yolo"
        if not y.is_dir():
            continue
        for p in y.glob("*.txt"):
            if p.name in SKIP_TXT:
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.split()
                if len(s) >= 5:
                    per[d.name][int(float(s[0]))] += 1
    return per


def seed_exposure():
    """반별 시드 장수. 그 클래스가 시드에서 만날 수 있는 최대 노출."""
    f = paths.LABELING / "seed" / "seed_candidates.csv"
    if not f.exists():
        return Counter()
    with f.open(encoding="utf-8-sig") as fh:
        return Counter(r["panel"] for r in csv.DictReader(fh))


def guide_cards():
    """반별 참조 카드에 그 클래스가 실제로 적혀 있는가."""
    out = {}
    d = paths.REPORTS / "labeling" / "class_reference"
    for m in d.glob("*.md"):
        out[m.stem] = m.read_text(encoding="utf-8")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    canon = canonical_counts()
    ref = reference_counts()
    tri = trial_counts()
    seed = seed_exposure()
    cards = guide_cards()
    people = sorted(tri)

    rows = []
    for c in v2.labelable_classes():
        n = c.class_name
        pans = v2.panels_of(n)
        ca, rf = canon.get(n, 0), ref.get(n, 0)
        counts = [tri[p][c.class_id] for p in people]
        drew = sum(1 for x in counts if x > 0)
        card = sum(1 for p in pans if p in cards and c.canonical_name in cards[p])

        if ca > 0 or rf > 0:
            grade = "CONFIRMED_PRESENT"
        elif drew > 0:
            grade = "LIKELY_PRESENT"
        elif pans and card > 0:
            grade = "NOT_YET_OBSERVED"
        else:
            grade = "UNKNOWN"

        unit = v2.annotation_unit(n)
        rows.append({
            "class_id": c.class_id, "guide_no": c.guide_no,
            "class_name": n, "canonical_name": c.canonical_name,
            "label_status": c.label_status,
            "panel_candidates": " ".join(v2.panel_id(p) for p in pans),
            "annotation_unit": unit,
            "deployable": int(v2.unit_confirmed(n)),
            "canonical_boxes": ca, "reference_boxes": rf,
            **{f"trial_{p.replace('annotator_', '')}": tri[p][c.class_id]
               for p in people},
            "trial_annotators_drew": drew, "trial_annotators_total": len(people),
            "seed_exposure_images": sum(seed.get(p, 0) for p in pans),
            "guide_reference_cards": card,
            "evidence_grade": grade,
            "unit_basis": v2.annotation_unit_basis(n),
        })

    f = paths.AUDIT / "class_evidence.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("클래스별 존재 근거 — 정본·참고·시험·참조카드 4개 소스 집계\n")
    hdr = f"{'id':>3} {'클래스':<14}{'정본':>6}{'참고':>6}"
    hdr += "".join(f"{p.replace('annotator_', ''):>4}" for p in people)
    hdr += f"{'그림':>5}{'배포':>5}  등급"
    print(hdr)
    for r in sorted(rows, key=lambda x: (x["evidence_grade"],
                                         -x["canonical_boxes"] - x["reference_boxes"])):
        line = f"{r['class_id']:>3} {r['canonical_name']:<14}"
        line += f"{r['canonical_boxes']:>6}{r['reference_boxes']:>6}"
        line += "".join(f"{r[f'trial_{p.replace(chr(97) and 'annotator_', '')}']:>4}"
                        for p in people)
        line += f"{r['trial_annotators_drew']:>5}{'O' if r['deployable'] else 'X':>5}"
        print(f"{line}  {r['evidence_grade']}")

    g = Counter(r["evidence_grade"] for r in rows)
    print(f"\n등급: " + " · ".join(f"{k} {v}" for k, v in sorted(g.items())))
    print(f"배포 대상 {sum(r['deployable'] for r in rows)}종 / "
          f"라벨 대상 {len(rows)}종")

    # 근거 문구가 실측과 어긋나는 것을 잡는다. vcb_contact 사건의 재발 방지.
    bad = [r for r in rows
           if "0건" in r["unit_basis"]
           and (r["canonical_boxes"] > 0 or r["reference_boxes"] > 0)]
    if bad:
        print("\n[경고] annotation_unit_basis 가 '0건' 이라고 적었는데 박스가 실재한다")
        for r in bad:
            print(f"  {r['canonical_name']}: 정본 {r['canonical_boxes']} · "
                  f"참고 {r['reference_boxes']}  <- {r['unit_basis']}")
    else:
        print("\n근거 문구 ↔ 실측 대조: 불일치 없음")
    print(f"\n-> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
