"""3-가공 전체를 훑어 이미지 1장 = 1행 인벤토리를 만든다.

이후 모든 집계(반별 현황·중복 분석·시드셋 선정)의 단일 출처다. 숫자를 문서에
손으로 적지 않기 위한 첫 단계이므로, 여기서 나온 CSV 를 다른 스크립트가 읽어 쓴다.

출력: data/metadata/image_inventory.csv
      reports/data_audit/filename_parse_failures.csv (파싱 실패분, 있으면)

원본은 읽기만 한다.
"""

import csv
import re
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

# A3_B4_P1_2022-07-15_IR2_08277.jpg
# A2_B1_P8_2022-07-11_IR2_1_00003.jpg  (같은 날 세션이 여러 개인 경우 IR2_1, IR2_2 ...)
PATTERN = re.compile(
    r"^(?P<site>A\d+)_(?P<building>B\d+)_(?P<panel>P\d+)_"
    r"(?P<date>\d{4}-\d{2}-\d{2})_(?P<camera>IR\d+)(?:_(?P<session>\d+))?_"
    r"(?P<seq>\d+)(?P<rgb>_rgb_image)?\.jpg$",
    re.IGNORECASE,
)

FIELDS = [
    "image_id", "panel_id", "panel_folder", "subfolder", "filename", "rel_path",
    "site", "building", "date", "camera", "session", "seq",
    "kind", "pair_id", "has_rgb_pair",
]


def scan():
    """반 폴더를 재귀로 훑는다.

    P1-TR반 은 하위에 'New Folder With Items' 를 두고 41,323장을 담고 있다.
    최상위만 보면 이 물량이 통째로 빠지므로 rglob 을 쓴다. 어느 하위 폴더에서
    왔는지는 subfolder 컬럼에 남겨 촬영 배치를 구분할 수 있게 한다.
    """
    rows, failures = [], []
    for panel in paths.PANELS:
        d = paths.panel_dir(panel)
        if not d.is_dir():
            failures.append({"panel_folder": panel, "filename": "",
                             "reason": "폴더 없음"})
            continue
        panel_id = panel.split("-")[0]
        for f in sorted(d.rglob("*")):
            if f.is_dir():
                continue
            if f.name.startswith("._"):
                # macOS AppleDouble 리소스 포크. 이미지가 아니다.
                failures.append({"panel_folder": panel, "filename": f.name,
                                 "reason": "AppleDouble(._) 부산물"})
                continue
            if f.suffix.lower() != ".jpg":
                failures.append({"panel_folder": panel, "filename": f.name,
                                 "reason": "jpg 아님"})
                continue
            m = PATTERN.match(f.name)
            if not m:
                failures.append({"panel_folder": panel, "filename": f.name,
                                 "reason": "파일명 패턴 불일치"})
                continue
            g = m.groupdict()
            is_rgb = bool(g["rgb"])
            # pair_id: IR 과 RGB 페어를 묶는 키 (접미사 뗀 stem)
            pair_id = f.stem[: -len(paths.RGB_SUFFIX)] if is_rgb else f.stem
            sub = f.parent.relative_to(d).as_posix()
            rows.append({
                "image_id": f"{panel_id}/{f.stem}",
                "panel_id": panel_id,
                "panel_folder": panel,
                "subfolder": "" if sub == "." else sub,
                "filename": f.name,
                "rel_path": f.relative_to(paths.PROCESSED).as_posix(),
                "site": g["site"], "building": g["building"],
                "date": g["date"], "camera": g["camera"],
                "session": g["session"] or "", "seq": g["seq"],
                "kind": "RGB" if is_rgb else "IR",
                "pair_id": f"{panel_id}/{pair_id}",
                "has_rgb_pair": "",
            })

    # IR 행에 페어 유무를 표시한다 (RGB 파일이 같은 pair_id 로 존재하는지).
    rgb_pairs = {r["pair_id"] for r in rows if r["kind"] == "RGB"}
    for r in rows:
        if r["kind"] == "IR":
            r["has_rgb_pair"] = "1" if r["pair_id"] in rgb_pairs else "0"
    return rows, failures


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows, failures = scan()

    paths.METADATA.mkdir(parents=True, exist_ok=True)
    out = paths.METADATA / "image_inventory.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n_ir = sum(1 for r in rows if r["kind"] == "IR")
    n_rgb = len(rows) - n_ir
    n_paired = sum(1 for r in rows if r["kind"] == "IR" and r["has_rgb_pair"] == "1")
    print(f"이미지 인벤토리 {len(rows)}행 -> {out}")
    print(f"  IR {n_ir} / RGB {n_rgb} / RGB 페어 있는 IR {n_paired}")

    if failures:
        paths.AUDIT.mkdir(parents=True, exist_ok=True)
        fout = paths.AUDIT / "filename_parse_failures.csv"
        with fout.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["panel_folder", "filename", "reason"])
            w.writeheader()
            w.writerows(failures)
        print(f"  파싱 실패 {len(failures)}건 -> {fout}")
    else:
        print("  파싱 실패 0건")


if __name__ == "__main__":
    main()
