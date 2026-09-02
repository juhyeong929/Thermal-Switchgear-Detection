"""지침서의 클래스 표를 **classes_v2.py 에서 생성**한다 (A-2).

왜 필요한가
    초판 감사에서 지침서 §1(반별 후보 목록)이 §2(단위 미확정 7종 그리기 금지) 및
    `classes_v2.PANEL_CLASSES` 와 **5개 반에서 충돌**했다. HTML 판은 같은 페이지 안에서
    "P7 = 1종" 이라 써 놓고 바로 아래 3종을 나열했다.

    원인은 단순하다 — **그 표들이 손으로 적혀 있었다.** DEC-021 이 P3 후보를 줄여도
    표는 따라오지 않는다. 이 스크립트는 표를 파생물로 만들어 그 경로를 끊는다.

무엇이 source 인가
    classes_v2.py  클래스 canonical metadata (이름·등급·반 후보·annotation unit)
    이것 하나뿐이다. 경계 규칙·속성·임계값은 labeling_rules.py 와 경계 규격서가
    계속 담당한다. **모든 규칙을 classes_v2 에 넣지 않는다** (A-2 단서).

핵심 구분 — 이 스크립트가 존재하는 이유
    labelable(panel)   후보 클래스. 단위 미확정 포함. 시드 수요 산정용
    deployable(panel)  **실제로 그리라고 배포할 클래스.** 지침서·CVAT 는 이것만 쓴다

v1 은 고치지 않는다
    `annotator_guide_v1.md/html` 은 A·B·C 가 실제로 본 문서이며 v1 시험의 증거다
    (C-2 버전 분리 정책). 여기서는 **v2 용 표를 새로 생성**하고, v1 이 현재 스키마와
    어디서 어긋나는지를 별도 리포트로 남긴다.

출력
    reports/labeling/generated/panel_class_table.md      지침서 v2 §1 에 그대로 붙인다
    reports/labeling/generated/panel_class_table.html    HTML 판 조각 (개수표 포함)
    reports/labeling/generated/panel_class_counts.csv    반별 후보/배포/보류 수
    reports/data_audit/guide_v1_divergence.csv           v1 표 ↔ 현재 스키마 차이

사용:
    python scripts/build_guide_tables.py
"""

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import labeling_rules as rules  # noqa: E402

OUT = paths.REPORTS / "labeling" / "generated"

# 지침서 v1 §1 표에 손으로 적혀 있던 목록. **비교 대상으로만 쓴다.**
# 출처: reports/labeling/annotator_guide_v1.md §1 (2026-08-27)
V1_PANEL_TABLE = {
    "P1-TR반": ["에폭시 표면", "몰드변압기 접촉부", "소음기부착형 전력퓨즈", "철심부"],
    "P2-LBS&LA반": ["LBS", "한류형 전력퓨즈", "LA", "케이블헤드",
                    "LBS 1차측 접촉부", "LBS 2차측 접촉부"],
    "P3-MOF반": ["변압기", "변류기", "비한류형 전력퓨즈", "변압기 접촉부", "변류기 접촉부"],
    "P4-MOF&PT반": ["변압기", "변류기", "비한류형 전력퓨즈", "변압기 접촉부",
                    "변류기 접촉부", "몰드타입 PT"],
    "P5-PF&PT반": ["소음기부착형 전력퓨즈", "몰드타입 PT", "분기 접촉부", "인입선로 접촉부"],
    "P6-VCB반": ["VCB 접촉부", "케이블헤드", "CT", "SA"],
    "P7-VCB&CT반": ["VCB 접촉부", "CT", "CT 접촉부"],
    "P8-ACB반": ["콘덴서", "MCCB", "MCCB 접촉부"],
    "P9-MCCB반": ["MCCB", "MCCB 접촉부"],
    "P10-ACB&MCCB반": ["콘덴서", "MCCB", "MCCB 접촉부"],
}
# HTML 판 '28종을 외울 필요는 없습니다' 개수표에 적혀 있던 값
V1_HTML_COUNTS = {"P7-VCB&CT반": 1, "P5-PF&PT반": 2, "P9-MCCB반": 2,
                  "P6-VCB반": 3, "P8-ACB반": 3, "P10-ACB&MCCB반": 3,
                  "P1-TR반": 4, "P2-LBS&LA반": 4, "P3-MOF반": 4, "P4-MOF&PT반": 5}


def caution_mark(cname):
    return " *" if v2.BY_NAME[cname].label_status == v2.CAUTION else ""


def rows():
    """반별 (배포 클래스, 보류 클래스) — 전부 classes_v2 에서 파생."""
    out = []
    for panel in v2.PANEL_CLASSES:
        dep = v2.deployable(panel)
        held = [c for c in v2.labelable(panel) if c not in dep]
        out.append({
            "panel": panel,
            "panel_id": v2.panel_id(panel),
            "deploy": [v2.BY_NAME[c].canonical_name + caution_mark(c) for c in dep],
            "held": [v2.BY_NAME[c].canonical_name for c in held],
            "provisional": panel in v2.PANEL_CLASSES_PROVISIONAL,
        })
    return out


def write_md(rs):
    L = ["<!-- 자동 생성 · scripts/build_guide_tables.py · 손으로 고치지 않는다 -->",
         "",
         "| 반 | 그리는 것 |", "|---|---|"]
    for r in rs:
        L.append(f"| {r['panel']} | {' · '.join(r['deploy']) or '— 없음 —'} |")
    L += ["", "`*` 표시 — 주의 등급. **또렷하게 알아볼 수 있을 때만** 그립니다.", ""]

    held_any = [r for r in rs if r["held"]]
    if held_any:
        L += ["### 이번 판에서 그리지 않는 것 (세는 단위 미확정)", "",
              "이 클래스들은 **여러분의 반에 실제로 있을 수 있지만** 무엇을 하나로 셀지가",
              "아직 정해지지 않았습니다. 보이더라도 **그리지 마세요.**", "",
              "| 반 | 이번 판 제외 |", "|---|---|"]
        for r in held_any:
            L.append(f"| {r['panel']} | {' · '.join(r['held'])} |")
        L.append("")
    L += ["### 어떤 반에서도 절대 그리지 않는 것", ""]
    L += [f"- {v2.BY_NAME[c].canonical_name}" for c in sorted(v2.EXCLUDED)]
    L.append("")
    (OUT / "panel_class_table.md").write_text("\n".join(L), encoding="utf-8")


def write_html(rs):
    n = {}
    for r in rs:
        n.setdefault(len(r["deploy"]), []).append(r["panel"])
    L = ["<!-- 자동 생성 · scripts/build_guide_tables.py · 손으로 고치지 않는다 -->",
         '<table class="panel-counts">',
         "<caption>28종을 외울 필요는 없습니다 — 자기 반에서 그리는 것만 보면 됩니다</caption>",
         "<tr><th>그리는 클래스 수</th><th>반</th></tr>"]
    for k in sorted(n):
        L.append(f"<tr><td>{k}종</td><td>{' · '.join(n[k])}</td></tr>")
    L += ["</table>", "", '<table class="panel-classes">',
          "<tr><th>반</th><th>그리는 것</th><th>이번 판 제외 (단위 미확정)</th></tr>"]
    for r in rs:
        L.append(f"<tr><td>{r['panel']}</td><td>{' · '.join(r['deploy']) or '—'}</td>"
                 f"<td>{' · '.join(r['held']) or '—'}</td></tr>")
    L.append("</table>")
    (OUT / "panel_class_table.html").write_text("\n".join(L), encoding="utf-8")


def write_counts(rs):
    with (OUT / "panel_class_counts.csv").open("w", newline="",
                                               encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["panel", "panel_id", "candidate_n", "deployable_n", "held_n",
                    "deployable", "held", "provisional"])
        for r in rs:
            w.writerow([r["panel"], r["panel_id"],
                        len(r["deploy"]) + len(r["held"]), len(r["deploy"]),
                        len(r["held"]), " ".join(r["deploy"]), " ".join(r["held"]),
                        int(r["provisional"])])


def write_divergence(rs):
    """v1 지침서 표가 현재 스키마와 어디서 어긋나는지. **v1 은 고치지 않는다.**"""
    by_panel = {r["panel"]: r for r in rs}
    out = []
    for panel, v1list in V1_PANEL_TABLE.items():
        r = by_panel[panel]
        dep = {d.rstrip(" *") for d in r["deploy"]}
        held = set(r["held"])
        v1set = set(v1list)
        for c in sorted(v1set - dep):
            kind = ("§2 가 금지한 단위 미확정 클래스를 §1 이 나열" if c in held
                    else "현재 스키마의 반 후보가 아님 (DEC 로 제외됨)")
            out.append({"panel": panel, "class_name": c,
                        "v1_says": "그린다", "schema_says": "그리지 않는다",
                        "kind": kind})
        for c in sorted(dep - v1set):
            out.append({"panel": panel, "class_name": c,
                        "v1_says": "없음", "schema_says": "그린다",
                        "kind": "v1 표에서 누락"})
        n_v1, n_now = V1_HTML_COUNTS[panel], len(r["deploy"])
        if n_v1 != n_now or n_v1 != len(v1list):
            out.append({"panel": panel, "class_name": "(HTML 개수표)",
                        "v1_says": f"{n_v1}종 (목록은 {len(v1list)}종)",
                        "schema_says": f"{n_now}종",
                        "kind": "HTML 개수표 ↔ §1 목록 ↔ 스키마 삼자 불일치"
                                if n_v1 != len(v1list) else "HTML 개수표가 스키마와 불일치"})
    f = paths.AUDIT / "guide_v1_divergence.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["panel", "class_name", "v1_says",
                                           "schema_says", "kind"])
        w.writeheader()
        w.writerows(out)
    return out


TEMPLATE = paths.REPORTS / "labeling" / "annotator_guide_v2.template.md"
GUIDE_V2 = paths.REPORTS / "labeling" / "annotator_guide_v2.md"
# 배포 전에 사람이 채워야 하는 자리. 남아 있으면 배포하지 않는다.
ESCALATION_MARKER = "<<채워 넣을 것"
ESCALATION_FILE = paths.REPORTS / "labeling" / "escalation.txt"


def escalation_text():
    """라벨러 연락처. **코드가 아니라 파일 하나에서 읽는다.**

    운영 정보(사람 이름·연락 수단·응답 시한)를 스크립트에 박아 두면 배포 때마다
    코드를 고치게 된다. 고칠 곳을 하나로 두고, 미기입 상태는 status_check 가 막는다.
    """
    if not ESCALATION_FILE.exists():
        return "(escalation.txt 가 없다 — 연락처를 채워 넣을 것)"
    lines = [l for l in ESCALATION_FILE.read_text(encoding="utf-8").splitlines()
             if not l.startswith("#")]
    return chr(10).join(lines).strip()


def unit_table_md():
    """세는 단위 표 — classes_v2 의 ANNOTATION_UNIT 에서 그대로 만든다."""
    by_unit = defaultdict(list)
    for c in v2.labelable_classes():
        by_unit[v2.annotation_unit(c.class_name)].append(c.canonical_name)
    L = ["| 클래스 | 세는 단위 |", "|---|---|"]
    for u in (v2.CONTACT_POINT, v2.TERMINAL_GROUP, v2.WHOLE_OBJECT):
        names = by_unit.get(u, [])
        if not names:
            continue
        if u == v2.WHOLE_OBJECT:
            L.append(f"| 그 밖 부품 전부 ({len(names)}종) | **{v2.UNIT_DESC[u]}** |")
        else:
            L.append(f"| {' · '.join(names)} | **{v2.UNIT_DESC[u]}** |")
    unk = by_unit.get(v2.UNIT_UNKNOWN, [])
    if unk:
        L.append(f"| {' · '.join(unk)} | **아직 정해지지 않았습니다. "
                 f"이번 판에서는 그리지 마세요** |")
    return "\n".join(L)


def unknown_unit_rows():
    unk = [c.canonical_name for c in v2.labelable_classes()
           if not v2.unit_confirmed(c.class_name)]
    return (f"| 접촉부 {len(unk)}종의 세는 단위 "
            f"({' · '.join(unk)}) | 실제 라벨링 사례가 모이면 정합니다 |")


def overlap_example():
    """§6 겹침 예시를 **정본 라벨 실측**에서 만든다.

    v1 §6 의 유일한 겹침 예시는 "케이블헤드 박스 안에 VCB 접촉부 박스가 들어갑니다"
    였다. 실측하면 두 번 틀렸다.

      · P6 참고 라벨   케이블헤드가 함께 있는 69박스 중 완전 포함은 6개(9%)
      · 정본 라벨      '작은 것이 큰 것 안에 들어가는' 관계가 최대 2% (1/44)

    실제로 흔한 것은 **포함이 아니라 부분 겹침**이다. 예시는 규칙보다 강하게
    행동을 유도하므로, 데이터에 없는 형태를 대표 사례로 보여 주면 안 된다.
    """
    def xy(b):
        cx, cy, w, h = b
        return cx - w/2, cy - h/2, cx + w/2, cy + h/2

    def inter(a, b):
        ax0, ay0, ax1, ay1 = xy(a)
        bx0, by0, bx1, by1 = xy(b)
        return (max(0, min(ax1, bx1) - max(ax0, bx0))
                * max(0, min(ay1, by1) - max(ay0, by0)))

    pairs, nested, tot = defaultdict(int), 0, 0
    root = paths.LABELING / "reviewed"
    for p in root.rglob("*.txt"):
        bs = []
        for line in p.read_text(encoding="utf-8").splitlines():
            t = line.split()
            if len(t) >= 5:
                bs.append((int(t[0]), tuple(float(x) for x in t[1:5])))
        for i, (ci, bi) in enumerate(bs):
            for cj, bj in bs[i+1:]:
                if ci == cj:
                    continue
                it = inter(bi, bj)
                if it <= 0:
                    continue
                key = tuple(sorted([v2.BY_ID[ci].canonical_name,
                                    v2.BY_ID[cj].canonical_name]))
                pairs[key] += 1
                tot += 1
                small = min((bi, bj), key=lambda b: b[2] * b[3])
                if it / (small[2] * small[3]) >= 0.9:
                    nested += 1
    if not pairs:
        return "(정본 라벨이 없어 예시를 만들지 못했다)"
    top, n = max(pairs.items(), key=lambda x: x[1])
    return (
        f"**정상인 겹침 예** — 정본 라벨에서 가장 흔한 겹침입니다.\n\n"
        f"{top[0]} 와(과) {top[1]} 의 박스가 **가장자리에서 겹쳐 보입니다** "
        f"(정본에서 {n:,}회). 둘은 다른 물체이므로 각각 그립니다.\n\n"
        f"> **겹친다 = 한쪽이 다른 쪽 안에 들어간다, 가 아닙니다.**\n"
        f"> 정본 {tot:,}건의 겹침 중 한쪽이 다른 쪽에 완전히 들어간 것은 "
        f"{nested}건({nested/tot:.0%}) 뿐입니다.\n"
        f"> 대부분은 **가장자리가 걸치는** 형태입니다. "
        f"박스가 서로를 감싸도록 억지로 맞추지 마세요."
    )


def render_guide(rs, changelog):
    """지침서 v2 를 템플릿 + 생성 표로 조립한다.

    **표를 손으로 적지 않는 것이 핵심이다.** v1 의 §1 표가 손으로 적혀 있었기 때문에
    DEC-021 이 반영되지 않았고 §2 와 5개 반에서 충돌했다.
    """
    if not TEMPLATE.exists():
        return None
    t = TEMPLATE.read_text(encoding="utf-8")
    table = (OUT / "panel_class_table.md").read_text(encoding="utf-8")
    # 생성 표의 주석 줄과 '절대 그리지 않는 것' 절은 템플릿이 따로 넣으므로 제외
    table = "\n".join(l for l in table.splitlines()
                      if not l.startswith("<!--")
                      and not l.startswith("### 어떤 반에서도"))
    table = table.split("### 어떤 반에서도")[0].rstrip()
    excluded = "\n".join(f"- **{v2.BY_NAME[c].canonical_name}**"
                         for c in sorted(v2.EXCLUDED))
    out = (t.replace("{{GUIDE_DATE}}", date.today().isoformat())
            .replace("{{PANEL_CLASS_TABLE}}", table)
            .replace("{{EXCLUDED_LIST}}", excluded)
            .replace("{{UNIT_TABLE}}", unit_table_md())
            .replace("{{UNKNOWN_UNIT_ROWS}}", unknown_unit_rows())
            .replace("{{SHOT_TYPES}}", " / ".join(rules.SHOT_TYPES))
            .replace("{{OVERLAP_EXAMPLE}}", overlap_example())
            .replace("{{ESCALATION}}", escalation_text())
            .replace("{{CHANGELOG}}", changelog))
    GUIDE_V2.write_text(out, encoding="utf-8")
    return out


CHANGELOG = """\
| # | 바뀐 것 | 왜 | 근거 |
|---|---|---|---|
| 1 | **반 정보를 알려 드립니다.** CVAT 작업 이름에 반이 적히고, 라벨 목록도 그 반 것만 나옵니다 | v1 은 §1 에서 "자기 반 목록만 그리세요" 라고 해 놓고 반을 알려 주지 않았습니다. 규칙을 지킬 수단이 없었습니다 | 시험 3/3 재현 — `A09` 에서 세 분이 서로 다른 클래스를 고르셨습니다 |
| 2 | **§1 표를 코드에서 자동 생성합니다** | v1 §1 표는 손으로 적혀 있어 스키마 변경을 따라오지 못했고, §2 와 5개 반에서 충돌했습니다 | `guide_v1_divergence.csv` 16건 |
| 3 | **`scope=object` 를 크게 강조했습니다** | 세 분 모두 한 번도 쓰지 않으셨습니다. 개인 성향이 아니라 문구 문제였습니다 | Skip 26건 전부 `scope=image` |
| 4 | **Skip 사유를 나눠 적어 달라고 다시 요청합니다** | 한 분이 12건을 전부 `other` 로 적으셨는데 내용은 대부분 `unknown_part` 였습니다 | `skip_log.csv` |
| 5 | **막혔을 때 물어볼 곳을 적었습니다** | v1 에는 연락처가 없었습니다. 물어볼 데가 없으면 각자 규칙을 만들게 됩니다 | 실무 점검 17문항 |
| 6 | **MCCB 접촉부의 가로 범위를 보강했습니다** | 전 클래스 중 mIoU 가 가장 낮았습니다 (0.69~0.78) | `agreement_2026-09-01.csv` |
| 7 | **시간 기록을 구간별로 나눠 달라고 요청합니다** | 세 분 모두 한 줄로만 적으셔서 구간 신뢰도가 낮습니다 | `time_log.csv` |
| 8 | P3-MOF반에서 **변압기 계열이 빠졌습니다** | 열화상에서 변류기와 구분할 수 없다는 것이 확인됐습니다 | DEC-021 |

### 바뀌지 **않은** 것

- 세는 단위(접속점 / 단자군 / 부품 전체) — v1 에서 잘 통했습니다 (단위 오류 0건)
- 잘림 30% 기준 · 겹침 규칙 · 제외 3종 · 속성 3종
- **작은 객체에 수치 기준을 두지 않는 것** — v1 그대로입니다.
  1차 시험에서 세 분의 하한이 오히려 벌어졌기 때문에 수치를 규칙으로 올리지 않았습니다.
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rs = rows()
    write_md(rs)
    write_html(rs)
    write_counts(rs)
    div = write_divergence(rs)

    print("지침서 클래스 표 생성 — source: schemas/classes_v2.py\n")
    print(f"  {'반':<16}{'후보':>5}{'배포':>5}{'보류':>5}   배포 목록")
    for r in rs:
        print(f"  {r['panel']:<16}{len(r['deploy']) + len(r['held']):>5}"
              f"{len(r['deploy']):>5}{len(r['held']):>5}   "
              f"{' · '.join(r['deploy']) or '— 없음 —'}")
    tot_d = sum(len(r["deploy"]) for r in rs)
    tot_h = sum(len(r["held"]) for r in rs)
    print(f"\n  반-클래스 조합: 배포 {tot_d} · 보류 {tot_h}")
    print(f"  배포 대상 클래스 {len({c for r in rs for c in r['deploy']})}종 "
          f"/ 라벨 대상 {len(v2.labelable_classes())}종")

    print(f"\nv1 지침서 대비 불일치 {len(div)}건 "
          f"(v1 은 수정하지 않는다 — v1 시험의 증거이므로)")
    for d in div:
        print(f"  {d['panel']:<16}{d['class_name']:<16}"
              f"v1={d['v1_says']:<20}스키마={d['schema_says']}")
    g = render_guide(rs, CHANGELOG)
    if g is None:
        print("\n[주의] annotator_guide_v2.template.md 가 없어 지침서를 만들지 않았다")
    else:
        n = g.count(ESCALATION_MARKER)
        print(f"\n지침서 v2 생성 -> {GUIDE_V2.name}")
        if n:
            print(f"  [배포 금지] 채워 넣을 자리 {n}곳 — 검수 담당자·연락 수단·응답 시한")
            print("  status_check 가 이 상태를 FAIL 로 잡는다.")
        else:
            print("  연락처 기입 완료")

    print(f"\n-> {OUT}")
    print(f"-> {paths.AUDIT / 'guide_v1_divergence.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
