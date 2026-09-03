"""라벨링 클래스 정의 — 가이드 v2 기준 28개 스키마. 단일 출처(single source of truth).

출처 (두 판을 나눠 적는다 — 어느 판에서 온 값인지가 곧 근거다)

  [1] 이전 판 `../수배전반_열화상_라벨링_가이드_v2.html`  (워크트리 삭제 · git 이력에 있음)
      - canonical_name / label_status / description -> 03 REFERENCE '가공 대상 종합' 표
      - alias                                       -> hero 의 '이번 개정에서 바뀐 내용' 10건
      - panel_candidates                            -> 02 PANELS 반별 가공대상 목록

  [2] 현행 판 `../수배전반 라벨링 가이드.pdf`  (2026-09-02 배포)
      - PF&PT 반 케이블헤드 통일 · branch_contact 폐지  -> p14        (DEC-025)
      - 반 10개 명칭·우선순위                            -> p3
      - 라벨러 주의 문구 (LA↔SA · SA↔케이블헤드 · 접촉부 보류) -> p8·p14·p16·p17

  **현행 판에는 03 REFERENCE 종합표가 없다.** 그래서 가공여부·제외 근거의 단일 출처는
  이 파일이며, 사람이 읽을 표는 scripts/build_reference_table.py 가 재생성한다 (DEC-026).

가이드에 없는 정보는 만들어 넣지 않는다. 아래 두 필드만 파생값이며 그 사실을 명시한다.
  - class_id     : 가이드번호 - 1 (YOLO 0-index 로 쓰기 위한 기계적 변환)
  - priority     : 이 클래스가 등장하는 반들의 가이드 우선순위 중 최솟값

pilot/classes.py 의 26개 스키마는 이 파일로 대체한다. 승계는 class_migration_26_to_28.csv.
"""

from dataclasses import dataclass, field

GUIDE_VERSION = "v2"
GUIDE_REVISED = "2026-08-24"     # 클래스 번호·가공여부의 출처가 된 판 (HTML 종합표)
# 현행 배포판. 종합표가 없어 클래스 체계의 출처가 되지는 못하고, 반별 목록과
# 주의 문구만 여기서 왔다. 두 날짜를 하나로 합치지 않는다 (DEC-026).
GUIDE_PDF_REVISED = "2026-09-02"

LABEL   = "가공"   # 가이드 O — 항상 라벨링
CAUTION = "주의"   # 가이드 ! — 식별 가능한 경우만 라벨, 판별 불가면 미라벨(Ignore)
EXCLUDE = "제외"   # 가이드 X — 어떤 반에서도 라벨링하지 않음
RETIRED = "폐지"   # 가이드 개정으로 클래스 자체가 없어짐. 신규 라벨 금지.
                  # EXCLUDE 와 다르다 — EXCLUDE 는 '있지만 그리지 않는다',
                  # RETIRED 는 '그 이름의 클래스가 더 이상 존재하지 않는다'.
                  # class_id 는 비우지 않고 그대로 둔다 (재번호화 금지).


@dataclass(frozen=True)
class ThermalClass:
    guide_no: int            # 가이드 종합표 번호 1..28 (보고·대조용, 절대 바꾸지 않음)
    class_name: str          # 코드/파일에서 쓰는 영문 키
    canonical_name: str      # 가이드 표기 그대로의 한글명 (라벨링 툴 표시명)
    label_status: str        # LABEL / CAUTION / EXCLUDE
    description: str         # 가이드 '비고' 열 원문. 없으면 빈 문자열
    alias: tuple = ()        # v1 명칭 등 (가이드 개정 내역에 근거)
    notes: str = ""          # 본 프로젝트에서 관찰한 사항. 가이드 원문과 구분

    @property
    def class_id(self) -> int:
        """YOLO 클래스 id. 가이드번호 - 1 (파생값)."""
        return self.guide_no - 1


CLASSES = [
    ThermalClass(1,  "core_iron", "철심부", CAUTION,
                 "배전반 내 위치때문에 잘 안보임"),
    ThermalClass(2,  "epoxy_surface", "에폭시 표면", LABEL, ""),
    ThermalClass(3,  "mold_tr_contact", "몰드변압기 접촉부", LABEL, ""),
    ThermalClass(4,  "lbs", "LBS", LABEL, ""),
    ThermalClass(5,  "lbs_primary", "LBS 1차측 접촉부", LABEL, "",
                 notes="v1 보류 -> v2 가공대상 전환"),
    ThermalClass(6,  "cl_power_fuse", "한류형 전력퓨즈", LABEL, "",
                 alias=("전력퓨즈",),
                 notes="LBS&LA 반. 퓨즈 3종은 형태로 구분한다"),
    ThermalClass(7,  "la", "LA", LABEL, ""),
    ThermalClass(8,  "transformer", "변압기", LABEL, ""),
    ThermalClass(9,  "ct_transformer", "변류기", LABEL, "",
                 alias=("분류기",), notes="v1 '분류기' 명칭 정정"),
    ThermalClass(10, "ncl_power_fuse", "비한류형 전력퓨즈", LABEL, "",
                 alias=("전력퓨즈", "MOF 1차측 전력퓨즈"),
                 notes="MOF&PT 반"),
    ThermalClass(11, "silencer_power_fuse", "소음기부착형 전력퓨즈", LABEL, "",
                 alias=("전력퓨즈",), notes="TR 반 · PF&PT 반 공통"),
    ThermalClass(12, "mold_pt", "몰드타입 PT", LABEL, "", alias=("PT",)),
    # [2026-09-02 폐지] 새 가이드 PDF p14 (PF&PT 반) "분기 접촉부 -> 케이블헤드 명칭 변경".
    # 이전 판은 VCB 반에서만 케이블헤드로 통일하고 PF&PT 반에는 '분기 접촉부' 를 남겼는데,
    # 새 판이 PF&PT 반에서도 케이블헤드로 바꾸면서 이 이름이 쓰이는 반이 하나도 없어졌다.
    #
    #   · 정본·참고 통틀어 라벨 실적 0건 -> 폐지해도 학습 데이터 손실이 없다
    #   · class_id 12 는 비우지 않고 그대로 둔다. cable_head(#14/id 13) 를 이 자리로
    #     옮기지 않는다 — 옮기면 P2·P6 의 기존 케이블헤드 라벨 의미가 바뀐다
    #   · cable_head 의 '이전 명칭' 으로 두어 자동 승계하지 않는다. 실적이 0건이므로
    #     승계할 라벨 자체가 없고, 승계 규칙을 남기면 나중에 오변환의 근거가 된다
    ThermalClass(13, "branch_contact", "분기 접촉부", RETIRED, "",
                 notes="[폐지] 새 가이드에서 PF&PT 반도 케이블헤드로 통일. "
                       "신규 라벨 금지 · 기존 실적 0건 · 라벨 승계 없음 (DEC-025)"),
    ThermalClass(14, "cable_head", "케이블헤드", LABEL, "",
                 alias=("분기 접촉부",),
                 notes="VCB·CNCV 반. v1 '분기 접촉부' 를 케이블헤드로 통일"),
    ThermalClass(15, "vcb_contact", "VCB 접촉부", LABEL, ""),
    ThermalClass(16, "ct", "CT", LABEL, "",
                 notes="v2 에서 VCB 반에 신규 추가. 계기 표시창이 달린 적갈색 몰드형"),
    ThermalClass(17, "sa", "SA", LABEL, "",
                 notes="v2 신규. 백색 애자형 원통, 대·소 3개 1조 (서지흡수기)"),
    ThermalClass(18, "capacitor", "콘덴서", LABEL, ""),
    ThermalClass(19, "mccb", "MCCB", LABEL, ""),
    # [2026-09-02] 개정 PDF p13·p14 가 PF&PT 반 가공대상 목록에 넣었고 보류 표기가
    # 없다. 주의 -> 가공으로 상향한다 (DEC-027).
    # 단 annotation unit 은 아직 UNKNOWN 이라 deployable() 에서는 빠진다.
    # 정본·참고 통틀어 라벨 실적 0건이라 단위 판정 근거가 없다 (NQ-13).
    ThermalClass(20, "incoming_contact", "인입선로 접촉부", LABEL, "",
                 notes="[2026-09-02] 개정 PDF 가공대상 포함 · 보류 표기 없음 -> "
                       "주의에서 가공으로 상향 (DEC-027). "
                       "이전 판 비고 '반사 때문에 탐지 정확도가 떨어짐' 은 "
                       "개정 판에서 사라졌다. 단위 미확정이라 아직 비배포 (NQ-13)"),
    ThermalClass(21, "busbar", "부스바", EXCLUDE,
                 "일정한 패턴이 없어 탐지 정확도가 떨어짐"),
    ThermalClass(22, "cable", "케이블", EXCLUDE,
                 "일정한 패턴이 없어 탐지 정확도가 떨어짐",
                 notes="케이블헤드(#14, 가공대상)와 혼동하지 않는다"),
    ThermalClass(23, "lbs_secondary", "LBS 2차측 접촉부", LABEL, "",
                 notes="v1 보류 -> v2 가공대상 전환"),
    ThermalClass(24, "transformer_contact", "변압기 접촉부", LABEL, "",
                 notes="v1 보류 -> v2 가공대상 전환"),
    ThermalClass(25, "ct_transformer_contact", "변류기 접촉부", LABEL, "",
                 notes="v1 보류 -> v2 가공대상 전환"),
    ThermalClass(26, "ct_contact", "CT 접촉부", CAUTION,
                 "배전반 내 위치때문에 잘 안보임"),
    # [2026-09-03] 개정 PDF p18(ACB&MCCB반)이 가공대상 목록에 넣었다. 제외 -> 주의 (DEC-030).
    # 인입선로 접촉부(DEC-027)와 같은 증거 구조다 — 이전 판은 제외/보류, 개정 판은
    # 가공대상 목록에 포함, 가공여부 기호 체계 자체는 사라졌다.
    #
    # 왜 '가공' 이 아니라 '주의' 인가 — 비고 원문이 "배전반 내 위치때문에 잘 안보임" 이고,
    # **같은 문구를 가진 철심부(#1) · CT 접촉부(#26)가 둘 다 주의**다. 가이드 안에서
    # 이 사유는 주의로 대응돼 왔다. 없던 등급을 새로 만들지 않고 그 대응을 따른다.
    #
    # annotation_unit 은 UNKNOWN 유지 — 정본·참고 통틀어 라벨 실적 0건이라 단위 근거가
    # 없다. deployable() 이 unit_confirmed() 로 한 번 더 거르므로 라벨러에게는 나가지 않는다.
    ThermalClass(27, "acb_contact", "ACB 접촉부", CAUTION,
                 "배전반 내 위치때문에 잘 안보임",
                 notes="[2026-09-03] 개정 PDF p18 가공대상 포함 -> 제외에서 주의로 승격 "
                       "(DEC-030). 단위 미확정이라 아직 비배포 (NQ-13)"),
    ThermalClass(28, "mccb_contact", "MCCB 접촉부", CAUTION,
                 "다른 접촉부와 구분이 안됨"),
]

BY_NAME = {c.class_name: c for c in CLASSES}
BY_ID   = {c.class_id: c for c in CLASSES}
BY_GUIDE_NO = {c.guide_no: c for c in CLASSES}
NAMES   = [c.class_name for c in sorted(CLASSES, key=lambda c: c.class_id)]
KOREAN  = {c.class_name: c.canonical_name for c in CLASSES}

EXCLUDED = {c.class_name for c in CLASSES if c.label_status == EXCLUDE}
CAUTIONED = {c.class_name for c in CLASSES if c.label_status == CAUTION}
# 폐지 클래스. EXCLUDED 와 **합치지 않는다** — 제외 3종(부스바·케이블·ACB 접촉부)은
# "가이드가 그리지 말라고 한 것" 이고, 폐지는 "그 클래스가 없어진 것" 이다.
# 둘을 같은 칸에 넣으면 제외 근거를 설명할 수 없게 된다.
RETIRED_CLASSES = {c.class_name for c in CLASSES if c.label_status == RETIRED}
# 라벨 대상이 아닌 것 전부. 반 후보·시드·CVAT 는 이 집합을 쓴다.
NOT_LABELED = EXCLUDED | RETIRED_CLASSES

# ---------------------------------------------------------------------------
# 반별 후보 클래스 — 3-가공 에 현존하는 10개 폴더 기준.
#
# 반(Panel)은 "이 데이터가 어디서 수집됐는가", 클래스는 "이 안에서 무엇을 라벨링하는가"
# 로 분리해 관리한다. 반은 합치지 않는다.
#
# 가이드 02 PANELS 는 8개 반만 상세를 두고, P3-MOF반 / P8-ACB반 / P9-MCCB반 은 단독
# 상세가 없다. 이 3개 반의 후보는 가이드에서 자동으로 나오지 않으므로 OPEN QUESTION 이며
# 아래 값은 잠정이다. -> reports/decisions/DEC-002-panel-structure.md
# ---------------------------------------------------------------------------
PANEL_CLASSES = {
    "P1-TR반":        ["core_iron", "epoxy_surface", "mold_tr_contact",
                       "silencer_power_fuse"],
    "P2-LBS&LA반":    ["lbs", "cl_power_fuse", "la", "cable_head",
                       "lbs_primary", "lbs_secondary"],
    # P3 는 변압기 계열을 뺐다 (DEC-021). "없다" 가 아니라 "열화상에서 신뢰성 있게
    # 구분할 수 없으므로 독립 라벨 대상으로 강제하지 않는다" 는 annotation 정책이다.
    "P3-MOF반":       ["ct_transformer", "ncl_power_fuse", "ct_transformer_contact"],
    "P4-MOF&PT반":    ["transformer", "ct_transformer", "ncl_power_fuse",
                       "transformer_contact", "ct_transformer_contact", "mold_pt"],
    # branch_contact 폐지에 따라 케이블헤드로 교체 (DEC-025). class_id 는 이동하지 않는다.
    "P5-PF&PT반":     ["silencer_power_fuse", "mold_pt", "cable_head",
                       "incoming_contact"],
    "P6-VCB반":       ["vcb_contact", "cable_head", "ct", "sa"],
    "P7-VCB&CT반":    ["vcb_contact", "ct", "ct_contact"],
    # P8 은 가이드 ⑧ 기준을 그대로 적용해 P10 과 같은 후보를 쓴다 (DEC-009 / OQ-002).
    # 층화표본에서 MCCB 와 콘덴서가 확인됐다. 클래스 스키마는 확장하지 않았다.
    "P8-ACB반":       ["capacitor", "mccb", "mccb_contact", "acb_contact"],
    "P9-MCCB반":      ["mccb", "mccb_contact"],
    "P10-ACB&MCCB반": ["capacitor", "mccb", "mccb_contact", "acb_contact"],
}

# 가이드에 단독 상세가 없어 후보를 잠정 배정한 반. 확정 전까지 표시해 둔다.
# P8 은 DEC-009 로 확정되어 빠졌다. P9 는 육안 확인만 됐다.
# P3 는 변압기 계열 문제는 DEC-021 로 닫혔으나 몰드타입 PT 포함 여부가 남아 있다 (NQ-14).
PANEL_CLASSES_PROVISIONAL = {"P3-MOF반", "P9-MCCB반"}

# 반별로 **일부러 뺀** 클래스와 그 이유. 비어 있는 것과 "빼기로 결정한 것" 은 다르다.
# 이 표가 없으면 나중에 "왜 P3 에 변압기가 없지?" 를 다시 조사하게 된다.
PANEL_CLASSES_EXCLUDED = {
    "P3-MOF반": {
        "transformer": "열화상에서 변류기와 구분 불가. 물리적 부재가 아니라 "
                       "식별 불가에 따른 annotation 정책 (DEC-021)",
        "transformer_contact": "위와 같음 (DEC-021)",
    },
}

# 데이터에서 후보 개체는 확인됐으나 전문가 판정 전까지 확정하지 않는 클래스 (DEC-009 / OQ-004).
# 시드 후보에는 포함하되 최종 라벨링 기준 확정 전까지 표시를 유지한다.
CLASSES_ON_HOLD = {"sa": "P6 에서 후보 개체 확인. LA(#07)와 외형이 유사해 전문가 판정 필요"}

# ---------------------------------------------------------------------------
# annotation unit — 무엇을 하나의 객체로 셀 것인가 (DEC-015)
#
# '접촉부' 라는 상위 개념으로 단위를 정하지 않는다. 실측 결과 같은 접촉부 계열이라도
# 클래스마다 단위가 다르다. 단위가 다르면 인스턴스 수가 달라지고 지표가 흔들린다.
#
#   WHOLE_OBJECT    부품 하나를 통째로 감싼다
#   CONTACT_POINT   볼트로 조여진 접속 지점 하나하나
#   TERMINAL_GROUP  기기 한쪽 단자군 전체를 하나로
#   UNKNOWN         근거 없음. 확정하지 않는다 (라벨러에게 배포하지 않는다)
# ---------------------------------------------------------------------------
WHOLE_OBJECT = "WHOLE_OBJECT"
CONTACT_POINT = "CONTACT_POINT"
TERMINAL_GROUP = "TERMINAL_GROUP"
UNIT_UNKNOWN = "UNKNOWN"

# 단위의 뜻. 보고서가 이 문구를 그대로 쓴다 (문서에 손으로 적지 않기 위함).
UNIT_DESC = {
    WHOLE_OBJECT:   "부품 하나를 통째로 감싼다",
    CONTACT_POINT:  "볼트로 조여진 접속 지점 하나하나",
    TERMINAL_GROUP: "기기 한쪽 단자군 전체를 하나로",
    UNIT_UNKNOWN:   "근거 없음 — 확정하지 않는다. 라벨러에게 배포하지 않는다",
}
UNIT_ORDER = [CONTACT_POINT, TERMINAL_GROUP, WHOLE_OBJECT, UNIT_UNKNOWN]

# 근거가 있는 것만 적는다. 나머지는 아래 annotation_unit() 이 기본값을 준다.
ANNOTATION_UNIT = {
    # 정본 근거 — 접촉부 높이 / 본체 높이 중앙 0.462, 0.379
    "mold_tr_contact":        CONTACT_POINT,
    "ct_transformer_contact": CONTACT_POINT,
    # 가이드 ACB&MCCB 반 예시 이미지 + P9 참고 1,777박스 세로비 0.922 (DEC-015)
    "mccb_contact":           TERMINAL_GROUP,
    # 참고 P6 159박스 + 표본 15장 육안 판정 — TERMINAL_GROUP 0건 (DEC-024)
    "vcb_contact":            CONTACT_POINT,
    # 라벨 실적 0건 — 시드 라벨링 이후 판단 (NQ-13)
    "lbs_primary":            UNIT_UNKNOWN,
    "lbs_secondary":          UNIT_UNKNOWN,
    "transformer_contact":    UNIT_UNKNOWN,
    "incoming_contact":       UNIT_UNKNOWN,
    "ct_contact":             UNIT_UNKNOWN,
    "acb_contact":            UNIT_UNKNOWN,
}

# 단위를 그렇게 정한 근거. 위 값과 1:1 로 붙어 있어야 보고서에 근거가 실린다.
# 명시되지 않은 클래스는 annotation_unit_basis() 가 기본 근거를 돌려준다.
ANNOTATION_UNIT_BASIS = {
    "mold_tr_contact":        "정본 P1 1,365박스 · 접촉부/본체 세로비 중앙 0.462 (DEC-014)",
    "ct_transformer_contact": "정본 P3·P4 219박스 · 세로비 중앙 0.379 (DEC-014)",
    "mccb_contact":           "가이드 ACB&MCCB 반 예시 이미지 + 참고 P9 1,777박스 · "
                              "세로비 중앙 0.922 (DEC-015)",
    "lbs_primary":            "정본·참고 모두 라벨 실적 0건 (NQ-13)",
    "lbs_secondary":          "정본·참고 모두 라벨 실적 0건 (NQ-13)",
    # 정본 P4 에 3박스뿐 — 단위를 정하기에는 표본이 부족하다 (부재가 아니라 희소)
    "transformer_contact":    "정본 3박스뿐 · 단위 판정 표본 부족 (NQ-13)",
    # [정정 2026-09-01] 이전 문구 "라벨 실적 0건" 은 사실이 아니었다.
    # 참고 등급 P6 에 159박스가 있고, 참고 등급은 DEC-015 가 mccb_contact 단위 판정에
    # 이미 채택한 증거 등급이다. 단 **존재 근거와 단위 확정은 별개**이므로(A-4 정책)
    # 좌표만으로는 확정하지 않고 표본을 열어 사람이 판정했다 (2026-09-02).
    # 판정표: reports/labeling/vcb_contact_review.csv · 실측치는
    # reports/data_audit/class_evidence.csv 가 스크립트로 집계한다.
    "vcb_contact":            "참고 P6 159박스 · 세로비 중앙 0.246 · 표본 15장 육안 판정 "
                              "CONTACT_POINT 10 / PARTIAL_LABELING 5 / TERMINAL_GROUP 0 "
                              "(DEC-024)",
    "incoming_contact":       "정본·참고 모두 라벨 실적 0건 (NQ-13)",
    "ct_contact":             "정본·참고 모두 라벨 실적 0건 (NQ-13)",
    # 제외에서 주의로 승격되면서 라벨 대상이 됐다(DEC-030). **여기 적지 않으면**
    # annotation_unit() 의 기본값 WHOLE_OBJECT 로 떨어져 unit_confirmed() 가 True 가 되고
    # 곧바로 배포 목록에 실린다. 접촉부 계열은 근거 없이 WHOLE_OBJECT 로 두지 않는다.
    "acb_contact":            "정본·참고 모두 라벨 실적 0건 (NQ-13 · DEC-030)",
}
DEFAULT_UNIT_BASIS = "부품 단위가 자명 — 별도 근거 불요 (DEC-015)"


def annotation_unit(class_name):
    """이 클래스는 무엇을 하나의 객체로 세는가.

    접촉부 계열은 ANNOTATION_UNIT 에 명시된 것만 확정이고 나머지는 UNKNOWN 이다.
    그 밖의 부품 클래스는 부품 단위가 자명하므로 WHOLE_OBJECT 로 본다.

    **라벨 대상이 아닌 클래스(제외·폐지)는 단위가 없다.** UNKNOWN 을 돌려준다.
    이 한 줄이 없으면 아래 사고가 난다 — 폐지 클래스를 ANNOTATION_UNIT 에서 지우는
    순간 기본값 WHOLE_OBJECT 로 떨어져 unit_confirmed() 가 True 가 되고,
    `label_status == EXCLUDE or not unit_confirmed(...)` 로 거르던 배포 경로
    (CVAT 라벨 정의 · 시험셋 export)에 폐지 클래스가 그대로 실린다.
    """
    if class_name in NOT_LABELED:
        return UNIT_UNKNOWN
    if class_name in ANNOTATION_UNIT:
        return ANNOTATION_UNIT[class_name]
    return WHOLE_OBJECT


def annotation_unit_basis(class_name):
    """그 단위로 정한 근거. 보고서가 그대로 싣는다."""
    return ANNOTATION_UNIT_BASIS.get(class_name, DEFAULT_UNIT_BASIS)


def unit_confirmed(class_name):
    """라벨러에게 배포할 수 있는가 (단위가 확정됐는가)."""
    return annotation_unit(class_name) != UNIT_UNKNOWN


def is_labelable(class_name):
    """라벨 대상인가 (제외도 폐지도 아닌가)."""
    return class_name not in NOT_LABELED


def labelable_classes():
    """라벨 대상 클래스 (제외 3종 + 폐지분을 뺀 것). class_id 순."""
    return [c for c in sorted(CLASSES, key=lambda x: x.class_id)
            if c.label_status not in (EXCLUDE, RETIRED)]


def units_summary():
    """단위별 {클래스 목록, 개수}. 보고서 표를 이것으로 만든다."""
    out = {u: [] for u in UNIT_ORDER}
    for c in labelable_classes():
        out[annotation_unit(c.class_name)].append(c)
    return out


def unit_counts():
    """(확정 클래스 수, 라벨 대상 총수)."""
    lab = labelable_classes()
    return sum(1 for c in lab if unit_confirmed(c.class_name)), len(lab)

# 가이드 01 SCOPE 의 촬영·가공 우선순위(원 안 숫자). 반 배치 순서와는 다르다.
# 가이드 그리드의 10개 반 중 현존 폴더에 대응하는 것만 옮겼다.
PANEL_PRIORITY = {
    "P1-TR반": 1, "P2-LBS&LA반": 2, "P3-MOF반": 3, "P4-MOF&PT반": 3,
    "P5-PF&PT반": 4, "P6-VCB반": 5, "P7-VCB&CT반": 8,
    "P8-ACB반": 9, "P9-MCCB반": 10, "P10-ACB&MCCB반": 9,
}

# 2026-08-27 3-가공 에서 삭제된 반. 3-가공.zip 에서 복구 가능.
# P11-CNCV반 은 가이드 ⑥ 반이며 케이블헤드(#14)의 주 출처였다.
PANELS_REMOVED = {"P11-CNCV반": ["cable_head"], "P12-배선반": [], "P13-기타": []}


def panels_of(class_name):
    """해당 클래스가 후보로 등장하는 반 목록 (파생값)."""
    return [p for p, cs in PANEL_CLASSES.items() if class_name in cs]


def priority_of(class_name):
    """등장 반들의 가이드 우선순위 최솟값 (파생값). 등장 반이 없으면 None."""
    ps = [PANEL_PRIORITY[p] for p in panels_of(class_name) if p in PANEL_PRIORITY]
    return min(ps) if ps else None


def labelable(panel):
    """해당 반의 후보 클래스 (EXCLUDE 만 제거). 단위 미확정도 포함한다.

    **배포용이 아니다.** 라벨러에게 보여줄 목록은 deployable() 을 쓴다.
    이 함수는 '이 반이 무엇을 담고 있는가'(시드 배분·수요 산정)를 위한 것이다.
    """
    return [c for c in PANEL_CLASSES[panel] if is_labelable(c)]


def deployable(panel):
    """해당 반에서 **실제로 그리라고 배포할** 클래스.

    EXCLUDE 3종과 annotation unit 미확정 클래스를 뺀다. 지침서 §1 표 · CVAT 반별
    라벨 목록 · 반별 참조 카드가 전부 이 함수 하나에서 나와야 한다.

    labelable() 과 나누는 이유 — 초판 감사에서 지침서 §1(후보 목록)과 §2(단위 미확정
    7종 그리기 금지)가 5개 반에서 충돌한 것이 이 구분을 코드로 두지 않았기 때문이다.
    """
    return [c for c in labelable(panel) if unit_confirmed(c)]


def panel_id(panel):
    """'P6-VCB반' -> 'P6'. CVAT task 이름·집계 키로 쓴다 (파생값)."""
    return panel.split("-", 1)[0]


BY_PANEL_ID = {panel_id(p): p for p in PANEL_CLASSES}


def yolo_names():
    """data.yaml 의 names 블록 (id -> 한글명)."""
    return {c.class_id: c.canonical_name for c in sorted(CLASSES, key=lambda x: x.class_id)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔 cp949 대응

    n = {s: sum(1 for c in CLASSES if c.label_status == s)
         for s in (LABEL, CAUTION, EXCLUDE, RETIRED)}
    print(f"가이드 {GUIDE_VERSION} ({GUIDE_REVISED}) — 클래스 {len(CLASSES)}개  "
          f"가공 {n[LABEL]} 주의 {n[CAUTION]} 제외 {n[EXCLUDE]} 폐지 {n[RETIRED]}\n")
    for panel, cs in PANEL_CLASSES.items():
        lab = labelable(panel)
        prov = " [잠정]" if panel in PANEL_CLASSES_PROVISIONAL else ""
        shown = ", ".join(
            BY_NAME[c].canonical_name + ("(주의)" if c in CAUTIONED else "") for c in lab)
        print(f"{panel:<16} p{PANEL_PRIORITY[panel]:<2} 라벨 {len(lab)}종{prov}: "
              f"{shown or '— 없음 —'}")
        skip = [c for c in cs if c in EXCLUDED]
        if skip:
            print(f"{'':<20} 제외: {', '.join(BY_NAME[c].canonical_name for c in skip)}")
    ret = sorted(RETIRED_CLASSES)
    if ret:
        names = ", ".join(f"#{BY_NAME[c].guide_no} {BY_NAME[c].canonical_name}"
                          for c in ret)
        print(f"{chr(10)}폐지(신규 라벨 금지 · class_id 유지): {names}")
