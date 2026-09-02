# 1차 시험 라벨링 30장 — 라벨러 전달문

> 2026-09-01 · 근거 `DEC-019` · `DEC-020` · 지침서 `annotator_guide_v1.html`
> 이 문서는 **그대로 복사해 라벨러에게 보내는 용도**다.
> **A·B·C 회수 완료 · D·E 대기.** 배포 절차는 `deploy_checklist_D_E.md`.
> **지침서 v1 을 고치지 않는다** — 앞사람과 다른 규칙을 보면 5인 비교가 무의미해진다.

---

## 보내는 것

| | 무엇 | 어디 |
|---|---|---|
| 1 | 지침서 (열어서 읽는 한 페이지) | `annotator_guide_v1.html` |
| 2 | 열화상 30장 | `data/labeling/draft/trial/images/` |
| 3 | 식별용 실화상 22장 | `data/labeling/draft/trial/reference_rgb/` |
| 4 | 라벨링 툴 클래스 목록 | `data/labeling/draft/trial/classes.txt` |
| 5 | 본인 작업 폴더 | `data/labeling/draft/trial/annotator_A` ~ `annotator_E` |

**보내지 않는 것: 기존 라벨.** B군 12장 중 일부는 과거에 그려진 라벨이 있지만
일부러 빼고 보낸다. 그걸 보고 따라 그리면 일치도 측정이 무의미해진다.

---

## 지시문 (이대로 전달)

> **시험셋 30장을 각자 독립적으로 라벨링합니다.**
>
> - 다른 라벨러의 결과를 보지 않습니다.
> - 기존 reference annotation 도 보지 않습니다.
> - 애매한 객체는 **개인적으로 규칙을 만들어 해결하지 말고** Skip 로그에 남깁니다.
> - 걸린 시간을 `time_log.csv` 에 적습니다. **빨리 하실 필요 없습니다.**
> - 작업이 끝나면 **CVAT 에서 두 가지를 export 해서 함께 제출합니다.**
>   `YOLO 1.1` 과 `CVAT for images 1.1`. 둘 다 필요합니다.
>
> 목적은 여러분을 평가하는 것이 아니라 **규칙이 실제로 통하는지 보는 것**입니다.
> Skip 이 많은 항목, 오래 걸린 항목이 곧 저희가 고쳐야 할 규칙입니다.

---

## 회수 포맷 — YOLO 1.1 + CVAT XML 두 개 (DEC-020)

**왜 두 개인가.** YOLO txt 한 줄은 `<class_id> <cx> <cy> <w> <h>` 다섯 칸이 전부라
**속성 필드가 없다.** 지침서 7항의 `truncated` / `occluded` / `ignore` 와 촬영유형은
YOLO 로만 받으면 그 자리에서 사라진다. 그래서 XML 을 함께 보존한다.
**라벨러의 작업 방식은 달라지지 않는다.** export 를 한 번 더 할 뿐이다.

```
data/labeling/draft/trial/annotator_A/
├── yolo/                  ← Export annotations → YOLO 1.1  (압축 풀어서)
│   ├── A01.txt
│   └── ...
├── cvat/
│   └── annotations.xml    ← Export annotations → CVAT for images 1.1
├── attributes.csv         ← 검수자가 스크립트로 생성 (라벨러가 만들지 않음)
├── attributes_unmatched.csv
├── skip_log.csv
└── time_log.csv
```

### YOLO 규격

```
<class_id> <cx> <cy> <w> <h>      예: 2 0.677422 0.773625 0.049531 0.164667
```

- 파일명 = 이미지 stem (`A01.jpg` → `A01.txt`)
- **빈 txt = 대상 없음.** Skip 을 빈 txt 로 처리하지 않는다 — Skip 은 `skip_log.csv` 한 곳에만
- 파일 자체가 없으면 그 장은 일치도 비교에서 빠진다
- `class_id` 는 **라벨러가 맞출 필요 없다.** CVAT export 가 자기 라벨 순서로 0부터 다시
  매기므로 `classes.txt` 와 반드시 어긋난다 — 회수 측에서 `obj.names` 로 복원한다(0단계).
  **대신 export 에 딸려 오는 `obj.names` 를 반드시 함께 제출한다.** 그게 없으면 복원이 불가능하다

### 속성이 저장되게 하려면 — CVAT 프로젝트 설정 (검수자 작업, 배포 전)

`pilot/cvat_prep.py` 는 라벨을 `"attributes": []` 로 만든다. **그 상태로 프로젝트를 만들면
라벨러 화면에 truncated 입력 칸 자체가 없고, XML 로 뽑아도 그 속성은 나오지 않는다.**

```bash
python scripts/cvat_labels_json.py     # -> data/labeling/draft/trial/cvat_labels.json
```

이 파일 내용을 CVAT 프로젝트 생성 화면의 **Raw 탭**에 붙여넣는다.

| 속성 | 어디서 저장되나 | 라벨러 조작 |
|---|---|---|
| `occluded` | **CVAT 내장 필드** — 정의 불필요 | 박스 선택 후 단축키 `Q` (XML: `<box occluded="1">`) |
| `truncated` | 라벨 정의의 **커스텀 체크박스** — 정의해야 저장됨 | 박스 선택 후 우측 속성 패널 체크 |
| `ignore` | 위와 같음 | 위와 같음 |
| 촬영유형 | **tag** 라벨 + `shot_type` select | 이미지마다 태그 1개 (클로즈업/중거리/전체) |

---

## 회수 후 (검수자 작업)

### 0. 정규화 — **가장 먼저**

```bash
python scripts/trial_ingest.py --all        # --dry-run 으로 먼저 봐도 된다
```

CVAT 의 YOLO export 는 **그 프로젝트의 라벨 순서로 class_id 를 0부터 다시 매긴다.**
`classes.txt` 의 `__사용안함_N` 자리표시자를 CVAT 은 모르기 때문에, 프로젝트를 어떻게
만들든 id 는 어긋난다. 이 단계를 건너뛰면 클래스별 지표가 엉뚱한 이름에 붙는다.

- 원본 export → `_raw_export/<라벨러>/` 로 옮겨 **그대로 보존** (라벨러 폴더 **밖**)
- 정규화본 → `yolo/A01.txt` … (평탄하게)
- 이름이 `classes.txt` 에 없으면 **아무것도 쓰지 않고 멈춘다**

> 원본을 라벨러 폴더 **안**에 두면 안 된다. `agreement.py` 는 폴더를 `rglob` 하므로
> `yolo/A01.txt` 와 원본 `A01.txt` 를 둘 다 읽어 정규화본을 덮어쓴다.
> 지표는 멀쩡해 보이는데 클래스 이름만 조용히 틀린다. 이 스크립트가 끝에 확인한다.

### 1. 일치도 — primary input 은 계속 YOLO 다

```bash
cd 4-라벨링
python scripts/agreement.py \
  data/labeling/draft/trial/annotator_A \
  data/labeling/draft/trial/annotator_B \
  data/labeling/draft/trial/annotator_C \
  data/labeling/draft/trial/annotator_D \
  data/labeling/draft/trial/annotator_E
```

`yolo/` 하위에 있어도 그대로 읽는다 (폴더를 rglob 한다). XML·CSV 는 라벨로 오인하지 않는다.

| 지표 | 무엇을 말해 주는가 |
|---|---|
| 개수 일치율 | **annotation unit 이 통했는가.** 세는 단위가 어긋나면 여기서 터진다 |
| mIoU | 경계 규칙이 통했는가 |
| Kappa | 클래스 정의가 통했는가 (목표 0.8 이상) |
| Skip 사유별 집계 | `rule_unclear` 가 몰린 항목 = 고쳐야 할 규칙 |
| 작업시간 · 분/장 | 400장 본 seed 물량 산정 근거 |

출력: `reports/labeling/agreement_<날짜>.csv` · `reports/labeling/trial_time_<날짜>.csv`

### 2. 속성 — 별도 분석용

```bash
python scripts/cvat_xml_to_attributes.py data/labeling/draft/trial/annotator_A
```

출력: `attributes.csv` (image_name · bbox_id · class_id · class_name · truncated ·
occluded + XML 에 실제로 있던 속성) · `attributes_unmatched.csv`

- **XML 에 없는 속성은 빈 칸으로 둔다.** `false` 로 채우지 않는다 — 비어 있는 것과 "아니다" 는 다르다
- YOLO 줄 번호와 XML shape 순서가 같다고 **가정하지 않는다.** (이미지 · 클래스 · 좌표)로 대응을
  복원하고 방법을 행마다 `match_method` 로 남긴다
- 대응 실패는 **버리지 않는다.** 양방향 4종(`xml_box_no_yolo_file` · `xml_box_no_match` ·
  `yolo_box_no_xml_match` · `yolo_file_no_xml_image`)을 전부 `attributes_unmatched.csv` 에 적는다

### 3. 검증

```bash
python scripts/status_check.py             # 회수 위생 — Skip 로그 정합성 포함
python scripts/test_cvat_attributes.py     # 44건 · fixture 로만 돈다
```

**정합성 검사를 통과한 뒤에 일치도를 낸다.** annotator_C 에서 배포본에 없는 `case_id` 3건과
"빈 파일인데 Skip 기록 없음" 3장이 나왔고, 고치기 전에는 그 3장이 "대상 없음" 으로
비교에 들어가 지표가 왜곡됐다.

### 4. 분석 (라벨러 1명분으로도 가능)

```bash
python scripts/trial_vs_existing.py                    # 숨겨 둔 기존 라벨과 대조
python scripts/diff_analysis.py <폴더> --class 전체      # 차이를 원인별로 분해
python scripts/box_size_profile.py                     # 라벨러별 박스 크기 행동 (NQ-12)
```

---

## 이 시험을 막고 있는 것은 없다

열려 있는 OPEN QUESTION 은 여럿이지만 **1차 시험 30장을 막는 항목은 0건**이다.
지침서 v1 이 미확정 항목을 "그리지 않는다 / Skip 한다" 로 처리하도록 쓰였기 때문이다.
근거: `reports/data_audit/open_questions.csv` 의 `blocks_current_labeling` 열 · `DEC-019`
