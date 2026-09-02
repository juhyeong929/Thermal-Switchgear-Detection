# 열화상 수배전반 라벨링 프로젝트

수배전반 열화상 이미지의 수집·가공·라벨링·검수·분석을 위한 Python 스크립트와 라벨 데이터를 관리하는 저장소입니다.

## 저장소 구성

```text
열화상/
├─ pilot/                 # 초기 실험 및 열화상 분석 스크립트
├─ 4-라벨링/              # 현재 라벨링 파이프라인
│  ├─ schemas/            # 클래스, 경로, 라벨링 규칙
│  ├─ scripts/            # 인벤토리·검수·CVAT·보고서 스크립트
│  ├─ data/               # 작업 데이터 (일부는 Git 제외)
│  ├─ reports/            # 분석 및 검수 결과
│  └─ README.md           # 라벨링 단계별 참고 문서
├─ 1-수집/                # 원본 수집 데이터 (별도 전달)
├─ 3-가공/                # 가공 이미지 (별도 전달)
├─ requirements.txt
└─ .gitignore
```

## 준비 사항

- Windows 10/11
- Python 3.11 또는 3.12 권장
- Git
- 원본·가공 데이터에 대한 별도 접근 권한

Python 3.13에서도 일부 스크립트는 동작할 수 있지만, `torch`, `torchvision`, `ultralytics`, `labelImg`의 호환성을 고려하면 3.11 또는 3.12가 안전합니다.

## 설치

PowerShell에서 저장소를 클론하고 가상환경을 만듭니다.

```powershell
git clone https://github.com/juhyeong929/Thermal-Switchgear-Detection.git
cd Thermal-Switchgear-Detection

py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell 실행 정책 때문에 가상환경 활성화가 차단되면, 현재 세션에서만 다음 명령을 실행합니다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\Activate.ps1
```

### PyTorch 설치 참고

`requirements.txt`의 `torch`와 `torchvision`은 기본 설치 기준입니다. NVIDIA GPU를 사용할 경우 [PyTorch 공식 설치 안내](https://pytorch.org/get-started/locally/)에서 CUDA 버전에 맞는 명령으로 설치하세요.

## 데이터 배치

이미지 원본과 대용량 생성 데이터는 저장소 용량 및 관리상의 이유로 GitHub에 올리지 않습니다. 별도로 전달받은 폴더를 저장소 루트에 배치해야 합니다.

```text
열화상/
├─ 1-수집/
├─ 3-가공/
└─ pilot/
   └─ data/
```

`4-라벨링/data`의 일부 작업 결과 역시 `.gitignore`에 의해 제외됩니다. 데이터가 없는 상태에서는 코드 문법 검사와 일부 메타데이터 작업만 실행할 수 있으며, 이미지 분석·학습·라벨 검수는 실행되지 않습니다.

## 주요 실행 방법

명령은 저장소 루트에서 실행하는 것을 권장합니다.

### 4-라벨링 파이프라인

```powershell
# 전체 기본 파이프라인
python 4-라벨링/scripts/run_all.py

# 저장소 상태 및 필수 산출물 확인
python 4-라벨링/scripts/status_check.py

# 라벨 분할 및 검수 예시
python 4-라벨링/scripts/build_splits.py
python 4-라벨링/scripts/audit_labels.py
```

중복 이미지 분석까지 포함하려면 실행 시간이 길고 추가 메모리가 필요하므로 다음처럼 실행합니다.

```powershell
python 4-라벨링/scripts/run_all.py --with-dedup
```

### pilot 스크립트

```powershell
cd pilot

# 라벨 좌표 이동, 검수, 분석 예시
python transfer.py
python qa_sheet.py labels
python analyze.py

# 열화상 모델 학습 및 예측 예시
python train.py --modality ir
python predict.py --help
```

각 스크립트의 옵션은 `python 스크립트명.py --help`로 확인할 수 있습니다. `pilot/README.md`와 `pilot/LABELING_GUIDE.md`에는 초기 실험 및 라벨링 세부 절차가 정리되어 있습니다.

Windows 기본 콘솔의 코드페이지가 `cp949`인 경우 도움말에 포함된 일부 특수문자를 출력하지 못할 수 있습니다. 그때는 현재 PowerShell 세션에서 UTF-8 출력을 설정한 뒤 실행합니다.

```powershell
$env:PYTHONIOENCODING = "utf-8"
python 4-라벨링/scripts/build_splits.py --help
```

## 기본 클래스

현재 주요 클래스 정의는 다음 파일에 있습니다.

- `4-라벨링/schemas/classes_v2.py`
- `4-라벨링/schemas/classes_v1_26.py`
- `pilot/classes.py`

라벨 클래스나 매핑을 변경할 때는 관련 CSV, 검수 규칙, 안내 문서가 함께 영향을 받으므로 클래스 파일만 단독으로 수정하지 않도록 합니다.

## CVAT 작업

CVAT용 작업 패키지 생성과 결과 가져오기는 `4-라벨링/scripts`의 CVAT 관련 스크립트를 사용합니다.

```powershell
python 4-라벨링/scripts/build_cvat_tasks.py --help
python 4-라벨링/scripts/cvat_xml_to_attributes.py --help
```

## 설치 확인

```powershell
python -c "import numpy, PIL, cv2, torch, torchvision, ultralytics, yaml; print('기본 패키지 설치 완료')"
python -m compileall -q pilot 4-라벨링
```

`PyQt5` 또는 `labelImg`를 사용하는 라벨링 UI 검증은 해당 패키지를 별도로 확인합니다.

```powershell
python -c "import PyQt5, labelImg; print('labelImg 환경 확인 완료')"
```

## Git 관리 원칙

- 코드·설정·라벨 규칙·문서는 Git으로 관리합니다.
- 원본 이미지, 대량 가공 이미지, 모델 가중치, 캐시, 학습 결과는 Git에 추가하지 않습니다.
- 데이터가 필요한 작업은 별도 데이터 전달 또는 공유 저장소에서 데이터를 먼저 준비해야 합니다.
- 작업 전후 `git status`로 변경된 파일을 확인합니다.

## 문제 해결

### `ModuleNotFoundError`

가상환경이 활성화되어 있는지 확인한 뒤 의존성을 다시 설치합니다.

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 이미지 또는 CSV를 찾을 수 없음

대부분 데이터 폴더가 없거나 저장소 루트가 아닌 위치에서 실행한 경우입니다. 먼저 `1-수집`, `3-가공`, `pilot/data`, `4-라벨링/data`의 존재 여부를 확인하세요.

### 한글 경로 문제

스크립트는 `pathlib` 기반의 상대경로를 사용합니다. 저장소 경로에 한글이 있어도 Windows 최신 Python에서는 동작하지만, 오래된 외부 프로그램이나 압축 해제 도구에서 문제가 발생하면 영문 경로에 클론해 보세요.
