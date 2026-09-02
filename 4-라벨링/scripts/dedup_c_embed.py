"""STEP 08 Stage D — 후보쌍 판정을 위한 이미지 임베딩을 계산한다.

pHash 는 저주파 구조만 본다. 촬영 위치가 조금 다르거나 온도 스케일이 달라 색이 뒤집힌
경우를 pHash 만으로 가르기 어렵다. 후보쌍(pHash 로 이미 좁혀진 쌍)에 대해서만 임베딩
코사인 유사도를 추가로 재서 최종 판정한다.

임베딩은 ImageNet 사전학습 ResNet18 의 penultimate 512차원을 L2 정규화해 쓴다.
열화상 전용 모델은 아니지만, 여기서 필요한 것은 '같은 장면인가'의 상대 비교이지
부품 인식이 아니므로 범용 특징으로 충분하다.

후보쌍에 등장하는 이미지가 전체의 94%라 어차피 대부분을 계산하게 되므로, **전량**을
계산해 저장한다. STEP 10 시드셋의 다양성 표집에 그대로 재사용한다.

원본은 읽기만 한다.

출력: data/dedup/embeddings.npy    (float16, N x 512, L2 정규화)
      data/dedup/embeddings_index.csv  (행 순서 -> image_id / rel_path)
"""

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
import torchvision.models as models

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

BATCH = 256
SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def load(rel):
    try:
        raw = (paths.PROCESSED / rel).read_bytes()
    except OSError:
        return np.zeros((3, SIZE, SIZE), np.float32)
    im = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        return np.zeros((3, SIZE, SIZE), np.float32)
    im = cv2.cvtColor(cv2.resize(im, (SIZE, SIZE)), cv2.COLOR_BGR2RGB)
    return (((im.astype(np.float32) / 255) - MEAN) / STD).transpose(2, 0, 1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    src = paths.DEDUP / "fingerprints.csv"
    with src.open(encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if not r["error"]]
    print(f"대상 {len(rows):,}장")

    torch.set_num_threads(24)
    net = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    net.fc = torch.nn.Identity()
    net.eval()

    out = np.zeros((len(rows), 512), np.float16)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for s in range(0, len(rows), BATCH):
            chunk = rows[s:s + BATCH]
            batch = torch.from_numpy(
                np.stack(list(pool.map(load, [r["rel_path"] for r in chunk]))))
            with torch.no_grad():
                e = net(batch)
            e = torch.nn.functional.normalize(e, dim=1)
            out[s:s + len(chunk)] = e.numpy().astype(np.float16)
            if (s // BATCH) % 40 == 0 and s:
                el = time.time() - t0
                print(f"  {s:,}/{len(rows):,}  경과 {el/60:.1f}분  "
                      f"남은 {(el/s*(len(rows)-s))/60:.1f}분", flush=True)

    np.save(paths.DEDUP / "embeddings.npy", out)
    idx = paths.DEDUP / "embeddings_index.csv"
    with idx.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "image_id", "panel_id", "rel_path"])
        for i, r in enumerate(rows):
            w.writerow([i, r["image_id"], r["panel_id"], r["rel_path"]])

    print(f"\n임베딩 {out.shape} -> embeddings.npy  ({(time.time()-t0)/60:.1f}분)")


if __name__ == "__main__":
    main()
