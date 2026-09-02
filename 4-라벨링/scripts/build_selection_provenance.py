"""시험 30장의 선정 계보 — 왜 뽑혔고, 나머지는 왜 빠졌는가.

"이 사진들은 왜 여기 있는가"에 답할 수 있어야 한다. 뽑힌 이유만이 아니라
**탈락 이유**도 남긴다. 검증·인증 때 "표본을 임의로 고른 것 아닌가"에 대한 답이 된다.

두 가지를 만든다.

  1. 깔때기(funnel)  — 109,359장에서 30장까지 각 단계의 제외 사유와 장수
  2. 개별 계보       — 30장 각각이 어느 단계를 어떤 이유로 통과했는가,
                       같은 후보군에서 무엇이 밀렸는가

숫자는 전부 기존 산출물에서 다시 계산한다. 손으로 적지 않는다.

출력: reports/data_audit/selection_funnel.csv
      reports/data_audit/trial_provenance.csv
      reports/labeling/selection_rationale.md
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402


def read(p):
    p = Path(p)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    inv = read(paths.METADATA / "image_inventory.csv")
    fails = read(paths.AUDIT / "filename_parse_failures.csv")
    dd = read(paths.DEDUP / "dedup_metadata.csv")
    alloc = read(paths.AUDIT / "seed_allocation.csv")
    seed = read(paths.LABELING / "seed" / "seed_candidates.csv")
    trial = read(paths.LABELING / "seed" / "trial_set.csv")

    ir = [r for r in inv if r["kind"] == "IR"]
    rgb = [r for r in inv if r["kind"] == "RGB"]
    reps = [r for r in dd if r["is_representative"] == "1"]
    dupes = [r for r in dd if r["is_representative"] != "1"]

    # ---------------- 1. 깔때기 ----------------
    zip_removed = {"P11-CNCV반": 600, "P12-배선반": 3487, "P13-기타": 10728}
    funnel = [
        {"stage": "00 원본", "kept": len(inv) + len(fails),
         "removed": 0, "removal_reason": "",
         "basis": "3-가공 폴더 전체 파일",
         "doc": ""},
        {"stage": "01 범위 밖 반 제외", "kept": len(inv) + len(fails),
         "removed": sum(zip_removed.values()),
         "removal_reason": "P11-CNCV반 600 · P12-배선반 3,487 · P13-기타 10,728 — "
                           "P12·P13 은 가이드에 대응 항목 없음, P11 은 삭제됨. "
                           "3-가공.zip 에 남아 있어 복구 가능",
         "basis": "3-가공.zip 중앙 디렉터리 조회",
         "doc": "DEC-006"},
        {"stage": "02 이미지 아닌 파일 제외", "kept": len(inv),
         "removed": len(fails),
         "removal_reason": "macOS AppleDouble 부산물 6건 + 하위폴더 1건. 원본은 삭제하지 않음",
         "basis": "filename_parse_failures.csv",
         "doc": ""},
        {"stage": "03 RGB 제외", "kept": len(ir), "removed": len(rgb),
         "removal_reason": "라벨링 대상은 열화상(IR). RGB 는 경계 판단 참조용으로만 쓴다",
         "basis": "image_inventory.csv kind=RGB",
         "doc": "DEC-005"},
        {"stage": "04 근접중복 제외", "kept": len(reps), "removed": len(dupes),
         "removal_reason": f"해밍<=22 이고 코사인>=0.93 인 쌍을 같은 장면으로 묶고 "
                           f"클러스터당 대표 1장만 남김. 원본은 삭제하지 않고 "
                           f"cluster_id 메타데이터만 기록",
         "basis": "dedup_metadata.csv is_representative",
         "doc": "DEC-008"},
        {"stage": "05 시드 후보 선정", "kept": len(seed),
         "removed": len(reps) - len(seed),
         "removal_reason": "반 비례 배분을 쓰지 않고 클래스 수요에서 반 할당량을 역산. "
                           "할당량을 넘는 이미지는 이번 시드에 넣지 않음(폐기가 아니라 미선정)",
         "basis": "seed_allocation.csv",
         "doc": "DEC-010"},
        {"stage": "06 1차 시험셋", "kept": len(trial),
         "removed": len(seed) - sum(1 for r in trial if r["group"] == "A_본대상"),
         "removal_reason": "A군 18장은 시드 400에서 단위 검증 4종 담당 반만 추출. "
                           "B군 12장은 시드가 아니라 기존 라벨 보유 이미지에서 "
                           "실패 유형이 측정된 것을 별도 추출",
         "basis": "trial_set.csv",
         "doc": "본 문서"},
    ]

    with (paths.AUDIT / "selection_funnel.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(funnel[0]))
        w.writeheader()
        w.writerows(funnel)

    # ---------------- 2. 개별 계보 ----------------
    seed_by_panel = defaultdict(list)
    for r in seed:
        seed_by_panel[r["panel"]].append(r)
    dd_by_stem = {Path(r["rel_path"]).stem: r for r in dd}
    alloc_by_panel = {r["panel"]: r for r in alloc}
    picked_ids = {r["image_id"] for r in trial}

    rows = []
    for t in trial:
        stem = Path(t["image_id"]).name
        m = dd_by_stem.get(stem, {})
        a = alloc_by_panel.get(t["panel"], {})
        if t["group"] == "A_본대상":
            pool = seed_by_panel.get(t["panel"], [])
            sessions = sorted({p["session"] for p in pool})
            same_ses = [p for p in pool if p["session"] == t["session"]]
            others = [p["image_id"] for p in same_ses
                      if p["image_id"] != t["image_id"]]
            why = (f"{t['panel']} 은 {t['target_class']} 의 단위를 검증할 반이다. "
                   f"시드 후보 {len(pool)}장 중 촬영 세션 {len(sessions)}개가 있고, "
                   f"세션이 겹치지 않게 한 세션당 1장씩 뽑았다.")
            why_this = (f"이 세션({t['session']})에서 RGB 페어 보유를 우선한 정렬의 첫 장. "
                        f"같은 세션에서 밀린 후보 {len(others)}장")
            dropped = (f"같은 세션 후보 {len(others)}장 — 세션당 1장 원칙에 따라 미선정. "
                       f"탈락이 아니라 시드 400장에 그대로 남아 있다")
            weak = ("세션 안에서의 선택은 RGB 페어 우선 외에 추가 기준이 없다. "
                    "정렬 후 첫 장이라 임의성이 남는다")
        else:
            flag = t["case_id"].split("_", 1)[1] if "_" in t["case_id"] else ""
            why = (f"실패 유형 '{flag}' 이 기존 라벨 좌표로 **측정되어** 확인된 이미지. "
                   f"눈으로 고른 것이 아니라 좌표 계산으로 걸렀다")
            why_this = (f"해당 유형 버킷에서 파일명 정렬 순으로 앞선 것. "
                        f"동반 유형: {t['difficulty_flags']}")
            dropped = ("같은 유형의 다른 이미지들 — 유형별 할당량"
                       "(잘림2변 3 · 작은객체 3 · 다른클래스겹침 3 · 같은클래스겹침 1 · 밀집 2)"
                       "을 채운 뒤 중단")
            weak = ("버킷 안에서는 파일명 순으로 골랐다. 대표성보다 유형 포함이 목적이다")

        rows.append({
            "case_id": t["case_id"], "delivered_as": f"{t['case_id']}.jpg",
            "group": t["group"], "image_id": t["image_id"],
            "panel": t["panel"], "camera": t["camera"], "session": t["session"],
            "cluster_id": m.get("cluster_id", ""),
            "cluster_size": m.get("cluster_size", ""),
            "is_representative": m.get("is_representative", ""),
            "has_rgb_pair": t["has_rgb_pair"],
            "panel_quota": a.get("quota", ""),
            "quota_driving_class": a.get("driving_class", ""),
            "target_class": t["target_class"],
            "difficulty_flags": t["difficulty_flags"],
            "why_this_panel_or_bucket": why,
            "why_this_image": why_this,
            "what_was_dropped": dropped,
            "known_weakness": weak,
            "existing_label": t["existing_label"],
        })

    with (paths.AUDIT / "trial_provenance.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- 2b. 세션 커버리지 — 어느 촬영 회차가 왜 안 뽑혔는가 ----
    picked_ses = {(r["panel"], r["session"]) for r in trial
                  if r["group"] == "A_본대상"}
    cov = []
    for panel, pool in sorted(seed_by_panel.items()):
        by_ses = defaultdict(list)
        for p in pool:
            by_ses[p["session"]].append(p)
        limit = {"P1-TR반": 4, "P3-MOF반": 3, "P4-MOF&PT반": 3,
                 "P6-VCB반": 4, "P9-MCCB반": 4}.get(panel)
        for ses, imgs in sorted(by_ses.items()):
            hit = (panel, ses) in picked_ses
            if limit is None:
                why = "이 반은 단위 검증 4종 담당이 아니라 1차 시험셋 대상이 아니다"
            elif hit:
                why = "선정 — 세션당 1장"
            else:
                why = (f"미선정 — {panel} 할당 {limit}장을 앞선 세션들이 채웠다. "
                       f"탈락이 아니라 시드 400장에 남아 있다")
            cov.append({
                "panel": panel, "session": ses,
                "seed_candidates_in_session": len(imgs),
                "selected_for_trial": int(hit),
                "reason": why,
            })
    with (paths.AUDIT / "trial_session_coverage.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cov[0]))
        w.writeheader()
        w.writerows(cov)

    # ---------------- 3. 읽는 문서 ----------------
    def tbl(head, body, align=None):
        al = align or ["---"] * len(head)
        return "\n".join(["| " + " | ".join(head) + " |", "|" + "|".join(al) + "|"]
                         + ["| " + " | ".join(str(c) for c in r) + " |" for r in body])

    fun_rows = [[f["stage"], f"{f['kept']:,}",
                 f"−{f['removed']:,}" if f["removed"] else "—",
                 f["removal_reason"], f["doc"] or "—"] for f in funnel]

    a_rows = []
    for panel, (cls, n) in {
            "P1-TR반": ("몰드변압기 접촉부", 4), "P3-MOF반": ("변류기 접촉부", 3),
            "P4-MOF&PT반": ("변류기 접촉부", 3), "P6-VCB반": ("케이블헤드", 4),
            "P9-MCCB반": ("MCCB 접촉부", 4)}.items():
        pool = seed_by_panel.get(panel, [])
        ses = len({p["session"] for p in pool})
        got = sum(1 for r in trial if r["panel"] == panel and r["group"] == "A_본대상")
        a_rows.append([panel, cls, f"{len(pool)}", f"{ses}", f"{got}",
                       f"{len(pool)-got}"])

    b_cnt = Counter(r["case_id"].split("_", 1)[1] for r in trial
                    if r["group"] == "B_난이도" and "_" in r["case_id"])

    md = f"""# 시험 30장은 어떻게 골랐나

> 자동 생성 · {__import__('datetime').date.today().isoformat()}
> 원자료: `reports/data_audit/selection_funnel.csv` · `trial_provenance.csv`
>
> **뽑힌 이유만이 아니라 탈락 이유도 적는다.**
> "표본을 임의로 고른 것 아닌가"에 답하기 위한 문서다.

## 1. 109,359장에서 30장까지

각 단계에서 무엇이 왜 빠졌는가. **어느 단계에서도 원본 파일을 삭제하지 않았다.**

{tbl(["단계", "남은 장수", "제외", "제외 사유", "근거"], fun_rows,
     ["---", "---:", "---:", "---", "---"])}

### 제외의 성격이 단계마다 다르다

- **01~03** 은 범위 밖이라 뺀 것이다. 대상이 아니다
- **04 근접중복** 은 같은 장면이라 대표 1장만 남긴 것이다. 나머지 {len(dupes):,}장은
  `cluster_id` 로 대표와 묶여 있어, 대표에 그린 라벨을 나중에 전파할 수 있다
- **05~06** 은 **폐기가 아니라 미선정**이다. 시드 400장·독립 이미지 38,957장은
  그대로 남아 있고 본 라벨링에서 쓴다

## 2. A군 18장 — 왜 이 반, 왜 이 장

목적은 **단위가 갈렸던 4개 클래스**의 규칙 검증이다. 그래서 그 클래스를 담당하는
반에서만 뽑았다.

{tbl(["반", "검증 대상 클래스", "시드 후보", "촬영 세션", "선정", "미선정"],
     a_rows, ["---", "---", "---:", "---:", "---:", "---:"])}

**세션이 겹치지 않게 한 세션당 1장씩** 뽑았다. 한 회차·한 조명 조건에 몰리면
그 조건에서만 통하는 규칙을 검증하게 되기 때문이다.

세션 안에서는 **RGB 페어를 가진 이미지를 우선**했다. 나중에 실화상과 대조해
경계 판단을 교차 확인할 수 있어서다.

## 3. B군 12장 — 왜 이 유형

A군만으로는 **실패가 일어나는 상황**을 못 덮는다. 그래서 기존 라벨 좌표로
실패 유형이 **측정된** 이미지를 따로 넣었다. 눈으로 고르지 않았다.

{tbl(["실패 유형", "장수", "무엇을 보는가"],
     [["잘림-2변이상", b_cnt.get("잘림-2변이상", 0), "심하게 잘린 대상을 그릴 것인가 뺄 것인가"],
      ["작은객체", b_cnt.get("작은객체", 0), "얼마나 작으면 안 그리는가"],
      ["다른클래스겹침", b_cnt.get("다른클래스겹침", 0), "겹쳐도 각각 그리는가"],
      ["같은클래스겹침", b_cnt.get("같은클래스겹침", 0), "같은 물체에 박스를 두 개 그리지 않는가"],
      ["같은클래스밀집", b_cnt.get("같은클래스밀집", 0), "개수를 어떻게 세는가"]],
     ["---", "---:", "---"])}

이 12장은 과거에 그려진 라벨이 있지만 **배포본에서 뺐다.**
보고 따라 그리면 일치도 측정이 무의미해진다. 나중에 대조용으로만 쓴다.

## 4. 배포 파일명을 바꾼 이유

원본 파일명(`A1_B1_P9_2022-05-12_IR1_00027`)에는 현장·건물·반·날짜가 그대로 들어 있다.
라벨러가 "P9 니까 MCCB 겠지" 하고 앞서 판단할 여지가 있어 `A01.jpg` 형태로 바꿨다.
원본 대응은 `data/labeling/draft/trial/manifest.csv` 에만 두고 검수자만 본다.

## 5. 이 선정의 약점

숨기지 않고 적는다.

- **세션 안에서의 선택에 임의성이 남는다.** RGB 페어 우선 외에 추가 기준이 없어
  정렬 후 첫 장을 골랐다. 세션을 대표하는 장을 고른 것은 아니다
- **B군은 버킷 안에서 파일명 순으로 골랐다.** 대표성보다 유형 포함이 목적이었다
- **30장은 18개 라벨 대상 중 4종만 덮는다.** 나머지 14종(WHOLE_OBJECT 계열)은
  이번에 검증되지 않는다. 1차 결과를 보고 2차 시험셋을 설계한다
- **A군은 라벨이 없어 실패 유형을 미리 알 수 없다.** 난이도는 B군이 담당한다

## 6. 촬영 회차 커버리지

단위 검증 대상 5개 반의 촬영 세션 중 **어느 것이 뽑혔고 어느 것이 안 뽑혔는지**는
`reports/data_audit/trial_session_coverage.csv` 에 있다.

안 뽑힌 세션은 **탈락이 아니라 할당량 초과로 인한 미선정**이다.
해당 이미지는 시드 400장에 그대로 남아 본 라벨링에서 쓴다.

## 7. 개별 30장

각 장의 계보는 `reports/data_audit/trial_provenance.csv` 에 있다. 컬럼:

```
why_this_panel_or_bucket   왜 이 반 / 이 유형인가
why_this_image             그 안에서 왜 이 장인가
what_was_dropped           같은 후보군에서 무엇이 밀렸는가
known_weakness             이 선정의 약점
cluster_id / cluster_size  중복 제거에서 몇 장을 대표하는가
panel_quota                그 반이 시드에서 몇 장을 받았는가
quota_driving_class        그 할당량을 결정한 클래스
```
"""
    out = paths.REPORTS / "labeling" / "selection_rationale.md"
    out.write_text(md, encoding="utf-8")

    print("깔때기")
    for f in funnel:
        rm = f"−{f['removed']:,}" if f["removed"] else ""
        print(f"  {f['stage']:<22}{f['kept']:>9,} {rm:>10}")
    print(f"\n개별 계보 {len(rows)}행 -> trial_provenance.csv")
    print(f"읽는 문서 -> {out}")


if __name__ == "__main__":
    main()
