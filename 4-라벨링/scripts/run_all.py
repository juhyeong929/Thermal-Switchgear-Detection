"""전 파이프라인을 순서대로 다시 돌린다. 산출물 재현용.

데이터가 바뀌었을 때 이것 하나만 돌리면 인벤토리부터 교수님 보고서까지 전부 갱신된다.
원본(`1-수집`, `3-가공`, `pilot`)은 어느 단계에서도 수정하지 않는다.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = [
    ("STEP 01  이미지 인벤토리",     "build_image_inventory.py"),
    ("STEP 03  기존 라벨 조사",      "audit_labels.py"),
    ("STEP 07  라벨 승계·검증",      "migrate_labels.py"),
    ("STEP 02  반/클래스 인벤토리",  "build_inventories.py"),
    ("STEP 04-05  스키마 표 생성",   "build_schema_tables.py"),
    # --- 아래 4개는 A-2/A-3 로 편입됐다 ------------------------------------
    # 전에는 시드·지침서 표·CVAT 정의가 파이프라인 **밖**에 있었다. 그래서
    # DEC-021 이 classes_v2 를 바꿔도 seed_candidates.csv 가 따라오지 않았고,
    # 라벨러가 폐기된 정책으로 작업할 뻔했다(2차 감사 V-3).
    # 클래스 정책에서 파생되는 것은 전부 여기서 다시 만든다.
    ("STEP 10  시드 후보 선정",      "seed_select.py"),
    ("클래스 존재 근거 집계",        "build_class_evidence.py"),
    ("가공 대상 종합표 재생성",      "build_reference_table.py"),
    ("지침서 클래스 표 생성",        "build_guide_tables.py"),
    ("반별 CVAT task 정의",          "build_cvat_tasks.py"),
    # ----------------------------------------------------------------------
    ("선정 계보 기록",               "build_selection_provenance.py"),
    ("정본 라벨 감사",               "canonical_audit.py"),
    ("규격 위반 격리",               "build_quarantine.py"),
    ("분할 정책·누수 감사",          "build_splits.py"),
    ("OSD 중첩 측정",                "osd_overlap.py"),
    ("flir.py 호환성 확인",         "flir_compat_check.py"),
    ("회차 비교표 (v1 대비 v2)",      "trial_compare.py"),
    ("인증 지표 집계",               "certification_evidence.py"),
    ("보고서 생성",                  "build_professor_report.py"),
    # 마지막에 정합성을 다시 센다. 시드 정책 지문 불일치가 여기서 FAIL 로 뜬다.
    ("상태 점검 (시드 지문 포함)",    "status_check.py"),
]

# 중복 분석은 전량 디코드와 임베딩이 필요해 40분 이상 걸린다. 기본에서 뺐다.
# 이미지가 바뀌었을 때만 `--with-dedup` 으로 다시 돌린다.
DEDUP_STEPS = [
    ("STEP 08a  지문 계산(exact+pHash)", "dedup_a_hash.py"),
    ("STEP 08b  LSH 후보쌍",             "dedup_b_candidates.py"),
    ("STEP 08c  임베딩",                 "dedup_c_embed.py"),
    ("STEP 08d  클러스터·대표 선정",     "dedup_d_cluster.py"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    steps = STEPS
    if "--with-dedup" in sys.argv:
        # 중복 결과가 보고서에 반영되도록 dedup 을 먼저 돌린다.
        steps = STEPS[:1] + DEDUP_STEPS + STEPS[1:]
    else:
        print("중복 분석은 건너뛴다 (--with-dedup 로 포함). "
              "기존 dedup 산출물이 있으면 보고서에 그대로 반영된다.")
    for title, script in steps:
        print(f"\n{'='*64}\n{title}  ({script})\n{'='*64}")
        r = subprocess.run([sys.executable, str(HERE / script)],
                           encoding="utf-8", errors="replace",
                           capture_output=True)
        print(r.stdout, end="")
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            sys.exit(f"실패: {script}")
    print("\n전 단계 완료")


if __name__ == "__main__":
    main()
