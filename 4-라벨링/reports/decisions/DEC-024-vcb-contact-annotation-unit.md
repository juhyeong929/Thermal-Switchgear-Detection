# DEC-024 — VCB 접촉부(#14) 의 annotation unit = CONTACT_POINT

```
상태        승인 대기 — 아래 승인란이 비어 있으면 이 문서는 아직 결정이 아니다
승인란      결정자: __________   날짜: __________
초안        reports/decisions/drafts/vcb-contact-annotation-unit.md
대상        NQ-13 의 7종 중 1종. 나머지 6종은 계속 열림
```

> **왜 번호를 먼저 붙였는가** — 지침서 v2 변경 이력과 `ANNOTATION_UNIT_BASIS` 가
> 이 문서를 참조한다. 번호가 없으면 참조가 끊긴다. **승인란은 사람이 채운다.**
> 승인 전에 되돌리려면 아래 "되돌리는 법" 을 그대로 실행한다.

## 날짜
2026-09-02

## 결정 내용

```
class            #14 vcb_contact · VCB 접촉부
annotation_unit  CONTACT_POINT      # 볼트로 조여진 접속 지점 하나하나
배포             P6-VCB반 · P7-VCB&CT반 에 배포한다 (v2 회차부터)
NQ-13 잔여       6종 (LBS 1·2차측 · 변압기 · 분기 · 인입선로 · CT 접촉부) — 계속 UNKNOWN
```

## 왜 이 한 종만 지금 정할 수 있었는가

NQ-13 은 7종을 **"라벨 실적 0건"** 이라는 공통 전제로 묶었다. 그 전제가 이 한 종에
대해서만 틀렸다. `data/backup/P6_6ban` 에 구 class_id 17 의 **159박스 / 111장**이 있다.
참고 등급은 DEC-015 가 `mccb_contact` 단위 판정에 **이미 채택한 증거 등급**이다.

나머지 6종은 정본·참고 어디에도 박스가 없어 이 경로를 쓸 수 없다.

## 근거 — 좌표만으로 정하지 않았다

좌표 근거는 **두 방향으로 갈렸다.** 그래서 사람이 표본을 열었다.

| 근거 | 값 | 가리키는 단위 |
|---|---|---|
| 접촉부/본체 세로비 중앙 | 0.246 (p25~p75 0.18~0.31) | `CONTACT_POINT` — 확정된 두 클래스(0.462 · 0.379)보다도 작다 |
| `TERMINAL_GROUP` 대조군 (MCCB 접촉부) | 0.922 (0.87~0.97) | 정면으로 어긋난다 |
| 장당 접촉부 개수 중앙 | **1** (1개 74장 · 2개 31장) | `TERMINAL_GROUP` 쪽 — 3상 설비면 3개 안팎이 자연스럽다 |

DEC-016 은 "좌표만으로는 하나의 물리적 접속점마다 박스 하나인가를 확정할 수 없다" 를
`NOT_AUDITABLE` 로 기록했다. 그 판단을 자동화하지 않기 위해 **표본 15장을 열었다.**

### 표본 육안 판정 (2026-09-02)

판정표: `reports/labeling/vcb_contact_review.csv`
표본: 접촉부 2개 이상인 장 5 + 1개인 장 10 (`scripts/vcb_contact_review.py` 생성)

```
CONTACT_POINT     10 / 15     박스 1개 = 접속점 1개
PARTIAL_LABELING   5 / 15     보이는 것보다 박스가 적다 (미작업 — 근거로 쓰지 않는다)
TERMINAL_GROUP     0 / 15     묶어 그린 사례가 하나도 없다
판단불가            0 / 15
```

**장당 1개가 지배적이었던 이유는 (b) 묶어 그려서가 아니라 (c) 덜 그려서였다.**
초안이 제시한 세 가설 (a)(b)(c) 중 `TERMINAL_GROUP` 을 지지하는 (b) 는 **0건**이다.
크기 근거와 개수 근거의 충돌이 해소됐고, 두 근거 모두 `CONTACT_POINT` 를 가리킨다.

## 이 결정이 바꾸지 않는 것

```
· 나머지 6종의 annotation unit       계속 UNKNOWN (NQ-13 본체는 열려 있다)
· 시드 400장 이미지 목록             무변경 — seed_regen_diff.csv change_kind = NO_CHANGE
· P6 참고 라벨의 등급                참고 그대로. 정본 승격이 아니다
· v1(1회차) 시험 결과 · 회수 데이터    무관 — v1 배포 라벨 목록에 없었고 id 14 박스 0건
```

**PARTIAL_LABELING 5건은 이 결정의 부산물이 아니라 별개의 사실이다.** P6 참고 라벨이
정본으로 승격될 수 없는 이유를 하나 더 실측으로 확인한 것이다 (DEC-011 · KL-5 보강).

## 반영 결과

| 무엇 | 어디 | 상태 |
|---|---|---|
| 단위 확정 · 근거 문구 | `schemas/classes_v2.py` `ANNOTATION_UNIT` · `ANNOTATION_UNIT_BASIS` | 반영 |
| 배포본 클래스 목록 | `data/labeling/draft/trial/classes.txt` 15번 줄 (자리표시자 → `VCB 접촉부`) | 반영 |
| CVAT 라벨 정의 | `trial/cvat_labels.json` (18종 → 19종) · `generated/cvat_labels/P6·P7` | 반영 |
| 지침서 §2 단위표 · §3 VCB 절 · 부록 A · 변경이력 9 | `annotator_guide_v2.md` (자동 생성) | 반영 |
| 반별 배포 클래스 | P6 3종 → **4종** · P7 1종 → **2종** | 반영 |
| 시드 정책 지문 | `seed_policy.json` `deployable` | 재생성 |
| 존재 근거 집계 | `reports/data_audit/class_evidence.csv` | 재생성 |

`status_check.py` [2] · [5-1] · [5-3] 전부 OK — 확인이 필요한 항목 0건.

### class_id 를 밀지 않았다

`classes.txt` 는 UNKNOWN 클래스 자리에 `__사용안함_N` 자리표시자를 두는 구조다.
14번 자리표시자를 이름으로 **바꿔 끼운 것**이므로 다른 클래스의 id 는 하나도 움직이지 않는다.
1회차 회수 YOLO 에 id 14 박스가 **0건**임을 확인한 뒤 바꿨다.

## 남은 일 — 이 결정이 열어 놓는 것

```
· P7-VCB&CT반의 배포 클래스가 1종 → 2종이 됐다. 1종일 때는 일치도 측정이
  사실상 무의미했다. 2회차에서 이 반의 지표를 처음으로 읽을 수 있다
· 지침서 §3 VCB 절의 "케이블헤드 밖 91%" 문구는 참고 라벨 실측이다.
  2회차 회수 후 새 라벨로 다시 확인한다
```

## 되돌리는 법

```
1. classes_v2.ANNOTATION_UNIT["vcb_contact"] 를 UNIT_UNKNOWN 으로 되돌린다
2. classes.txt 15번 줄을 __사용안함_14 로 되돌린다
3. python scripts/cvat_labels_json.py && python scripts/run_all.py
4. build_guide_tables.CHANGELOG 의 9행과 템플릿 §3 VCB 절을 지운다
```

## 관련
DEC-011 (참고 등급) · DEC-014 · DEC-015 (단위 판정 전례) · DEC-016 (NOT_AUDITABLE) · NQ-13
