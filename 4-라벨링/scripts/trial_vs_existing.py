"""시험셋 30장 중 **기존 라벨이 숨겨져 있던 장**을 꺼내 비교용 폴더로 만든다.

왜 필요한가
    라벨러 간 일치도(mIoU·Kappa)는 2명 이상부터 계산된다. 1명분만 회수된 지금
    **혼자서도 잴 수 있는 유일한 정량 지표**가 '기존 라벨과 얼마나 같은가' 다.
    시험셋 B군 12장에는 과거 라벨이 있고, 라벨러에게는 일부러 감춰 배포했다.

무엇을 만드나
    data/labeling/draft/trial/_existing/<case_id>.txt   v2 class_id 로 통일한 YOLO
    data/labeling/draft/trial/_existing/manifest.csv    무엇을 어디서 가져왔는지 · 등급

    그 폴더를 `agreement.py` 에 라벨러 폴더와 함께 주면 개수 일치·mIoU·Kappa 가 그대로 나온다.
    `agreement.py` 는 수정하지 않는다.

**기존 라벨은 정답이 아니다.** 두 가지를 반드시 함께 읽어야 한다.

    1. 등급이 섞여 있다. 정본(canonical)은 검수 계보가 파일로 확인된 것이고,
       참고(reference)는 미작업 의심분·검수 이력 부재로 **승격 보류된 것**이다 (DEC-011).
       참고 등급과의 차이는 '누가 틀렸나' 가 아니다.
    2. 정본에도 규격 위반이 있다 — 같은 클래스 중복 20쌍이 격리돼 있다 (DEC-016/017).

    그래서 이 대조는 **'어디서 갈리는가'** 를 찾는 도구다. 점수가 아니다.

좌표 변환
    출처마다 class_id 체계가 다르다. 정본(reviewed/)은 이미 v2 이고,
    참고(backup/)는 구 26개 스키마다. **이름이 아니라 그 폴더의 obj.names 와
    26->28 변환표로 되돌린다.** 모르는 이름이 나오면 그 박스를 버리지 않고 보고한다.

사용
    python scripts/trial_vs_existing.py
    python scripts/agreement.py <라벨러 폴더> data/labeling/draft/trial/_existing
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import classes_v1_26 as v1  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
OUT = TRIAL / "_existing"

# 정본 — 이미 v2 class_id 로 승계돼 있다 (STEP 07)
CANONICAL = {
    "P1": paths.LABELING / "reviewed" / "P1_A3검수완료",
    "P3": paths.LABELING / "reviewed" / "P3__p3",
    "P4": paths.LABELING / "reviewed" / "P4__p4",
}
# 참고 — 구 26개 스키마. 같은 폴더의 obj.names 로 되돌린다
REFERENCE = {
    "P6": paths.PROJECT / "data" / "backup" / "P6_6ban",
    "P9": paths.PROJECT / "data" / "backup" / "P9_9ban",
}


def find_label(stem, panel_id):
    """(경로, 등급, obj.names 경로|None) — 없으면 (None, ...)."""
    d = CANONICAL.get(panel_id)
    if d and d.is_dir():
        for p in d.rglob(f"{stem}.txt"):
            return p, "canonical", None
    d = REFERENCE.get(panel_id)
    if d and d.is_dir():
        for p in d.rglob(f"{stem}.txt"):
            if p.name in ("train.txt", "obj.names"):
                continue
            names = d / "obj.names"
            return p, "reference", (names if names.exists() else None)
    return None, None, None


def old_name_to_v2(name, panel_id):
    """구 스키마 이름 -> v2 class_id. 26->28 변환표를 그대로 쓴다 (DEC-003)."""
    for old_id, (key, ko) in v1.OLD_BY_ID.items():
        if ko != name:
            continue
        new_key = v1.new_id(old_id, panel_id)
        if new_key is None:
            return None, "변환표에서 제외(라벨 대상 아님)"
        c = v2.BY_ID.get(new_key) if isinstance(new_key, int) else v2.BY_NAME.get(new_key)
        return (c.class_id, "") if c else (None, "v2 클래스를 찾지 못함")
    return None, "구 스키마에 없는 이름"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    with (TRIAL / "manifest.csv").open(encoding="utf-8-sig") as fh:
        man = list(csv.DictReader(fh))

    OUT.mkdir(parents=True, exist_ok=True)
    rows, dropped = [], []
    n_box = 0

    for m in man:
        if m["existing_label"] == "없음":
            continue
        stem = Path(m["original_image_id"]).name
        panel_id = m["panel"].split("-")[0]
        src, grade, names_path = find_label(stem, panel_id)
        if src is None:
            dropped.append({"case_id": m["case_id"], "reason": "라벨 파일을 찾지 못함",
                            "detail": f"{panel_id} / {stem}"})
            continue

        old_names = None
        if names_path:
            old_names = [l.strip() for l in names_path.read_text(
                encoding="utf-8").splitlines() if l.strip()]

        out_lines, boxes_in = [], 0
        for line in src.read_text(encoding="utf-8").splitlines():
            t = line.split()
            if len(t) < 5:
                continue
            boxes_in += 1
            cid = int(float(t[0]))
            if grade == "canonical":
                new = cid                       # 이미 v2
            else:
                if cid >= len(old_names or []):
                    dropped.append({"case_id": m["case_id"],
                                    "reason": "obj.names 범위를 벗어난 class_id",
                                    "detail": str(cid)})
                    continue
                new, why = old_name_to_v2(old_names[cid], panel_id)
                if new is None:
                    dropped.append({"case_id": m["case_id"],
                                    "reason": why, "detail": old_names[cid]})
                    continue
            out_lines.append(" ".join([str(new)] + t[1:5]))

        (OUT / f"{m['case_id']}.txt").write_text(
            ("\n".join(out_lines) + "\n") if out_lines else "", encoding="utf-8")
        n_box += len(out_lines)
        rows.append({
            "case_id": m["case_id"], "grade": grade, "panel": m["panel"],
            "camera": m["camera"], "boxes_in": boxes_in, "boxes_out": len(out_lines),
            "source": str(src.relative_to(paths.PROJECT)),
            "target_class_for_review": m["target_class_for_review"],
        })

    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    if dropped:
        with (OUT / "dropped.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["case_id", "reason", "detail"])
            w.writeheader(); w.writerows(dropped)

    n_can = sum(1 for r in rows if r["grade"] == "canonical")
    print(f"기존 라벨을 가진 장 {len(rows)} · 박스 {n_box}")
    print(f"  정본(canonical) {n_can}장 · 참고(reference) {len(rows) - n_can}장")
    print(f"  {'case_id':<22}{'등급':<12}{'반':<14}{'박스':>5}")
    for r in rows:
        print(f"  {r['case_id']:<22}{r['grade']:<12}{r['panel']:<14}{r['boxes_out']:>5}")
    if dropped:
        print(f"\n  변환하지 못한 박스 {len(dropped)}건 -> dropped.csv (버리지 않고 기록한다)")
        for d in dropped[:6]:
            print(f"    {d['case_id']:<22}{d['reason']}  {d['detail']}")

    print("\n주의 — 기존 라벨은 정답이 아니다")
    print("  · 참고(reference) 등급은 검수 이력 부재로 정본 승격이 보류된 것이다 (DEC-011)")
    print("  · 정본에도 규격 위반 20쌍이 격리돼 있다 (DEC-016/017)")
    print("  · 차이는 '누가 틀렸나' 가 아니라 '어디서 갈리는가' 로 읽는다")
    print(f"\n-> {OUT}")
    print("다음: python scripts/agreement.py <라벨러 폴더> "
          f"{OUT.relative_to(paths.PROJECT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
