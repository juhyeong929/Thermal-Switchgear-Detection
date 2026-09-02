"""라벨러별 **박스 크기 행동**을 비교한다. NQ-12 를 의견이 아니라 데이터로 확정하려고.

왜 필요한가
    지침서 v1 은 작은 객체에 수치 기준을 주지 않는다 — "식별 가능성으로 판단" 뿐이다.
    그런데 1차 시험에서 라벨러 A 는 MCCB 접촉부 58개의 최소 면적 0.00257 · p05 0.00306 ·
    0.003 미만 3.4% 로, **임계값을 듣지 않았는데 0.003 근처를 재현했다.**

    두 해석이 가능하고 지금 데이터로는 가릴 수 없다.
      A. '식별 가능성' 이라는 인간 판단이 재현성이 높다   -> 수치를 강제할 필요 없음
      B. 사람이 내부적으로 크기 기준을 만들어 쓴다        -> 수치를 공식화하면 더 일관됨

    **여러 명의 하한이 모이는지 흩어지는지**가 이것을 가른다. 그래서 그리기 행동만 잰다.
    '그렸다/안 그렸다' 가 아니라 **면적 분포**를 본다.

무엇을 재나
    라벨러마다 · 클래스마다   n · 최소 · p05 · 중앙 · p95 · 임계값 미만 비율
    그리고 라벨러 간 하한이 얼마나 퍼졌는지 (p05 의 최소~최대 폭)

    기존 라벨(`_existing/`)도 같은 방식으로 넣어 대조군으로 쓴다.

**임계값을 라벨러에게 알려 주지 않는다.** 이 스크립트는 회수 뒤 검수자만 돌린다.
지침서에 수치를 넣으면 뒤에 오는 라벨러가 앞사람과 다른 규칙을 본 것이 되어
재현성 검증 자체가 무너진다 (`labeling_rules.SMALL_OBJECT_SCOPE`).

사용
    python scripts/box_size_profile.py                      # 제출한 라벨러 전원 + 기존
    python scripts/box_size_profile.py --class "MCCB 접촉부"
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import labeling_rules as rules  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
ANNOTATORS = ["annotator_A", "annotator_B", "annotator_C", "annotator_D", "annotator_E"]
SKIP_TXT = {"classes.txt", "obj.names", "train.txt"}
TH = rules.SMALL_OBJECT_CANDIDATE


def areas(folder, only_cls=None):
    """{class_id: [면적, ...]} — 정규화 면적. 빈 파일은 자연히 빠진다."""
    d = Path(folder)
    ydir = d / "yolo" if (d / "yolo").is_dir() else d
    out = {}
    for f in sorted(ydir.glob("*.txt")):
        if f.name in SKIP_TXT:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            t = line.split()
            if len(t) < 5:
                continue
            cid = int(float(t[0]))
            if only_cls is not None and cid != only_cls:
                continue
            out.setdefault(cid, []).append(float(t[3]) * float(t[4]))
    return out


def stats(v):
    v = np.asarray(v)
    return {
        "n": len(v),
        "min": round(float(v.min()), 5),
        "p05": round(float(np.percentile(v, 5)), 5),
        "median": round(float(np.median(v)), 5),
        "p95": round(float(np.percentile(v, 95)), 5),
        "below_th": int((v < TH).sum()),
        "below_th_pct": round(float((v < TH).mean()) * 100, 1),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--class", dest="cls", default=None, help="클래스 이름. 없으면 전 클래스")
    ap.add_argument("--min-n", type=int, default=5, help="이 개수 미만은 통계를 내지 않는다")
    a = ap.parse_args()

    cid = None
    if a.cls:
        hit = [c for c in v2.CLASSES if c.canonical_name == a.cls]
        if not hit:
            sys.exit(f"그런 클래스가 없다: {a.cls}")
        cid = hit[0].class_id

    sources = [(w, TRIAL / w) for w in ANNOTATORS if (TRIAL / w).is_dir()]
    if (TRIAL / "_existing").is_dir():
        sources.append(("_existing(기존)", TRIAL / "_existing"))

    rows = []
    for name, d in sources:
        per = areas(d, cid)
        for c, v in sorted(per.items()):
            if len(v) < a.min_n:
                continue
            rows.append({"annotator": name,
                         "class_name": v2.BY_ID[c].canonical_name, **stats(v)})

    if not rows:
        sys.exit("잰 것이 없다 — 아직 제출된 라벨이 없거나 개수가 너무 적다")

    out = paths.REPORTS / "labeling" / f"box_size_profile_{date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

    print(f"작은 객체 하한 후보 = {TH}  ({rules.SMALL_OBJECT_STATUS})")
    print(f"{rules.SMALL_OBJECT_SCOPE}\n")

    classes = sorted({r["class_name"] for r in rows})
    for cn in classes:
        sub = [r for r in rows if r["class_name"] == cn]
        print(f"■ {cn}")
        print(f"  {'라벨러':<18}{'n':>4}{'최소':>9}{'p05':>9}{'중앙':>9}"
              f"{'<임계':>7}{'비율':>7}")
        for r in sub:
            print(f"  {r['annotator']:<18}{r['n']:>4}{r['min']:>9.5f}{r['p05']:>9.5f}"
                  f"{r['median']:>9.5f}{r['below_th']:>7}{r['below_th_pct']:>6.1f}%")

        lab = [r for r in sub if not r["annotator"].startswith("_")]
        if len(lab) >= 2:
            p05 = [r["p05"] for r in lab]
            spread = max(p05) - min(p05)
            print(f"\n  라벨러 {len(lab)}명의 p05: {min(p05):.5f} ~ {max(p05):.5f}"
                  f"  (폭 {spread:.5f})")
            # 판단 근거만 제시한다. 결론은 사람이 낸다.
            if spread <= 0.001:
                print("  -> 하한이 모인다. '식별 가능성' 판단의 재현성이 높다는 쪽 근거")
            else:
                print("  -> 하한이 흩어진다. 사람마다 다른 기준을 쓴다는 쪽 근거 "
                      "(수치 명시를 재검토할 사유)")
            near = sum(1 for v in p05 if abs(v - TH) <= 0.001)
            print(f"  -> p05 가 {TH}±0.001 안에 든 라벨러 {near}/{len(lab)}명")
        else:
            print(f"\n  라벨러 {len(lab)}명 — **2명 이상부터 재현성을 말할 수 있다**")
        print()

    print(f"-> {out}")
    print("판정은 사람이 한다. 이 표는 NQ-12 의 근거일 뿐이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
