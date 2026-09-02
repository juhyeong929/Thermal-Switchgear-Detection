"""STEP 08 Stage C — pHash LSH 로 근접중복 '후보쌍' 만 뽑는다.

106,685장을 전부 서로 비교하면 약 57억 쌍이다. 그렇게 하지 않는다.
64bit pHash 를 16bit 씩 4개 밴드로 쪼개고, **한 밴드라도 완전히 같은 쌍**만 후보로 올린다
(LSH banding). 해밍거리가 작은 쌍은 어느 한 밴드가 통째로 일치할 확률이 높으므로,
가까운 쌍을 놓치지 않으면서 비교량을 몇 자릿수 줄일 수 있다.

후보는 **같은 반 안에서만** 만든다. 반은 독립 데이터 도메인이라(DEC-002) 서로 다른 반의
이미지를 한 클러스터로 묶지 않는다. 촬영 회차는 넘나들게 둔다 — 같은 설비를 다른 회차에
다시 찍은 것이야말로 train/val 누수의 주범이라 반드시 같은 클러스터로 묶여야 한다.

임계값은 여기서 정하지 않는다. 해밍거리 분포를 산출해 다음 단계에서 근거를 보고 고른다.

출력: data/dedup/candidate_pairs.csv       (해밍거리 <= MAX_HAMMING 인 쌍)
      reports/data_audit/dedup_hamming_distribution.csv
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

BAND_BITS = 16                    # 64bit -> 16bit x 4밴드
N_BANDS = 64 // BAND_BITS
MAX_HAMMING = 16                  # 후보로 기록해 둘 상한. 확정 임계값이 아니다.
MAX_BUCKET = 4000                 # 이보다 큰 버킷은 쌍 폭발을 막기 위해 건너뛴다


def load():
    p = paths.DEDUP / "fingerprints.csv"
    if not p.exists():
        sys.exit("fingerprints.csv 가 없다. scripts/dedup_a_hash.py 를 먼저 실행한다.")
    with p.open(encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if not r["error"]]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = load()
    print(f"대상 {len(rows):,}장")

    by_panel = defaultdict(list)
    for i, r in enumerate(rows):
        by_panel[r["panel_id"]].append(i)

    hashes = np.array([int(r["phash"], 16) for r in rows], dtype=np.uint64)
    # 해밍거리를 바이트 팝카운트 룩업으로 센다 (64bit -> 8바이트).
    hv = hashes.view(np.uint8).reshape(-1, 8)
    POPCNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1)

    pairs = []
    dist_hist = np.zeros(65, dtype=np.int64)
    skipped_buckets = 0

    for panel, idxs in sorted(by_panel.items(), key=lambda x: -len(x[1])):
        idxs = np.array(idxs)
        seen = set()
        for b in range(N_BANDS):
            shift = np.uint64(b * BAND_BITS)
            key = (hashes[idxs] >> shift) & np.uint64((1 << BAND_BITS) - 1)
            order = np.argsort(key, kind="stable")
            k_sorted, i_sorted = key[order], idxs[order]
            # 같은 밴드 값을 가진 연속 구간이 하나의 버킷이다.
            bounds = np.flatnonzero(np.diff(k_sorted)) + 1
            for grp in np.split(i_sorted, bounds):
                n = len(grp)
                if n < 2:
                    continue
                if n > MAX_BUCKET:
                    skipped_buckets += 1
                    continue
                a, c = np.triu_indices(n, k=1)
                ga, gc = grp[a], grp[c]
                d = POPCNT[hv[ga] ^ hv[gc]].sum(1)
                dist_hist += np.bincount(d, minlength=65)
                keep = d <= MAX_HAMMING
                for x, y, dd in zip(ga[keep], gc[keep], d[keep]):
                    lo, hi = (x, y) if x < y else (y, x)
                    if (lo, hi) in seen:
                        continue
                    seen.add((lo, hi))
                    pairs.append((lo, hi, int(dd)))
        print(f"  {panel:<5} {len(idxs):>7,}장  누적 후보쌍 {len(pairs):,}")

    out = paths.DEDUP / "candidate_pairs.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["panel_id", "image_a", "image_b", "hamming",
                    "same_session", "rel_a", "rel_b"])
        for a, b, d in pairs:
            ra, rb = rows[a], rows[b]
            w.writerow([ra["panel_id"], ra["image_id"], rb["image_id"], d,
                        int(ra["session_key"] == rb["session_key"]),
                        ra["rel_path"], rb["rel_path"]])

    hpath = paths.AUDIT / "dedup_hamming_distribution.csv"
    with hpath.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["hamming", "candidate_pairs", "cumulative"])
        cum = 0
        for d in range(65):
            if dist_hist[d] == 0 and d > MAX_HAMMING:
                continue
            cum += int(dist_hist[d])
            w.writerow([d, int(dist_hist[d]), cum])

    print(f"\n후보쌍 {len(pairs):,}건 (해밍 <= {MAX_HAMMING}) -> {out.name}")
    print(f"과대 버킷 건너뜀 {skipped_buckets}건 (> {MAX_BUCKET})")
    print(f"해밍 분포 -> {hpath.name}")
    print("\n해밍거리별 후보쌍 (LSH 로 걸러진 쌍 기준)")
    for d in range(0, MAX_HAMMING + 1):
        if dist_hist[d]:
            print(f"  {d:>2}  {int(dist_hist[d]):>10,}")


if __name__ == "__main__":
    main()
