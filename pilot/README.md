# IR1 100쌍 파일럿

2,606쌍 전체 라벨링에 들어가기 전에, 100쌍으로 다음 전 과정이 실제로 도는지 확인하는
소규모 실험이다.

```
실화상 라벨 1회 작성 → 열화상 좌표 자동 전이 → YOLO 학습 → 방사 온도 추출 → 이상 발열 판정
```

## 원본 데이터 취급

`1-수집`, `3-가공` 은 **읽기 전용**으로만 접근한다. 이동·삭제·수정하지 않는다.
필요한 100쌍은 `pilot/data` 로 복사해서 쓴다.

## 현재 상태

| 단계 | 상태 | 산출물 |
|---|---|---|
| 정합 상수 보정 | 완료 | `calibration.json` |
| 100쌍 추출 | 완료 | `data/` (rgb·ir·temp 각 100) |
| 방사 온도 추출 | 완료 | `data/temp/*.npy`, `out/temp_index.csv` |
| 라벨 없는 이상 발열 기준선 | 완료 | `out/hotspots.csv`, `out/qa_hotspot.png` |
| 배관 연기 테스트 | 완료 | `out/smoke_*` (합성 박스, 성능 의미 없음) |
| **실화상 라벨링** | **대기 — 사람 작업** | `data/labels_rgb/*.txt` |
| 라벨 전이 → 학습 → 판정 | 라벨 대기 | — |

## 남은 작업: 실화상 100장 라벨링

### 대상
`data/rgb/*.jpg` — 실화상 99장. **열화상이 아니라 실화상에 그린다.**
부품 각인·케이블 색상이 보여 클래스 판단이 빠르고 라벨러 간 불일치가 줄어든다.
열화상 라벨은 `transfer.py` 가 만들어 준다.

기본값은 `3-가공` 의 `<stem>_rgb_image.jpg` (320×240) 이다. 이 파일은 **이미 열화상
FOV 로 정합되어 저장**된 것이라 좌표 변환이 필요 없다 (12개 반 전수 확인, 열화상과
에지 NCC 중앙값 0.667). `transfer.py` 는 이 경우 좌표를 그대로 복사한다.

더 높은 해상도로 작업하려면 `python select_pairs.py --rgb-source embedded` 로 다시
추출한다. 열화상 JPEG 내부의 640×480 실화상을 쓰며, 화각이 1.53배 넓으므로
`transfer.py` 가 보정 변환(scale 1.5325, shift −5/+9)을 적용한다. 작은 부품 경계를
조금 더 정밀하게 잡을 수 있지만 변환 단계가 하나 늘어난다.

### 도구
YOLO txt 포맷으로 저장되면 무엇을 쓰든 상관없다. 100장 규모면 `labelImg` 가 가장 간단하다.

```bash
pip install labelImg
python fix_labelimg.py        # 필수 — 패치 없이는 그리기·스크롤·줌에서 죽는다
python verify_labelimg.py     # 터졌던 경로 7개를 offscreen 으로 실제 실행해 확인
python -m labelImg.labelImg data/rgb data/classes_labelimg.txt data/labels_rgb
```

labelImg 1.8.6 은 2021년 이후 유지되지 않아 현재 PyQt5(5.15.11)와 맞지 않는다. 당시에는
float 인자가 int 로 암묵 변환됐지만 지금은 `TypeError` 가 난다. 좌표 계산이 나눗셈을 쓰므로
십자선 커서·미리보기 사각형·라벨 텍스트·휠 스크롤·줌 5개 경로에서 전부 터진다.
`fix_labelimg.py` 가 7곳을 고치며, `.bak` 을 남기므로 `--restore` 로 되돌릴 수 있다.
수정 대상은 설치된 labelImg 패키지 파일뿐이고 열화상 데이터는 건드리지 않는다.

`labelImg.exe` 는 PATH에 없으므로 위 모듈 형태로 실행한다.
좌측 하단 저장 포맷을 **YOLO** 로 바꾼 뒤 작업한다. 단축키는 `W` 박스 그리기,
`D` 다음 이미지, `A` 이전 이미지, `Ctrl+S` 저장이다.

> labelImg 는 저장 폴더에 `classes.txt` 를 함께 만든다. 라벨 파일이 아니므로
> `transfer.py` · `train.py` · `qa_sheet.py` 가 모두 이름으로 걸러낸다. 지우지 않아도 된다. 결과가 `data/labels_rgb/<파일명>.txt` 로
`<class_id> <cx> <cy> <w> <h>` (0~1 정규화) 형식으로 쌓이면 된다.

### 클래스 16개

`classes.py` 에 정의되어 있다. 라벨링 PDF의 26개 체크포인트 중 `가공 여부 = O` 인
16개만 채택했다.

| id | 키 | 한글 | id | 키 | 한글 |
|---|---|---|---|---|---|
| 0 | epoxy_surface | 에폭시 표면 | 8 | mof_fuse | MOF 1차측 전력퓨즈 |
| 1 | mold_tr_contact | 몰드변압기 접촉부 | 9 | power_fuse | 전력퓨즈 |
| 2 | lbs | LBS | 10 | pt | PT |
| 3 | lbs_primary | LBS 1차측 접촉부 | 11 | branch_contact | 분기 접촉부 |
| 4 | cl_power_fuse | 한류형 전력퓨즈 | 12 | vcb_contact | VCB 접촉부 |
| 5 | la | LA | 13 | ct | CT |
| 6 | transformer | 변압기 | 14 | capacitor | 콘덴서 |
| 7 | ct_transformer | 변류기 | 15 | mccb | MCCB |

보류·제외 항목(철심부, 부스바, 케이블, 각종 접촉부)은 **별도 클래스로 만들지 않는다.**
PDF에 "다른 접촉부와 구분이 안 됨"으로 적힌 것을 클래스로 두면 라벨러 불일치가 그대로
모델 혼동으로 넘어간다. 상위 부품에 포함시킨다.

### 작업 규칙

1. **반별로 후보 클래스를 좁혀서 작업한다.** `classes.PANEL_CLASSES` 에 반별 후보가
   정의되어 있다. `data/index.csv` 의 `panel` 열로 어느 반인지 알 수 있다.
   P9-MCCB반 이미지에서는 MCCB 계열만 후보로 두면 실수가 줄어든다.
2. **박스는 부품 외곽에 맞춘다.** 온도를 박스 내부에서 집계하므로, 배경을 많이 물면
   기준온도가 희석되어 판정이 둔해진다.
3. **확실하지 않으면 그리지 않는다.** 100장 규모에서는 틀린 라벨 1개가 크게 작용한다.
4. **실화상 화각이 열화상보다 넓다.** 가장자리 부품은 전이 과정에서 자동으로 탈락하므로
   신경쓰지 않고 그려도 된다.

## 라벨 도착 후 실행 순서

```bash
python transfer.py                      # 실화상 라벨 → 열화상 라벨
python qa_sheet.py labels               # 전이 결과 눈으로 확인 (필수)
python train.py --modality ir           # 열화상 모델 학습 (CPU 기준 수십 분)
python analyze.py                       # 탐지 + 온도 → 부품별 판정
```

라벨만으로 판정 상한을 먼저 보고 싶으면:

```bash
python analyze.py --from-labels data/labels_ir --tag gt_
```

완벽한 탐지기를 가정한 결과다. 학습된 모델 결과와 비교하면 모델의 손실분이 나온다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `flir.py` | FLIR APP1 파서. raw 열화상, Planck 상수, 내장 실화상 추출 및 섭씨 변환 |
| `calibrate.py` | 실화상↔열화상 정합 상수 보정 (MSX 에지 FFT 상관) |
| `transfer.py` | 좌표 전이. 실화상 YOLO 라벨 → 열화상 YOLO 라벨 |
| `select_pairs.py` | 반별 층화 100쌍 추출 및 내보내기 |
| `scan_temps.py` | 2,606쌍 전체 온도 통계 인덱스 |
| `hotspot.py` | 라벨 없는 이상 발열 탐지 (기준선) |
| `classes.py` | 클래스 16개 정의, 반별 후보, 제외 항목 근거 |
| `train.py` | 데이터셋 구성 + YOLO 학습 (세션 단위 train/val 분할) |
| `analyze.py` | 탐지 + 온도 → 상간/주변 비교 판정 |
| `qa_sheet.py` | 정합·발열·라벨 검증 시각화 |
| `smoke_test.py` | 합성 박스로 전 단계 배관 점검 |
| `fix_labelimg.py` | labelImg 1.8.6 ↔ PyQt5 5.15 호환 패치 (`--restore` 로 복구) |
| `verify_labelimg.py` | 패치된 labelImg 을 offscreen Qt 로 실제 실행해 검증 |
| `predict.py` | 학습된 모델로 사전 라벨링 (검수용 박스 자동 생성) |
| `sweep.py` | 모델·입력해상도 조합 비교 |
| `cvat_prep.py` | CVAT 협업 패키지 생성 (클래스 정의·담당자별 작업·지침) |
| `cvat_import.py` | CVAT YOLO 1.1 내보내기를 파이프라인으로 들여오기 |
| `agreement.py` | 라벨러 간 일치도 측정 (판정 일치율 주 기준) |

## CVAT 5인 협업

```bash
python predict.py --all              # 사전 라벨 생성
python cvat_prep.py                  # out/cvat/ 에 협업 패키지 생성
```

`out/cvat/` 산출물

| 파일 | 용도 |
|---|---|
| `labels.json` | CVAT 프로젝트 생성 시 클래스 정의(Raw)에 붙여넣기 |
| `GUIDE.md` | 라벨러에게 그대로 배포하는 작업 지침 |
| `calibration_images.zip` | 1단계 기준 합의용 20장 (5명 전원이 같은 것을 작업) |
| `task_<A~E>_images.zip` | 담당자별 이미지 |
| `task_<A~E>_preannot.zip` | 담당자별 사전 라벨 (CVAT YOLO 1.1 import) |
| `assignment.csv` | 사진별 담당자·교차검증 배정 |

작업이 끝나면 담당자별로 따로 내보내 일치도를 재고, 조정 후 병합본을 학습에 넣는다.

```bash
python cvat_import.py exports/A.zip --into annot/A     # 담당자별
python agreement.py annot/A annot/B annot/C annot/D annot/E
python cvat_import.py exports/final.zip --into data/labels_rgb --clear
python transfer.py && python train.py --modality ir && python analyze.py
```

### 합격 기준

이 프로젝트는 박스 안 화소에서 온도를 집계하므로, IoU 가 아니라 **판정 일치율**이 주
기준이다. 동일 라벨의 박스 경계만 흔들어 측정한 민감도는 다음과 같다.

| 경계 오차 | 판정 일치율 |
|---|---|
| ±1.6 px | 99.1% |
| ±3.2 px | 94.5% |
| ±6.4 px | 91.9% |
| ±9.6 px | 90.2% |
| ±16 px | 87.7% |

즉 **박스 경계만으로도 ±10px 에서 90% 로 떨어진다.** 클래스·개수 불일치까지 감안하면
경계 오차는 **±5px 이내**로 관리해야 전체 90% 를 넘길 수 있다.

- 판정 일치율 ≥ 90% (주 기준)
- matched IoU 중앙값 ≥ 0.70
- 라벨러 간 박스 개수 차이 ≤ 10%

## 알아둘 것

- **측정 상한.** FLIR E8 의 측정 범위는 −20 ~ +250 °C 다. 이를 넘는 값은 외삽이므로
  측정값으로 쓰면 안 된다. `over_range` 플래그로 표시된다.
- **설비 아닌 발열체.** 100쌍 중 최고온 상위는 대부분 조명기구·히터다. 온도만으로는
  걸러지지 않는다. 부품 탐지가 필요한 이유가 이것이다.
- **P1-TR반 주의.** 몰드변압기는 정상 운전에서도 뜨겁고, 프레임을 가득 채워서 배경
  기준온도가 설비 자신의 온도로 오염된다. 주변 대비 판정이 여기서 대량 오탐을 낸다.
  동종 부품 간 상간 비교(`dT_phase`)를 우선 근거로 삼아야 한다.
- **`._` 파일.** `3-가공` 에 macOS AppleDouble 잔재 8개가 있다. 데이터 로더에서
  걸러야 한다 (`select_pairs.py` 는 걸러낸다).
- **시계열은 없다.** 이 파일럿은 단일 프레임 이상 발열 탐지까지다. 추세 기반 예지보전은
  데이터 구조상 불가능하다.
