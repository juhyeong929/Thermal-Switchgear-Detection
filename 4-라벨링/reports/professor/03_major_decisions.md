# 03. 주요 의사결정

## 이번 회차 핵심 — 기존 라벨의 의미 검증

기존 `분기 접촉부` 와 v2 `케이블헤드` 의 의미 차이를 검토한 결과,
**가이드 자체의 예시 이미지 및 "명칭 통일" 근거를 통해 동일 대상임을 확인**하였다.
가이드의 케이블헤드 예시 화면 2장이 CVAT 상에서 `분기 접촉부` 로 라벨되어 있었다.

이에 따라 **P6 기존 라벨의 v2 매핑은 유지하되, 기존 라벨의 품질 문제와 검수 이력 부족으로
canonical 승격은 보류**하였다. 라벨을 `canonical`(P1/P3/P4)과 `reference`(P6/P9)로
등급을 나눠 관리한다.

> 자동 생성 · 2026-09-02 · 원문은 `reports/decisions/`

각 결정은 **문제 → 검토한 선택지 → 선택한 이유 → 근거 → 영향** 순으로 기록되어 있다.
"임의로 바꾼 것"과 "데이터 조사에 따른 결정"을 구분할 수 있게 하기 위한 형식이다.

| 번호 | 결정 | 요지 |
|---|---|---|
| [DEC-001](DEC-001-class-schema-v2.md) | 클래스 스키마를 가이드 v2 28개로 확정 | 라벨링 클래스를 「수배전반 열화상 라벨링 가이드 v2」의 28개 체크포인트로 확정한다. YOLO class_id 는 **가이드번호 − 1** 로 둔다. 정의는 `schemas/classes_v2.py` 한 곳에만 둔다. |
| [DEC-002](DEC-002-panel-structure.md) | 반(Panel)을 독립 데이터 도메인으로 유지, 원본은 이동하지 않음 | 0. **작업 범위는 현존 10개 반이다.** P11~P13 은 원본 zip 잔존 여부와 복구 필요성을 별도 결정사항(DEC-006)으로 관리하며, 복구하기 전까지 라벨링 범위에 포함하지 않는다. 1. `3-가공` 의 반 폴더를 **병합하지 않는다.** 각 반은 독립 데이터 도메인이다. |
| [DEC-003](DEC-003-label-migration-26-to-28.md) | 기존 26개 스키마 라벨을 v2 28개로 승계 | `pilot` 의 기존 라벨 중 **정본 3개 소스**만 v2 로 변환해 `data/labeling/reviewed` 에 둔다. 원본은 변환 전에 `data/backup` 으로 통째 복사한다. `pilot` 은 한 글자도 수정하지 않는다. |
| [DEC-004](DEC-004-labeling-exclusion-policy.md) | 라벨링 제외 / Ignore 정책 | 가이드 v2 와 파이프라인 문서의 제외 규칙을 `schemas/labeling_rules.py` 한 곳에 코드로 고정하고, 문서는 이 파일을 인용한다. **가이드·파이프라인에 없는 임계값을 새로 만들지 않는다.** |
| [DEC-005](DEC-005-rgb-labeling-policy.md) | 열화상 직접 라벨링을 기본으로 하고, RGB 페어는 보조로만 쓴다 | 본 작업의 라벨링 대상은 **열화상 이미지 자체**다. RGB 페어를 필수 입력으로 가정하지 않는다. RGB 페어는 (a) 경계 판단 참조 (b) 시드셋 우선 선정 (c) 보조 검수 용도로만 쓰고, 그 존재 여부는 `data/metadata/image_inventory.csv` 의 `h |
| [DEC-006](DEC-006-removed-panels-and-recovery.md) | 삭제된 반과 미탐지 하위 폴더의 처리 | 1. 삭제된 P11~P13 을 **복구하지 않는다.** 다만 복구 가능하다는 사실과 물량을 기록에 남긴다. 2. `P1-TR반/New Folder With Items` 의 41,323장은 **P1 데이터로 인정**하고 인벤토리에 포함한다. 하위 폴더명은 `subfolder` 컬럼으로 보 |
| [DEC-007](DEC-007-truncation-threshold.md) | 잘림(truncated) 판정 기준 구체화 | 프레임 밖 잘림 판정을 **재현 가능한 수치 기준**으로 구체화한다. ``` 분모 = 그 부품을 잘리지 않게 촬영했을 때 추정되는 전체 면적 분자 = 지금 이 프레임 안에 보이는 영역의 면적 노출 비율 < 30% -> 박스 생략 (Ignore) 노출 비율 >= 30% -> 보이는 영역만 |
| [DEC-008](DEC-008-dedup-method.md) | 중복 판정 방법과 임계값을 정답셋으로 보정 | 1. 106,685장을 전부 비교하지 않는다. **exact → pHash LSH 후보 축소 → 후보군 임베딩 검증 → 클러스터 → 대표 선정** 순으로 진행한다. 2. 후보는 **같은 반 안에서만** 만든다. 촬영 회차는 넘나들게 둔다. 3. 임계값을 손으로 정하지 않는다. **pHa |
| [DEC-009](DEC-009-panel-class-resolution.md) | 반별 후보 클래스 확정 (OQ-001~004) | | OQ | 대상 | 결정 | 상태 | |---|---|---|---| | OQ-002 | P8-ACB반 | **가이드 ⑧ 기준을 그대로 적용.** P10 과 동일 후보를 쓴다. 신규 클래스 추가 없음 | 닫음 | | OQ-003 | 케이블헤드 #14 | **라벨링 대상 유지.** P1 |
| [DEC-010](DEC-010-seed-selection.md) | 시드셋 후보 선정 설계 | 표본 풀은 STEP 08 의 대표(독립) 이미지 38,957장. 목표 400장(파이프라인 04단계 권고 300~500). **반 비례 배분을 쓰지 않는다.** 클래스 수요에서 반 할당량을 역산한다. |
| [DEC-011](DEC-011-reference-vs-canonical-labels.md) | 검증된 정본과 참고용 라벨을 분리한다 | 라벨을 **두 등급으로 나눠 관리한다.** 합치지 않는다. | 등급 | 대상 | 박스 | 용도 | |---|---|---:|---| | **canonical (정본)** | P1 / P3 / P4 | 4,177 | 학습·지표의 기준 | | **reference (참고)** | P6 54 |
| [DEC-012](DEC-012-cablehead-boundary.md) | 케이블헤드(#14) 경계 규칙: 사례 분석과 부분 확정 |  |
| [DEC-013](DEC-013-nq8-semantic-identity.md) | NQ-8: 구 `분기 접촉부` 와 v2 `#14 케이블헤드` 의 의미 동일성 |  |
| [DEC-014](DEC-014-contact-boundary-and-grades.md) | 접촉부 경계는 클래스별로 다르다 + 라벨 등급 명시 | 1. **접촉부 계열에 공통 경계 규칙을 두지 않는다.** 클래스마다 라벨 단위가 다르다. 2. `DEC-011` 의 `접촉부는 단자군 단위` 를 **정정한다.** 과일반화였다. 3. P6·P9 참고 라벨에 `annotation_grade = reference` 를 명시한다. 4. 케이 |
| [DEC-015](DEC-015-nq11-annotation-unit.md) | NQ-11: MCCB 접촉부의 annotation unit + 클래스별 단위 체계 도입 |  |
| [DEC-016](DEC-016-canonical-audit.md) | 정본(canonical) 라벨 감사 결과 (OQ-009) |  |
| [DEC-017](DEC-017-canonical-quarantine.md) | 정본 규격 위반 박스의 격리 (OQ-013) | DEC-016 감사에서 나온 **같은 클래스 중복 20쌍**을 다음처럼 처리한다. ``` canonical_original 정본 파일은 그대로 둔다. 수정하지 않는다 ↓ QUARANTINE 목록에 등재 data/labeling/quarantine/canonical_quarantine.c |
| [DEC-018](DEC-018-split-policy.md) | train / val / test 분할 정책 (도구·감사까지) |  |
| [DEC-019](DEC-019-trial-first-and-interim-policies.md) | 조사보다 시험 라벨링을 먼저 한다 · OQ 4건 잠정 정책 | 1. **1차 시험 라벨링(30장)을 지금 착수한다.** OQ 를 전부 해소한 뒤에 하지 않는다. 2. **OQ-010 · OQ-015 · OQ-016 · OQ-017 은 닫지 않는다.** 조사 결과를 그대로 보존한 채 *지금 무엇을 쓰고 있는가* 를 잠정 정책으로 기록한다. 3. ** |
| [DEC-020](DEC-020-annotation-return-format.md) | 시험 라벨링 회수 포맷: YOLO 1.1 + CVAT XML 이중 회수 | 1. **주 포맷은 YOLO 1.1 을 유지한다.** 프로젝트 표준을 바꾸지 않는다. 일치도(개수 일치 · mIoU · Kappa)의 primary input 은 계속 YOLO 다. 2. **CVAT for images 1.1 XML 을 함께 회수해 보존한다.** bbox 속성이 YOL |
| [DEC-021](DEC-021-p3-mof-candidate-policy.md) | P3-MOF반 후보 클래스 정책 (OQ-001 종결) | **P3-MOF반에서 변압기 계열(변압기 #8 · 변압기 접촉부 #24)을 독립 라벨링 대상으로 강제하지 않는다.** 열화상 영상에서 신뢰성 있게 식별 가능한 변류기 계열만 라벨링한다. ``` P3-MOF반 ├─ 변류기 -> 라벨링 ├─ 변류기 접촉부 -> 라벨링 ├─ 비한류형 전력퓨즈 |
| [DEC-022](DEC-022-quarantine-resolution.md) | 정본 격리 20쌍 판정 (OQ-013 · REV-003 종결) | DEC-017 이 격리해 둔 **같은 클래스 중복 20쌍**을 육안 판정했다. ``` 큰쪽_유지 11쌍 작은쪽_유지 8쌍 둘다_제외 1쌍 둘다_유효 0쌍 <- 감사 오탐이 한 건도 없었다 판단불가 0쌍 ``` **정본 라벨 파일은 수정하지 않았다.** 판정 결과는 격리 목록의 `stat |
| [DEC-023](DEC-023-oq016-closure.md) | OQ-016 종결: 현행 cluster split 유지 + 잔여 위험 문서화 | ``` decision = KEEP_CURRENT_CLUSTER_SPLIT threshold = 0.93 (변경 없음) 분할 단위 = cluster (변경 없음) 비율 = 70/15/15 (변경 없음 · 근거는 여전히 OQ-015) residual_risk = 근접 후보군 내 동일 시야 |
| [DEC-024](DEC-024-vcb-contact-annotation-unit.md) | VCB 접촉부(#14) 의 annotation unit = CONTACT_POINT | ``` class #14 vcb_contact · VCB 접촉부 annotation_unit CONTACT_POINT # 볼트로 조여진 접속 지점 하나하나 배포 P6-VCB반 · P7-VCB&CT반 에 배포한다 (v2 회차부터) NQ-13 잔여 6종 (LBS 1·2차측 · 변압기 · 분 |
| [DEC-025](DEC-025-branch-contact-retired.md) | 분기 접촉부(#13) 폐지, 케이블헤드로 명칭 통일 | ``` branch_contact (#13 / class_id 12) label_status 가공 -> 폐지(RETIRED) 신규 라벨링 금지 기존 실적 0건 (정본·참고 통틀어) 라벨 승계 하지 않는다 — cable_head 의 동의어로 두지 않는다 class_id 12 비우지 않고  |
| [DEC-026](DEC-026-reference-table-source.md) | 가공여부·제외 근거의 단일 출처를 `classes_v2.py` 로 확정하고 종합표를 재생성한다 | ``` decision = SCHEMA_IS_SOURCE_OF_TRUTH_REGENERATE_REFERENCE_TABLE 1. 가공여부·제외 근거의 단일 출처는 schemas/classes_v2.py 다 - ThermalClass.description 이 이전 판 종합표의 '비고' 열  |

## 변경 전 → 변경 후

| 구분 | 변경 전 | 변경 후 | 이유 |
|---|---|---|---|
| 클래스 | 26개 (2022 PDF) | 28개 (가이드 v2) | 가이드 v2 개정 10건 반영 — 명칭 3건, 보류→가공 4건, 신규 1건 |
| class_id | 0부터 순차 | 가이드번호 − 1 | 가이드 종합표와 직접 대조 가능 |
| 반 구조 | 가이드 8개 반 기준 | 현존 10개 폴더 유지 | 수집 출처를 규칙에 맞춰 지우지 않음 |
| 라벨링 대상 | 실화상(RGB) → 좌표 전이 | 열화상 직접 | RGB 페어가 전체의 2.5%뿐 |
| 기존 라벨 | pilot 내 13개 소스 혼재 | 정본 3개 승계 | 소스 간 대조로 검수 계보 확인 |
| **라벨 등급** | 구분 없음 | canonical / reference 분리 | P6·P9 라벨에 미작업 의심분·이상치·검수 이력 부재가 확인되어 승격 보류 |
| **annotation unit** | `접촉부`를 하나의 규칙으로 | 클래스별로 따로 정의 (18/25 확정) | 정본은 접속점 단위, 참고는 단자군 단위로 **실제로 달랐다** |
| **케이블헤드 경계** | 상부 도체 제외(추정) | 상부 금속 단자·수직 도체 포함 | 가이드 자체 예시 이미지 2장으로 확정. 추정이 틀렸다 |
| **라벨링 착수 방식** | 시드 400장 바로 시작 | 1차 시험 30장 → 일치도 검증 → 규칙 수정 → 400장 | 규칙이 통하는지 먼저 확인하는 편이 되돌리는 비용보다 싸다 |
| **회수 포맷** | YOLO 1.1 만 회수 — bbox 외 속성이 소실됨 | YOLO 1.1(일치도용) + CVAT XML(속성 보존) 이중 회수 | YOLO 1.1 에는 bbox 외 attribute 저장 구조가 없다. 라벨러 작업 방식은 바꾸지 않고 정보 손실만 막는다 (DEC-020) |
