"""반별 부품 식별 참조 카드를 만든다 — 라벨러의 설비 지식 부족을 메우기 위한 자료.

라벨러가 전기설비 전문가가 아니면 열화상에서 변압기와 변류기를 구분할 수 없다.
경계 규칙을 아무리 정교하게 써도 **"무슨 부품인지 모르는" 문제는 규칙으로 못 푼다.**

메우는 방법 두 가지를 자료로 만든다.

  1. 가이드 v2 의 반별 전경 사진 — 색상 박스로 어느 것이 무슨 부품인지 표시되어 있다.
     이것이 이 프로젝트가 가진 유일한 공식 식별 근거다.
  2. 같은 장면의 실화상(RGB) — 부품 각인·색상이 보여 열화상보다 판단이 쉽다.

**가이드 HTML 은 읽기만 한다.** 이미지는 이미 추출해 둔 것을 반별로 묶기만 한다.

출력: reports/labeling/class_reference/<반>.md   반별 카드
      reports/labeling/class_reference/images/   참조 이미지 사본
"""

import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

GUIDE_IMG = (paths.PROJECT / "experiments" / "seed_selection" / "guide_images")
OUT = paths.REPORTS / "labeling" / "class_reference"

# 가이드 이미지 파일명 앞 두 자리 -> 어느 반의 어떤 자료인가.
# 캡션에 이미 반과 색상이 적혀 있어 그대로 옮긴다 (해석을 더하지 않는다).
GUIDE_MAP = {
    "P1-TR반": [
        ("03", "TR 반 전경 — 철심부(적) 에폭시 표면(녹) 몰드변압기 접촉부(주황)"),
        ("04", "TR 반 상세 — 부위별 명칭 및 소음기부착형 전력퓨즈(분홍)"),
    ],
    "P2-LBS&LA반": [
        ("05", "LBS&LA 반 전경 — LBS 1·2차측 접촉부(분홍/파랑) · LA(녹)"),
        ("06", "LBS 구조 상세 — 1차측(분홍) 2차측(파랑) 접촉부 위치"),
    ],
    "P3-MOF반": [
        ("07", "MOF&PT 반 전경 — 변압기 접촉부(분홍) / 변류기 접촉부(파랑)"),
    ],
    "P4-MOF&PT반": [
        ("07", "MOF&PT 반 전경 — 변압기 접촉부(분홍) / 변류기 접촉부(파랑)"),
    ],
    "P5-PF&PT반": [
        ("08", "PF&PT 반 전경 — 소음기부착형 전력퓨즈(주황) / 몰드타입 PT(적) / 분기 접촉부(청록)"),
        ("09", "라벨링 예시 화면 — 전력용 퓨즈(적) / PT(녹)"),
    ],
    "P6-VCB반": [
        ("10", "VCB 반 전경 — VCB 접촉부(주황) / 케이블헤드(적)"),
        ("11", "신규 참고 사진 — CT 3조 배치"),
        ("12", "CT(변류기) 참고 — 계기 표시창이 달린 적갈색 몰드형"),
        ("13", "SA(서지흡수기) 참고 — 백색 애자형 원통, 대·소 3개 1조"),
        ("14", "라벨링 예시 화면 — 케이블헤드"),
    ],
    "P7-VCB&CT반": [
        ("17", "VCB&CT 반 전경 — CT(녹) / CT 접촉부(파랑) / VCB 접촉부(주황)"),
        ("12", "CT(변류기) 참고 — 계기 표시창이 달린 적갈색 몰드형"),
    ],
    "P8-ACB반": [
        ("18", "ACB&MCCB 반 전경 — ACB 접촉부(적/파랑) / MCCB(녹) / 콘덴서(주황)"),
    ],
    "P9-MCCB반": [
        ("18", "ACB&MCCB 반 전경 — ACB 접촉부(적/파랑) / MCCB(녹) / 콘덴서(주황)"),
    ],
    "P10-ACB&MCCB반": [
        ("18", "ACB&MCCB 반 전경 — ACB 접촉부(적/파랑) / MCCB(녹) / 콘덴서(주황)"),
    ],
}


def guide_files():
    return {p.name[:2]: p for p in GUIDE_IMG.glob("*.jpg")}


def rgb_samples(panel_id, limit=3):
    """그 반의 RGB 페어 표본. 실화상은 부품 각인·색상이 보여 식별이 쉽다."""
    out = []
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "RGB" and r["panel_id"] == panel_id:
                out.append(r["rel_path"])
                if len(out) >= limit * 8:
                    break
    # 촬영일이 겹치지 않게 고른다
    seen, picked = set(), []
    for rel in out:
        day = Path(rel).name.split("_")[3] if len(Path(rel).name.split("_")) > 3 else ""
        if day in seen:
            continue
        seen.add(day)
        picked.append(rel)
        if len(picked) >= limit:
            break
    return picked


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    imgdir = OUT / "images"
    imgdir.mkdir(parents=True, exist_ok=True)
    gf = guide_files()

    for panel, refs in GUIDE_MAP.items():
        pid = panel.split("-")[0]
        cands = [c for c in v2.labelable(panel) if v2.unit_confirmed(c)]
        held = [c for c in v2.labelable(panel) if not v2.unit_confirmed(c)]

        lines = [f"# {panel} — 부품 식별 참조", "",
                 "> 이 카드는 **무엇을 그릴지 정하기 전에 무엇인지 알아보기 위한** 자료다.",
                 "> 경계 규칙은 지침서를 보고, 여기서는 부품 종류만 확인한다.", ""]

        lines += [f"## 이 반에서 그리는 것 — {len(cands)}종", ""]
        for c in cands:
            cls = v2.BY_NAME[c]
            desc = cls.description or cls.notes or ""
            unit = v2.UNIT_DESC[v2.annotation_unit(c)]
            lines.append(f"- **{cls.canonical_name}** (#{cls.guide_no:02d}) — 세는 단위: {unit}"
                         + (f"  \n  {desc}" if desc else ""))
        if held:
            lines += ["", "### 이번에 그리지 않는 것", ""]
            for c in held:
                lines.append(f"- {v2.BY_NAME[c].canonical_name} — 세는 단위 미확정")

        lines += ["", "## 그리지 않는 것 (전 반 공통)", "",
                  "- 부스바 — 길게 뻗은 도체 막대",
                  "- 케이블 — 전선 자체 (**케이블헤드와 다르다**)",
                  "- ACB 접촉부", ""]

        lines += ["## 가이드 참조 사진", "",
                  "색상 박스가 어느 것이 무슨 부품인지 알려준다. "
                  "**이 프로젝트의 공식 식별 근거다.**", ""]
        for num, cap in refs:
            src = gf.get(num)
            if not src:
                continue
            dst = imgdir / f"guide_{num}{src.suffix}"
            if not dst.exists():
                shutil.copy2(src, dst)
            lines.append(f"### {cap}")
            lines.append(f"![{cap}](images/{dst.name})")
            lines.append("")

        rgbs = rgb_samples(pid)
        if rgbs:
            lines += ["## 같은 반의 실화상 표본", "",
                      "열화상은 색과 각인이 사라져 판단이 어렵다. "
                      "같은 반을 실화상으로 보면 부품 형태를 익히기 쉽다.", ""]
            for i, rel in enumerate(rgbs, 1):
                dst = imgdir / f"{pid}_rgb_{i}.jpg"
                if not dst.exists():
                    shutil.copy2(paths.PROCESSED / rel, dst)
                lines.append(f"![{pid} 실화상 {i}](images/{dst.name})")
            lines.append("")

        lines += ["## 그래도 모르겠으면", "",
                  "**Skip 하고 `모름` 사유를 적는다.** 추측해서 그리지 않는다.",
                  "지식이 없어서 못 그린 것과 규칙이 애매해서 못 그린 것은 "
                  "고치는 방법이 다르므로, 사유를 나눠 적어야 한다.", ""]

        (OUT / f"{panel}.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"{panel:<16}참조 {len(refs)}장 · 실화상 {len(rgbs)}장 · 그리는 것 {len(cands)}종")

    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
