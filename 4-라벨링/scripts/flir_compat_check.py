"""D — pilot/flir.py 가 현재 데이터에 그대로 쓰이는지 **확인만** 한다.

라디오메트릭 온도 추출이 되는지 확인하는 것이 목적이다. 여기서 무언가를 고치거나
파이프라인에 편입하지 않는다. pilot 은 읽기 전용이다.

방법: 반 x 카메라 층마다 표본을 뽑아 flir.read() 를 돌리고 성공/실패와 온도 범위를
      기록한다. 원본은 열기만 한다.

출력: reports/data_audit/flir_compat.csv
"""

import csv
import random
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

sys.path.insert(0, str(paths.PILOT))
PER_STRATUM = 10         # 층마다 표본 수
SEED = 20260828


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import flir
    except Exception as e:
        sys.exit(f"pilot/flir.py 를 import 하지 못했다: {e}")

    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        inv = [r for r in csv.DictReader(fh) if r["kind"] == "IR"]

    strata = defaultdict(list)
    for r in inv:
        strata[(r["panel_id"], r["camera"])].append(r)

    rng = random.Random(SEED)
    rows = []
    for key, items in sorted(strata.items()):
        for r in rng.sample(items, min(PER_STRATUM, len(items))):
            p = paths.PROCESSED / r["rel_path"]
            rec = {"panel_id": r["panel_id"], "camera": r["camera"],
                   "rel_path": r["rel_path"], "exists": p.exists(),
                   "status": "", "raw_shape": "", "visual_shape": "",
                   "model": "", "temp_min": "", "temp_max": "", "error": ""}
            if not p.exists():
                rec["status"] = "FILE_NOT_FOUND"
                rows.append(rec)
                continue
            try:
                temp, visual, meta = flir.read(p)
                rec["status"] = "OK"
                rec["raw_shape"] = f"{temp.shape[1]}x{temp.shape[0]}"
                rec["visual_shape"] = ("—" if visual is None
                                       else f"{visual.shape[1]}x{visual.shape[0]}")
                rec["model"] = meta.model
                rec["temp_min"] = f"{float(temp.min()):.1f}"
                rec["temp_max"] = f"{float(temp.max()):.1f}"
            except Exception as e:
                rec["status"] = "FAIL"
                rec["error"] = f"{type(e).__name__}: {e}"
                traceback.clear_frames(sys.exc_info()[2])
            rows.append(rec)

    paths.AUDIT.mkdir(parents=True, exist_ok=True)
    with (paths.AUDIT / "flir_compat.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    st = Counter(r["status"] for r in rows)
    print(f"D — pilot/flir.py 호환성 확인 (표본 {len(rows)}장, "
          f"층 {len(strata)}개 x {PER_STRATUM}장)")
    print()
    print(f"  {'판정':<16}{'건수':>6}")
    for k, v in st.most_common():
        print(f"  {k:<16}{v:>6}")
    print()
    ok = [r for r in rows if r["status"] == "OK"]
    if ok:
        print(f"  해상도    {dict(Counter(r['raw_shape'] for r in ok))}")
        print(f"  실화상    {dict(Counter(r['visual_shape'] for r in ok))}")
        print(f"  모델      {dict(Counter(r['model'] for r in ok))}")
        tmin = min(float(r["temp_min"]) for r in ok)
        tmax = max(float(r["temp_max"]) for r in ok)
        print(f"  온도 범위 {tmin:.1f} ~ {tmax:.1f} C")
    bad = [r for r in rows if r["status"] == "FAIL"]
    if bad:
        print()
        print(f"  실패 {len(bad)}건 — 사유별")
        for k, v in Counter(r["error"].split(":")[0] for r in bad).most_common():
            print(f"    {k:<28}{v:>5}")
        print()
        print("  실패 표본 (반 · 카메라 · 사유)")
        for r in bad[:8]:
            print(f"    {r['panel_id']:<5}{r['camera']:<6}{r['error'][:70]}")
    print()
    print("**확인만 했다.** 파이프라인에 편입하거나 pilot 을 수정하지 않았다.")


if __name__ == "__main__":
    main()
