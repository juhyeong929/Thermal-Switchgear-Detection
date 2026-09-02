# Practical Independent Audit

감사일: 2026-09-02  
감사 범위: 저장소 루트 전체, `1-수집/`, `3-가공/`, `4-라벨링/`, `pilot/`, ZIP 보존본, 코드·문서·실험 산출물  
감사 방식: 독립 재검토. 코드·원본 데이터·기존 라벨은 수정하지 않음. 본 보고서와 동봉 CSV만 신규 산출물.

## 1. Executive Verdict

### [FINAL VERDICT]

```text
47 / 100
RED
NOT_READY
```

### [400-SEED DECISION]

**NO.** 현재 상태로 외부 5인 라벨러에게 400장 seed 작업을 넘기지 않는다.

### [WHY]

가장 큰 문제는 데이터가 없거나 자동화가 전혀 없다는 것이 아니다. 현재 문제는 **배포 기준과 생성 산출물이 같은 상태를 가리키지 않는다는 것**, 그리고 3인 시험의 높은 pooled Kappa가 어려운 이미지·누락·Skip을 충분히 포함하지 않는다는 것이다. 또한 6개 labelable class의 annotation unit이 아직 UNKNOWN이고, OQ-016은 근접 유사 후보의 약 20% 동일 시야 위험을 확인했지만 이를 완전히 해소하지 못했다.

`annotator_guide_v2.md`는 존재하지만 D/E 회수 전 pending 상태이고, 실무 배포에 필요한 최종 승인·버전 고정·adjudication 절차가 확인되지 않는다. 따라서 현재는 연구용 분석 기반은 있으나 외부 업체 위탁용 운영 패키지는 아니다.

### [PROFESSOR-LEVEL ONE-SENTENCE VERDICT]

현재 프로젝트는 데이터 계보와 실패 기록은 비교적 잘 남아 있지만, **현재 코드·생성 문서·배포 가이드·평가 지표가 동일한 버전으로 잠기지 않아 5인 외부 라벨링을 시작하면 결과를 방어하기 어렵다.**

## 2. Score: 47 / 100

| 영역 | 점수 | 판정 근거 |
|---|---:|---|
| 데이터 무결성 | 7/10 | `image_inventory.csv` 109,359행, 실제 경로 109,359개 존재. `fingerprints.csv` 106,685행 모두 SHA-256. 다만 원본 대용량 데이터는 Git 외부이고 전체 보존본에 대한 독립 checksum manifest는 NOT EVIDENCED. |
| 클래스/스키마 | 5/10 | 28개 정의와 25개 labelable class는 존재. 그러나 6개 unit UNKNOWN, P3/P9 잠정성, 코드와 생성 evidence/seed 산출물의 불일치가 남아 있다. |
| 라벨링 규칙 | 6/15 | 경계 규격서와 v2 초안은 상세하지만 v1의 반별 목록과 미확정 unit 금지 규칙이 충돌한다. v2 최종 배포·승인 상태는 NOT EVIDENCED. |
| 라벨러 작업 가능성 | 4/15 | 3인 시험은 실제 수행됐지만 Skip 2~12장, 22~60분, 후보 밖 클래스 선택 등 운영 편차가 컸다. 5인 최종 조건은 아직 미측정. |
| annotation 품질관리 | 5/15 | 독립 라벨 3인·중복 검수 20쌍·REV 로그는 있다. 그러나 recall 감사, 독립 adjudicator, 전체 이미지 기준 agreement, 체계적 재라벨 정책은 NOT EVIDENCED. |
| 중복/누수/분할 | 5/10 | exact/near duplicate 파이프라인과 기준선 재현은 강점. 하지만 cross-split cluster 0은 cluster 정의에 대한 결과일 뿐 leakage 0의 증명이 아니며, REV-005에서 근접 후보군 내 SAME/NEAR 22/101이 확인됐다. |
| 재현성/자동화 | 5/10 | 상대경로·seed·재현 산출물은 있다. 반면 데이터가 Git 외부이고 `requirements.txt`는 새로 추가된 무버전 목록이며, 생성 산출물 stale과 full pipeline의 쓰기·환경 의존성이 남아 있다. |
| 실무 운영성 | 2/5 | task·skip/time log의 기본 흔적은 있으나 5인 assignment, adjudication, SLA, rework, reviewer independence가 운영 절차로 고정되지 않았다. |
| 교수님 보고/추적성 | 3/5 | 결정 로그·교수님 보고·외부 감사 요약은 존재한다. 그러나 `C-1 오류율`, `C-2 Kappa`, `C-4 서명` 표현은 한계 없이 읽힐 위험이 있고 생성본 간 stale 불일치가 있다. |
| 연구 방법론 | 5/5 | 실패한 union-find, threshold sweep, OQ-016 잠정판정 철회 등 실패와 한계를 기록했다. 다만 이 강점이 운영 blocker를 상쇄하지는 않는다. |
| **총점** | **47/100** | **RED / NOT_READY** |

## 3. GREEN / YELLOW / RED

**RED — 현재 상태로 실무 투입 불가.**

이는 프로젝트 전체가 무가치하다는 뜻이 아니다. 데이터·코드·실험 기록을 외부 5인에게 곧바로 배포할 수 없다는 뜻이다. 최종 guide/schema/artifact lock, 6개 UNKNOWN unit 처리, 품질 측정 재설계, split residual-risk 처리 후 재심사해야 한다.

## 4. What is actually solid

### Strength 1 — 원본과 가공본을 분리하고 원본 삭제를 금지한 계보

- **Evidence:** `DEC-006`, `DEC-003`, `selection_funnel.csv`, `data/backup/`, `1-수집.zip`, `3-가공.zip`.
- **Why it matters:** 현재 `3-가공`에서 제외된 P11~P13 물량과 원본 보존 원칙을 추적할 수 있다.
- **제한:** 원본 ZIP과 폴더가 Git에 포함되지 않으므로 새 컴퓨터에서 자동 재현되는 보존본은 아니다.

### Strength 2 — exact hash와 near-duplicate를 분리한 파이프라인

- **Evidence:** `dedup_a_hash.py`의 SHA-256, pHash; `dedup_c_embed.py`; `dedup_d_cluster.py`; `fingerprints.csv` 106,685행.
- **Why it matters:** 파일 동일성과 시각적 유사성을 같은 지표로 뭉개지 않는다.
- **제한:** cosine 0.93와 leader 방식은 recall을 완전히 보장하지 않는다.

### Strength 3 — OQ-016에서 이전 결론을 철회하고 잔여 위험을 남김

- **Evidence:** `reports/data_audit/oq016/RESULT.md`, `REV-005`, `DEC-023`.
- **Why it matters:** 0 leakage로 과장하지 않고 101쌍 중 SAME 20, NEAR 2, DIFFERENT 79를 기록했다.
- **제한:** 표본은 교차 후보쌍의 일부이며 전체 이미지 leakage율이 아니다.

### Strength 4 — 정본과 reference를 구분하고 canonical도 감사함

- **Evidence:** `DEC-011`, `DEC-016`, `DEC-017`, `DEC-022`, `canonical_quarantine.csv`.
- **Why it matters:** canonical이라는 이름만으로 무결성을 가정하지 않고 20쌍을 격리·판정했다.
- **제한:** recall·semantic correctness·경계의 전수 독립 검증은 없다.

### Strength 5 — 실패 실험과 수정 이력을 보존함

- **Evidence:** `logs/`, `DEC-001~023`, threshold calibration, split constraint simulation, v1/v2 guide history.
- **Why it matters:** 결정의 출발점과 철회·정정 경로를 방어할 수 있다.
- **제한:** 기록이 있다는 것과 현재 배포물이 그 기록을 반영했다는 것은 별개이며, 실제로 stale 불일치가 발견됐다.

## 5. Major Risks

각 항목은 `FACT → INFERENCE → RISK` 순서로 읽는다.

1. **배포 버전 불일치:** 현재 `classes_v2.py`는 `vcb_contact`를 `CONTACT_POINT`로 확정하지만 `class_evidence.csv`, 생성 panel table, `seed_policy.json`은 VCB 접촉부를 미확정/비배포로 남긴다. → **누가 무엇을 그릴지 파일마다 달라진다.**
2. **unit 미확정:** `lbs_primary`, `lbs_secondary`, `transformer_contact`, `branch_contact`, `incoming_contact`, `ct_contact`가 코드상 UNKNOWN이다. → 25개 labelable class 중 6개는 동일한 인스턴스 수를 기대할 수 없다.
3. **평가 선택편향:** A/B/C의 비교 장수는 15~17/30이고 matched box만 Kappa에 들어간다. A/B/C의 Skip은 각각 12/2/12장이다. → pooled Kappa 0.902는 전체 annotation 품질이나 5인 운영 합의도를 나타내지 않는다.
4. **정본 품질 미확정:** 정본 4,177 bbox의 class/후보 위반과 duplicate는 일부 검사됐지만 누락(recall), 의미, boundary는 전수 독립 검증되지 않았다. → 4,158은 “정제된 ground truth”가 아니라 “duplicate 판정 적용 후 유지된 승계 라벨”로만 불러야 한다.
5. **split residual risk:** cluster cross-split 0은 설계상 cluster을 나누지 않았다는 뜻이다. REV-005는 근접 후보 교차쌍에서 SAME/NEAR 22/101, 모집단 가중 추정 약 20%를 기록했다. → 평가 점수의 낙관 편향 가능성이 남아 있다.

## 6. Blocking Issues

상세 표는 `blocking_issues.csv`에 있다.

### BLK-1 — 생성 산출물과 현재 schema가 서로 다름 — CRITICAL

- **FACT:** 현재 Python 실행 결과는 labelable 25개, unit confirmed 19개이며 `vcb_contact`는 deployable이다. 반면 `class_evidence.csv`는 VCB 접촉부를 `UNKNOWN`, `deployable=0`으로 기록하고, `seed_policy.json`/생성 가이드에도 VCB 접촉부가 배포 목록에서 빠져 있다.
- **INFERENCE:** 산출물은 코드와 같은 버전으로 갱신·검증되지 않았다.
- **RISK:** 라벨러 배포물, seed quota, 품질 보고가 다른 schema를 기준으로 삼을 수 있다.
- **조치:** 단일 source에서 guide·panel table·class evidence·seed policy를 재생성하고 SHA/version lock 후 모든 downstream CSV를 재검증한다.
- **지금 해결:** YES.

### BLK-2 — annotation unit 6개 UNKNOWN — CRITICAL

- **FACT:** `classes_v2.py`에서 6개 class가 `UNIT_UNKNOWN`; `class_evidence.csv`도 동일하게 기록한다. `annotator_guide_v2.md`는 “이번 판에서는 그리지 마세요”라고 쓰지만 final approval은 NOT EVIDENCED.
- **INFERENCE:** 25개를 목표로 하는 라벨링 계약에 6개가 operational definition 없이 들어가 있다.
- **RISK:** 동일한 물리 객체를 라벨러마다 다른 개수·범위로 기록한다.
- **조치:** 포함·제외를 명시적 결정으로 확정하고 class list, seed quota, C-3 분모를 함께 갱신한다.
- **지금 해결:** YES.

### BLK-3 — C-2가 전체 품질을 대표하지 않음 — HIGH

- **FACT:** A-B 17/30, A-C 15/30, B-C 17/30만 비교됐다. IoU≥0.5 matched boxes만 Kappa에 사용되고 pooled matched 281개 중 대다수가 MCCB 계열이다. count agreement는 53.1%, 66.7%, 53.1%다.
- **INFERENCE:** Kappa 0.902는 paired box의 class agreement에 가까우며 detection recall, missing box, skip policy, 5인 합의를 측정하지 않는다.
- **RISK:** 외부 라벨러 투입 후 누락·과소라벨·Skip 편차가 반복될 수 있다.
- **조치:** Skip 포함 image/object 단위 agreement, class별 precision/recall, box matching coverage, adjudication 전후 agreement를 사전 정의하고 D/E 포함 5인 조건으로 재측정한다.
- **지금 해결:** 400장 배포 전.

### BLK-4 — 정본 4,158을 ground truth로 사용할 근거 부족 — HIGH

- **FACT:** 4,177 bbox에서 duplicate 20쌍을 조사해 고유 19개 제외·18개 해제 후 학습 대상 4,158이 됐다. 하지만 canonical audit는 `unit_audit_status=NOT_AUDITABLE`인 class가 많고, recall 전수 검사는 없다.
- **INFERENCE:** 4,158은 duplicate 정리 결과이지 독립 gold standard가 아니다.
- **RISK:** 누락·잘못된 경계·잘못된 class가 학습/평가 기준에 남아 baseline을 오염시킨다.
- **조치:** 독립 reviewer가 class별·panel별·난이도별 표본을 재라벨하고 omission/commission/boundary를 따로 측정한다.
- **지금 해결:** full training 전. 최소한 seed 전 표본 감사는 즉시.

### BLK-5 — split leakage 잔여 위험을 품은 채 최종 평가셋을 고정할 수 없음 — HIGH

- **FACT:** cluster cross-split은 0이지만, near-threshold 후보 교차쌍은 41,184/96,292이고 REV-005에서 101쌍 중 22쌍이 SAME/NEAR였다. DEC-023은 현재 split을 유지하면서 residual risk를 관리한다.
- **INFERENCE:** “cluster 기준 누수 0”과 “평가 누수 0”은 다르다.
- **RISK:** 비슷한 장면이 train/val/test에 나뉘어 성능이 실제 일반화보다 높게 보일 수 있다.
- **조치:** 최종 보고에서 residual risk를 전면 표시하고, panel/session holdout 등 보수적 평가셋을 별도로 구성해 성능 범위를 제시한다.
- **지금 해결:** 최종 모델 성능 발표 전.

## 7. Dataset Audit

### 7.1 데이터 무결성 — WARN

- **FACT:** 로컬에는 `1-수집/` 약 370,536개 파일, `3-가공/` 약 109,366개 파일, `4-라벨링/` 3,987개 파일, `pilot/` 24,517개 파일이 있다. 원본 ZIP은 약 18.04GB, 가공 ZIP은 약 3.14GB다.
- **FACT:** `selection_funnel.csv`는 109,366 → 109,359(이미지가 아닌 7개 제외) → 106,685(IR만) → 38,957 대표 → 400 seed를 기록한다. CSV 경로 검증에서 109,359/109,359, seed 400/400, split 106,685/106,685가 현재 파일에 존재했다.
- **FACT:** `fingerprints.csv`는 106,685행 모두 SHA-256과 error 없음이다.
- **FACT:** P11~P13은 `3-가공`에서 제외됐지만 `3-가공.zip`에서 복구 가능하다고 기록돼 있다.
- **UNKNOWN:** `1-수집/` 전체와 두 ZIP의 독립 외부 checksum manifest, 장기 보존 위치, 복구 시험의 완료 상태.
- **판정:** 로컬 분석 계보는 PASS에 가깝지만, 외부 전달/장기 보존 기준에서는 WARN.

### 7.2 RGB/IR/온도

- **FACT:** 전체 IR 106,685장은 IR1 2,512(2.4%), IR2 54,686(51.3%), IR3 49,487(46.4%)다. RGB pair는 주로 IR1에 있고 panel inventory의 pair count로 추적한다.
- **FACT:** FLIR 호환성 표본 300장은 IR1 100/100 OK, IR2 0/100, IR3 0/100이다. 정본 라벨 1,036장은 전부 IR1이다.
- **INFERENCE:** temperature/radiometric 기반 분석과 정본 품질 결론은 전체 카메라 분포를 대표하지 않는다.
- **RISK:** IR1 도메인에 과적합된 모델 또는 OSD 특성에 영향을 받은 모델을 전체 IR2/IR3 성능으로 오해할 수 있다.
- **판정:** WARN.

### 7.3 원본/backup/path tracking

- **FACT:** `4-라벨링/data/backup`에 P1/P6/P9 라벨 스냅샷이 있고 원본 라벨은 수정하지 않는다는 결정이 반복된다.
- **FACT:** `paths.py`는 저장소 위치 기준 상대경로를 사용한다.
- **UNKNOWN:** backup 자체가 원본의 완전한 byte-level snapshot인지, 외부 PC에서 복구 검증됐는지.
- **판정:** WARN.

## 8. Annotation Rule Audit

### 8.1 문서 간 일치

- **FACT:** v1은 §1에서 P2의 LBS 1·2차 접촉부, P4의 변압기 접촉부, P5의 분기/인입선로 접촉부, P6/P7의 VCB/CT 접촉부를 반 후보로 나열한다. 같은 문서 §2는 이 7종의 unit이 정해지지 않아 그리지 말라고 한다.
- **FACT:** `guide_v1_divergence.csv`는 이 충돌과 HTML 개수표·목록·schema의 차이를 열거한다.
- **FACT:** v2 markdown은 반 정보를 공개하고 위 6개 UNKNOWN unit을 배포 제외한다. 그러나 `annotator_guide_v2.md`와 template가 함께 존재하고 D/E round가 pending이다.
- **FACT:** `classes_v2.py`, `class_evidence.csv`, `seed_policy.json`, 생성 panel table 사이에는 `vcb_contact`의 현재 상태가 일치하지 않는다.
- **판정:** **FAIL.** 외부 배포용 “한 가지 기준”이 아직 없다.

### 8.2 28개 class 전수 요약

아래 `status`는 존재·관측 여부와 unit 확정 여부를 분리했다. `vcb_contact`는 **현재 코드**와 **기존 생성 산출물**이 충돌하므로 별도 표시했다.

| id | class_name | annotation_unit | panel_candidate | evidence | status |
|---:|---|---|---|---|---|
| 0 | core_iron | WHOLE_OBJECT | P1 | canonical 634 | CONFIRMED_PRESENT |
| 1 | epoxy_surface | WHOLE_OBJECT | P1 | canonical 1,448 | CONFIRMED_PRESENT |
| 2 | mold_tr_contact | CONTACT_POINT | P1 | canonical 1,365; DEC-014 | CONFIRMED_PRESENT |
| 3 | lbs | WHOLE_OBJECT | P2 | no canonical/reference/trial box | NOT_YET_OBSERVED |
| 4 | lbs_primary | UNKNOWN | P2 | no box; NQ-13 | NOT_YET_OBSERVED / NOT_DEPLOYABLE |
| 5 | cl_power_fuse | WHOLE_OBJECT | P2 | trial B 15 | LIKELY_PRESENT |
| 6 | la | WHOLE_OBJECT | P2 | trial C 3 | LIKELY_PRESENT |
| 7 | transformer | WHOLE_OBJECT | P4 | canonical 1 | CONFIRMED_PRESENT, RARE |
| 8 | ct_transformer | WHOLE_OBJECT | P3/P4 | canonical 189 | CONFIRMED_PRESENT |
| 9 | ncl_power_fuse | WHOLE_OBJECT | P3/P4 | canonical 191 | CONFIRMED_PRESENT |
| 10 | silencer_power_fuse | WHOLE_OBJECT | P1/P5 | canonical 127; trial 0 | CONFIRMED_PRESENT, TRIAL_UNTESTED |
| 11 | mold_pt | WHOLE_OBJECT | P4/P5 | trial A/B 3/8 | LIKELY_PRESENT |
| 12 | branch_contact | UNKNOWN | P5 | no box; NQ-13 | NOT_YET_OBSERVED / NOT_DEPLOYABLE |
| 13 | cable_head | WHOLE_OBJECT | P2/P6 | reference 387; trial A/C | CONFIRMED_PRESENT, REFERENCE_ONLY |
| 14 | vcb_contact | CONTACT_POINT in code; UNKNOWN in artifacts | P6/P7 | reference 159; NQ-13 | **VERSION_CONFLICT** |
| 15 | ct | WHOLE_OBJECT | P6/P7 | trial A/C 2/2 | LIKELY_PRESENT |
| 16 | sa | WHOLE_OBJECT | P6 | trial A 3; OQ-004 HOLD | LIKELY_PRESENT / EXPERT_HOLD |
| 17 | capacitor | WHOLE_OBJECT | P8/P10 | reference 1 | CONFIRMED_PRESENT, RARE |
| 18 | mccb | WHOLE_OBJECT | P8/P9/P10 | reference 994; trial A/B/C | CONFIRMED_PRESENT |
| 19 | incoming_contact | UNKNOWN | P5 | no box; NQ-13 | NOT_YET_OBSERVED / NOT_DEPLOYABLE |
| 20 | busbar | EXCLUDED | none | schema exclusion | EXCLUDED |
| 21 | cable | EXCLUDED | none | schema exclusion | EXCLUDED |
| 22 | lbs_secondary | UNKNOWN | P2 | no box; NQ-13 | NOT_YET_OBSERVED / NOT_DEPLOYABLE |
| 23 | transformer_contact | UNKNOWN | P4 | canonical 3; unit sample insufficient | CONFIRMED_PRESENT / NOT_DEPLOYABLE |
| 24 | ct_transformer_contact | CONTACT_POINT | P3/P4 | canonical 219; DEC-014 | CONFIRMED_PRESENT |
| 25 | ct_contact | UNKNOWN | P7 | no box; NQ-13 | NOT_YET_OBSERVED / NOT_DEPLOYABLE |
| 26 | acb_contact | EXCLUDED | P8/P10 | schema exclusion; reference legacy findings | EXCLUDED |
| 27 | mccb_contact | TERMINAL_GROUP | P8/P9/P10 | reference 1,778; DEC-015 | CONFIRMED_PRESENT, REFERENCE_ONLY |

**판정:** 25개 labelable class를 “실제 라벨 운영 준비 완료”로 읽을 수 없다. 현재 코드 기준 19개 unit confirmed, 6개 UNKNOWN이지만 downstream evidence/seed는 이전 18개 confirmed 상태를 보인다.

### 8.3 INCLUDE / EXCLUDE / SKIP / attributes

- **FACT:** v1/v2는 empty label과 Skip을 구분하고 `skip_log.csv`, `time_log.csv`, YOLO+CVAT XML 이중 회수를 요구한다.
- **FACT:** `truncated`, `occluded`, `ignore`, `scope=image/object`를 문서화했다.
- **FACT:** C의 회수에서 배포본에 없는 case_id 3건과 빈 파일인데 Skip 기록이 없는 3건이 발견됐다.
- **INFERENCE:** 제출 위생 검사가 실제로 필요했고, 문서만으로는 충분하지 않았다.
- **RISK:** 업체 회수물에서 empty/Skip/partial object가 다시 섞일 가능성이 있다.
- **판정:** WARN. 위생 검사와 샘플 회수 계약을 배포 전 필수화해야 한다.

### 8.4 boundary

- **FACT:** boundary spec은 최소 pixel bbox, cablehead의 상부 도체 포함·케이블 제외, 접촉부 class별 unit, truncation 30%, small object는 식별 가능성, same-class duplicate 금지를 구분한다.
- **FACT:** cablehead elbow/base는 pending 또는 unknown으로 남는다.
- **FACT:** small-object candidate 0.003은 공식 threshold가 아니라고 명시돼 있다.
- **INFERENCE:** 문서가 조심스럽게 “모르는 것은 그리지 말라”고 했지만, 업체 계약에는 반드시 최종 처리 규칙·검수 escalation이 있어야 한다.
- **판정:** WARN/FAIL. 현재의 미확정 상태를 그대로 업체에 전달할 수 없다.

## 9. Human Annotation Audit

### 9.1 A–F 질문에 대한 판정

| 질문 | FACT | INFERENCE | 판정 |
|---|---|---|---|
| A. 클래스 선택 안정성 | Kappa는 높지만 A09 등에서 3인이 서로 다른 class를 골랐고 후보 밖 class도 그렸다. | 반 정보와 MOF 구분 문제가 class selection을 흔든다. | **FAIL** |
| B. annotation unit 안정성 | 3인 시험에서 scope=object 0회; 6개 unit은 UNKNOWN. | 시험에서 확인된 4개 핵심 class만 부분 안정이다. | **FAIL** |
| C. bbox 경계 안정성 | pair mIoU 0.721~0.768; MCCB contact 약 0.69~0.72. | 경계는 실무상 재량이 남아 있다. | **WARN** |
| D. Skip 정책 안정성 | Skip 2/30, 12/30, 12/30; v1에서 26건 모두 image scope. | 작업자 성향과 문구가 함께 영향을 줬다. | **FAIL** |
| E. 시간 편차 | A 22분, B 60분, C 44분. | 업체 capacity planning에 3배 가까운 편차가 위험하다. | **WARN/FAIL** |
| F. 차이 발생 규칙 | MOF 변압기/변류기, 반 후보 공개 여부, small object, MCCB contact가 반복된다. | 원인 분류는 됐지만 최종 adjudication rule은 닫히지 않았다. | **WARN** |

### 9.2 지표 해석

- **FACT:** A-B Kappa 0.856, A-C 0.954, B-C 0.896, 산술평균 0.902.
- **FACT:** 비교 장수는 15~17/30이며 Kappa는 IoU≥0.5 matched boxes에 대해서만 계산된다. count agreement는 53.1~66.7%다.
- **FACT:** 기존 라벨 대조는 7/12장, Kappa 1.000, count agreement 30.8%, mIoU 0.741이다.
- **INFERENCE:** Kappa 1.000은 paired class mismatch가 없었다는 뜻이지 기존 라벨과 라벨 개수·누락·경계가 맞았다는 뜻이 아니다.
- **판정:** 현재 품질 측정은 “matched class consistency”의 보조지표로는 유효하지만, 전체 annotation 품질 측정으로는 FAIL.

## 10. Dedup / Leakage Audit

### 10.1 Dedup

- **FACT:** 106,685 이미지가 38,957 대표로 줄었고 총 reduction rate는 63.48%다. P1 reduction 65.56%, P9 64.33%, P6 59.27% 등 panel별 편차가 있다.
- **FACT:** exact SHA-256, pHash 후보, embedding, cosine 0.93 leader 방식, representative metadata가 있다.
- **FACT:** threshold calibration에서 0.93 기준선은 38,957 cluster로 재현됐고 0.91~0.93에서 뚜렷한 sweet spot은 없었다.
- **INFERENCE:** 방법론과 재현은 강하지만 0.93이 모든 동일 시야를 포착한다는 근거는 아니다.
- **판정:** dedup 방법론 **PASS WITH LIMITATION**.

### 10.2 Leakage

- **FACT:** `split_leakage.csv`의 cluster cross-split은 0/38,957이다.
- **FACT:** 근접 미달 쌍 cross-split은 41,184/96,292(42.8%)이다.
- **FACT:** REV-005 101쌍은 SAME 20, NEAR 2, DIFFERENT 79, UNCERTAIN 0이다. 기록상 모집단 가중 추정은 약 20%다.
- **FACT:** session split 대안은 cluster cross-split 490과 P4/P7 validation 고갈 문제로 기각됐다.
- **INFERENCE:** 현재 split은 내부 cluster 정책에는 일관되지만, scene-level independence를 완전히 보장하지 않는다.
- **판정:** **WARN**, “누수 없음” 표현은 금지하고 residual-risk를 포함한 평가가 필요하다.

## 11. Reproducibility Audit

- **FACT:** 상대경로 기반 `paths.py`, 고정 seed, `seed_policy.json`, selection provenance, decision log, `requirements.txt`가 있다.
- **FACT:** Python AST/문법 검사와 현재 CSV 경로 존재 검사는 통과했다.
- **FACT:** `requirements.txt`는 패키지명만 있고 버전 lock이 없다. `torch`, `torchvision`, `ultralytics`, `labelImg` 호환 조합은 환경에 의존한다.
- **FACT:** raw/processed 데이터와 일부 `pilot/data`는 GitHub에서 제외된다. root clone만으로는 full pipeline을 실행할 수 없다.
- **FACT:** `run_all.py`는 여러 script를 순차 실행하며 dry-run 모드가 확인되지 않았다. 실행하면 산출물을 쓴다.
- **FACT:** 현재 생성 seed/evidence 산출물이 코드와 불일치한다.
- **판정:** 코드 위치 재현성은 **WARN/PASS**, end-to-end 재현성은 **FAIL**.

## 12. Operational Readiness

### 라벨러 관리

- task assignment 파일과 case provenance는 있다.
- annotator A/B/C의 작업 폴더, skip log, time log, XML/YOLO는 있다.
- 5인 또는 10인의 assignment version, guide checksum, reviewer ID, adjudication owner, rework SLA는 NOT EVIDENCED.

### 품질관리

- 독립 시험 라벨링은 3인까지 수행됐다.
- 기존 정본 duplicate 20쌍은 전수 판정됐다.
- 독립 recall audit, blind gold set, reviewer 간 독립 adjudication, 업체별 acceptance/rejection 기준은 NOT EVIDENCED.

### 판정

**FAIL for external vendor handoff.** 현재는 연구자 주도 trial 운영에는 적합하지만 계약 가능한 production QA pack은 아니다.

## 13. Professor Report Audit

- **FACT:** `reports/professor/00~06`과 certification evidence/gaps/traceability가 있다.
- **FACT:** 보고서에는 Kappa의 paired-box 한계, C-1 표기 권고, C-4 서명 5/5의 실체가 포함돼 있다.
- **FACT:** 동시에 `C-1 라벨링 오류율 0.50%`, `C-4 충족`, `C-2 v1 baseline 0.902`는 제목이나 표만 읽으면 전체 품질·5인 인증·독립 검수를 암시할 수 있다.
- **FACT:** professor-facing generated outputs가 current code와 일치하지 않는 사례가 있다(`class_evidence.csv`, generated panel table, seed policy).
- **INFERENCE:** 교수님이 요약 표만 읽으면 “정본·C-2·누수 검증이 완료됐다”고 과대해석할 가능성이 있다.
- **판정:** **WARN.** 본문에 caveat는 있으나 front-page status와 artifact lock이 충분하지 않다.

## 14. Research Methodology Audit

- **PASS:** 결정문과 로그가 DEC-001~023으로 연결돼 있고, 실패한 union-find·threshold·split 대안도 보존돼 있다.
- **PASS:** 측정값과 사람 판단을 구분하려는 문구가 반복된다. OQ-016의 기존 잠정 판단을 철회한 기록은 긍정적 증거다.
- **WARN:** Kappa 기준 0.8의 프로젝트 내 rationale은 확인되지 않았다. certification README가 외부 선례 mAP 70%를 설명하지만, Kappa 0.8의 근거는 NOT EVIDENCED.
- **WARN:** 0.003 small-object candidate와 0.93 cosine threshold는 실험값이지만, 최종 운영 오류·recall과 직접 연결되지 않는다.
- **FAIL for final claim:** 정본 4,158, 0 leakage, C-2 PASS를 최종 ground truth/일반화 성능 보증으로 확장해서는 안 된다.

## 15. Questions Professor May Ask

| 질문 | 현재 답 | 근거 | 취약점 | 보완 필요 |
|---|---|---|---|---|
| 왜 28개 클래스인가? | 가이드 v2 1~28을 기계적으로 YOLO id로 변환했다. | `classes_v2.py`, DEC-001/003 | 28개가 모두 operationally labelable하다는 뜻은 아니다. | 6 UNKNOWN의 포함/제외를 별도 결정 |
| 왜 일부는 정본이고 일부는 reference인가? | P1/P3/P4 승계본은 계보·검수가 있고 P6/P9는 참고 등급이다. | DEC-011, label source inventory | reference의 semantic/recall 품질이 독립 검증되지 않았다. | source별 QA grade와 승격 기준 |
| Kappa 0.902면 라벨 품질이 좋은가? | matched box class agreement의 baseline일 뿐이다. | agreement CSV, certification README | Skip과 unmatched box가 빠지고 P9가 76%를 차지한다. | 전체 object/image metrics, 5인 v2 |
| 누수가 0이라는 근거가 있는가? | cluster가 split을 가로지른 건 0이다. | split_leakage.csv | near-threshold SAME/NEAR 위험은 약 20% 추정이다. | 보수적 holdout 평가 |
| 20% 위험이면 왜 split을 유지했나? | 대안 threshold와 제약이 분포를 훼손해 현행을 유지했다. | OQ-016 RESULT, DEC-023 | 성능 해석에 위험이 남는다. | residual-risk를 성능 보고에 병기 |
| 4,158 bbox를 왜 믿는가? | duplicate 20쌍을 판정해 19개를 제외하고 18개를 해제한 승계 라벨이다. | DEC-022, quarantine CSV | recall·semantic·boundary 전수 검증은 없다. | blind audit sample |
| 라벨러 기준이 사람마다 다른데 어떻게 해결했나? | v2에서 반 공개·scope 강조·Skip 사유를 보강했다. | annotator_guide_v2.md | D/E 회수와 최종 승인 전이다. | 5인 v2 certification |
| 왜 0.003인가? | 접촉부 3종의 candidate 분포가 그 주변에 모였다. | boundary spec, NQ-12 | 3인에서 p05 폭이 2.5배 확대됐고 공식 threshold가 아니다. | threshold를 정책으로 쓰지 말고 별도 실험 |
| 왜 RGB를 사용하지 않았나? | IR이 주 라벨 대상이고 RGB는 일부 pair만 있다. | DEC-005, FLIR report | 전체 IR의 2.4% 수준인 IR1 편향과 camera domain 차이가 있다. | RGB 사용 목적과 평가 subset 명시 |
| IR2/IR3 온도 데이터는 어떻게 하나? | 표본상 IR1만 radiometric APP1이 있고 IR2/IR3는 없다. | flir_compat.md/csv | 전수 radiometric 검사는 아니다. | 입력 정책을 모델 단계 전에 확정 |
| VCB 접촉부는 그리는가? | 현재 코드상 CONTACT_POINT/deployable이지만 생성 evidence/seed에는 UNKNOWN/비배포로 남아 있다. | `classes_v2.py` vs `class_evidence.csv`/`seed_policy.json` | 버전 불일치 자체가 blocker다. | artifacts 재생성·lock |
| C-1 0.50%는 무엇의 오류율인가? | 확정 오류 19 + 시험 지적 2 / 4,177로 계산된 단일 시점 수치다. | certification evidence | annotation error, duplicate error, audit-detected error가 혼합돼 있다. | 명칭·분모·오류 taxonomy 수정 |
| C-2 기준 0.8은 왜인가? | pipeline 문서의 자체 목표치로 보인다. | certification README | threshold rationale NOT EVIDENCED. | 외부 근거 또는 내부 operating criterion 문서화 |
| 5명의 독립 adjudication은 했나? | A/B/C 3인 독립 시험은 했지만 5인 adjudication은 NOT EVIDENCED. | trial files, review_log.csv | C-4 서명 5/5가 5인 라벨러 agreement를 뜻하지 않는다. | reviewer role 분리 |

## 16. Required Actions Before 400-image Seed Labeling

1. `classes_v2.py`를 단일 source로 하여 guide, CVAT names, `class_evidence.csv`, `seed_policy.json`, `seed_allocation.csv`, panel table를 모두 재생성한다.
2. 6개 UNKNOWN unit의 처리 방침을 결정한다. 결정하지 못하면 400장 목표·C-3 분모·배포 class에서 명시적으로 제외한다.
3. `annotator_guide_v2.md`를 최종판으로 승인하고 파일명·버전·checksum·CVAT project 설정을 하나의 배포 manifest로 고정한다.
4. v2 조건(반 정보 공개, `scope=object`, Skip taxonomy)으로 D/E를 포함한 5인 시험을 수행한다.
5. pooled Kappa만으로 PASS하지 말고 Skip 포함 metrics와 class별 matched coverage, count agreement, omission/commission을 산출한다.
6. P3/P9 잠정 panel, MOF ambiguity, SA, cablehead elbow/base의 escalation owner와 response rule을 확정한다.
7. 400장 seed의 실제 class coverage를 라벨 후 측정할 뿐 아니라, 배포 전에 반별 5~10장 존재성 probe로 목표 달성 가능성을 확인한다.
8. `status_check.py`가 stale artifact를 FAIL로 막도록 현재 schema와 모든 generated output의 consistency check를 수행한다.

**조건부로 허용 가능한 활동:** 위 조치 전에는 외부 본작업이 아니라 내부 calibration/labeler training용 소규모 시험만 허용한다.

## 17. Required Actions Before Full Dataset Labeling

1. 정본·reference·quarantine를 source/quality grade별로 분리한 뒤 독립 blind audit sample을 운영한다.
2. duplicate, missing object, wrong class, wrong boundary, invalid attribute를 서로 다른 오류 taxonomy로 집계한다.
3. panel/session/camera holdout 평가셋을 별도로 구성해 near-duplicate residual risk가 있는 일반 split과 비교한다.
4. radiometric input, OSD 처리, RGB 사용 여부를 모델 학습 전에 결정하고 IR1-only evidence의 한계를 명시한다.
5. vendor handoff pack에 task assignment, guide version, class list, example IDs, escalation SLA, reviewer ID, rework policy, acceptance criteria를 포함한다.
6. package install을 Python 3.11/3.12 및 torch/torchvision/ultralytics 조합으로 재현하고, 데이터 외부 전달 방식과 checksum manifest를 함께 제공한다.
7. 최종 교수님 보고서의 PASS/완료/정본/누수 없음 표현을 scope와 분모가 있는 표현으로 바꾼다.

## 18. Final Verdict

```text
READY: NO
READY_WITH_CONDITIONS: NO (현재는 조건이 충족되지 않음)
NOT_READY: YES
```

**400장 seed labeling:** NO.  
**외부 5인 이상 라벨러 위탁:** NO.  
**내부 규칙 검증·calibration 시험:** YES, 단 production dataset으로 승격하지 않는다.

이 판정은 코드가 존재한다는 이유로 낮추거나 높인 것이 아니다. 현재 실제 산출물과 규칙이 서로 다른 상태를 보이고, 5인 운영 조건과 누락·경계 품질이 아직 측정되지 않았기 때문에 내린 보수적 판정이다.
