"""전체 배관(plumbing)이 도는지 확인하는 연기 테스트.

사람 라벨이 도착하기 전에 실화상 라벨 -> 전이 -> 학습 -> 추론 -> 온도 판정까지가
끊김 없이 도는지 확인한다. 여기서 쓰는 박스는 합성한 가짜이며 학습 성능에는 아무 의미가
없다. 오직 배관 점검용이다.

가짜 라벨은 smoke/ 아래에만 만든다. data/labels_rgb (사람이 작성할 진짜 라벨)는 절대
건드리지 않는다.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import transfer  # noqa: E402
from classes import NAMES, PANEL_CLASSES  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
SMOKE = HERE / "smoke"
PY = sys.executable


def make_fake_labels(seed=0):
    if SMOKE.exists():
        shutil.rmtree(SMOKE)
    (SMOKE / "labels_rgb").mkdir(parents=True)
    (SMOKE / "labels_ir").mkdir(parents=True)
    rng = random.Random(seed)
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    total = 0
    for rec in index:
        cands = [NAMES.index(n) for n in PANEL_CLASSES.get(rec["panel"], []) if n in NAMES]
        if not cands:
            cands = [0]
        lines = []
        for _ in range(rng.randint(2, 4)):
            w = rng.uniform(0.12, 0.30)
            h = rng.uniform(0.12, 0.30)
            cx = rng.uniform(w / 2 + 0.08, 1 - w / 2 - 0.08)
            cy = rng.uniform(h / 2 + 0.08, 1 - h / 2 - 0.08)
            lines.append(f"{rng.choice(cands)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            total += 1
        (SMOKE / "labels_rgb" / f"{rec['stem']}.txt").write_text("\n".join(lines) + "\n",
                                                                 encoding="utf-8")
    print(f"[1/5] 합성 라벨 {len(index)}파일 / 박스 {total}개 생성 (가짜, 성능 의미 없음)")
    return total


def run(cmd, step):
    print(f"\n[{step}] $ {' '.join(str(c) for c in cmd[1:])}")
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout or "").strip().splitlines()[-12:])
    if tail:
        print(tail)
    if r.returncode != 0:
        print((r.stderr or "")[-1500:])
        raise SystemExit(f"실패: {step}")
    return r


def main():
    n_boxes = make_fake_labels()

    # 2) 좌표 전이
    kept = dropped = 0
    for f in sorted((SMOKE / "labels_rgb").glob("*.txt")):
        k, d = transfer.convert_label_file(f, SMOKE / "labels_ir" / f.name)
        kept += k
        dropped += d
    print(f"\n[2/5] 좌표 전이: {kept}개 생성, {dropped}개 탈락 "
          f"({dropped/max(n_boxes,1)*100:.1f}% — 열화상 화각이 좁아 생기는 정상 손실)")

    # 3) 학습 (배관 확인용이므로 최소 epoch)
    run([PY, "train.py", "--modality", "ir", "--labels", str(SMOKE / "labels_ir"),
         "--epochs", "3", "--name", "smoke", "--batch", "4"], "3/5 학습")

    # 4) 추론 + 온도 판정
    run([PY, "analyze.py", "--weights", str(HERE / "runs" / "smoke" / "weights" / "best.pt"),
         "--conf", "0.05", "--draw", "3"], "4/5 추론 및 온도 판정")

    print("\n[5/5] 전 단계 정상 동작 확인")
    print("  실화상 라벨 -> 좌표 전이 -> 데이터셋 구성 -> YOLO 학습 -> 추론 -> 부품별 온도 -> 판정")
    print("\n남은 입력은 사람이 그리는 진짜 박스 하나뿐이다.")
    print("  data/rgb 100장에 라벨 작성 -> data/labels_rgb 에 저장")
    print("  python transfer.py && python train.py --modality ir && python analyze.py")


if __name__ == "__main__":
    main()
