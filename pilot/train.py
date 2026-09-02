"""YOLO 학습용 데이터셋을 구성하고 학습을 돌린다.

  python train.py --modality ir     열화상 모델 (실제 배포 대상)
  python train.py --modality rgb    실화상 모델 (라벨 품질 확인 및 사전라벨링용)

배포 시스템이 보는 것은 열화상이므로 ir 이 본 모델이다. rgb 모델은 나머지 2,500쌍을
사전 라벨링해 사람 작업을 줄이는 용도로 쓴다.

검증 분할은 촬영 세션 단위로 나눈다. 같은 배전반을 연속 촬영한 프레임들이 train/val 에
섞이면 성능이 부풀려진다.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import NAMES  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"


def build_dataset(modality: str, labels_dir: Path, val_ratio=0.25, seed=0,
                  img_dir: Path | None = None) -> Path:
    img_src = img_dir or (DATA / ("ir" if modality == "ir" else "rgb"))
    root = HERE / "dataset" / modality
    if root.exists():
        shutil.rmtree(root)

    from transfer import label_files
    stems = sorted(p.stem for p in label_files(labels_dir)
                   if (img_src / f"{p.stem}.jpg").exists())
    if not stems:
        raise SystemExit(f"라벨이 없습니다: {labels_dir}")

    # 세션(현장_건물_반_촬영일) 단위 분할 — 같은 배전반이 양쪽에 걸치지 않게
    groups = {}
    for s in stems:
        parts = s.split("_")
        groups.setdefault("_".join(parts[:4]), []).append(s)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)

    n_target = max(1, int(len(stems) * val_ratio))

    # 세션을 통째로 배정하되, 클래스 분포가 한쪽으로 쏠리지 않게 고른다.
    # 세션 단위로만 나누면 특정 반의 라벨이 통째로 train 에 몰려 val 에 그 클래스가
    # 하나도 없는 상태가 되고, 그러면 검증 점수가 의미를 잃는다.
    import collections
    sess_cls, total_cls = {}, collections.Counter()
    for k, ss in groups.items():
        c = collections.Counter()
        for s in ss:
            for ln in (labels_dir / f"{s}.txt").read_text(encoding="utf-8").splitlines():
                p = ln.split()
                if len(p) >= 5:
                    c[int(p[0])] += 1
        sess_cls[k] = c
        total_cls.update(c)

    def imbalance(chosen_cls, n_img):
        """val 의 클래스별 비율이 목표(val_ratio)에서 얼마나 벗어나는지."""
        pen = sum(total_cls[c] * abs(chosen_cls.get(c, 0) / total_cls[c] - val_ratio)
                  for c in total_cls)
        return pen + abs(n_img - n_target) * 2.0

    val, cur_cls, remaining = set(), collections.Counter(), list(keys)
    while remaining and len(val) < n_target:
        best, best_score = None, None
        for k in remaining:
            if len(val) + len(groups[k]) >= len(stems):     # 학습이 비면 안 된다
                continue
            trial = cur_cls + sess_cls[k]
            sc = imbalance(trial, len(val) + len(groups[k]))
            if best_score is None or sc < best_score:
                best, best_score = k, sc
        if best is None:
            break
        val.update(groups[best])
        cur_cls += sess_cls[best]
        remaining.remove(best)

    if not val:
        # 세션이 하나뿐이면 세션 분할이 불가능하므로 이미지 단위로 나눈다.
        # 같은 배전반이 양쪽에 걸치므로 검증 점수는 낙관적으로 읽어야 한다.
        shuffled = sorted(stems)
        random.Random(seed).shuffle(shuffled)
        val = set(shuffled[:n_target])
        print("  주의: 세션이 1개뿐이라 이미지 단위로 분할했습니다. 검증 점수가 부풀려집니다.")
    if len(val) >= len(stems):
        raise SystemExit("학습 데이터가 0장입니다. val_ratio 를 낮추거나 세션을 늘리세요.")

    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
    for s in stems:
        split = "val" if s in val else "train"
        shutil.copy2(img_src / f"{s}.jpg", root / "images" / split / f"{s}.jpg")
        shutil.copy2(labels_dir / f"{s}.txt", root / "labels" / split / f"{s}.txt")

    yaml = root / "data.yaml"
    yaml.write_text(
        f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\n\n"
        f"nc: {len(NAMES)}\nnames:\n"
        + "".join(f"  {i}: {n}\n" for i, n in enumerate(NAMES)),
        encoding="utf-8")

    n_tr = len(stems) - len(val)
    print(f"[{modality}] 학습 {n_tr}장 / 검증 {len(val)}장  (세션 {len(keys)}개 기준 분할)")
    return yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modality", choices=["ir", "rgb"], default="ir")
    ap.add_argument("--labels", default=None, help="라벨 디렉터리 (기본: data/labels_{modality})")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=None, help="기본: ir=320, rgb=640")
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--name", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--images", default=None, help="이미지 디렉터리 (기본: data/ir)")
    args = ap.parse_args()

    labels_dir = Path(args.labels) if args.labels else DATA / f"labels_{args.modality}"
    imgsz = args.imgsz or (320 if args.modality == "ir" else 640)
    yaml = build_dataset(args.modality, labels_dir,
                         img_dir=Path(args.images) if args.images else None)

    from ultralytics import YOLO
    model = YOLO(args.model)
    model.train(
        data=str(yaml), epochs=args.epochs, imgsz=imgsz, batch=args.batch,
        project=str(HERE / "runs"), name=args.name or f"{args.modality}_pilot",
        device="cpu", workers=0, seed=args.seed, val=True, plots=True,
        # 100장 규모에서는 증강을 세게 걸어야 과적합이 덜하다.
        # 단, 열화상은 좌우 대칭 구조가 많아 flipud 는 끄고 fliplr 만 쓴다.
        hsv_h=0.0, hsv_s=0.3, hsv_v=0.4, degrees=5.0, translate=0.1,
        scale=0.4, fliplr=0.5, flipud=0.0, mosaic=0.5, erasing=0.0,
    )
    print(f"\n결과: {HERE / 'runs' / (args.name or f'{args.modality}_pilot')}")


if __name__ == "__main__":
    main()
