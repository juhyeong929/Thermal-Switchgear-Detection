"""400장 시드 라벨링 배포본을 만든다. **반별로 나눠서** 내보낸다.

시험 30장(`trial_set_export.py`)과 무엇이 다른가
------------------------------------------------
시험은 파일명을 `case_id` 로 바꿔 **반을 감췄다.** 라벨러가 "이 반이니 이 클래스겠지"
하고 앞서 판단하는 것을 막으려는 의도였다. 그런데 지침서 §1 은 "자기 반 목록에 없는
클래스는 그리지 않습니다" 를 가장 강한 규칙으로 두므로, 반을 감추면 **그 규칙을 지킬
수단이 없어진다.** 4명 전원이 후보 밖 클래스를 그렸다(A 3 · B 23 · C 3 · D 7).

그래서 본작업은 반대로 간다 (A-1 · NQ-15 판정).

    반을 공개한다 · 반별 폴더로 나눈다 · 반별 CVAT task 에 그 반 라벨만 넣는다

본작업에서 라벨러는 당연히 자기 반을 안다. 실제 운영 조건을 맞추는 것이지
문제를 쉽게 만드는 것이 아니다.

무엇을 내보내지 않는가
----------------------
**기존 라벨을 함께 내보내지 않는다.** 정본·참고 라벨이 있는 장이 섞여 있지만
라벨러가 그것을 보면 따라 그리게 된다. 이미지만 복사하고, 라벨 파일이 섞여
들어가지 않았는지 끝에서 검사한다.

출력
    data/labeling/seed/deploy/
        images/<PID>/<원본이름>.jpg          400장 (반별)
        reference_rgb/<PID>/..._rgb.jpg      같은 장면 실화상 (있는 것만)
        cvat_labels/<PID>.json               반별 CVAT 라벨 정의
        classes.txt                          회수 class_id 복원 기준 (28줄)
        manifest.csv                         400행 — 반·카메라·클러스터·대상 클래스
        panels.csv                           반별 요약 (task 이름 · 장수 · 배포 클래스)
"""

import argparse
import csv
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

SEED = paths.LABELING / "seed"
OUT = SEED / "deploy"
GEN = paths.REPORTS / "labeling" / "generated"
LABEL_EXT = {".txt", ".xml", ".json"}

# ---------------------------------------------------------------------------
# 일치도 중복 배정 (agreement overlap subset)
#
# 2차 시험 회차를 취소했으므로(DEC-028) v2 운영조건의 C-2 를 낼 경로가 없어졌다.
# 별도 회차를 되살리는 대신 **본작업 400장 안에 50장을 두 사람에게 겹쳐 배정**해
# 실제 배포 조건 그대로 일치도를 측정한다 (DEC-029).
#
#   · 같은 사람이 두 번 그리는 것이 아니다. 두 사람이 **서로 모르게 처음부터** 그린다
#   · 단순 비례가 아니라 **반별 최소 표본 + P9 보강**으로 나눈다.
#     P3(15장)·P9(21장)은 모집단이 작아 비례로 뽑으면 2장 안팎이 되어
#     agreement 계산에 들어가지 못한다
#   · 이 50장은 별도 작업이 아니다. 400장 배포 안에 들어 있고 manifest 로만 구분된다
# ---------------------------------------------------------------------------
OVERLAP_QUOTA = {
    "P1-TR반": 5, "P2-LBS&LA반": 5, "P3-MOF반": 4, "P4-MOF&PT반": 5,
    "P5-PF&PT반": 5, "P6-VCB반": 5, "P7-VCB&CT반": 5, "P8-ACB반": 5,
    "P9-MCCB반": 6, "P10-ACB&MCCB반": 5,
}
OVERLAP_TOTAL = sum(OVERLAP_QUOTA.values())          # 50


def pick_overlap(rs, n):
    """한 반에서 겹쳐 배정할 n장을 고른다. **무작위가 아니라 재현 가능하게** 뽑는다.

    세션(촬영 회차)이 한쪽에 몰리면 같은 장면만 두 번 보게 되어 일치도가 부풀려진다.
    세션·이미지 순으로 정렬한 뒤 균등 간격으로 집어 세션을 가로지르게 한다.
    같은 입력이면 언제 돌려도 같은 50장이 나온다.
    """
    ordered = sorted(rs, key=lambda r: (r["session"], r["image_id"]))
    if n >= len(ordered):
        return {r["image_id"] for r in ordered}
    step = len(ordered) / n
    return {ordered[int(i * step)]["image_id"] for i in range(n)}


def rgb_index():
    """pair_id -> 실화상 경로. 열화상만으로 부품을 못 알아볼 때 참고용이다."""
    idx = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "RGB":
                idx[r["pair_id"]] = paths.PROCESSED / r["rel_path"]
    return idx


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="복사하지 않고 계획만 본다")
    ap.add_argument("--pair", default="seed_A,seed_B",
                    help="중복 배정 50장을 맡을 두 라벨러 (쉼표로 둘). "
                         "실제 이름으로 바꿔서 배포한다")
    ap.add_argument("--no-overlap", action="store_true",
                    help="중복 배정 없이 내보낸다 (C-2 v2 근거를 포기하는 선택)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with (SEED / "seed_candidates.csv").open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    print(f"시드 후보 {len(rows)}장")

    pair = [x.strip() for x in a.pair.split(",") if x.strip()]
    if not a.no_overlap and len(pair) != 2:
        print("--pair 는 라벨러 두 명이어야 한다. 예: --pair 홍길동,김철수")
        return 1

    rgb_of = rgb_index()
    by_panel = defaultdict(list)
    for r in rows:
        by_panel[r["panel"]].append(r)

    overlap = set()
    if not a.no_overlap:
        for panel, rs in by_panel.items():
            overlap |= pick_overlap(rs, OVERLAP_QUOTA.get(panel, 0))

    manifest, missing, n_rgb = [], [], 0
    for panel, rs in sorted(by_panel.items()):
        pid = v2.panel_id(panel)
        img_dir, rgb_dir = OUT / "images" / pid, OUT / "reference_rgb" / pid
        if not a.dry_run:
            img_dir.mkdir(parents=True, exist_ok=True)
            rgb_dir.mkdir(parents=True, exist_ok=True)
        for r in rs:
            src = paths.PROCESSED / r["rel_path"]
            if not src.exists():
                missing.append(r["image_id"])
                continue
            name = Path(r["rel_path"]).name
            if not a.dry_run:
                shutil.copy2(src, img_dir / name)

            rgb_src = rgb_of.get(r["image_id"])
            rgb_name = ""
            if rgb_src and rgb_src.exists():
                rgb_name = f"{Path(name).stem}_rgb.jpg"
                if not a.dry_run:
                    shutil.copy2(rgb_src, rgb_dir / rgb_name)
                n_rgb += 1

            is_ov = r["image_id"] in overlap
            manifest.append({
                "panel": panel, "panel_id": pid,
                "delivered_as": f"images/{pid}/{name}",
                "image_id": r["image_id"], "camera": r["camera"],
                "session": r["session"], "cluster_id": r["cluster_id"],
                "target_classes": r["target_classes"],
                "reference_rgb": f"reference_rgb/{pid}/{rgb_name}" if rgb_name else "없음",
                "selection_reason": r["reason"], "priority": r["priority"],
                "panel_provisional": r["panel_provisional"],
                # --- 일치도 중복 배정 (DEC-029) ---
                "agreement_subset": OVERLAP_TOTAL if is_ov else 0,
                "overlap": "true" if is_ov else "false",
                "annotator_pair": "/".join(pair) if is_ov else "",
            })

    if missing:
        print(f"  [실패] 원본을 찾지 못한 장 {len(missing)}: {missing[:5]}")
        return 1

    # 반별 요약 — 배포 담당자가 CVAT task 를 만들 때 그대로 보는 표
    panels = []
    for panel, rs in sorted(by_panel.items(), key=lambda x: v2.PANEL_PRIORITY[x[0]]):
        pid = v2.panel_id(panel)
        dep = v2.deployable(panel)
        hold = [c for c in v2.labelable(panel) if not v2.unit_confirmed(c)]
        panels.append({
            "panel_id": pid, "panel": panel,
            "cvat_task_name": f"{pid} · {panel}",
            "images": len(rs),
            "deployable_n": len(dep),
            "deployable": " · ".join(v2.KOREAN[c] for c in dep),
            "unit_unknown_not_deployed": " · ".join(v2.KOREAN[c] for c in hold),
            "overlap_images": sum(1 for m in manifest
                                  if m["panel"] == panel and m["overlap"] == "true"),
            "labels_json": f"cvat_labels/{pid}.json",
            "provisional_panel": "Y" if panel in v2.PANEL_CLASSES_PROVISIONAL else "",
        })

    if a.dry_run:
        print("\n(dry-run — 아무것도 쓰지 않았다)")
    else:
        (OUT / "cvat_labels").mkdir(parents=True, exist_ok=True)
        for p in panels:
            shutil.copy2(GEN / "cvat_labels" / f"{p['panel_id']}.json",
                         OUT / "cvat_labels" / f"{p['panel_id']}.json")
        shutil.copy2(paths.LABELING / "draft" / "trial" / "classes.txt",
                     OUT / "classes.txt")
        subset = [m for m in manifest if m["overlap"] == "true"]
        for name, data in (("manifest.csv", manifest), ("panels.csv", panels),
                           ("agreement_subset.csv", subset)):
            if not data:
                continue
            with (OUT / name).open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(data[0]))
                w.writeheader()
                w.writerows(data)

        # 라벨이 섞여 나가면 라벨러가 그대로 따라 그린다. 마지막에 반드시 검사한다.
        stray = [p for p in (OUT / "images").rglob("*")
                 if p.is_file() and p.suffix.lower() in LABEL_EXT]
        if stray:
            print(f"  [실패] 배포본에 라벨 파일이 섞였다: {stray[:5]}")
            return 1

    print(f"\n{'반':<16}{'장수':>5}{'실화상':>7}{'배포':>5}  배포 클래스")
    for p in panels:
        n_r = sum(1 for m in manifest
                  if m["panel_id"] == p["panel_id"] and m["reference_rgb"] != "없음")
        prov = " [잠정]" if p["provisional_panel"] else ""
        print(f"{p['panel']:<16}{p['images']:>5}{n_r:>7}{p['deployable_n']:>5}  "
              f"{p['deployable']}{prov}")
        if p["unit_unknown_not_deployed"]:
            print(f"{'':<16}{'':>17}  (단위 미확정 비배포: "
                  f"{p['unit_unknown_not_deployed']})")
    print(f"\n합계 {len(manifest)}장 · 실화상 {n_rgb}장 · 반 {len(panels)}개")
    n_ov = sum(1 for m in manifest if m["overlap"] == "true")
    if n_ov:
        print(f"일치도 중복 배정 {n_ov}장 -> {pair[0]} 와 {pair[1]} 가 "
              f"**서로 모르게** 처음부터 각자 그린다 (DEC-029)")
        per = " · ".join(f"{q['panel_id']} {q['overlap_images']}" for q in panels)
        print(f"  반별: {per}")
    else:
        print("일치도 중복 배정 없음 — C-2 의 v2 조건 근거를 만들지 않는 선택이다")
    if not a.dry_run:
        print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
