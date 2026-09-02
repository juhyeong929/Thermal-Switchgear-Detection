"""라벨링 클래스 정의 — 26개 스키마 (표준).

aivoucher-labelling_22.05.27.pdf 의 26개 체크포인트를 그대로 쓴다. 순서는 실제 라벨링
작업물(IR1_3반/data.yaml)과 일치해야 하므로 바꾸지 않는다.

처음에는 PDF 에서 '가공 여부 O' 인 16개만 채택하고 접촉부는 상위 부품에 합치도록
권고했으나, 실제 작업 결과 변류기 접촉부를 상별로 일관되게(장당 2~6개) 구분해 그릴 수
있음이 확인되어 26개 스키마를 표준으로 채택했다. 열화는 접촉부에서 먼저 나타나므로
접촉부를 따로 잡는 편이 진단에 유리하다.
"""

# (인덱스, 영문 키, 한글명, PDF 판정, 주로 등장하는 반)
CLASSES = [
    (0,  "core_iron",              "철심부",              "주의", "P1-TR반"),
    (1,  "epoxy_surface",          "에폭시 표면",          "채택", "P1-TR반"),
    (2,  "mold_tr_contact",        "몰드변압기 접촉부",     "채택", "P1-TR반"),
    (3,  "power_fuse",             "전력퓨즈",             "채택", "P1-TR반, P5-PF&PT반"),
    (4,  "lbs",                    "LBS",                "채택", "P2-LBS&LA반"),
    (5,  "lbs_primary",            "LBS 1차측 접촉부",     "채택", "P2-LBS&LA반"),
    (6,  "lbs_secondary",          "LBS 2차측 접촉부",     "주의", "P2-LBS&LA반"),
    (7,  "cl_power_fuse",          "한류형 전력퓨즈",       "채택", "P2-LBS&LA반"),
    (8,  "la",                     "LA",                 "채택", "P2-LBS&LA반"),
    (9,  "transformer",            "변압기",              "채택", "P3-MOF반, P4-MOF&PT반"),
    (10, "transformer_contact",    "변압기 접촉부",         "주의", "P3-MOF반, P4-MOF&PT반"),
    (11, "ct_transformer",         "변류기",              "채택", "P3-MOF반, P4-MOF&PT반"),
    (12, "mof_fuse",               "MOF 1차측 전력퓨즈",   "채택", "P3-MOF반, P4-MOF&PT반"),
    (13, "ct_transformer_contact", "변류기 접촉부",         "주의", "P3-MOF반, P4-MOF&PT반"),
    (14, "pt",                     "PT",                 "채택", "P4-MOF&PT반, P5-PF&PT반"),
    (15, "branch_contact",         "분기 접촉부",           "채택", "P6-VCB반, P8-ACB반, P11-CNCV반"),
    (16, "incoming_contact",       "인입선로 접촉부",       "주의", "-"),
    (17, "vcb_contact",            "VCB 접촉부",          "채택", "P6-VCB반, P7-VCB&CT반"),
    (18, "ct",                     "CT",                 "채택", "P7-VCB&CT반"),
    (19, "ct_contact",             "CT 접촉부",           "주의", "P7-VCB&CT반"),
    (20, "capacitor",              "콘덴서",              "채택", "P10-ACB&MCCB반"),
    (21, "mccb",                   "MCCB",               "채택", "P9-MCCB반, P10-ACB&MCCB반"),
    (22, "mccb_contact",           "MCCB 접촉부",         "주의", "P9-MCCB반, P10-ACB&MCCB반"),
    (23, "acb_contact",            "ACB 접촉부",          "제외", "P8-ACB반, P10-ACB&MCCB반"),
    (24, "busbar",                 "부스바",              "제외", "-"),
    (25, "cable",                  "케이블",              "제외", "-"),
]

NAMES = [c[1] for c in CLASSES]
KOREAN = {c[1]: c[2] for c in CLASSES}
KOREAN_BY_ID = {c[0]: c[2] for c in CLASSES}
VERDICT_PDF = {c[0]: c[3] for c in CLASSES}

# PDF 가 '일정한 패턴이 없어 탐지 정확도가 떨어짐' 으로 제외한 것들.
# 라벨이 들어오면 경고하되 버리지는 않는다 (나중에 판단할 수 있게).
DISCOURAGED = {24, 25, 23}

# 이전 16개 스키마 -> 26개 스키마 인덱스 변환 (기존 라벨 마이그레이션용)
NAMES16 = ["epoxy_surface", "mold_tr_contact", "lbs", "lbs_primary", "cl_power_fuse",
           "la", "transformer", "ct_transformer", "mof_fuse", "power_fuse", "pt",
           "branch_contact", "vcb_contact", "ct", "capacitor", "mccb"]
MAP16TO26 = {i: NAMES.index(n) for i, n in enumerate(NAMES16)}

# 반별로 후보 클래스를 좁히면 라벨러 실수와 오탐이 줄어든다.
PANEL_CLASSES = {
    "P1-TR반":        ["epoxy_surface", "mold_tr_contact", "power_fuse", "core_iron"],
    "P2-LBS&LA반":    ["lbs", "lbs_primary", "lbs_secondary", "cl_power_fuse", "la"],
    "P3-MOF반":       ["transformer", "transformer_contact", "ct_transformer",
                       "ct_transformer_contact", "mof_fuse"],
    "P4-MOF&PT반":    ["transformer", "transformer_contact", "ct_transformer",
                       "ct_transformer_contact", "mof_fuse", "pt"],
    "P5-PF&PT반":     ["power_fuse", "pt", "branch_contact"],
    "P6-VCB반":       ["vcb_contact", "branch_contact"],
    "P7-VCB&CT반":    ["vcb_contact", "ct", "ct_contact"],
    "P8-ACB반":       ["branch_contact", "acb_contact"],
    "P9-MCCB반":      ["mccb", "mccb_contact", "branch_contact"],
    "P10-ACB&MCCB반": ["capacitor", "mccb", "mccb_contact", "branch_contact", "acb_contact"],
    "P11-CNCV반":     ["branch_contact"],
    "P12-배선반":      ["branch_contact"],
    "P13-기타":        ["branch_contact", "mccb"],
}
