"""시험 라벨링 30장을 라벨러 작업 폴더로 내보낸다.

**기존 라벨을 함께 내보내지 않는다.** B군 12장은 정본/참고 라벨을 이미 갖고 있지만,
라벨러가 그것을 보면 그대로 따라 그리게 되어 일치도 측정이 무의미해진다.
이 스크립트는 **이미지만** 복사하고, 라벨 파일이 섞여 들어가지 않았는지 검사한다.

원본(`3-가공`, `pilot`)은 읽기만 한다. 30장은 라벨러에게 배포해야 하므로 복사한다
(DEC-002 의 '원본 미이동' 은 106,685장 전체를 옮기지 않는다는 뜻이며,
 작업용 소량 복사는 그 취지에 어긋나지 않는다).

라벨러가 전기설비 전문가가 아니면 열화상만으로는 부품을 식별할 수 없다. 그래서
**같은 장면의 실화상(RGB)이 있으면 함께 내보낸다.** 박스는 열화상에 그리되, 무엇인지
헷갈릴 때 실화상을 참고한다. RGB 는 320x240 으로 열화상 화각에 정합되어 있다.

출력: data/labeling/draft/trial/images/*.jpg      라벨러 배포용 (열화상)
      data/labeling/draft/trial/reference_rgb/    같은 장면 실화상 (있는 것만)
      data/labeling/draft/trial/manifest.csv      무엇을 왜 넣었는지
      data/labeling/draft/trial/classes.txt       라벨링 툴용 클래스 목록
      data/labeling/draft/trial/skip_log.csv      Skip 사유 기록 서식
      data/labeling/draft/trial/annotator_*/       라벨러별 작업 폴더
                     yolo/                         YOLO 1.1 txt 회수 자리
                     cvat/                         CVAT XML 회수 자리 (속성 보존)
                     skip_log.csv                  Skip 사유 (개인용)
                     time_log.csv                  작업시간 기록 (개인용)
"""

import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
IMAGES = TRIAL / "images"
RGBDIR = TRIAL / "reference_rgb"

# Skip 사유는 나눠서 받는다. 고치는 방법이 다르기 때문이다.
#   rule_unclear  규칙이 애매하다        -> 규칙을 고친다
#   not_visible   가려지거나 잘려 안 보인다 -> 규칙대로 Skip 이 정답이다
#   unknown_part  무슨 부품인지 모르겠다   -> 참조 카드·교육을 보강한다
SKIP_REASONS = ["rule_unclear", "not_visible", "unknown_part", "other"]

ANNOTATORS = ["annotator_A", "annotator_B", "annotator_C", "annotator_D", "annotator_E"]

# 작업시간을 함께 받는다. 목적은 라벨러 평가가 아니라 **본 작업 물량 산정**이다.
# 30장에 걸린 시간을 모르면 400장·38,957장의 소요를 추정할 근거가 없다.
# 그래서 "빨리"가 아니라 "실제로 걸린 시간"을 적게 한다. 중간에 쉬면 줄을 나눠 적는다.
TIME_LOG_HEADER = ["annotator", "date", "start", "end", "minutes",
                   "cases_done", "note"]


_INDEX = None


def _build_index():
    """image_id(stem) -> 3-가공 실제 경로. 정본 소스는 rel_path 가 비어 있어 필요하다."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    _INDEX = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] != "IR":
                continue
            _INDEX[Path(r["rel_path"]).stem] = paths.PROCESSED / r["rel_path"]
    return _INDEX


def make_annotator_packets():
    """라벨러별 작업 폴더와 기록 서식을 만든다. **이미 있는 파일은 건드리지 않는다.**

    작업 중인 사람의 기록을 덮어쓰면 되돌릴 수 없으므로 항상 존재 확인이 먼저다.
    """
    made, kept = [], []
    for who in ANNOTATORS:
        d = TRIAL / who
        d.mkdir(parents=True, exist_ok=True)
        # 회수는 두 포맷이다 (DEC-020). 폴더를 미리 갈라 둬야 섞이지 않는다.
        #   yolo/  YOLO 1.1 txt  — 일치도(개수·mIoU·Kappa)의 primary input
        #   cvat/  annotations.xml — 속성(truncated/occluded/ignore·촬영유형) 보존용
        # agreement.py 는 폴더를 rglob 하므로 yolo/ 안에 있어도 그대로 읽는다.
        for sub in ("yolo", "cvat"):
            (d / sub).mkdir(exist_ok=True)

        skip = d / "skip_log.csv"
        if skip.exists():
            kept.append(skip)
        else:
            with skip.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["annotator", "case_id", "scope", "skip_reason",
                            "class_if_known", "note"])
                w.writerow([f"# 이 파일은 {who} 님 것입니다. "
                            f"annotator 칸에 {who} 이라고 적으세요", "", "", "", "", ""])
                w.writerow(["# 아래 예시 다음 줄부터 한 줄씩 추가하세요. "
                            "# 로 시작하는 줄은 무시됩니다", "", "", "", "", ""])
                w.writerow(["# scope       image = 이 장 전체를 못 하겠다 / "
                            "object = 일부만 못 하겠다", "", "", "", "", ""])
                w.writerow(["# skip_reason " + " · ".join(SKIP_REASONS),
                            "", "", "", "", ""])
                w.writerow(["# 예시", who, "object", "unknown_part", "",
                            "왼쪽 원통이 변압기인지 PT인지 모르겠음"])
            made.append(skip)

        tlog = d / "time_log.csv"
        if tlog.exists():
            kept.append(tlog)
        else:
            n = len(TIME_LOG_HEADER)
            def row(*cells):
                return list(cells) + [""] * (n - len(cells))
            with tlog.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(TIME_LOG_HEADER)
                w.writerow(row(f"# 이 파일은 {who} 님 것입니다"))
                w.writerow(row("# 실제로 걸린 시간을 적습니다. 빨리 하라는 뜻이 아닙니다."))
                w.writerow(row("# 본 작업(400장) 소요를 추정할 근거가 이것뿐입니다."))
                w.writerow(row("# 중간에 쉬었으면 줄을 나눠 적으세요. 쉰 시간은 빼고 적습니다."))
                w.writerow(row("# start/end 는 HH:MM. minutes 를 직접 적으면 그 값을 씁니다."))
                w.writerow(row("# cases_done 은 그 구간에 끝낸 장수 (예: A01-A09 면 9)"))
                w.writerow(row("# 예시", "2026-08-28", "14:00", "14:35", "", "9",
                               "처음이라 지침서를 자주 봄"))
            made.append(tlog)
    return made, kept


def source_path(row):
    """rel_path 는 출처에 따라 3-가공 기준이거나 pilot 기준이거나 비어 있다."""
    rel = row["rel_path"]
    if rel:
        for base in ((paths.PROCESSED, paths.PILOT)
                     if row["source"].startswith("3-가공")
                     else (paths.PILOT, paths.PROCESSED)):
            p = base / rel
            if p.exists():
                return p
    # 정본(P1/P3/P4) 은 라벨만 4-라벨링 에 있고 이미지는 3-가공 에 있다.
    stem = Path(row["image_id"]).name
    p = _build_index().get(stem)
    return p if p and p.exists() else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    src_csv = paths.LABELING / "seed" / "trial_set.csv"
    with src_csv.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    IMAGES.mkdir(parents=True, exist_ok=True)
    RGBDIR.mkdir(parents=True, exist_ok=True)

    # 같은 장면의 실화상 찾기용 색인
    rgb_of = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "RGB":
                rgb_of[r["pair_id"]] = paths.PROCESSED / r["rel_path"]

    manifest, missing, n_rgb = [], [], 0
    for r in rows:
        p = source_path(r)
        if p is None:
            missing.append(r["case_id"])
            continue
        # 파일명을 case_id 로 바꿔 배포한다. 원본 파일명에 반·세션이 드러나
        # 라벨러가 "이 반이니 이 클래스겠지" 하고 앞서 판단하는 것을 줄인다.
        dst = IMAGES / f"{r['case_id']}.jpg"
        shutil.copy2(p, dst)

        # 같은 장면의 실화상이 있으면 함께 내보낸다 (식별 참고용)
        stem = Path(r["image_id"]).name
        pair_key = f"{r['panel_id']}/{stem}"
        rgb_src = rgb_of.get(pair_key)
        rgb_name = ""
        if rgb_src and rgb_src.exists():
            rgb_dst = RGBDIR / f"{r['case_id']}_rgb.jpg"
            shutil.copy2(rgb_src, rgb_dst)
            rgb_name = rgb_dst.name
            n_rgb += 1

        manifest.append({
            "case_id": r["case_id"], "group": r["group"],
            "delivered_as": dst.name,
            "original_image_id": r["image_id"],
            "panel": r["panel"], "camera": r["camera"],
            "source": r["source"],
            "target_class_for_review": r["target_class"],
            "difficulty_flags": r["difficulty_flags"],
            "existing_label": r["existing_label"],
            "reference_rgb": rgb_name or "없음",
            "selection_reason": r["reason"],
            "provenance": "reports/data_audit/trial_provenance.csv 의 같은 case_id 행",
        })

    with (TRIAL / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)

    # 라벨링 툴용 클래스 목록 — 단위가 확정된 것만. YOLO id 순서를 지킨다.
    names = []
    for c in sorted(v2.CLASSES, key=lambda x: x.class_id):
        if not v2.is_labelable(c.class_name) or not v2.unit_confirmed(c.class_name):
            names.append(f"__사용안함_{c.class_id}")
        else:
            names.append(c.canonical_name)
    (TRIAL / "classes.txt").write_text("\n".join(names) + "\n", encoding="utf-8")

    # ---- Skip 사유 기록 서식 ----
    skip_log = TRIAL / "skip_log.csv"
    if not skip_log.exists():
        with skip_log.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["annotator", "case_id", "scope", "skip_reason",
                        "class_if_known", "note"])
            w.writerow(["# scope: image = 이 장 전체를 못 하겠다(비교에서 제외) / "
                        "object = 일부만 못 하겠다(나머지는 그대로 비교)",
                        "", "", "", "", ""])
            w.writerow(["# skip_reason: " + " / ".join(SKIP_REASONS), "", "", "", "", ""])
            w.writerow(["# rule_unclear=규칙이 애매 · not_visible=안 보임 · "
                        "unknown_part=무슨 부품인지 모름 · other=그 밖", "", "", "", "", ""])
            w.writerow(["# 예", "A08", "object", "unknown_part", "",
                        "왼쪽 원통이 변압기인지 PT인지 모르겠음"])

    # ---- 라벨러별 작업 폴더 ----
    made, kept = make_annotator_packets()

    # ---- 라벨 유출 검사 ----
    leaked = [p.name for p in IMAGES.rglob("*")
              if p.is_file() and p.suffix.lower() in {".txt", ".xml", ".json"}]
    print(f"이미지 {len(manifest)}장 -> {IMAGES}")
    if missing:
        print(f"  [경고] 원본을 못 찾은 항목 {len(missing)}: {missing}")
    leaked += [p.name for p in RGBDIR.rglob("*")
               if p.is_file() and p.suffix.lower() in {".txt", ".xml", ".json"}]
    print(f"  라벨 파일 유출 검사: {'실패 — ' + str(leaked) if leaked else '통과 (0건)'}")
    print(f"  식별 참고용 실화상: {n_rgb}/{len(manifest)}장 -> reference_rgb/")

    a = sum(1 for m in manifest if m["group"] == "A_본대상")
    b = len(manifest) - a
    withlabel = sum(1 for m in manifest if m["existing_label"] != "없음")
    print(f"\n  A 본대상 {a}장 (기존 라벨 없음)")
    print(f"  B 난이도 {b}장 (기존 라벨 {withlabel}장 — **배포본에 포함하지 않음**)")
    print(f"\n  라벨링 툴 클래스 목록 -> classes.txt "
          f"({sum(1 for n in names if not n.startswith('__'))}종 사용)")
    print(f"  매니페스트 -> manifest.csv  (원본 파일명·정답 여부는 검수자만 본다)")
    print(f"  Skip 사유 서식 -> skip_log.csv (rule_unclear / not_visible / unknown_part)")
    print(f"  라벨러 작업 폴더 {len(ANNOTATORS)}개 -> annotator_*/ "
          f"(새로 만든 서식 {len(made)} · 기존 보존 {len(kept)})")
    print(f"  작업시간 서식 -> annotator_*/time_log.csv (본 작업 물량 산정용)")
    print(f"  회수 자리 -> annotator_*/yolo/ (일치도용) · annotator_*/cvat/ (속성 보존용)")
    print(f"  선정 계보  -> reports/labeling/selection_rationale.md")
    print(f"  식별 참조 카드 -> reports/labeling/class_reference/")


if __name__ == "__main__":
    main()
