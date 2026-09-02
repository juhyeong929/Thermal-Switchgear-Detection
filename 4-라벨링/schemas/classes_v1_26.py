"""구 26개 스키마와 v2 28개 스키마 사이의 승계 정의.

구 스키마 출처: `pilot/classes.py` (2022.05.27 PDF 26개 체크포인트 기준).
이 파일은 pilot 을 수정하지 않고 그 정의를 그대로 옮겨 적은 것이다. 인덱스 순서는
실제 라벨 파일이 쓰는 값이므로 절대 바꾸지 않는다.

migration_type
  renamed   같은 부품, v2 에서 명칭만 바뀜
  same      명칭·의미 그대로
  status    의미는 같고 가공여부가 v1 보류 -> v2 가공으로 바뀜
  split     v2 에서 반에 따라 서로 다른 클래스로 갈림 -> SPLIT_BY_PANEL 참조
"""

from .classes_v2 import BY_NAME

# (구 id, 구 영문키, 구 한글명)
OLD_CLASSES = [
    (0,  "core_iron",              "철심부"),
    (1,  "epoxy_surface",          "에폭시 표면"),
    (2,  "mold_tr_contact",        "몰드변압기 접촉부"),
    (3,  "power_fuse",             "전력퓨즈"),
    (4,  "lbs",                    "LBS"),
    (5,  "lbs_primary",            "LBS 1차측 접촉부"),
    (6,  "lbs_secondary",          "LBS 2차측 접촉부"),
    (7,  "cl_power_fuse",          "한류형 전력퓨즈"),
    (8,  "la",                     "LA"),
    (9,  "transformer",            "변압기"),
    (10, "transformer_contact",    "변압기 접촉부"),
    (11, "ct_transformer",         "변류기"),
    (12, "mof_fuse",               "MOF 1차측 전력퓨즈"),
    (13, "ct_transformer_contact", "변류기 접촉부"),
    (14, "pt",                     "PT"),
    (15, "branch_contact",         "분기 접촉부"),
    (16, "incoming_contact",       "인입선로 접촉부"),
    (17, "vcb_contact",            "VCB 접촉부"),
    (18, "ct",                     "CT"),
    (19, "ct_contact",             "CT 접촉부"),
    (20, "capacitor",              "콘덴서"),
    (21, "mccb",                   "MCCB"),
    (22, "mccb_contact",           "MCCB 접촉부"),
    (23, "acb_contact",            "ACB 접촉부"),
    (24, "busbar",                 "부스바"),
    (25, "cable",                  "케이블"),
]

OLD_BY_ID = {i: (k, ko) for i, k, ko in OLD_CLASSES}

# 구 id -> (v2 class_name, migration_type, 근거)
MIGRATION = {
    0:  ("core_iron",              "same",    ""),
    1:  ("epoxy_surface",          "same",    ""),
    2:  ("mold_tr_contact",        "same",    ""),
    3:  ("silencer_power_fuse",    "renamed", "가이드 개정 2번: TR 반 전력퓨즈 -> 소음기부착형 전력퓨즈"),
    4:  ("lbs",                    "same",    ""),
    5:  ("lbs_primary",            "status",  "가이드 개정 3번: LBS 1차측 접촉부 보류 -> 가공"),
    6:  ("lbs_secondary",          "status",  "가이드 개정 3번: LBS 2차측 접촉부 보류 -> 가공"),
    7:  ("cl_power_fuse",          "same",    "가이드 개정 1번: 한류형 전력퓨즈로 명칭 확정"),
    8:  ("la",                     "same",    ""),
    9:  ("transformer",            "same",    ""),
    10: ("transformer_contact",    "status",  "가이드 개정 4번: 변압기 접촉부 보류 -> 가공"),
    11: ("ct_transformer",         "same",    "가이드 개정 4번: '분류기' -> '변류기' 명칭 정정"),
    12: ("ncl_power_fuse",         "renamed", "가이드 개정 4번: MOF&PT 반 전력퓨즈 -> 비한류형 전력퓨즈"),
    13: ("ct_transformer_contact", "status",  "가이드 개정 4번: 변류기 접촉부 보류 -> 가공"),
    14: ("mold_pt",                "renamed", "가이드 개정 5번: PT -> 몰드타입 PT"),
    15: (None,                     "split",   "가이드 개정 6·7번: 반에 따라 케이블헤드 / 분기 접촉부로 갈림"),
    16: ("incoming_contact",       "same",    ""),
    17: ("vcb_contact",            "same",    ""),
    18: ("ct",                     "same",    ""),
    19: ("ct_contact",             "same",    ""),
    20: ("capacitor",              "same",    ""),
    21: ("mccb",                   "same",    ""),
    22: ("mccb_contact",           "same",    ""),
    23: ("acb_contact",            "same",    ""),
    24: ("busbar",                 "same",    ""),
    25: ("cable",                  "same",    ""),
}

# 구 15 branch_contact 는 v2 에서 반에 따라 이름이 갈린다.
# 가이드 ⑤ VCB 반 · ⑥ CNCV 반 -> 케이블헤드로 통일 / ④ PF&PT 반 -> 분기 접촉부 유지.
# 그 밖의 반(P8·P9·P10 등)에서 이 클래스가 쓰였다면 가이드에 대응 항목이 없으므로
# 자동 변환하지 않고 보류한다.
SPLIT_BY_PANEL = {
    "P5": "branch_contact",   # PF&PT 반 — 분기 접촉부 (명칭 유지)
    "P6": "cable_head",       # VCB 반   — 케이블헤드로 통일
    "P11": "cable_head",      # CNCV 반  — 케이블헤드로 통일 (현재 폴더 삭제됨)
}

# v2 에서 새로 생겨 구 스키마에 대응이 없는 클래스 — 전량 신규 라벨링 필요
NEW_IN_V2 = ["sa"]


def new_id(old_id, panel_id=None):
    """구 class id -> v2 class id. 확정 불가면 None 을 돌려준다 (자동 변환 금지 신호)."""
    name, kind, _ = MIGRATION[old_id]
    if kind == "split":
        name = SPLIT_BY_PANEL.get(panel_id)
        if name is None:
            return None
    return BY_NAME[name].class_id
