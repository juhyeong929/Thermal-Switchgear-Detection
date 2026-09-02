"""STEP 08 Stage A+B — 파일 해시(exact) 와 pHash(near) 를 계산한다.

106,685장을 서로 다 비교하는 일은 하지 않는다. 먼저 값싼 지문 두 개를 뽑아 두고,
비교는 다음 단계에서 후보군 안에서만 한다.

  Stage A  파일 바이트 SHA-256   -> 완전 동일 파일(exact duplicate)
  Stage B  pHash 64bit           -> 근접 중복 후보를 좁히기 위한 지각 해시

pHash 는 imagehash 패키지 없이 직접 구현한다 (32x32 그레이 -> DCT-II -> 좌상단 8x8
저주파 계수 -> 중앙값 기준 이진화). 외부 의존을 늘리지 않기 위해서다.

원본은 읽기만 한다. 삭제·수정하지 않는다.

출력: data/dedup/fingerprints.csv
"""

import csv
import hashlib
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

HASH_SIZE = 8          # pHash 비트폭 (8x8 = 64bit)
DCT_SIZE = 32          # DCT 입력 해상도
CHUNK = 256


def _dct_matrix(n):
    """DCT-II 기저 행렬. scipy 없이 쓰기 위해 직접 만든다."""
    k = np.arange(n).reshape(-1, 1)
    i = np.arange(n).reshape(1, -1)
    m = np.cos(np.pi * (2 * i + 1) * k / (2 * n))
    m[0] *= np.sqrt(1 / n)
    m[1:] *= np.sqrt(2 / n)
    return m


DCT = _dct_matrix(DCT_SIZE)


def phash(gray):
    """32x32 그레이 이미지 -> 64bit 지각 해시 (16자리 hex)."""
    small = cv2.resize(gray, (DCT_SIZE, DCT_SIZE), interpolation=cv2.INTER_AREA)
    f = DCT @ small.astype(np.float64) @ DCT.T
    block = f[:HASH_SIZE, :HASH_SIZE].flatten()
    # DC 성분은 전체 밝기라 빼고 중앙값을 잡는다. 밝기 차이에 덜 흔들린다.
    med = np.median(block[1:])
    bits = block > med
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return f"{v:016x}"


def fingerprint(rel_path):
    """이미지 1장의 지문. 실패해도 예외를 밖으로 던지지 않는다."""
    p = paths.PROCESSED / rel_path
    try:
        raw = p.read_bytes()
    except OSError as e:
        return rel_path, "", "", 0, 0, 0, f"읽기 실패: {e.__class__.__name__}"

    sha = hashlib.sha256(raw).hexdigest()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return rel_path, sha, "", 0, 0, len(raw), "디코드 실패"
    h, w = img.shape[:2]
    return rel_path, sha, phash(img), w, h, len(raw), ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    inv = paths.METADATA / "image_inventory.csv"
    with inv.open(encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh)]
    # IR 열화상만 대상으로 한다. RGB 페어는 IR 을 따라가므로 따로 세지 않는다.
    targets = [r for r in rows if r["kind"] == "IR"]
    print(f"대상 {len(targets):,}장 (IR only, 10개 반)")

    out = paths.DEDUP / "fingerprints.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {r["rel_path"]: r for r in targets}

    done = 0
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["image_id", "panel_id", "rel_path", "camera", "session_key",
                    "sha256", "phash", "width", "height", "bytes", "error"])
        with ProcessPoolExecutor() as ex:
            for rel, sha, ph, iw, ih, nb, err in ex.map(
                    fingerprint, [r["rel_path"] for r in targets], chunksize=CHUNK):
                m = meta[rel]
                # 촬영 회차 키 — 이후 클러스터·분할이 회차를 넘나들지 않게 하는 데 쓴다.
                skey = f"{m['site']}_{m['building']}_{m['date']}_{m['camera']}_{m['session']}"
                w.writerow([m["image_id"], m["panel_id"], rel, m["camera"], skey,
                            sha, ph, iw, ih, nb, err])
                done += 1
                if done % 10000 == 0:
                    print(f"  {done:,} / {len(targets):,}")

    print(f"\n지문 {done:,}건 -> {out}")


if __name__ == "__main__":
    main()
