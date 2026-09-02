"""원본·작업 경로 중앙 정의.

원본 데이터(`1-수집`, `3-가공`)는 **이동하지 않는다.** 66,186장을 복사하면 디스크가
두 배로 들고 원본/사본 어느 쪽이 기준인지 흐려진다. 대신 여기서 경로만 참조하고,
작업 산출물(메타데이터·중복분석·라벨)만 `4-라벨링/data` 아래에 쌓는다.
근거: reports/decisions/DEC-002-panel-structure.md
"""

from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent      # 4-라벨링
ROOT    = PROJECT.parent                              # 열화상

# --- 원본 (읽기 전용, 수정 금지) ---------------------------------------------
RAW_COLLECT   = ROOT / "1-수집"          # 촬영 원본
PROCESSED     = ROOT / "3-가공"          # 반별로 정리된 열화상 (라벨링 입력)
ARCHIVE_ZIP   = ROOT / "3-가공.zip"      # 삭제된 P11~P13 및 미전개분의 복구원
GUIDE_HTML    = ROOT / "수배전반_열화상_라벨링_가이드_v2.html"
PIPELINE_HTML = ROOT / "수배전반_열화상_라벨링_파이프라인.html"
PILOT         = ROOT / "pilot"           # 사전 실험. 참조 전용

# --- 작업 산출물 -------------------------------------------------------------
DATA      = PROJECT / "data"
METADATA  = DATA / "metadata"
DEDUP     = DATA / "dedup"
LABELING  = DATA / "labeling"
SPLITS    = DATA / "splits"
BACKUP    = DATA / "backup"              # 기존 라벨 원본 스냅샷

SCHEMAS   = PROJECT / "schemas"
SCRIPTS   = PROJECT / "scripts"
REPORTS   = PROJECT / "reports"
AUDIT     = REPORTS / "data_audit"
DECISIONS = REPORTS / "decisions"
PROFESSOR = REPORTS / "professor"
LOGS      = PROJECT / "logs"

# --- 반 정의 -----------------------------------------------------------------
# 작업 범위: 현존 데이터는 10개 반이며, 각 반은 독립 데이터 도메인으로 유지한다(병합 금지).
# P11~P13 은 원본 zip 잔존 여부와 복구 필요성을 별도 결정사항(DEC-006)으로 관리하며,
# 복구하기 전까지 라벨링 작업 범위에 포함하지 않는다.
PANELS = [
    "P1-TR반", "P2-LBS&LA반", "P3-MOF반", "P4-MOF&PT반", "P5-PF&PT반",
    "P6-VCB반", "P7-VCB&CT반", "P8-ACB반", "P9-MCCB반", "P10-ACB&MCCB반",
]

# 2026-08-27 3-가공 에서 삭제됨. 3-가공.zip 에 잔존해 복구 가능하나, 복구 전까지는
# 범위 밖이다. 인벤토리에는 '삭제됨' 상태로 기록만 남긴다.
PANELS_REMOVED = ["P11-CNCV반", "P12-배선반", "P13-기타"]

RGB_SUFFIX = "_rgb_image"   # 3-가공 의 실화상 페어 파일 접미사


def panel_dir(panel):
    return PROCESSED / panel


def is_rgb(name):
    return RGB_SUFFIX in str(name)
