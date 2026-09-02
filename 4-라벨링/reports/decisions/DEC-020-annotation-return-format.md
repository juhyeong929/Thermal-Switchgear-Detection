# DEC-020 — 시험 라벨링 회수 포맷: YOLO 1.1 + CVAT XML 이중 회수

## 날짜
2026-08-31

## 결정 내용

1. **주 포맷은 YOLO 1.1 을 유지한다.** 프로젝트 표준을 바꾸지 않는다.
   일치도(개수 일치 · mIoU · Kappa)의 primary input 은 계속 YOLO 다.
2. **CVAT for images 1.1 XML 을 함께 회수해 보존한다.** bbox 속성이 YOLO 에
   저장되지 않기 때문이다.
3. **라벨러의 작업 방식은 바꾸지 않는다.** export 를 한 번 더 할 뿐이다.
4. `agreement.py` 는 **수정하지 않는다.** 속성은 별도 분석 경로로 뺀다.

## 무엇이 문제였나

YOLO 1.1 의 한 줄은 다섯 칸이 전부다.

```
<class_id> <cx> <cy> <w> <h>
```

**속성을 담을 자리가 없다.** 그런데 지침서 7항은 박스마다
`truncated` / `occluded` / `ignore` 를, 이미지마다 촬영유형(클로즈업·중거리·전체)을
기록하라고 한다. YOLO 로만 회수하면 **그 정보는 회수 시점에 소멸한다.**
정본 4,177박스에 속성이 하나도 없는 것도 같은 이유다.

없어진 정보는 나중에 복원할 수 없다. 30장을 받기 전에 정해야 하는 문제였다.

## 검토한 선택지

| | 방법 | 판단 |
|---|---|---|
| **A** | CVAT 에서 두 번 export — YOLO 1.1 + CVAT XML | **채택.** 라벨러 부담 0, 정보 손실 0 |
| B | YOLO txt + `attributes.csv` 를 라벨러가 손으로 작성 | 기각. 라벨러 부담과 누락 위험이 크다 |
| C | 속성을 포기하고 YOLO 만 회수 | 기각. 지침서가 요구하는 것을 스스로 버리는 셈 |

## 함께 발견한 것 — 속성은 지금 구조로는 저장되지 않는다

`pilot/cvat_prep.py` 는 라벨을 `"attributes": []` 로 만든다. **그 정의로 프로젝트를
만들면 라벨러 화면에 `truncated` 입력 칸 자체가 없고, XML 로 뽑아도 나오지 않는다.**
A안을 결정하는 것만으로는 부족하고 프로젝트 라벨 정의를 고쳐야 한다.

`occluded` 는 다르다. CVAT **내장 필드**라 정의하지 않아도 항상 저장된다
(단축키 `Q`, XML 에서는 `<box occluded="1">`). 그래서 커스텀으로 다시 정의하지 않는다.

→ `scripts/cvat_labels_json.py` 를 추가했다. `schemas/classes_v2.py` ·
`schemas/labeling_rules.py` 에서 직접 뽑으므로 `classes.txt` 와 어긋날 수 없다
(생성 시 18종 일치를 그 자리에서 확인한다).

| 속성 | 저장되는 경로 | 라벨러 조작 |
|---|---|---|
| `occluded` | CVAT 내장 필드 | 단축키 `Q` |
| `truncated` · `ignore` | 라벨 정의의 커스텀 체크박스 | 우측 속성 패널 |
| 촬영유형 | `촬영유형` tag + `shot_type` select | 이미지당 태그 1개 |

## 회수 구조

```
data/labeling/draft/trial/annotator_A/
├── yolo/                  YOLO 1.1 (압축 해제)   — 일치도의 primary input
├── cvat/annotations.xml   CVAT for images 1.1    — 속성 보존
├── attributes.csv         검수자가 스크립트로 생성
├── attributes_unmatched.csv
├── skip_log.csv
└── time_log.csv
```

기존 폴더 구조를 그대로 두고 하위 폴더만 갈랐다. `agreement.py` 는 작업 폴더를
`rglob` 하므로 `yolo/` 안에 있어도 **수정 없이** 읽는다. 실측으로 확인했다
(평탄 구조와 중첩 구조의 출력이 문자 단위로 동일).

## 추가 확정 (2026-08-31 실측) — CVAT export 는 class_id 를 다시 매긴다

실제 제출본으로 확인한 사실이다. **CVAT 의 YOLO 1.1 export 는 그 프로젝트의 라벨 목록
순서로 0부터 번호를 다시 매긴다.** 우리 `classes.txt` 는 v2 class_id(= 가이드번호 − 1)를
지키려고 쓰지 않는 자리에 `__사용안함_N` 을 넣은 성긴 번호 체계인데, CVAT 은 그
자리표시자를 모른다.

```
classes.txt   ... 케이블헤드=13 ... 콘덴서=17 MCCB=18 ... MCCB 접촉부=27
obj.names     ... 케이블헤드=11 ... 콘덴서=14 MCCB=15 ... MCCB 접촉부=17
```

즉 **CVAT 을 쓰는 한 id 는 반드시 어긋난다.** 프로젝트를 다시 만들어도 마찬가지다
(1차 제출본 73/126 불일치 → 라벨 정의를 `cvat_labels.json` 으로 고쳐 재제출한 2차도
103/122 불일치). 라벨 정의의 문제가 아니라 **export 형식의 성질**이다.

좌표와 개수는 온전하고 이름은 그대로 나오므로 **손실은 없다.** `obj.names` 로
이름 → `classes.txt` 줄 번호를 되돌리면 정확히 복원된다.

→ `scripts/trial_ingest.py` 를 회수 절차의 **첫 단계**로 추가했다.
원본 export 는 `_raw_export/<라벨러>/` 로 옮겨 보존하고, 정규화본을 `yolo/*.txt` 로 쓴다.

**원본을 라벨러 폴더 안에 두면 안 된다.** 처음에 `annotator_A/yolo_raw/` 로 두었다가
사고를 확인했다 — `agreement.py` 는 작업 폴더를 `rglob("*.txt")` 하므로 `yolo/A01.txt` 와
`yolo_raw/.../A01.txt` 를 **둘 다 읽고** 뒤에 온 원본이 정규화본을 덮어썼다. 지표는
100% 로 멀쩡해 보이는데 클래스 이름만 조용히 틀린다. 폴더 밖으로 빼면 구조적으로
불가능해지고, `agreement.py` 는 여전히 손대지 않아도 된다. `trial_ingest.py` 는 끝에
`yolo/` 밖에 txt 가 남았는지 다시 확인하고 남아 있으면 실패로 끝낸다.
이름이 하나라도 `classes.txt` 에 없으면 **아무것도 쓰지 않고 멈춘다** — 모르는 클래스를
임의의 번호에 넣지 않는다. `agreement.py` 는 여전히 수정하지 않는다.

배포 지침에 있던 "`class_id` = `classes.txt` 줄 번호로 제출" 은 **라벨러가 지킬 수 있는
조건이 아니었다.** 라벨러에게 요구하지 않고 회수 측에서 복원한다.

## bbox 연결 규칙 — 번호를 가정하지 않는다

**YOLO 1.1 에는 shape id 가 없다.** 따라서 XML shape 순서와 YOLO 줄 번호가 같다고
가정할 수 없다. 대응은 (이미지 → 클래스 → 좌표) 로 복원하고, 무엇으로 붙었는지를
행마다 `match_method` 로 남긴다.

```
1 exact_same_class    같은 클래스 · IoU >= 0.999   같은 export 이므로 정상 경로
2 iou_same_class      같은 클래스 · IoU >= 0.5
3 iou_class_mismatch  자리는 같은데 클래스가 다름 -> 붙이되 표시한다
```

**실패를 버리지 않는다.** 양방향 4종을 `attributes_unmatched.csv` 에 전부 적는다 —
`xml_box_no_yolo_file` · `xml_box_no_match` · `yolo_box_no_xml_match` ·
`yolo_file_no_xml_image`. 매칭 수 + 실패 수 = 전체 박스 수가 양쪽 모두 성립하는지를
테스트로 강제한다.

## 만들어내지 않는 것

**XML 에 없는 속성을 채우지 않는다.** `truncated` 가 정의되지 않은 프로젝트에서 받은
XML 이면 그 열은 **빈 칸**으로 두고 경고한다. `false` 로 채우면 "잘리지 않았다" 라는
없는 사실을 만들어 내는 것이다. **비어 있는 것과 "아니다" 는 다르다.**

라벨 정의에 **선언만 되고 한 번도 쓰이지 않은** 속성도 열로 만들지 않는다.

## Skip 과 빈 파일

DEC-019 이전과 같다. **빈 txt = 대상 없음**, **Skip = `skip_log.csv` 에만**.
Skip 을 빈 txt 로 대신하지 않는다. `agreement.py` 의 `NOT_SCORED`(단위 미확정 7종)와
`FORBIDDEN`(제외 클래스 = 규칙 위반) 정책은 그대로이며, 이번 변경과 충돌하지 않는다.
테스트 8번이 이것을 검사한다.

## 검증

`scripts/test_cvat_attributes.py` — **37건 전부 통과**. fixture 는 임시 폴더에서만
만들고 끝나면 지운다. 실제 30장·라벨러 폴더는 읽지도 쓰지도 않으며,
`agreement.py` 가 쓰는 보고서 파일은 실행 전 백업해 원상 복구한다.

## 영향

- 라벨러: export 한 번 추가. 그 외 변화 없음
- 검수자: `cvat_labels_json.py` 로 프로젝트 라벨 정의 생성 (배포 전 1회),
  회수 후 `cvat_xml_to_attributes.py` 실행
- `agreement.py` · 정본 라벨 · 분할 파일 · 30장 구성: **무수정**
