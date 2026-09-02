"""CVAT 협업용 패키지를 만든다.

만드는 것 (out/cvat/)
  labels.json                 CVAT 프로젝트 생성 시 Raw 탭에 붙여넣는 클래스 정의 16개
  calibration_images.zip      1단계 기준 합의용 20장 (5명 전원이 같은 것을 라벨링)
  task_A_<반들>_images.zip     담당자별 이미지
  task_A_..._preannot.zip     담당자별 사전 라벨 (CVAT YOLO 1.1 import 포맷)
  assignment.csv              어느 사진이 누구 담당인지, 중복 배정 여부
  GUIDE.md                    라벨러에게 그대로 주는 작업 지침

사전 라벨은 기존 사람 라벨이 있으면 그것을, 없으면 학습된 모델 예측을 넣는다.
라벨러는 처음부터 그리지 않고 검수·수정한다.

원본 데이터는 읽기만 한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN, KOREAN_BY_ID, NAMES, PANEL_CLASSES  # noqa: E402
from transfer import label_files  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out" / "cvat"

# 담당자별 반 배정. 한 사람이 2~4개 클래스만 보게 묶었다.
# 같은 반을 여러 사람이 나눠 갖지 않는다 — 연속 촬영 프레임이 거의 같은 사진이라
# 나눠 가지면 거의 동일한 사진에 서로 다른 라벨이 붙는다.
ASSIGN = {
    "A": ["P1-TR반", "P8-ACB반", "P13-기타"],
    "B": ["P2-LBS&LA반", "P5-PF&PT반"],
    "C": ["P3-MOF반", "P4-MOF&PT반"],
    "D": ["P6-VCB반", "P7-VCB&CT반"],
    "E": ["P9-MCCB반", "P10-ACB&MCCB반", "P11-CNCV반"],
}
# 교차 검증용 중복: A의 일부를 B도 라벨링 (A->B->C->D->E->A)
CROSS = {"A": "B", "B": "C", "C": "D", "D": "E", "E": "A"}

PALETTE = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
           "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
           "#9a6324", "#800000", "#808000", "#000075"]


def write_labels_json():
    spec = [{"name": n, "color": PALETTE[i % len(PALETTE)],
             "type": "rectangle", "attributes": []}
            for i, n in enumerate(NAMES)]
    p = OUT / "labels.json"
    p.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return p


def zip_images(stems, path: Path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for s in stems:
            z.write(DATA / "rgb" / f"{s}.jpg", f"{s}.jpg")
    return path


def zip_preannot(stems, path: Path, human: dict[str, str], pred_dir: Path | None):
    """CVAT YOLO 1.1 import 포맷.

    obj.data / obj.names / train.txt / obj_train_data/*.txt 구조를 갖는다.
    """
    n_human = n_pred = n_empty = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("obj.data",
                   f"classes = {len(NAMES)}\n"
                   "train = data/train.txt\n"
                   "names = data/obj.names\n"
                   "backup = backup/\n")
        z.writestr("obj.names", "\n".join(NAMES) + "\n")
        z.writestr("train.txt",
                   "\n".join(f"data/obj_train_data/{s}.jpg" for s in stems) + "\n")
        for s in stems:
            if s in human:
                body = human[s]
                n_human += 1
            elif pred_dir and (pred_dir / f"{s}.txt").exists():
                body = (pred_dir / f"{s}.txt").read_text(encoding="utf-8")
                n_pred += 1 if body.strip() else 0
                n_empty += 0 if body.strip() else 1
            else:
                body = ""
                n_empty += 1
            z.writestr(f"obj_train_data/{s}.txt", body)
    return n_human, n_pred, n_empty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calib", type=int, default=20, help="기준 합의용 장수")
    ap.add_argument("--cross-ratio", type=float, default=0.10, help="교차 중복 비율")
    ap.add_argument("--pred-dir", default=str(DATA / "labels_pred"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rng = random.Random(args.seed)

    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    by_panel: dict[str, list[str]] = {}
    for r in index:
        by_panel.setdefault(r["panel"], []).append(r["stem"])
    panel_of = {r["stem"]: r["panel"] for r in index}

    human = {f.stem: f.read_text(encoding="utf-8")
             for f in label_files(DATA / "labels_rgb")}
    pred_dir = Path(args.pred_dir) if Path(args.pred_dir).is_dir() else None

    print(f"전체 {len(index)}장 / 기존 사람 라벨 {len(human)}개 / "
          f"모델 사전예측 {'있음' if pred_dir else '없음'}\n")

    # --- 1단계: 기준 합의용 캘리브레이션 세트 (모든 반에서 골고루) ---
    calib = []
    panels = sorted(by_panel)
    i = 0
    while len(calib) < args.calib:
        p = panels[i % len(panels)]
        cand = [s for s in by_panel[p] if s not in calib]
        if cand:
            calib.append(rng.choice(cand))
        i += 1
        if i > 500:
            break
    zip_images(calib, OUT / "calibration_images.zip")
    print(f"캘리브레이션 {len(calib)}장 -> calibration_images.zip")
    print("  5명 전원이 같은 20장을 각자 라벨링합니다. 사전 라벨은 넣지 않습니다")
    print("  (모델 박스를 보면 판단이 끌려가 일치도 측정이 오염됩니다)\n")

    # --- 2단계: 담당자별 배정 + 교차 중복 ---
    rows = []
    for who, panel_list in ASSIGN.items():
        own = [s for p in panel_list for s in by_panel.get(p, [])]
        own = [s for s in own if s not in calib]
        rng.shuffle(own)
        n_cross = max(1, round(len(own) * args.cross_ratio))
        cross_out = set(own[:n_cross])          # 이 사람 것 중 다음 사람도 볼 것
        for s in own:
            rows.append({"stem": s, "panel": panel_of[s], "owner": who,
                         "cross_to": CROSS[who] if s in cross_out else ""})

    # 교차분을 상대방 작업 목록에도 넣는다
    per_person: dict[str, list[str]] = {w: [] for w in ASSIGN}
    for r in rows:
        per_person[r["owner"]].append(r["stem"])
        if r["cross_to"]:
            per_person[r["cross_to"]].append(r["stem"])

    with open(OUT / "assignment.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["stem", "panel", "owner", "cross_to"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["owner"], r["panel"], r["stem"])))

    print("담당자별 작업 패키지")
    for who in sorted(per_person):
        stems = sorted(set(per_person[who]))
        tag = f"task_{who}"
        zip_images(stems, OUT / f"{tag}_images.zip")
        nh, np_, ne = zip_preannot(stems, OUT / f"{tag}_preannot.zip", human, pred_dir)
        n_cross = sum(1 for r in rows if r["cross_to"] == who)
        cls = sorted({c for p in ASSIGN[who] for c in PANEL_CLASSES.get(p, [])})
        print(f"  {who}: {len(stems):3d}장 (본인 {len(stems)-n_cross} + 교차검증 {n_cross})")
        print(f"     반   {', '.join(ASSIGN[who])}")
        print(f"     클래스 {', '.join(KOREAN[c] for c in cls)}")
        print(f"     사전라벨 사람 {nh} / 모델 {np_} / 없음 {ne}")

    write_labels_json()
    (OUT / "GUIDE.md").write_text(guide_text(), encoding="utf-8")
    print(f"\n-> {OUT}")
    print("   labels.json  GUIDE.md  assignment.csv  calibration_images.zip  task_*_{images,preannot}.zip")


def guide_text() -> str:
    rows = "\n".join(
        f"| {i} | `{n}` | {KOREAN_BY_ID[i]} |" for i, n in enumerate(NAMES))
    panels = "\n".join(
        f"| `{p.split('-')[0]}` | {p.split('-', 1)[1]} | "
        f"{', '.join(KOREAN[c] for c in cs)} |"
        for p, cs in PANEL_CLASSES.items())
    return f"""# 수배전반 열화상 라벨링 지침

## 이 작업이 무엇에 쓰이는가

박스 안의 화소에서 실제 온도를 집계해 부품별 발열 이상을 판정한다. 그래서 이 작업은
일반 객체탐지 라벨링과 두 가지가 다르다.

1. **박스 경계가 판정 결과를 바꾼다.** 배경이 많이 들어가면 박스 온도가 희석되어
   이상을 놓친다. 일반 탐지보다 타이트하게 그린다.
2. **상(相)별로 따로 그려야 한다.** 같은 부품의 R·S·T 를 비교해 판정하므로,
   3상을 한 박스로 묶으면 판정 자체가 불가능해진다.

## 규칙

1. **부품 1개 = 박스 1개.** 3상이면 박스 3개. 절대 묶지 않는다. (가장 중요)
2. **부품 외곽에 딱 맞춘다.** 벽·바닥·빈 공간을 물지 않는다.
3. **오버레이를 피한다.** 사진 오른쪽 컬러바, 왼쪽 위 온도수치, 왼쪽 아래 FLIR 로고.
   그 위에 박스가 걸치면 온도가 오염된다.
4. **한 변이 8px 미만이면 그리지 않는다.** 그 이하는 온도가 노이즈다.
5. **50% 이상 보일 때만 그린다.** 가려진 것은 넘긴다.
6. **조명·히터는 절대 그리지 않는다.** 형광등·전열기가 배전반 부품보다 훨씬 뜨겁다.
   이것이 최대 오탐 원인이다. 부품이 아니면 뜨거워도 무시한다.
7. **확실하지 않으면 그리지 않는다.** 틀린 라벨이 빈 라벨보다 해롭다.
8. **부스바·케이블·철심부는 대상이 아니다.**

## 클래스 16개

| id | 키 | 한글 |
|---|---|---|
{rows}

접촉부를 세분하지 않는다. "MCCB 접촉부"는 따로 만들지 말고 `mccb` 하나로 묶는다.

## 담당 반과 후보 클래스

파일명 `A1_B1_P9_2022-06-17_IR1_00014` 의 **`P9` 가 반 번호**다. 아래 표의 후보
클래스만 쓴다. 표에 없는 클래스는 그 반에서 나오지 않는다.

| 반 | 이름 | 후보 클래스 |
|---|---|---|
{panels}

## 판단이 애매할 때

메모에 파일명과 함께 남기고 넘긴다. 혼자 결정하지 않는다. 같은 쟁점이 반복되면
전체 회의에서 규칙으로 정한 뒤 소급 적용한다.

이미 확인된 쟁점 (1단계에서 먼저 합의할 것):

- 몰드변압기의 **에폭시 표면**을 코일 3개로 나눠 그리는가, 몸통 1개로 그리는가
- **변압기**도 같은 질문
- 접촉부 경계를 볼트 체결부까지만 잡는가, 러그·케이블 끝까지 포함하는가
- MOF&PT반에 **한류형 전력퓨즈·CT** 가 실제로 있는가 (후보표 수정 필요 여부)
"""


if __name__ == "__main__":
    main()
