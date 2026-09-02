"""가공 대상 종합표를 **스키마에서** 재생성한다.

왜 이 스크립트가 필요한가
--------------------------
이전 발주처 가이드(HTML)에는 `03 REFERENCE — 가공 대상 종합` 표가 있었다.
클래스 번호 1~28 · 한글명 · 가공여부(O/!/X) · 그렇게 정한 근거가 한 장에 있었고,
`classes_v2.py` 와 `labeling_rules.py` 는 그 표를 출처로 적고 있었다.

2026-09-02 배포판(PDF)에는 **그 표가 없다.** 반별 가공대상 목록만 있고
클래스 번호도 가공여부 기호도 없다. 즉 현행 배포 가이드만 보고는

    · class_id 가 왜 그 번호인가
    · 부스바 · 케이블 · ACB 접촉부가 왜 제외인가

를 설명할 수 없다. 근거 자체는 `classes_v2.py` 의 `description`(가이드 비고 원문)에
옮겨져 있으므로, 사람이 읽을 표를 **코드에서 다시 만들어** 그 자리를 메운다.

문서에 손으로 적지 않는다. 스키마를 고치면 이 표가 따라 바뀐다.

출력: reports/labeling/generated/class_reference_table.md
      reports/labeling/generated/class_reference_table.csv
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

OUT = paths.REPORTS / "labeling" / "generated"

# 가이드 종합표의 기호. 폐지는 가이드에 없던 상태이므로 기호를 새로 만들지 않고 글자로 적는다.
MARK = {v2.LABEL: "O", v2.CAUTION: "!", v2.EXCLUDE: "X", v2.RETIRED: "폐지"}


def basis(c):
    """그 상태로 정한 근거. 가이드 원문이 있으면 그것을, 없으면 프로젝트 판정을 적는다."""
    if c.description:
        return c.description          # 가이드 '비고' 열 원문
    if c.label_status == v2.RETIRED:
        return c.notes or "가이드 개정으로 폐지"
    return "가이드 비고 없음 — 기본 가공대상"


def rows():
    for c in sorted(v2.CLASSES, key=lambda x: x.class_id):
        yield {
            "guide_no": c.guide_no,
            "class_id": c.class_id,
            "class_name": c.class_name,
            "canonical_name": c.canonical_name,
            "label_status": c.label_status,
            "mark": MARK[c.label_status],
            "basis": basis(c),
            "annotation_unit": v2.annotation_unit(c.class_name),
            "unit_confirmed": "Y" if v2.unit_confirmed(c.class_name) else "N",
            "unit_basis": v2.annotation_unit_basis(c.class_name),
            "panels": " ".join(v2.panel_id(p) for p in v2.panels_of(c.class_name)),
            "aliases": " | ".join(c.alias),
            "notes": c.notes,
        }


FIELDS = ["guide_no", "class_id", "class_name", "canonical_name", "label_status",
          "mark", "basis", "annotation_unit", "unit_confirmed", "unit_basis",
          "panels", "aliases", "notes"]

HEADER = """# 가공 대상 종합표 (재생성)

> **이 파일은 손으로 고치지 않는다.** `scripts/build_reference_table.py` 가
> `schemas/classes_v2.py` 에서 만든다. 스키마를 고치고 다시 돌린다.

## 이 표가 왜 여기 있는가

이전 발주처 가이드(HTML)의 `03 REFERENCE — 가공 대상 종합` 표가
**2026-09-02 배포판(PDF)에서 없어졌다.** 새 판은 반별 가공대상 목록만 두고
클래스 번호·가공여부 기호·근거 열을 두지 않는다.

그 결과 **현행 배포 가이드만으로는 다음을 설명할 수 없다.**

```
· class_id 가 왜 그 번호인가            (가이드번호 - 1 의 기계적 변환)
· 부스바 · 케이블 · ACB 접촉부가 왜 제외인가
```

근거 문장 자체는 이전 판에서 `classes_v2.py` 의 `description` 으로 옮겨져 있다.
아래 표는 그것을 사람이 읽을 형태로 되살린 것이다.

```
현행 배포 가이드   {pdf}
이전 판(종합표 원문 출처)  {html}
                   워크트리에서 삭제됨 — git 이력에서만 열람 가능
단일 출처          schemas/classes_v2.py
```

## 상태 기호

| 기호 | 상태 | 뜻 |
|---|---|---|
| `O` | 가공 | 항상 라벨링 |
| `!` | 주의 | 식별 가능할 때만 라벨. 판별 불가면 미라벨/Ignore |
| `X` | 제외 | 물체는 있지만 어떤 반에서도 그리지 않는다 |
| `폐지` | 폐지 | 가이드 개정으로 **클래스 자체가 없어졌다.** 신규 라벨 금지 |

**`X`(제외)와 `폐지`는 다르다.** 제외는 "있지만 그리지 않는다", 폐지는
"그 이름의 클래스가 더 이상 없다" 이다. 둘을 한 칸에 합치면 제외 3종의 근거를
설명할 수 없게 되므로 코드에서도 집합을 나눠 둔다
(`EXCLUDED` / `RETIRED_CLASSES`).

## 종합표

"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    data = list(rows())

    csv_path = OUT / "class_reference_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(data)

    lines = ["| # | id | 클래스 | 상태 | 근거 | 세는 단위 | 출현 반 |",
             "|---:|---:|---|:---:|---|---|---|"]
    for r in data:
        unit = v2.UNIT_DESC[r["annotation_unit"]] if r["unit_confirmed"] == "Y" else "**미확정**"
        if r["label_status"] in (v2.EXCLUDE, v2.RETIRED):
            unit = "—"
        lines.append(f"| {r['guide_no']} | {r['class_id']} | {r['canonical_name']} "
                     f"| `{r['mark']}` | {r['basis']} | {unit} | {r['panels'] or '—'} |")

    n = {s: sum(1 for c in v2.CLASSES if c.label_status == s)
         for s in (v2.LABEL, v2.CAUTION, v2.EXCLUDE, v2.RETIRED)}
    ok, tot = v2.unit_counts()
    tail = (f"\n**클래스 {len(v2.CLASSES)}개** — 가공 {n[v2.LABEL]} · 주의 {n[v2.CAUTION]} · "
            f"제외 {n[v2.EXCLUDE]} · 폐지 {n[v2.RETIRED]}\n\n"
            f"**라벨 대상 {tot}종 중 단위 확정 {ok}종.** 미확정 "
            f"{tot - ok}종은 라벨러에게 배포하지 않는다 (NQ-13).\n")

    md_path = OUT / "class_reference_table.md"
    md_path.write_text(
        HEADER.format(pdf=paths.GUIDE_PDF.name, html=paths.GUIDE_HTML.name)
        + "\n".join(lines) + "\n" + tail, encoding="utf-8")

    print(f"가공 대상 종합표 재생성 — {len(data)}행")
    print(f"  가공 {n[v2.LABEL]} · 주의 {n[v2.CAUTION]} · 제외 {n[v2.EXCLUDE]} · "
          f"폐지 {n[v2.RETIRED]} · 단위 확정 {ok}/{tot}")
    print(f"-> {md_path}")
    print(f"-> {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
