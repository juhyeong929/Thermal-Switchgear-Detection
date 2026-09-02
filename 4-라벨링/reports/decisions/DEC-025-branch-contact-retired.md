# DEC-025 — 분기 접촉부(#13) 폐지, 케이블헤드로 명칭 통일

```
상태        승인 대기 — 아래 승인란이 비어 있으면 이 문서는 아직 결정이 아니다
승인란      결정자: __________   날짜: __________
근거 자료    수배전반 라벨링 가이드.pdf (2026-09-02 배포판) p14
```

## 날짜
2026-09-02

## 결정 내용

```
branch_contact (#13 / class_id 12)
    label_status   가공 -> 폐지(RETIRED)
    신규 라벨링     금지
    기존 실적       0건 (정본·참고 통틀어)
    라벨 승계       하지 않는다 — cable_head 의 동의어로 두지 않는다
    class_id 12    비우지 않고 그대로 둔다 (재번호화 금지)

cable_head (#14 / class_id 13)
    공식 명칭으로 통일. class_id 는 **바꾸지 않는다**
    P5-PF&PT반 후보에 추가
```

## 왜 바뀌었는가

새 배포 가이드 PDF p14 (PF&PT 반) 에 명시돼 있다.

> **분기 접촉부 -> 케이블헤드 명칭 변경**

이전 판은 같은 물체를 반에 따라 다르게 불렀다.

```
이전 판   #13 분기 접촉부   "PF PT 반 전용 명칭"
          #14 케이블헤드    "VCB·CNCV 반"
          VCB 반 슬라이드에만 "분기 접촉부는 케이블헤드로 명칭을 통일한다"
새 판     PF&PT 반 가공대상 = 소음기부착형 전력퓨즈 · PT · 인입선로 접촉부 · 케이블헤드
```

`분기 접촉부` 라는 이름을 쓰는 반이 **하나도 남지 않았다.** 그래서 폐지한다.

## 왜 class_id 를 옮기지 않는가

`cable_head` 를 비는 `class_id 12` 자리로 내리는 방식은 **채택하지 않았다.**

```
이미 존재하는 라벨   P2-LBS&LA반 · P6-VCB반 의 케이블헤드
                    정본 4,177박스 체계 안에서 class_id 13 으로 기록돼 있다
id 를 옮기면        같은 숫자가 다른 물체를 가리키게 된다.
                    기존 YOLO txt · 분할 · 감사 결과의 의미가 전부 흔들린다
```

**이름 통일과 class_id 이동은 분리한다.** 이름은 하나로 합치되 번호는 움직이지 않는다.
`class_id 12` 는 빈 슬롯으로 남고, 배포본 `classes.txt` 에서는 자리표시자
`__사용안함_12` 로 유지된다.

## 왜 안전한가

```
branch_contact 라벨 실적   정본 0박스 · 참고 0박스
```

폐지해도 학습 데이터 손실이 없다. 승계할 라벨이 애초에 없으므로 자동 변환도 필요 없다.

**`cable_head` 의 `alias` 에 '분기 접촉부' 가 남아 있는 것은 가이드 개정 이력이지
변환 규칙이 아니다.** 실적 0건이므로 변환 대상도 없다. 승계 규칙으로 오해되지 않도록
`branch_contact` 쪽에 "라벨 승계 없음" 을 명시했다.

## RETIRED 를 EXCLUDE 와 합치지 않은 이유

```
EXCLUDE  물체는 있지만 그리지 않기로 했다        부스바 · 케이블 · ACB 접촉부
         가이드가 근거를 적어 두었다 ("일정한 패턴이 없어…")
RETIRED  그 이름의 클래스가 더 이상 존재하지 않는다   분기 접촉부
```

둘을 한 집합에 넣으면 제외 3종의 근거를 설명할 수 없게 된다. 코드에서도
`EXCLUDED` 와 `RETIRED_CLASSES` 를 나누고, 라벨 대상 판정에는 합집합
`NOT_LABELED` 를 쓴다.

## 반영 결과

| 무엇 | 어디 |
|---|---|
| 상태 상수 `RETIRED` 신설 · 집합 분리 | `schemas/classes_v2.py` |
| 라벨 대상 판정 헬퍼 `is_labelable()` | `schemas/classes_v2.py` |
| P5 후보 `branch_contact` -> `cable_head` | `schemas/classes_v2.py` `PANEL_CLASSES` |
| 단위표에서 제거 (폐지 클래스는 단위를 정하지 않는다) | `ANNOTATION_UNIT` · `ANNOTATION_UNIT_BASIS` |
| v1 26종 승계 매핑 `P5 -> cable_head` | `schemas/classes_v1_26.py` `SPLIT_BY_PANEL` |
| 폐지 클래스도 규칙 위반으로 채점 | `scripts/agreement.py` `FORBIDDEN` |
| 시드 정책 지문에 `retired` 추가 | `scripts/seed_select.py` |
| 지침서 변경이력 10 | `annotator_guide_v2.md` |

```
라벨 대상        25종 -> 24종
단위 미확정      6종 -> 5종     (branch_contact 가 빠짐. 나머지 5종은 그대로 열림)
P5 배포 클래스   2종 -> 3종     (소음기부착형 전력퓨즈 · 몰드타입 PT · 케이블헤드)
케이블헤드 출현 반  P2 P6 -> P2 P5 P6
```

`status_check.py` 확인이 필요한 항목 0건.
`seed_regen_diff.csv` `change_kind = NO_CHANGE` — **400장 이미지 목록은 바뀌지 않았다.**
(중간 단계에서 `METADATA_ONLY` 로 `target_classes` 열 61행이 갱신됐고, 재실행 후 안정됐다.)

## 이 결정이 바꾸지 않는 것

```
· 인입선로 접촉부   별도 결정으로 분리 — DEC-027 (아래 참조)
· 기존 케이블헤드 라벨의 class_id 13
· 정본 4,177박스 · 1차 시험 회수분
· 나머지 5종의 단위 UNKNOWN (NQ-13 본체)
```

### 함께 검토한 것 — 인입선로 접촉부

같은 개정 PDF 를 근거로 인입선로 접촉부의 등급도 함께 검토했고, **주의 -> 가공**
으로 상향했다. 별도 결정으로 분리해 기록한다 -> **DEC-027**.

이 문서의 결정(분기 접촉부 폐지)과는 독립이다. 하나가 뒤집혀도 다른 하나는 남는다.

## 되돌리는 법

```
1. classes_v2.CLASSES 의 branch_contact 를 LABEL 로 되돌리고
   ANNOTATION_UNIT / ANNOTATION_UNIT_BASIS 에 UNIT_UNKNOWN 항목을 복원한다
2. PANEL_CLASSES["P5-PF&PT반"] 의 cable_head 를 branch_contact 로 되돌린다
3. classes_v1_26.SPLIT_BY_PANEL["P5"] 를 branch_contact 로 되돌린다
4. python scripts/run_all.py
```

## 관련
DEC-002 (반 구조) · DEC-003 (26->28 승계) · DEC-004 (제외 정책) · DEC-024 · DEC-026 · NQ-13
