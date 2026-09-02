# 4-라벨링 — 수배전반 열화상 부품 객체 라벨링

검증·인증을 받을 본 작업 공간이다. 1차 목표는 **부품 객체 라벨링 데이터셋 구축**이다.
이상발열 탐지 모델이나 최종 시스템 설계는 이번 범위가 아니다.

## 원칙

1. **원본을 수정하지 않는다.** `1-수집`, `3-가공`, `pilot` 은 읽기 전용이다.
   이동·삭제·덮어쓰기를 하지 않는다.
2. **추측과 측정을 구분한다.** 로그에 `FACT` / `INFERENCE` / `DECISION` 으로 표시한다.
3. **숫자를 문서에 손으로 적지 않는다.** 전부 스크립트가 CSV 에서 집계한다.
4. **애매한 것을 코드에 몰래 결정하지 않는다.** `open_questions.csv` 에 남긴다.
5. **반(Panel)과 클래스(Class)를 혼동하지 않는다.**
   반 = 이 데이터가 어디서 수집되었는가 / 클래스 = 이 안에서 무엇을 라벨링하는가.
   반은 합치지 않고, 클래스만 공통 28개로 관리한다.
6. **관찰을 규칙으로 몰래 승격하지 않는다.** 시험 도중에 지침서를 고치면 뒤에 오는
   라벨러가 앞사람과 다른 규칙을 본 것이 되어 재현성 검증 자체가 무너진다.
   감사·분석용 수치에는 배포 금지를 값 옆에 적어 둔다 (`SMALL_OBJECT_SCOPE`).

## 5분 요약

| 질문 | 답 | 출처 |
|---|---|---|
| 이미지 몇 장인가 | IR 106,685 · RGB 2,674 | `reports/data_audit/panel_inventory.csv` |
| 반은 몇 개인가 | 현존 10개 (+ 삭제 3개, 복구 가능) | 위와 동일 |
| 클래스는 무엇인가 | 가이드 v2 28개 (가공 21 · 주의 4 · 제외 3) | `schemas/classes_v2.py` |
| 기존 라벨은 얼마나 | 4,177 bbox / 1,036 파일 (P1·P3·P4) | `reports/data_audit/migration_verification.csv` |
| 어떻게 승계했나 | 26→28 변환, 손실 0 · 보류 0 | `schemas/class_migration_26_to_28.csv` |
| 무엇을 라벨링하지 않나 | 부스바 · 케이블 · ACB 접촉부 | `schemas/labeling_rules.py` |
| 지금 어디까지 왔나 | STEP 10 완료 · 11~13 진행중 · **1차 시험 회수 3/5명** | `reports/status/progress.csv` · `trial_status.csv` |
| 무엇이 막혀 있나 | 열린 OPEN QUESTION 21건 · **지금 라벨링을 막는 것 0건** | `open_questions.csv` 의 `blocks_current_labeling` |
| 결정은 몇 건인가 | DEC-001 ~ DEC-023 (23건) | `reports/decisions/` |
| 지금 무엇을 기다리나 | **라벨러 D·E 2명** — 나머지 판정은 전부 끝났다 | `deploy_checklist_D_E.md` |
| 지금 최대 리스크는 | 데이터 누수가 아니라 **사람이 같은 기준을 재현하는가** | `trial_agreement_2026-09-01.md` |

교수님 보고용 정리본: `reports/professor/00_current_status.md` 부터 순서대로.
**알려진 한계: `KNOWN_LIMITATIONS.md`** — 지표를 읽을 때 함께 봐야 하는 것들.
**인증 대비 증거: `reports/certification/README.md`** — 이 저장소의 최종 목적이다.

## 인증이 무엇을 요구하는가

기준은 우리가 만든 것이 아니다. 파이프라인 문서 03 Quality Evidence 절이 출처이며,
유사 도메인에서 **국가 AI 학습데이터 구축사업**(과기정통부·NIA) 품질 검증을 통과한
선례(AI Hub dataSetSn=235, mAP@0.5 기준 70% · 실측 83.8%)를 참고 기준선으로 삼는다.

| | 지표 | 목표치 | 지금 |
|---|---|---|---|
| C-1 | 라벨링 오류율 | 종료 시 0 에 수렴 | **0.50%** (확정 19 + 지적 2 / 4,177) |
| C-2 | **라벨러 간 일치도** | **Kappa 0.8 이상** | **0.902 PASS** — 3쌍 평균 (기반 74%) |
| C-3 | 클래스 균형 | 시드 기준 클래스당 30~50 | 미측정 — 시드 라벨링 전 |
| C-4 | **검수 이력** | **전량 추적 가능** | **충족** — 10/10 · 서명 5/5 · 판정 대기 0 |
| C-5 | 모델 성능 (참고선) | mAP@0.5 ≥ 70% | 미측정 |

```bash
python scripts/certification_evidence.py   # 지표 5종을 파일에서 집계
python scripts/review_log.py               # 검수 대장 생성·점검
```

**빈 칸을 추정치로 채우지 않는다.** 심사에서 위험한 것은 빈 칸이 아니라 근거 없는 숫자다.
대체 지표를 본 지표인 척 쓰지도 않는다 — 기존 라벨 대조 Kappa 1.000 은 C-2 를 대신하지 못한다.

## 구조

```
4-라벨링/
├── schemas/          클래스·규칙·경로 정의 (단일 출처)
│   ├── classes_v2.py            가이드 v2 28개 클래스
│   ├── classes_v1_26.py         구 26개 스키마 + 26→28 변환 정의
│   ├── labeling_rules.py        제외/Ignore/속성 규칙
│   ├── paths.py                 원본·작업 경로
│   └── *.csv                    위 정의에서 자동 생성된 표
├── scripts/          집계·변환·회수·검증 (40개)
├── reports/
│   ├── data_audit/   인벤토리 CSV · OPEN QUESTION · oq016/ 표본
│   ├── decisions/    DEC-001 ~ DEC-023
│   ├── labeling/     지침서 · 경계 규격서 · 회수 전달문 · 시험 결과
│   ├── status/       progress.csv · trial_status.csv
│   └── professor/    보고용 문서 6종 (자동 생성)
├── logs/             날짜별 작업 로그
├── data/
│   ├── metadata/     image_inventory.csv
│   ├── backup/       기존 라벨 원본 스냅샷 (무수정)
│   ├── labeling/
│   │   ├── seed/         시드 후보 400 · 시험셋 30
│   │   ├── draft/trial/  배포본 · 라벨러 폴더 · _existing · _raw_export
│   │   ├── reviewed/     정본 라벨 (v2 승계본)
│   │   ├── quarantine/   격리 목록 (정본 무수정)
│   │   └── final/        미착수
│   ├── dedup/        중복 분석 결과 (106,685 -> 38,957)
│   └── splits/       train/val/test (cluster 단위 · 최종 고정 전)
└── experiments/      dedup · seed_selection · data_audit(canonical·oq016) ·
                      labeling_review · baseline · active_learning
```

원본 이미지는 여기로 복사하지 않는다. `schemas/paths.py` 가 `3-가공` 을 가리킨다.
근거: `reports/decisions/DEC-002-panel-structure.md`

## 재현

```bash
cd 4-라벨링
python scripts/run_all.py        # 인벤토리 → 라벨 승계 → 스키마 표 → 보고서
```

개별 확인:

```bash
python -m schemas.classes_v2       # 반별 라벨 대상 요약
python -m schemas.labeling_rules   # 제외/Ignore 규칙 요약
```

스키마 모듈은 패키지 상대 import 를 쓰므로 `python -m` 으로 실행한다.

## 진행 단계

STEP 01~10 완료. 11~13 진행중. 상세는 `reports/status/progress.csv`.

```
[완료] 01 저장소·데이터 구조 조사      06 제외/Ignore 규칙 반영
       02 반 인벤토리                  07 기존 bbox 승계 검증
       03 기존 클래스 인벤토리         08 중복·유사도 분석 (106,685 -> 38,957)
       04 v2 28개 스키마               09 실질 라벨링 물량 산정
       05 26→28 변환표                 10 시드 후보 400장 선정
[진행] 11 시드셋 구성 — 지침서 v1 · 시험셋 30장 배포 완료
       12 일치도 검증 — A·B·C 회수 · 3자 Kappa 0.902 · 기존 라벨 대조 완료
          ★ 다음은 D·E 의 독립 라벨링 (사람 작업)
       13 학습셋 분할 정책 — 누수 검증 종결(DEC-023). 최종 고정은 라벨 수집 후
```

라벨러에게 보낼 것: `reports/labeling/trial_instructions.md` · 배포 절차 `deploy_checklist_D_E.md`

## 1차 시험에서 나온 것 (라벨러 3/5명 · 30장)

측정 근거: `reports/labeling/trial_agreement_2026-09-01.md` ·
`mccb_diff_findings_2026-08-31.md` · `trial_vs_existing_2026-08-31.md`

### 라벨러 간 일치도 — 세 쌍 모두 인증 목표 통과

| 쌍 | Kappa | mIoU | 개수 일치율 |
|---|---:|---:|---:|
| A · B | 0.856 | 0.758 | 53.1% |
| A · C | **0.954** | 0.768 | 66.7% |
| B · C | 0.896 | 0.721 | 53.1% |
| **평균** | **0.902** | | |

> Kappa 는 **짝지어진 박스에서만** 계산된다. 쌍별 매칭 기반 중 가장 좁은 것이 74% 이고
> 개수 일치율은 53~67% 다. **전체 annotation 품질 점수로 읽지 않는다.**

### 작업 성향은 크게 갈렸다

| | A | B | C |
|---|---:|---:|---:|
| 박스 | 122 | 142 | 128 |
| 이미지 Skip | 12 | **2** | 12 |
| 작업시간 | 22분 | 60분 | 44분 |
| `scope=object` | 0 | 0 | **0** |
| 후보 밖 클래스 박스 | 3 | **23** | 3 |

### 통한 것 / 갈린 것

| | 결과 |
|---|---|
| **클래스 정의** | 통했다 — Kappa 0.856~0.954 |
| **annotation unit** | 통했다 — A_SPLIT · A_MERGE **0건** |
| 개수 | 갈린다 — 일치율 53~67% |
| 경계 | 갈린다 — mIoU 0.72~0.77, 방향성 없음 |
| Skip 정책 | **`scope=object` 3/3 미사용** — 개인 성향이 아니다 |

### 시험이 실제로 열린 질문을 재현했다

- **MOF 변압기/변류기 구분 불가** → `DEC-021` (P3 후보에서 변압기 계열 제외)
- **반 정보를 감춰 반별 후보 규칙을 쓸 수 없다** → `NQ-15` (3/3 재현.
  `A09` 에서 세 사람이 세 클래스로 갈렸다)
- **주의 등급의 "보일 때만" 재량 폭** → `NQ-16` (철심부 A 4박스 vs B 0박스)
- **작은 객체 하한 0.003** → `NQ-12` (2인 수렴 → 3인에서 폭 2.5배 확산. 재검토)
- **P3 에 몰드타입 PT** → `NQ-14` (A·B 가 독립적으로 같은 판단)

## 이 저장소에서 조용히 틀리는 것들

지표는 멀쩡한데 결과만 틀리는 종류라 눈으로 못 잡는다. 전부 실측으로 확인했고 장치를 걸어 뒀다.

| 함정 | 무슨 일이 벌어지나 | 장치 |
|---|---|---|
| CVAT YOLO export | 프로젝트 라벨 순서로 **class_id 를 0부터 다시 매긴다.** `classes.txt` 의 자리표시자를 모른다 | `trial_ingest.py` 가 `obj.names` 로 복원. 원본은 `_raw_export/` |
| 원본 export 위치 | 라벨러 폴더 **안**에 두면 `agreement.py` 가 같은 이름 txt 를 둘 다 읽어 정규화본을 덮어쓴다 | 원본을 폴더 **밖**으로. `trial_ingest.py` 가 잔여 txt 를 검사 |
| 선언된 OSD 영역 | 후보 영역이지 **가림 증거가 아니다.** 좌표만으로 "OSD 탓" 하면 틀린다 | `OQ-010` 에 정정 기록 |
| 근접 미달 쌍 42.8% | **누수율이 아니다.** 실측 추정은 20%이며 그것도 전체 데이터가 아니라 **근접 후보쌍이 분모**다 | `KNOWN_LIMITATIONS.md` KL-1 · `DEC-023` |
| 감사용 임계값 | 분석용 수치가 지침서로 새면 뒤 라벨러가 앞사람과 다른 규칙을 본다 | `labeling_rules.SMALL_OBJECT_SCOPE = "지침서 배포 금지"` |

## 시험 라벨링 회수 (DEC-019 · DEC-020)

```bash
# 배포 전 1회 — 이걸 빼면 라벨러 화면에 truncated 입력 칸이 없다
python scripts/cvat_labels_json.py

# 0단계 (필수) — CVAT 은 class_id 를 자기 라벨 순서로 다시 매긴다. obj.names 로 되돌린다
python scripts/trial_ingest.py --all

python scripts/agreement.py <라벨러 폴더들>              # 일치도 — 2명 이상
python scripts/cvat_xml_to_attributes.py <라벨러 폴더>   # 속성 (YOLO 가 못 담는 것)
```

### 분석 (1명분으로도 가능한 것)

```bash
python scripts/trial_vs_existing.py                    # 숨겨 둔 기존 라벨과 대조
python scripts/diff_analysis.py <폴더> --class 전체      # 차이를 원인별로 분해
python scripts/box_size_profile.py                     # 라벨러별 박스 크기 행동 (NQ-12)
```

### 점검

```bash
python scripts/status_check.py            # 문서가 아니라 파일을 읽어 상태를 다시 센다
python scripts/test_cvat_attributes.py    # 회수 도구 검증 44건
python scripts/oq016_sample.py --n 100    # 누수 검증용 층화 표본 (OQ-016)
```

배포 체크리스트: `reports/labeling/deploy_checklist_D_E.md`

## pilot 재사용

`pilot` 은 사전 실험 기록이다. **수치는 성능 근거로 쓰지 않고**, 재현 절차와 스크립트만
검토해서 가져온다.

| 용도 | pilot 스크립트 | 상태 |
|---|---|---|
| FLIR radiometric 온도 추출 | `flir.py`, `extract_all_temp.py` | 핫스팟 단계에서 필요 |
| RGB↔IR 좌표 정합 | `calibrate.py`, `transfer.py`, `calibration.json` | IR1 구간에서만 유효 (DEC-005) |
| labelImg 패치 | `fix_labelimg.py`, `verify_labelimg.py` | PyQt5 5.15.11 / Py3.13 호환 |
| CVAT 연동 | `cvat_prep.py`, `cvat_import.py` | 라벨러 다수 투입 시 |
| 라벨러 일치도 | `agreement.py` | **가져와 사용 중** (회수 구조 변경에도 무수정) |
| 데이터셋 분할 | `merge_split.py` | 쓰지 않음 — `build_splits.py` 로 재작성 (cluster 단위) |
| 학습·사전라벨 | `train.py`, `predict.py`, `review_autolabel.py` | STEP 12 |

가져오지 않는 것: `dataset/`, `runs/`, `out/` 의 학습 결과와 지표.

## 이번 범위가 아닌 것

이상발열 데이터 생성 · hotspot detector 개발 · 최종 이상탐지 모델 설계 ·
고정 카메라 시스템 구현 · RGB 전체 투영 파이프라인.
