"""OQ-016 판정 결과를 집계한다. **누수율 하나로 요약하지 않는다.**

무엇을 내나
    유사도 구간 · 세션 관계 · 반 · 카메라별로 나눠 낸다. 그리고 층화 표본이므로
    **모집단 가중 추정**을 함께 낸다 — 표본의 단순 비율이 아니라 층 크기로 다시 가중한 값이다.

    세션과 cluster 는 같은 의미가 아니다. "같은 세션이면 누수" 로 결론내지 않는다.
    그래서 다음 두 가지를 따로 센다.
      · 같은 세션인데 DIFFERENT_SCENE
      · 다른 세션인데 SAME_SCENE

무엇을 하지 않나
    **CASE 판정을 스크립트가 내리지 않는다.** 분기 조건과 숫자를 나란히 놓을 뿐이다.
    clustering 을 다시 만들지 않고 split 도 바꾸지 않는다.

출력
    reports/data_audit/oq016/result_summary.csv   축별 집계
    reports/data_audit/oq016/same_scene_pairs.csv 동일 시야로 판정된 쌍 목록

사용
    python scripts/oq016_summarize.py
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

BASE = paths.AUDIT / "oq016"
RISK = {"SAME_SCENE", "NEAR_DUPLICATE"}      # 둘 다 '누수 위험 있음' 으로 센다


def read(p):
    with Path(p).open(encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh)
                if not str(list(r.values())[0]).startswith("#")]


def rate(rows, key=None):
    """(n, same, near, diff, unc, 위험비율)"""
    c = Counter(r["verdict"].strip() for r in rows)
    n = len(rows)
    risk = c["SAME_SCENE"] + c["NEAR_DUPLICATE"]
    return {"n": n, "SAME_SCENE": c["SAME_SCENE"], "NEAR_DUPLICATE": c["NEAR_DUPLICATE"],
            "DIFFERENT_SCENE": c["DIFFERENT_SCENE"], "UNCERTAIN": c["UNCERTAIN"],
            "risk_rate": round(risk / n, 4) if n else ""}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sample = {r["pair_id"]: r for r in read(BASE / "sample_pairs.csv")}
    rev = read(BASE / "visual_review.csv")
    done = [r for r in rev if r["verdict"].strip()]

    if len(done) < len(rev):
        print(f"판정 {len(done)}/{len(rev)} — 미완. 부분 집계만 낸다.\n")

    rows = []
    for r in done:
        s = sample.get(r["pair_id"])
        if not s:
            continue
        rows.append({**s, "verdict": r["verdict"].strip(), "note": r.get("note", "")})

    tot = rate(rows)
    print(f"판정 {len(rows)}쌍 (모집단 41,184 의 {len(rows)/41184:.3%})")
    print(f"  SAME_SCENE {tot['SAME_SCENE']} · NEAR_DUPLICATE {tot['NEAR_DUPLICATE']} · "
          f"DIFFERENT_SCENE {tot['DIFFERENT_SCENE']} · UNCERTAIN {tot['UNCERTAIN']}")
    print(f"  표본 위험 비율(SAME+NEAR) {tot['risk_rate']:.1%}")

    # ---- 모집단 가중 추정 — 층화 표본이므로 단순 비율이 아니다 ----
    summ = read(BASE / "summary.csv")
    pop = {r["cell"]: int(r["population"]) for r in summ}
    total_pop = sum(pop.values())
    by_cell = defaultdict(list)
    for r in rows:
        by_cell[r["cell"]].append(r)
    # 잔층은 summary 에 묶음 한 줄로 있다. 개별 cell 이 pop 에 없으면 잔층으로 본다
    minor_key = next((k for k in pop if k.startswith("(잔층")), None)
    minor_pop = pop.get(minor_key, 0)
    num = den = 0.0
    minor_rows = []
    for cell, rs in by_cell.items():
        if cell in pop:
            p = pop[cell]
            num += p * rate(rs)["risk_rate"]
            den += p
        else:
            minor_rows += rs
    if minor_rows and minor_pop:
        num += minor_pop * rate(minor_rows)["risk_rate"]
        den += minor_pop
    weighted = num / den if den else None
    if weighted is not None:
        print(f"  **모집단 가중 추정 위험 비율 {weighted:.1%}** "
              f"(층 크기로 다시 가중 · 표본 비율과 다를 수 있다)")
        print(f"  -> 교차 쌍 41,184 중 약 {round(41184*weighted):,}쌍 추정")

    out = []
    out.append({"axis": "전체", "value": "-", **tot})
    if weighted is not None:
        out.append({"axis": "전체(모집단 가중)", "value": "-", "n": den,
                    "SAME_SCENE": "", "NEAR_DUPLICATE": "", "DIFFERENT_SCENE": "",
                    "UNCERTAIN": "", "risk_rate": round(weighted, 4)})

    def block(title, keyfn, order=None):
        print(f"\n■ {title}")
        print(f"  {'':<26}{'n':>4}{'SAME':>6}{'NEAR':>6}{'DIFF':>6}{'위험':>8}")
        groups = defaultdict(list)
        for r in rows:
            groups[keyfn(r)].append(r)
        keys = order or sorted(groups)
        for k in keys:
            if k not in groups:
                continue
            st = rate(groups[k])
            print(f"  {str(k):<26}{st['n']:>4}{st['SAME_SCENE']:>6}"
                  f"{st['NEAR_DUPLICATE']:>6}{st['DIFFERENT_SCENE']:>6}"
                  f"{st['risk_rate']:>7.1%}")
            out.append({"axis": title, "value": k, **st})

    block("유사도 구간", lambda r: r["cos_bin"])
    block("세션 관계", lambda r: "같은 세션" if r["same_session"] == "1" else "다른 세션")
    block("반", lambda r: r["panel"])
    block("카메라", lambda r: r["camera_a"])

    # ---- 세션과 cluster 는 같은 의미가 아니다 ----
    print("\n■ 세션·cluster 와의 관계 — 따로 세야 하는 두 가지")
    a = [r for r in rows if r["same_session"] == "1" and r["verdict"] == "DIFFERENT_SCENE"]
    b = [r for r in rows if r["same_session"] == "0" and r["verdict"] in RISK]
    print(f"  같은 세션인데 DIFFERENT_SCENE   {len(a):>3}건  "
          f"-> 세션이 곧 장면이 아니다")
    print(f"  다른 세션인데 SAME/NEAR         {len(b):>3}건  "
          f"-> 세션 단위 분할로도 못 막았을 쌍")
    same_cl = [r for r in rows if r["same_cluster"] == "1"]
    print(f"  같은 cluster 인데 split 이 다름  {len(same_cl):>3}건  "
          f"-> 0 이 아니면 명백한 누수")
    out += [{"axis": "교차분석", "value": "같은 세션 · DIFFERENT_SCENE", "n": len(a),
             "SAME_SCENE": "", "NEAR_DUPLICATE": "", "DIFFERENT_SCENE": len(a),
             "UNCERTAIN": "", "risk_rate": ""},
            {"axis": "교차분석", "value": "다른 세션 · SAME/NEAR", "n": len(b),
             "SAME_SCENE": "", "NEAR_DUPLICATE": "", "DIFFERENT_SCENE": "",
             "UNCERTAIN": "", "risk_rate": ""},
            {"axis": "교차분석", "value": "같은 cluster · split 다름", "n": len(same_cl),
             "SAME_SCENE": "", "NEAR_DUPLICATE": "", "DIFFERENT_SCENE": "",
             "UNCERTAIN": "", "risk_rate": ""}]

    with (BASE / "result_summary.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["axis", "value", "n", "SAME_SCENE",
                                           "NEAR_DUPLICATE", "DIFFERENT_SCENE",
                                           "UNCERTAIN", "risk_rate"])
        w.writeheader(); w.writerows(out)

    risky = [r for r in rows if r["verdict"] in RISK]
    with (BASE / "same_scene_pairs.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        f = ["pair_id", "verdict", "cosine", "cos_bin", "same_session", "same_cluster",
             "panel", "camera_a", "camera_b", "split_a", "split_b",
             "image_id_a", "image_id_b", "note"]
        w = csv.DictWriter(fh, fieldnames=f, extrasaction="ignore")
        w.writeheader(); w.writerows(sorted(risky, key=lambda r: -float(r["cosine"])))

    # ---- 분기 조건을 숫자와 나란히 놓는다. 판정은 사람이 한다 ----
    print("\n■ 결론 분기 (판정은 사람이 한다)")
    for k, cond in (("CASE A", "SAME_SCENE 거의 없음 -> cluster split 유지 근거 강화"),
                    ("CASE B", "적지만 존재 -> 잔여 미탐지 기록 · 보수적 처리 검토"),
                    ("CASE C", "상당수 존재 -> **cluster split 최종 확정하지 않음**"),
                    ("CASE D", "UNCERTAIN 이 많음 -> 시각 검증 기준 보강")):
        print(f"  {k}  {cond}")
    print(f"\n  관측: SAME_SCENE {tot['SAME_SCENE']}/{tot['n']} "
          f"({tot['SAME_SCENE']/tot['n']:.1%}) · "
          f"위험(SAME+NEAR) {tot['risk_rate']:.1%} · "
          f"UNCERTAIN {tot['UNCERTAIN']}")

    print(f"\n-> {BASE / 'result_summary.csv'}")
    print(f"-> {BASE / 'same_scene_pairs.csv'} ({len(risky)}쌍)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
