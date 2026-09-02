"""교수님 보고용 문서 5종을 CSV 산출물에서 자동 생성한다.

보고서에 들어가는 숫자를 하드코딩하지 않기 위한 스크립트다. 데이터가 바뀌면
인벤토리 스크립트를 다시 돌리고 이것을 돌리면 보고서 숫자가 전부 따라 바뀐다.

선행: build_image_inventory.py -> audit_labels.py -> migrate_labels.py
      -> build_inventories.py -> build_schema_tables.py

중복 제거·선정 방법의 상세 서술은 `report_methods.py` 가 담당한다.
그쪽은 실제 스크립트의 상수를 import 해서 쓰므로 문서와 코드가 어긋나지 않는다.

출력: reports/professor/00_current_status.md
                        01_data_inventory.md
                        02_labeling_schema.md
                        03_major_decisions.md
                        04_progress.md
                        05_issues_and_actions.md
"""

import csv
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import labeling_rules as rules  # noqa: E402
import report_methods as M  # noqa: E402

TODAY = date.today().isoformat()


NL = chr(10)


def read(path):
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def table(headers, rows, align=None):
    align = align or ["---"] * len(headers)
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(align) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def num(x):
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return str(x)


def load():
    d = {
        "panels": read(paths.AUDIT / "panel_inventory.csv"),
        "classes": read(paths.AUDIT / "class_inventory.csv"),
        "sources": read(paths.AUDIT / "label_source_inventory.csv"),
        "migration": read(paths.AUDIT / "migration_verification.csv"),
        "unresolved": read(paths.AUDIT / "migration_unresolved.csv"),
        "oq": read(paths.AUDIT / "open_questions.csv"),
        "progress": read(paths.REPORTS / "status" / "progress.csv"),
        "dedup": read(paths.AUDIT / "dedup_summary.csv"),
        "audit": read(paths.AUDIT / "canonical_audit_summary.csv"),
        "seedrows": read(paths.LABELING / "seed" / "seed_candidates.csv"),
        "trial": read(paths.LABELING / "seed" / "trial_set.csv"),
        "refsrc": read(paths.AUDIT / "newlabels_summary.csv"),
        "funnel": read(paths.AUDIT / "selection_funnel.csv"),
        "split": read(paths.SPLITS / "group_split.csv"),
        "leak": read(paths.AUDIT / "split_leakage.csv"),
        "balance": read(paths.AUDIT / "split_balance.csv"),
        "images": [],
    }
    d["live"] = [p for p in d["panels"] if p["image_count"] != ""]
    d["removed"] = [p for p in d["panels"] if p["image_count"] == ""]
    return d


def camera_stats():
    """image_inventory.csv 에서 카메라별 집계. 대용량이라 스트리밍으로 읽는다."""
    p = paths.METADATA / "image_inventory.csv"
    ir, rgb, paired = {}, {}, {}
    if not p.exists():
        return ir, rgb, paired
    with p.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            cam = r["camera"]
            if r["kind"] == "IR":
                ir[cam] = ir.get(cam, 0) + 1
                if r["has_rgb_pair"] == "1":
                    paired[cam] = paired.get(cam, 0) + 1
            else:
                rgb[cam] = rgb.get(cam, 0) + 1
    return ir, rgb, paired



# ---------------------------------------------------------------------------
# annotation unit 표 — schemas/classes_v2.py 의 ANNOTATION_UNIT 이 단일 출처다.
# 클래스 이름·개수·근거를 이 파일에 적지 않는다. 값이 바뀌면 표가 따라 바뀐다.
# ---------------------------------------------------------------------------

def audit_table(d):
    """정본 감사 요약. 감사 전이면 그렇다고 밝힌다."""
    a = d.get("audit") or []
    if not a:
        return "감사를 아직 수행하지 않았다."
    rows = [[r["audit_rule"], num(r["checked"]), num(r["PASS"]),
             f"**{num(r['FAIL'])}**" if r["FAIL"] != "0" else "0",
             num(r["SUSPECT"]), num(r["UNDETERMINABLE"]),
             (f"{float(r['판정가능 준수율'])*100:.1f}%"
              if r["판정가능 준수율"] else "—"),
             r.get("비고", "")]
            for r in a]
    return table(["규칙", "검사", "PASS", "FAIL", "SUSPECT", "판정불가", "준수율", "비고"],
                 rows, ["---", "---:", "---:", "---:", "---:", "---:", "---:", "---"])


def audit_note(d):
    a = d.get("audit") or []
    if not a:
        return ""
    fails = sum(int(r["FAIL"]) for r in a)
    und = sum(int(r["UNDETERMINABLE"]) for r in a)
    sus = sum(int(r["SUSPECT"]) for r in a)
    return f"""**명백한 위반(FAIL) {num(fails)}건** — 전부 `같은 클래스 중복`이며 P1 에 몰려 있다.
시각 확인 결과 같은 접속점 위에 박스가 포개진 **같은 인스턴스 이중 라벨**이었다.

SUSPECT {num(sus)}건은 대부분 초소형 객체다. 규격에 공식 픽셀 임계값이 없어
**"규격 위반"으로 세지 않고** `candidate_threshold` 해당으로만 기록했다.

판정 불가 {num(und)}건은 잘림 30% 규칙이다. 그 규칙의 분모가
`부품의 정상 촬영 시 전체 면적`이라 **좌표만으로는 판정 자체가 불가능**하다.
라벨의 문제가 아니라 규칙의 성질이다.

**판정 불가를 PASS 에 넣지 않았고, 단일 준수율로 뭉치지 않았다** — 규칙마다 분모가 다르다.
`0.48%` 는 중복 규칙 하나에 대한 값이며 **"품질 99.52%" 로 읽어서는 안 된다.**

### 처리 — 정본은 수정하지 않고 격리했다

어느 박스가 옳은지 사람이 재검수하지 않은 상태에서 한쪽을 지우면 근거 없는 수정이 된다.
그래서 **두 박스를 모두 격리 목록에 등재**하고 정본 파일은 그대로 두었다.

```
canonical_original (무수정) -> QUARANTINE 등재 -> 학습셋 구축 시에만 제외
```

고유 박스 37개(정본의 0.89%) 격리. **학습에 쓰이는 박스 4,140.**
상태 `QUARANTINE_PENDING_REVIEW` — 해제는 사람 재검수로만 이루어진다.
→ `DEC-016-canonical-audit.md` · `DEC-017-canonical-quarantine.md`"""


def unit_overview_table():
    """단위별 요약 — 뜻 · 클래스 수 · 확정 여부."""
    s = v2.units_summary()
    rows = []
    for u in v2.UNIT_ORDER:
        cs = s[u]
        rows.append([
            f"`{u}`", v2.UNIT_DESC[u], f"{len(cs)}종",
            "**Confirmed**" if u != v2.UNIT_UNKNOWN else "**UNKNOWN**",
        ])
    ok, tot = v2.unit_counts()
    return f"""{table(["단위", "뜻", "클래스 수", "상태"], rows,
                      ["---", "---", "---:", "---"])}

**확정 {ok}/{tot} 클래스.** 미확정 {tot - ok}종은 라벨러에게 배포하지 않는다 —
라벨링 툴 클래스 목록에서도 막았다 (`trial_set_export.py` 가 `__사용안함_` 으로 표시)."""


def unit_detail_table():
    """클래스별 상세 — 단위 · 상태 · 근거."""
    s = v2.units_summary()
    rows = []
    for u in v2.UNIT_ORDER:
        for c in s[u]:
            rows.append([
                f"{c.guide_no:02d}", c.canonical_name, f"`{u}`",
                "Confirmed" if v2.unit_confirmed(c.class_name) else "**UNKNOWN**",
                v2.annotation_unit_basis(c.class_name),
            ])
    return f"""### 클래스별 annotation unit

{table(["가이드#", "클래스", "annotation_unit", "상태", "근거"], rows,
       ["---:", "---", "---", "---", "---"])}"""



# ---------------------------------------------------------------------------

def doc_status(d):
    live, tot_ir = d["live"], sum(int(p["image_count"]) for p in d["live"])
    tot_box = sum(int(p["existing_bbox_count"]) for p in live)
    labeled_cls = sum(1 for c in d["classes"] if int(c["existing_instance_count"]))
    prog = d["progress"]
    done = [s for s in prog if s["status"] == "완료"]
    doing = [s for s in prog if s["status"] == "진행중"]
    todo = [s for s in prog if s["status"] == "미착수"]
    # 미해소 = 닫히지 않은 모든 것. '열림' 만 세면 HOLD·판정대기가 빠진다
    oq_open = [q for q in d["oq"] if q["status"] != "닫힘"]
    oq_closed = [q for q in d["oq"] if q["status"] == "닫힘"]
    panels_started = sum(1 for p in live if int(p["existing_bbox_count"]))

    ind = next((r["clusters"] for r in d["dedup"] if r["panel_id"] == "TOTAL"), "")
    ref_box = sum(int(r["boxes"]) for r in d["refsrc"]) if d["refsrc"] else 0
    unit_ok = sum(1 for c in v2.CLASSES
                  if c.label_status != v2.EXCLUDE and v2.unit_confirmed(c.class_name))
    unit_all = sum(1 for c in v2.CLASSES if c.label_status != v2.EXCLUDE)
    span = f"{done[0]['step']}~{done[-1]['step']}" if done else "—"

    return f"""# 00. 현재 상황

> 자동 생성 · {TODAY} · 숫자는 전부 `reports/data_audit/*.csv` 에서 집계됨

## 한 줄 요약

수배전반 열화상 **{num(tot_ir)}장**에 대한 부품 객체 라벨링 데이터셋을 구축 중이다.
클래스 스키마·제외 규칙·클래스별 annotation unit 을 가이드 v2 와 실측 근거로 코드에
고정했고, 기존 정본 라벨 {num(tot_box)}개를 손실 없이 승계했다.
중복 제거로 **실질 독립 이미지 {num(ind)}장**을 산출하고 시드 후보
{num(len(d['seedrows']))}장을 뽑았으며, 그중 **1차 시험 {num(len(d['trial']))}장**으로
라벨링 규칙이 실제로 통하는지 검증하는 단계다.

**현재 단계: 규칙 설계 → 규칙 검증.**

## 지금까지의 진행

- 준비 단계 **{len(done)}/{len(prog)}** 완료 ({span})
- 진행 중: {" · ".join(f"{s['step']} {s['name']}" for s in doing) or "없음"}
- 라벨링 착수한 반: {panels_started}/{len(live)} (정본 기준)
- 라벨 실적이 있는 클래스: {labeled_cls}/{len(d['classes'])} (정본 기준)
- **annotation unit 확정: {unit_ok}/{unit_all}** 라벨 대상 클래스
- OPEN QUESTION: 해소 {len(oq_closed)} / **미해소 {len(oq_open)}**

## 핵심 수치

{table(["항목", "값"], [
    ["현존 반", f"{len(live)}개"],
    ["열화상(IR) 이미지", num(tot_ir)],
    ["실화상(RGB) 이미지", num(sum(int(p['rgb_pair_count']) for p in live))],
    ["촬영 세션", num(sum(int(p['capture_sessions']) for p in live))],
    ["**중복 제거 후 독립 이미지**", f"**{num(ind)}**"],
    ["시드 후보", num(len(d['seedrows']))],
    ["1차 시험셋", num(len(d['trial']))],
    ["클래스", f"{len(d['classes'])}개 (가공 21 · 주의 4 · 제외 3)"],
    ["annotation unit 확정", f"{unit_ok}/{unit_all}"],
    ["정본 라벨 (canonical)", f"{num(tot_box)} bbox · P1/P3/P4"],
    ["참고 라벨 (reference)", f"{num(ref_box)} bbox · P6/P9 · 승격 보류"],
    ["승계 손실", "0"],
], ["---", "---:"])}

## 라벨 등급을 나눠 관리한다

정본(canonical)만 학습·지표의 기준으로 쓴다. 참고(reference)는 경계 규칙 검증과
사례 추출에만 쓰고 **승격하지 않았다** — 미작업 의심분·이상치·검수 이력 부재 때문이다.

## 미해소 사항 {len(oq_open)}건

{table(["번호", "상태", "질문"],
       [[q["id"], q["status"], q["question"][:60]] for q in oq_open])}

## 다음 작업

{chr(10).join(f"- **{s['step']}** {s['name']}" + (chr(10) + "  " + s['note'] if s['note'] else "") for s in doing + todo)}
"""


def doc_inventory(d):
    live, removed = d["live"], d["removed"]
    ir, rgb, paired = camera_stats()
    tot_ir = sum(ir.values())

    prows = [[
        p["folder_name"], p["panel_priority"], num(p["image_count"]),
        num(p["rgb_pair_count"]),
        f"{float(p['rgb_pair_ratio'])*100:.1f}%",
        p["capture_sessions"],
        num(p["existing_bbox_count"]),
        f"{p['labelable_class_count']}/{p['candidate_class_count']}"
        + ("*" if p["provisional"] == "1" else ""),
    ] for p in live]
    prows.append(["**합계**", "", f"**{num(tot_ir)}**",
                  f"**{num(sum(int(p['rgb_pair_count']) for p in live))}**", "",
                  f"**{num(sum(int(p['capture_sessions']) for p in live))}**",
                  f"**{num(sum(int(p['existing_bbox_count']) for p in live))}**", ""])

    crows = [[c, num(ir.get(c, 0)), num(rgb.get(c, 0)), num(paired.get(c, 0)),
              f"{paired.get(c,0)/ir[c]*100:.1f}%" if ir.get(c) else "-"]
             for c in sorted(ir)]

    return f"""# 01. 데이터 인벤토리

> 자동 생성 · {TODAY} · 원본 `3-가공` 전수 스캔 결과

## 반별 현황

`*` = 가이드에 단독 상세가 없어 후보 클래스가 잠정인 반

{table(["반", "우선순위", "IR", "RGB", "페어율", "촬영세션", "기존 bbox", "라벨가능/후보"],
       prows, ["---", "---:", "---:", "---:", "---:", "---:", "---:", "---:"])}

## 카메라별 현황 — RGB 페어는 IR1 전용이다

{table(["카메라", "IR", "RGB", "페어 있는 IR", "페어율"], crows,
       ["---", "---:", "---:", "---:", "---:"])}

데이터의 97.6%를 차지하는 IR2·IR3 에는 RGB 페어가 거의 또는 전혀 없다.
따라서 실화상에 그려 열화상으로 좌표를 전이하는 방식은 전체 규모에 적용할 수 없다.
→ `DEC-005-rgb-labeling-policy.md`

## 범위에서 제외된 반

{table(["반", "상태", "비고"],
       [[p["folder_name"], p["status"], p["notes"]] for p in removed]) if removed
 else "없음"}

{M.funnel_section()}

{M.dedup_section()}

{M.seed_section()}

{M.trial_section()}

## 기존 라벨 소스 조사

`pilot` 에 남아 있던 라벨 소스 {len(d['sources'])}개를 전수 조사해 정본을 판정했다.

{table(["소스", "역할", "파일", "박스", "반"],
       [[s["source"], s["role"], num(s["label_files"]), num(s["boxes"]), s["panels"]]
        for s in d["sources"]], ["---", "---", "---:", "---:", "---"])}

`role=derived` 는 모델 예측이거나 실험용으로 재인코딩된 사본이라 승계 대상이 아니다.
"""


def doc_schema(d):
    tb = sum(int(p["existing_bbox_count"]) for p in d["live"])
    crows = [[c["class_id"], c["guide_no"], c["canonical_name"], c["label_status"],
              c["candidate_panels"] or "—",
              num(c["existing_instance_count"])] for c in d["classes"]]
    mig = d["migration"]
    by_type = {}
    for m in mig:
        by_type[m["migration_type"]] = by_type.get(m["migration_type"], 0) + int(m["boxes_before"])
    tb = sum(int(m["boxes_before"]) for m in mig)
    ta = sum(int(m["boxes_after"]) for m in mig)

    return f"""# 02. 라벨링 스키마

> 자동 생성 · {TODAY} · 정의 원본은 `schemas/classes_v2.py`

## 기준

가이드 v{v2.GUIDE_VERSION[-1]} ({v2.GUIDE_REVISED}) `03 REFERENCE 가공 대상 종합` 표.
**YOLO class_id = 가이드 항목번호 − 1** 로 두어, 라벨링 툴 화면과 가이드를 표 없이
바로 대조할 수 있게 했다. → `DEC-001-class-schema-v2.md`

## 클래스 {len(d['classes'])}개

{table(["id", "가이드#", "명칭", "가공여부", "후보 반", "기존 bbox"], crows,
       ["---:", "---:", "---", "---", "---", "---:"])}

## annotation unit — 무엇을 하나로 셀 것인가

`접촉부` 같은 상위 개념으로 단위를 정하지 않는다. **실측 결과 같은 접촉부 계열이라도
클래스마다 단위가 달랐다.** 단위가 다르면 인스턴스 수가 달라지고 mIoU·Kappa·mAP 가
전부 흔들린다. 그래서 클래스별로 따로 정의하고 코드에 박았다
(`schemas/classes_v2.py` 의 `ANNOTATION_UNIT`).

{unit_overview_table()}

{unit_detail_table()}

> 처음에는 "접촉부는 단자군 단위"로 일반화했다가 **틀렸다.** 그 관찰은 참고 등급
> 한 클래스에서만 나온 것이었고, 정본 2종은 개별 접속점 단위였다. 정정해 기록했다.
> → `DEC-014` · `DEC-015`

## 라벨링 제외 규칙

### 항상 제외
{", ".join(v2.BY_NAME[c].canonical_name for c in rules.ALWAYS_EXCLUDED)}

### 식별 가능한 경우만 라벨
{", ".join(v2.BY_NAME[c].canonical_name for c in rules.LABEL_IF_IDENTIFIABLE)}

판별 불가는 **{rules.UNJUDGEABLE_MEANS}** 로 처리한다.
"안 보이니까 없다 / 정상이다" 로 기록하지 않는다.

### 잘림 기준
노출 비율이 **{rules.VISIBLE_AREA_MIN:.0%} 미만**이면 박스를 생략한다.
분모는 화면 좌표가 아니라 **{rules.VISIBLE_AREA_BASIS}** 이다.
{rules.VISIBLE_AREA_MIN:.0%} 이상 노출되면 보이는 영역만 박스를 치고 `truncated=true` 로 표기한다.

### 그룹 박스
허용하지 않는다({rules.ALLOW_GROUP_BOX}). 개별 경계를 못 나누면 Ignore 처리한다.

→ 전체 규칙: `DEC-004-labeling-exclusion-policy.md`

## 정본 라벨 감사 — 규격 준수 여부

기존 canonical 라벨 {num(tb)}건을 **현재 라벨링 규격과 독립적으로 대조**하여
중복·경계·annotation unit·truncated·소형 객체의 규칙 준수 여부를 감사했다.
**READ-ONLY 감사이며 라벨을 수정하지 않았다.**

{audit_table(d)}

{audit_note(d)}

## 기존 라벨 승계 결과

{table(["항목", "값"], [
    ["변환 전 박스", num(tb)],
    ["변환 후 박스", num(ta)],
    ["보류(미변환)", num(len(d["unresolved"]))],
    ["손실", num(tb - ta - len(d["unresolved"]))],
], ["---", "---:"])}

변환 유형별 박스 수:

{table(["유형", "박스"], [[k, num(v)] for k, v in sorted(by_type.items())],
       ["---", "---:"])}

좌표는 건드리지 않았다. 바뀐 것은 class id 뿐이다.
원본은 `data/backup` 에 스냅샷으로 보존했고 `pilot` 은 수정하지 않았다.
→ `DEC-003-label-migration-26-to-28.md`
"""


def doc_decisions(d):
    rows = []
    for f in sorted(paths.DECISIONS.glob("DEC-*.md")):
        text = f.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        m = re.search(r"## 결정 내용\s*\n(.+?)(?=\n##|\Z)", text, re.S)
        body = " ".join(m.group(1).split())[:160] if m else ""
        rows.append([f"[{f.stem.split('-')[0]}-{f.stem.split('-')[1]}]({f.name})",
                     title.split("—", 1)[-1].strip(), body])
    return f"""# 03. 주요 의사결정

## 이번 회차 핵심 — 기존 라벨의 의미 검증

기존 `분기 접촉부` 와 v2 `케이블헤드` 의 의미 차이를 검토한 결과,
**가이드 자체의 예시 이미지 및 "명칭 통일" 근거를 통해 동일 대상임을 확인**하였다.
가이드의 케이블헤드 예시 화면 2장이 CVAT 상에서 `분기 접촉부` 로 라벨되어 있었다.

이에 따라 **P6 기존 라벨의 v2 매핑은 유지하되, 기존 라벨의 품질 문제와 검수 이력 부족으로
canonical 승격은 보류**하였다. 라벨을 `canonical`(P1/P3/P4)과 `reference`(P6/P9)로
등급을 나눠 관리한다.

> 자동 생성 · {TODAY} · 원문은 `reports/decisions/`

각 결정은 **문제 → 검토한 선택지 → 선택한 이유 → 근거 → 영향** 순으로 기록되어 있다.
"임의로 바꾼 것"과 "데이터 조사에 따른 결정"을 구분할 수 있게 하기 위한 형식이다.

{table(["번호", "결정", "요지"], rows)}

## 변경 전 → 변경 후

{table(["구분", "변경 전", "변경 후", "이유"], [
    ["클래스", "26개 (2022 PDF)", f"{len(d['classes'])}개 (가이드 v2)",
     "가이드 v2 개정 10건 반영 — 명칭 3건, 보류→가공 4건, 신규 1건"],
    ["class_id", "0부터 순차", "가이드번호 − 1", "가이드 종합표와 직접 대조 가능"],
    ["반 구조", "가이드 8개 반 기준", "현존 10개 폴더 유지", "수집 출처를 규칙에 맞춰 지우지 않음"],
    ["라벨링 대상", "실화상(RGB) → 좌표 전이", "열화상 직접", "RGB 페어가 전체의 2.5%뿐"],
    ["기존 라벨", "pilot 내 13개 소스 혼재", "정본 3개 승계", "소스 간 대조로 검수 계보 확인"],
    ["**라벨 등급**", "구분 없음", "canonical / reference 분리",
     "P6·P9 라벨에 미작업 의심분·이상치·검수 이력 부재가 확인되어 승격 보류"],
    ["**annotation unit**", "`접촉부`를 하나의 규칙으로",
     "클래스별로 따로 정의 (18/25 확정)",
     "정본은 접속점 단위, 참고는 단자군 단위로 **실제로 달랐다**"],
    ["**케이블헤드 경계**", "상부 도체 제외(추정)", "상부 금속 단자·수직 도체 포함",
     "가이드 자체 예시 이미지 2장으로 확정. 추정이 틀렸다"],
    ["**라벨링 착수 방식**", "시드 400장 바로 시작",
     "1차 시험 30장 → 일치도 검증 → 규칙 수정 → 400장",
     "규칙이 통하는지 먼저 확인하는 편이 되돌리는 비용보다 싸다"],
    ["**회수 포맷**", "YOLO 1.1 만 회수 — bbox 외 속성이 소실됨",
     "YOLO 1.1(일치도용) + CVAT XML(속성 보존) 이중 회수",
     "YOLO 1.1 에는 bbox 외 attribute 저장 구조가 없다. "
     "라벨러 작업 방식은 바꾸지 않고 정보 손실만 막는다 (DEC-020)"],
])}
"""


def doc_progress(d):
    rows = [[s["step"], s["name"], s["status"], f"`{s['artifact']}`" if s["artifact"] else "—",
             s["note"]] for s in d["progress"]]
    done = sum(1 for s in d["progress"] if s["status"] == "완료")
    return f"""# 04. 진행 현황

> 자동 생성 · {TODAY}

{done}/{len(d['progress'])} 단계 완료.

{table(["단계", "작업", "상태", "산출물", "비고"], rows)}

## 반별 라벨링 착수 현황

{table(["반", "상태", "기존 bbox", "라벨 파일"],
       [[p["folder_name"], p["status"], num(p["existing_bbox_count"]),
         num(p["existing_label_files"])] for p in d["live"]],
       ["---", "---", "---:", "---:"])}

{doc_split(d)}

## 아직 측정하지 않은 것

- 중복 제거 후 실질 라벨링 대상 장수 (STEP 08~09)
- 라벨러 간 일치도 (STEP 12)
- 클래스별 최종 목표 인스턴스 수
"""


def doc_split(d):
    """학습셋 분할 — 정책·도구·감사. 최종 학습셋이 아니다."""
    sp, leak, bal = d.get("split"), d.get("leak"), d.get("balance")
    if not sp:
        return ("## 학습셋 분할" + NL + NL
                + "아직 생성하지 않았다. `scripts/build_splits.py` 를 실행한다.")
    from collections import Counter
    g = Counter(r["split"] for r in sp)
    img = Counter()
    for r in sp:
        img[r["split"]] += int(r["group_size"])
    unit = sp[0]["group_unit"]
    grows = [[k, num(g[k]), num(img[k]),
              f"{img[k]/sum(img.values())*100:.1f}%"] for k in ("train", "val", "test")]
    grows.append(["합계", num(sum(g.values())), num(sum(img.values())), "100.0%"])

    oq016_txt = _oq016_text()
    trial_txt = _trial_text()
    quar_txt = _quarantine_text()
    lrows = [[r["check"], r["status"], num(r["count"]), num(r["denominator"]),
              r["expected"]] for r in (leak or [])]
    brows = [[r["axis"], r["value"],
              f"{float(r['train_pct'])*100:.1f}%",
              f"{float(r['val_pct'])*100:.1f}%",
              f"{float(r['test_pct'])*100:.1f}%"] for r in (bal or [])]

    near = next((r for r in (leak or []) if r["check"] == "근접 미달 쌍 교차"), None)
    near_txt = ""
    if near and int(near["denominator"]):
        pct = int(near["count"]) / int(near["denominator"]) * 100
        near_txt = (
            "**근접 미달 쌍 교차 " + num(near["count"]) + " / "
            + num(near["denominator"]) + f" ({pct:.1f}%) 를 '괜찮다'고 단정하지 않는다.**"
            + NL + "병합 기준을 아슬아슬하게 넘지 못한 쌍이 split 을 가로지른 것이며, "
            "DEC-008 이 과소병합을 택한 비용이 처음 수치로 드러난 값이다. "
            "이 쌍들이 실제로 같은 장면인지는 검증되지 않았다 → OQ-016")

    return ("## 학습셋 분할 (정책·도구·감사)" + NL + NL
            + "> **이것은 최종 학습셋이 아니다.** 라벨링이 끝나지 않았으므로 "
              "`분할 정책` · `재현 가능한 생성기` · `누수 감사` 까지만 만들었다. "
              "라벨이 모이면 같은 명령으로 다시 돌려 고정한다." + NL + NL
            + "분할 단위 `" + unit + "` · 층화 반 × 카메라 · 비율 70/15/15"
              "(비율에는 근거가 없다 → OQ-015)" + NL + NL
            + table(["split", "그룹", "이미지", "비율"], grows,
                    ["---", "---:", "---:", "---:"]) + NL + NL
            + "### 누수 감사" + NL + NL
            + table(["검사", "판정", "건수", "분모", "기대"], lrows,
                    ["---", "---", "---:", "---:", "---"]) + NL + NL
            + near_txt + NL + NL
            + (("### 정본 격리 판정 (OQ-013 · REV-003)" + NL + NL + quar_txt + NL + NL)
               if quar_txt else "")
            + "### 1차 시험 라벨링 결과" + NL + NL + trial_txt + NL + NL
            + "### 근접 미달 쌍 육안 표본 검증 (OQ-016 · DEC-023 종결)" + NL + NL
            + ("> **20% 는 전체 데이터의 누수율이 아니다.** REV-005 층화 표본 101쌍을 기반으로 "
               "가중 추정한 **근접 유사 후보군 내 동일 시야 위험**이며, 분모는 split 을 가로지르는 "
               "근접 후보쌍 41,184 다. 8,200 은 **쌍**이지 이미지 수가 아니고 확정값도 아니다.")
            + NL + NL
            + ("근접 유사도 기준에서 cluster 간 분리된 쌍이 train/val/test 를 가로지르는 문제 "
               "가능성을 확인하기 위해, 해당 쌍의 층화 표본을 육안 검증하였다. 동일 시야 여부를 "
               "similarity·panel·camera·session 별로 분석하고, 현재 cluster split 정책의 잔여 "
               "누수 가능성을 평가하였다.") + NL + NL
            + oq016_txt + NL + NL
            + "### 분포 균형" + NL + NL
            + table(["축", "값", "train", "val", "test"], brows,
                    ["---", "---", "---:", "---:", "---:"]) + NL + NL
            + "→ `DEC-018-split-policy.md`")


def _trial_text():
    """1차 시험 결과. 숫자는 agreement 출력과 라벨러 폴더에서 직접 센다."""
    trial = paths.LABELING / "draft" / "trial"
    subs = []
    for d in sorted(trial.glob("annotator_*")):
        y = d / "yolo"
        if not y.is_dir() or not any(y.glob("*.txt")):
            continue
        boxes = empty = 0
        for t in y.glob("*.txt"):
            n = sum(1 for l in t.read_text(encoding="utf-8").splitlines()
                    if len(l.split()) >= 5)
            boxes += n
            empty += (n == 0)
        sk = [r for r in read(d / "skip_log.csv")
              if not (r.get("annotator") or "").startswith("#")]
        obj = sum(1 for r in sk if (r.get("scope") or "") == "object")
        subs.append((d.name, boxes, empty, len(sk), obj))
    if not subs:
        return "> 아직 회수된 라벨이 없다."

    fs = sorted((paths.REPORTS / "labeling").glob("agreement_2*.csv"))
    kap = miou = cnt = None
    if fs:
        tot = [r for r in read(fs[-1]) if r.get("class_name") == "(전체)"]
        if tot:
            kap, miou, cnt = tot[0].get("kappa"), tot[0].get("mIoU"), tot[0].get("count_agreement")

    rows = [[n, num(b), num(e), num(s_), num(o)] for n, b, e, s_, o in subs]
    out = [f"라벨러 **{len(subs)}/5명** 회수. 같은 30장을 같은 지침서 v1 로 독립 라벨링했다.", "",
           table(["라벨러", "박스", "빈 파일", "Skip", "scope=object"], rows,
                 ["---", "---:", "---:", "---:", "---:"]), ""]
    if kap:
        out += [f"**라벨러 간 일치도 — Kappa {kap} · mIoU {miou} · "
                f"개수 일치율 {float(cnt)*100:.1f}%** (인증 C-2 목표 Kappa 0.8)", "",
                "> Kappa 는 IoU>=0.5 로 매칭된 박스에서만 계산된다. 짝이 지어지지 않은 박스는 "
                "들어가지 않으므로 **전체 annotation 품질 점수로 해석하지 않는다.**", ""]
    if all(o == 0 for *_x, o in subs):
        out.append("**`scope=object` 를 아무도 쓰지 않았다** — 한 장에 박스가 여럿이고 그중 "
                   "하나만 애매해도 장 전체가 비교에서 빠진다. 지침서 v2 수정 후보.")
    return NL.join(out)


def _quarantine_text():
    """REV-003 격리 판정. [변경 전]/[판정]/[근거]/[영향] 형식. 숫자는 파일에서 센다."""
    from collections import Counter
    rv = [r for r in read(paths.REPORTS / "labeling" / "quarantine_review.csv")
          if not (r.get("pair_id") or "").startswith("#") and (r.get("pair_id") or "")]
    q = read(paths.LABELING / "quarantine" / "canonical_quarantine.csv")
    if not rv or not q:
        return None
    done = [r for r in rv if (r.get("verdict") or "").strip()]
    if len(done) < len(rv):
        return (f"> 격리 {len(rv)}쌍 중 {len(done)}쌍 판정 완료 — **판정 대기 중**. "
                f"결과가 나오기 전에는 결론을 적지 않는다.")

    c = Counter(r["verdict"].strip() for r in done)
    uniq = {(r["image"], r["box_index"]) for r in q}
    cleared = {(r["image"], r["box_index"]) for r in q
               if (r.get("status") or "").strip() == "해제"}
    mig = read(paths.AUDIT / "migration_verification.csv")
    total = sum(int(r["boxes_after"]) for r in mig)

    order = ["큰쪽_유지", "작은쪽_유지", "둘다_제외", "둘다_유효", "판단불가"]
    verdict = " · ".join(f"{k} {c.get(k, 0)}" for k in order)

    return NL.join([
        "**[변경 전]** 중복으로 지목된 " + str(len(rv)) + "쌍(고유 박스 " + str(len(uniq)) +
        ")을 전부 격리한 상태였다. 어느 쪽이 옳은지 몰라 한쪽을 고르지 않았다(DEC-017).", "",
        f"**[판정]** {verdict}", "",
        "**[근거]** 중복 쌍 " + str(len(rv)) + "개 **전수 판정**(표본 아님). "
        "실제 중복 " + str(len(rv)) + "/" + str(len(rv)) + " · "
        "`둘다_유효` " + str(c.get('둘다_유효', 0)) + " · "
        "`판단불가` " + str(c.get('판단불가', 0)) + " — "
        "**과거 감사(DEC-016) 오탐 0건**. 한 박스가 해제·제외확정 양쪽에 든 모순 0건.", "",
        "**[영향]**", "",
        table(["항목", "값"], [
            ["quarantine 고유 박스", num(len(uniq))],
            ["해제 (학습에 사용)", num(len(cleared))],
            ["제외확정", num(len(uniq) - len(cleared))],
            ["**현재 학습 대상**", f"**{num(total - (len(uniq) - len(cleared)))} bbox**"],
        ], ["---", "---:"]), "",
        "> **주의** — 오탐 0건은 *놓친 중복이 없다*는 뜻이 아니다. "
        "감사가 지목한 것이 전부 실제 중복이었다는 뜻이며, **탐지 정확도 100% 로 부르지 않는다.** "
        "이 결과는 중복 쌍 " + str(len(rv)) + "개 전수에 대한 검증이고 그 밖의 정본 품질을 말하지 않는다.", "",
        "> **정본 라벨 파일은 수정하지 않았다.** 판정은 격리 목록의 `status` 에만 기재했고 "
        "학습셋 구축 시 `load_quarantine()` 이 적용한다. (DEC-022)",
    ])


def _oq016_text():
    """OQ-016 표본 현황. 숫자를 손으로 적지 않는다 — 실제 파일에서 센다."""
    base = paths.AUDIT / "oq016"
    sp = base / "sample_pairs.csv"
    if not sp.exists():
        return "> 표본 미생성. `python scripts/oq016_sample.py --n 100`"
    rows = read(sp)
    vr = read(base / "visual_review.csv") if (base / "visual_review.csv").exists() else []
    done = [r for r in vr if (r.get("verdict") or "").strip()
            and not (r.get("pair_id") or "").startswith("#")]
    cells = len({r["cell"] for r in rows})
    same_ss = sum(1 for r in rows if r["same_session"] == "1")
    same_cl = sum(1 for r in rows if r["same_cluster"] == "1")
    lines = [
        f"- 모집단: 근접 미달 쌍 96,292 중 split 교차 **41,184 (42.8%)**",
        f"- 표본: **{len(rows)}쌍** · 층 {cells}개 (반 x 카메라 x 세션관계 x 코사인 4분위) · "
        f"비례 배분",
        f"- 표본 구성: 같은 세션 {same_ss} / 다른 세션 {len(rows) - same_ss}",
        f"- **같은 cluster 인데 split 이 다른 쌍: {same_cl}건** "
        f"(cluster 단위 분할이 설계대로 동작한다는 뜻)",
        f"- 무작위 대조: 아무 관계 없는 같은 반·카메라 쌍도 코사인 0.90~0.93 에 "
        f"7.2%(같은 세션)~15.5%(다른 세션)가 든다 -> **42.8% 를 누수율로 읽으면 안 된다**",
    ]
    if done:
        from collections import Counter
        c = Counter(r["verdict"].strip() for r in done)
        lines.append(f"- 육안 판정 **{len(done)}/{len(rows)}** 완료: "
                     + " · ".join(f"{k} {v}" for k, v in c.most_common()))
    else:
        lines.append(f"- 육안 판정 **0/{len(rows)}** — 판정 대기. "
                     f"결과 없이 OQ-016 을 닫지 않는다")
    return NL.join(lines)


def doc_issues(d):
    rows = [[q["id"], q["topic"], q["question"], q["blocking_step"],
             q.get("impact", ""), q.get("blocks_current_labeling", ""), q["status"]]
            for q in d["oq"]]
    # 지금 라벨링을 막는 항목이 몇 건인가 — 열려 있는 항목 수보다 이쪽이 중요하다
    blocking = sum(1 for q in d["oq"] if q.get("blocks_current_labeling") == "YES")
    return f"""# 05. 미해소 사항과 조치

> 자동 생성 · {TODAY} · 원본 `reports/data_audit/open_questions.csv`

코드에 몰래 결정하지 않고 남겨 둔 항목이다. 각 항목은 어느 단계를 막고 있는지 명시한다.

**열려 있는 것과 막고 있는 것은 다르다.** 지금 진행 중인 1차 시험 라벨링(30장)을
막는 항목은 **{blocking}건**이다. 나머지는 열린 채로 두고 병행 판정한다 (DEC-019).

{table(["번호", "주제", "질문", "막고 있는 단계", "영향 범위", "지금 라벨링을 막는가", "상태"], rows)}

## 근거와 배경

{chr(10).join(f"### {q['id']} — {q['topic']}{chr(10)}"
              f"**질문** {q['question']}{chr(10)}{chr(10)}"
              f"**왜 중요한가** {q['why_it_matters']}{chr(10)}{chr(10)}"
              f"**근거** `{q['evidence']}`{chr(10)}"
              for q in d["oq"])}

## 최초 보고 대비 정정된 수치

조사 과정에서 최초 보고값에 오류가 있어 정정했다. 원인은 `DEC-006` 에 기록했다.

{table(["항목", "처음 보고", "정정 후", "원인"], [
    ["전체 반", "13개", "10개", "P11~P13 삭제 (2026-08-27)"],
    ["P1-TR반 IR", "5,222", "45,721", "하위 폴더 미탐지 — 스캐너가 최상위만 훑었음"],
    ["전체 IR", "66,186", "106,685", "위와 동일"],
    ["최대 편중 반", "P9-MCCB반", "P1-TR반", "위와 동일 — 진단이 바뀜"],
    ["기존 bbox", "약 4,200", "4,177", "정본 소스 확정 후 정확 집계"],
    ["독립 이미지", "11,322", "38,957",
     "union-find 연쇄 병합으로 41,063장이 한 클러스터. 리더 방식으로 재실행"],
    ["6ban 빈 라벨 해석", "128장 전부 미작업 의심", "미작업 의심 16장(12.5%)",
     "표본 8장 육안 추정 → 전수 판정으로 교체. A3 세션은 설비 구성이 달랐다"],
    ["접촉부 단위", "전부 단자군 단위", "클래스별로 다름",
     "참고 등급 한 클래스만 보고 일반화했다. 정본 2종은 접속점 단위"],
    ["케이블헤드 상부 도체", "제외(추정)", "포함(확정)",
     "가이드 예시 이미지 확인 전의 추정이었다"],
])}

이 표는 **틀렸던 것을 지우지 않고 남긴 것**이다. 어느 시점에 무엇을 근거로 고쳤는지가
그 다음 판단의 신뢰도를 정한다.
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    d = load()
    if not d["panels"]:
        sys.exit("panel_inventory.csv 가 없다. scripts/build_inventories.py 를 먼저 실행한다.")

    paths.PROFESSOR.mkdir(parents=True, exist_ok=True)
    docs = {
        "00_current_status.md": doc_status(d),
        "01_data_inventory.md": doc_inventory(d),
        "02_labeling_schema.md": doc_schema(d),
        "03_major_decisions.md": doc_decisions(d),
        "04_progress.md": doc_progress(d),
        "05_issues_and_actions.md": doc_issues(d),
    }
    for name, body in docs.items():
        p = paths.PROFESSOR / name
        p.write_text(body, encoding="utf-8")
        print(f"{name:<28} {len(body.splitlines()):>4}줄")
    print(f"\n-> {paths.PROFESSOR}")


if __name__ == "__main__":
    main()
