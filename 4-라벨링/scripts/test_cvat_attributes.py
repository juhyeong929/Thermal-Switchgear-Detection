"""회수 포맷 검증 — YOLO 1.1 + CVAT XML 이중 회수가 실제로 동작하는지 8가지를 잰다.

**실제 30장과 라벨러 폴더는 건드리지 않는다.** 전부 임시 폴더의 fixture 로 돌린다.
`agreement.py` 가 보고서를 쓰는 경로만은 실제 폴더이므로, 실행 전 파일을 백업하고
끝나면 원래대로 되돌린다 (없었으면 지운다).

검사 항목
  1 YOLO export 정상 파싱            5 매칭 실패가 누락 없이 별도 보고되는가
  2 CVAT XML 정상 파싱               6 기존 agreement.py 결과가 변하지 않는가
  3 YOLO/XML bbox 매칭               7 클래스 순서가 유지되는가
  4 attributes.csv 생성              8 빈 파일과 Skip 이 구분되는가
                                     9 CVAT class_id 정규화 · 원본이 정규화본을 덮지 않는가

사용:
    python scripts/test_cvat_attributes.py
"""

import csv
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import cvat_xml_to_attributes as C  # noqa: E402
import trial_ingest as I  # noqa: E402
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    return ok


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------
CLASSES = ["철심부", "에폭시 표면", "몰드변압기 접촉부", "LBS", "__사용안함_4", "한류형 전력퓨즈"]

# A01: 박스 2개. **XML 순서를 YOLO 줄 순서와 일부러 반대로 쓴다.**
#      줄 번호를 가정하는 구현이면 여기서 틀린다.
YOLO_A01 = ["2 0.500000 0.500000 0.100000 0.200000",   # line 0
            "0 0.200000 0.300000 0.050000 0.050000"]   # line 1
# A01 에 XML 에 없는 박스 하나를 더 둔다 -> yolo_box_no_xml_match
YOLO_A01_EXTRA = "5 0.800000 0.800000 0.040000 0.040000"


def box_xml(label, cx, cy, w, h, W, H, occluded, truncated, ignore="false"):
    x0, y0 = (cx - w / 2) * W, (cy - h / 2) * H
    x1, y1 = (cx + w / 2) * W, (cy + h / 2) * H
    return (f'    <box label="{label}" occluded="{occluded}" source="manual" '
            f'xtl="{x0:.2f}" ytl="{y0:.2f}" xbr="{x1:.2f}" ybr="{y1:.2f}" z_order="0">\n'
            f'      <attribute name="truncated">{truncated}</attribute>\n'
            f'      <attribute name="ignore">{ignore}</attribute>\n'
            f'    </box>\n')


def make_xml(with_truncated=True):
    W, H = 640.0, 480.0
    meta = ("  <meta><task><labels>\n"
            "    <label><name>몰드변압기 접촉부</name><attributes>\n"
            + ("      <attribute><name>truncated</name></attribute>\n"
               if with_truncated else "")
            + "      <attribute><name>ignore</name></attribute>\n"
              "      <attribute><name>미사용속성</name></attribute>\n"
              "    </attributes></label>\n"
              "  </labels></task></meta>\n")

    def b(label, cx, cy, w, h, occ, trunc):
        s = box_xml(label, cx, cy, w, h, W, H, occ, trunc)
        if not with_truncated:
            s = "\n".join(l for l in s.splitlines()
                          if 'name="truncated"' not in l) + "\n"
        return s

    x = '<?xml version="1.0" encoding="utf-8"?>\n<annotations>\n  <version>1.1</version>\n'
    x += meta
    x += f'  <image id="0" name="images/A01.jpg" width="{W:.0f}" height="{H:.0f}">\n'
    #  YOLO 와 **반대 순서**로 적는다
    x += b("철심부", 0.2, 0.3, 0.05, 0.05, "1", "false")
    x += b("몰드변압기 접촉부", 0.5, 0.5, 0.1, 0.2, "0", "true")
    #  YOLO 에 대응이 없는 박스 -> xml_box_no_match
    x += b("LBS", 0.9, 0.1, 0.03, 0.03, "0", "false")
    x += ('    <tag label="촬영유형" source="manual">\n'
          '      <attribute name="shot_type">중거리</attribute>\n'
          '    </tag>\n')
    x += "  </image>\n"
    #  A02 는 박스 0개 (대상 없음)
    x += f'  <image id="1" name="images/A02.jpg" width="{W:.0f}" height="{H:.0f}">\n  </image>\n'
    #  A03 은 YOLO 파일이 없다 -> xml_box_no_yolo_file
    x += f'  <image id="2" name="images/A03.jpg" width="{W:.0f}" height="{H:.0f}">\n'
    x += b("철심부", 0.4, 0.4, 0.06, 0.06, "0", "false")
    x += "  </image>\n</annotations>\n"
    return x


def build_fixture(root):
    """임시 시험 폴더 한 벌. 실제 데이터는 복사하지 않는다."""
    trial = root / "trial"
    (trial).mkdir(parents=True)
    (trial / "classes.txt").write_text("\n".join(CLASSES) + "\n", encoding="utf-8")

    a = trial / "annotator_A"
    (a / "yolo").mkdir(parents=True)
    (a / "cvat").mkdir(parents=True)
    (a / "yolo" / "A01.txt").write_text(
        "\n".join(YOLO_A01 + [YOLO_A01_EXTRA]) + "\n", encoding="utf-8")
    (a / "yolo" / "A02.txt").write_text("", encoding="utf-8")          # 대상 없음
    (a / "yolo" / "A04.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    (a / "cvat" / "annotations.xml").write_text(make_xml(), encoding="utf-8")
    return trial, a


def write_skiplog(folder, who, rows):
    with (folder / "skip_log.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["annotator", "case_id", "scope", "skip_reason",
                    "class_if_known", "note"])
        w.writerow(["# 주석 줄", "", "", "", "", ""])
        for r in rows:
            w.writerow([who] + list(r))


# ---------------------------------------------------------------------------
def run_agreement(dirs):
    """agreement.py 를 실제로 돌린다.

    돌려주는 것: (종료코드, 경로 줄을 뺀 출력, 원본 출력, stderr).
    비교에는 경로를 뺀 쪽을 쓴다 — 임시 폴더 이름이 실행마다 다르기 때문이다.
    """
    r = subprocess.run([sys.executable, str(HERE / "agreement.py")] + [str(d) for d in dirs],
                       capture_output=True, text=True, encoding="utf-8")
    body = [l for l in r.stdout.splitlines() if "->" not in l]
    return r.returncode, "\n".join(body), r.stdout, r.stderr


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="trialfmt_"))

    # agreement.py 가 쓰는 실제 보고서 파일을 미리 백업한다
    today = date.today().isoformat()
    guarded = [paths.REPORTS / "labeling" / f"agreement_{today}.csv",
               paths.REPORTS / "labeling" / f"trial_time_{today}.csv"]
    backup = {p: (p.read_bytes() if p.exists() else None) for p in guarded}

    try:
        trial, a = build_fixture(tmp)

        print("\n[1] YOLO export 정상 파싱")
        y = C.load_yolo(a / "yolo")
        check("파일 3개를 읽는다 (A01·A02·A04)", len(y) == 3, f"{sorted(y)}")
        check("A01 박스 3개 · 줄 번호 보존", [b[0] for b in y["A01"]] == [0, 1, 2])
        check("빈 파일도 항목으로 남는다 (대상 없음)", y["A02"] == [])
        check("좌표를 정규화 float 로 읽는다", abs(y["A01"][0][2] - 0.5) < 1e-9)

        print("\n[2] CVAT XML 정상 파싱")
        images, declared = C.parse_xml(a / "cvat" / "annotations.xml")
        check("이미지 3장", len(images) == 3, f"{[i['stem'] for i in images]}")
        check("A01 박스 3개", len(images[0]["boxes"]) == 3)
        check("내장 occluded 를 true/false 로 읽는다",
              images[0]["boxes"][0]["attrs"]["occluded"] == "true")
        check("커스텀 truncated 를 읽는다",
              images[0]["boxes"][1]["attrs"]["truncated"] == "true")
        check("이미지 태그(촬영유형)를 읽는다",
              images[0]["image_attrs"].get("shot_type") == "중거리")
        check("라벨 정의에 선언된 속성 목록을 읽는다",
              {"truncated", "ignore", "미사용속성"} <= declared, f"{sorted(declared)}")
        check("픽셀->정규화 변환이 맞다",
              all(abs(v - e) < 1e-6 for v, e in
                  zip(images[0]["boxes"][1]["norm"], (0.5, 0.5, 0.1, 0.2))))

        print("\n[3] YOLO/XML bbox 매칭 — 줄 번호를 가정하지 않는다")
        rows, bad, s = C.convert(a)
        by_id = {r["bbox_id"]: r for r in rows}
        check("XML 순서가 반대여도 올바른 YOLO 줄에 붙는다",
              by_id["A01#0"]["yolo_line"] == 1 and by_id["A01#1"]["yolo_line"] == 0,
              f"A01#0->line{by_id['A01#0']['yolo_line']} · "
              f"A01#1->line{by_id['A01#1']['yolo_line']}")
        check("동일 좌표는 exact_same_class 로 붙는다",
              all(r["match_method"] == "exact_same_class" for r in rows),
              f"{sorted({r['match_method'] for r in rows})}")
        check("class_id 는 classes.txt 줄 번호를 따른다",
              by_id["A01#1"]["class_id"] == 2 and by_id["A01#0"]["class_id"] == 0)

        print("\n[4] attributes.csv 생성")
        out = a / "attributes.csv"
        with out.open(encoding="utf-8-sig") as fh:
            got = list(csv.DictReader(fh))
        check("파일이 생겼고 행 수가 매칭 수와 같다",
              out.exists() and len(got) == len(rows) == 2, f"{len(got)}행")
        check("최소 필드가 전부 있다",
              {"image_name", "bbox_id", "class_id", "class_name",
               "attr_truncated", "attr_occluded"} <= set(got[0]))
        check("truncated 값이 보존된다",
              [r["attr_truncated"] for r in got if r["bbox_id"] == "A01#1"] == ["true"])
        check("occluded 값이 보존된다",
              [r["attr_occluded"] for r in got if r["bbox_id"] == "A01#0"] == ["true"])
        check("XML 에 실제로 있던 그 밖 속성도 열로 나온다", "attr_ignore" in got[0])
        check("선언만 되고 안 쓰인 속성은 열로 만들지 않는다",
              "attr_미사용속성" not in got[0])
        check("이미지 단위 속성이 열로 나온다",
              got[0].get("image_shot_type") == "중거리")

        # truncated 가 정의되지 않은 프로젝트에서 받은 XML
        b2 = tmp / "trial" / "annotator_B"
        (b2 / "yolo").mkdir(parents=True)
        (b2 / "cvat").mkdir(parents=True)
        (b2 / "yolo" / "A01.txt").write_text("\n".join(YOLO_A01) + "\n", encoding="utf-8")
        (b2 / "cvat" / "annotations.xml").write_text(make_xml(with_truncated=False),
                                                     encoding="utf-8")
        rows2, bad2, s2 = C.convert(b2)
        with (b2 / "attributes.csv").open(encoding="utf-8-sig") as fh:
            got2 = list(csv.DictReader(fh))
        check("없는 속성은 열은 두되 값을 만들지 않는다",
              "attr_truncated" in got2[0]
              and all(r["attr_truncated"] == "" for r in got2))
        check("없는 속성을 경고로 알린다", s2["missing_min_attrs"] == ["truncated"],
              f"{s2['missing_min_attrs']}")

        print("\n[5] 매칭 실패가 누락 없이 별도 보고되는가")
        with (a / "attributes_unmatched.csv").open(encoding="utf-8-sig") as fh:
            un = list(csv.DictReader(fh))
        reasons = sorted({r["reason"] for r in un})
        check("실패 4종이 전부 기록된다",
              reasons == ["xml_box_no_match", "xml_box_no_yolo_file",
                          "yolo_box_no_xml_match", "yolo_file_no_xml_image"],
              f"{reasons}")
        check("파일 행 수와 반환값이 같다", len(un) == len(bad) == 4, f"{len(un)}행")
        xml_total = sum(len(i["boxes"]) for i in images)
        xml_side = len(rows) + sum(1 for r in un
                                   if r["reason"].startswith("xml_box"))
        check("XML 박스가 하나도 사라지지 않는다 (매칭+실패 = 전체)",
              xml_side == xml_total, f"{xml_side} == {xml_total}")
        yolo_total = sum(len(v) for v in y.values())
        yolo_side = len(rows) + sum(1 for r in un if r["reason"].startswith("yolo_"))
        check("YOLO 박스가 하나도 사라지지 않는다", yolo_side == yolo_total,
              f"{yolo_side} == {yolo_total}")

        print("\n[6] 기존 agreement.py 결과가 변하지 않는가")
        flat = tmp / "flat"
        for who in ("annotator_A", "annotator_B"):
            (flat / who).mkdir(parents=True)
            for f in (tmp / "trial" / who / "yolo").glob("*.txt"):
                shutil.copy(f, flat / who / f.name)
        rc1, out1, _, err1 = run_agreement([flat / "annotator_A", flat / "annotator_B"])
        # 중첩 구조(yolo/ · cvat/ · attributes.csv 가 함께 있는 실제 회수 형태)
        rc2, out2, _, err2 = run_agreement([tmp / "trial" / "annotator_A",
                                            tmp / "trial" / "annotator_B"])
        check("두 구조 모두 정상 종료", rc1 == 0 and rc2 == 0, err1 or err2)
        check("yolo/ 하위 폴더 · XML · CSV 가 있어도 결과가 같다", out1 == out2)
        check("mIoU 를 실제로 계산했다", "mIoU" in out2 and "—" not in out2.split("mIoU")[1][:8],
              out2.split("mIoU")[1].splitlines()[0].strip() if "mIoU" in out2 else "")
        check("attributes.csv / xml 을 라벨로 오인하지 않는다", "attributes" not in out2)

        print("\n[7] 클래스 순서가 유지되는가 (실제 classes.txt · 읽기만 한다)")
        real = paths.LABELING / "draft" / "trial" / "classes.txt"
        names = [n.strip() for n in real.read_text(encoding="utf-8").splitlines()]
        ok_idx, mism = True, []
        for c in v2.CLASSES:
            if c.label_status == v2.EXCLUDE or not v2.unit_confirmed(c.class_name):
                continue
            if names[c.class_id] != c.canonical_name:
                ok_idx = False
                mism.append(f"{c.class_id}:{names[c.class_id]}!={c.canonical_name}")
        check("classes.txt 줄 번호 == v2 class_id", ok_idx, "; ".join(mism))
        ph = [i for i, n in enumerate(names) if n.startswith("__사용안함")]
        check("자리표시자가 그대로 있다 (지우면 뒤 번호가 밀린다)", len(ph) > 0,
              f"{len(ph)}개 · id {ph}")
        check("줄 수 == v2 클래스 수", len(names) == len(v2.CLASSES),
              f"{len(names)} == {len(v2.CLASSES)}")

        print("\n[8] 빈 파일과 Skip 이 구분되는가")
        sk = tmp / "skiptest"
        for who in ("annotator_A", "annotator_B"):
            d = sk / who
            d.mkdir(parents=True)
            (d / "A01.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
            (d / "A02.txt").write_text("", encoding="utf-8")        # 대상 없음
            (d / "A03.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
        write_skiplog(sk / "annotator_A", "annotator_A",
                      [["A03", "image", "rule_unclear", "", "규칙이 애매"]])
        write_skiplog(sk / "annotator_B", "annotator_B", [])
        rc, out3, raw3, err3 = run_agreement([sk / "annotator_A", sk / "annotator_B"])
        check("Skip 한 이미지는 비교에서 빠진다", "비교한 이미지 2/3" in out3,
              [l.strip() for l in out3.splitlines() if "비교한 이미지" in l])
        check("빈 파일은 비교에 남는다 (Skip 이 아니다)",
              "비교한 이미지 2/3" in out3 and "이미지Skip 1" in out3)
        check("Skip 사유가 집계된다 (무엇을 고쳐야 하는지 알려 준다)",
              "Skip 사유별 집계" in raw3 and "rule_unclear" in raw3,
              next((l.strip() for l in raw3.splitlines() if "rule_unclear" in l), ""))

        print("\n[9] CVAT class_id 정규화 — 원본이 정규화본을 덮지 않는가")
        # CVAT 은 자기 라벨 목록으로 0부터 다시 매긴다. 자리표시자를 건너뛴 압축 번호다.
        compact = [n for n in CLASSES if not n.startswith("__사용안함")]
        ing = tmp / "ingest" / "trial"
        (ing / "images").mkdir(parents=True)
        (ing / "classes.txt").write_text("\n".join(CLASSES) + "\n", encoding="utf-8")
        for stem in ("A01", "A02"):
            (ing / "images" / f"{stem}.jpg").write_bytes(b"")
        cdir = ing / "annotator_C"
        exp = cdir / "yolo" / "annotator_C"
        (exp / "obj_train_data" / "images").mkdir(parents=True)
        (exp / "obj.names").write_text("\n".join(compact) + "\n", encoding="utf-8")
        # id 4 = 한류형 전력퓨즈 (obj.names) -> classes.txt 에서는 5
        (exp / "obj_train_data" / "images" / "A01.txt").write_text(
            "4 0.5 0.5 0.1 0.1\n0 0.2 0.2 0.1 0.1\n", encoding="utf-8")
        (exp / "obj_train_data" / "images" / "A02.txt").write_text("", encoding="utf-8")

        old_trial, old_raw = I.TRIAL, I.RAW_ROOT
        I.TRIAL, I.RAW_ROOT = ing, ing / "_raw_export"
        try:
            ok, info = I.ingest(cdir)
        finally:
            I.TRIAL, I.RAW_ROOT = old_trial, old_raw

        check("정규화가 성공한다", ok, "; ".join(info["problems"]))
        check("압축된 id 를 classes.txt id 로 되돌린다",
              (cdir / "yolo" / "A01.txt").read_text(encoding="utf-8").split()[0] == "5",
              (cdir / "yolo" / "A01.txt").read_text(encoding="utf-8").split("\n")[0])
        check("빈 파일도 그대로 옮긴다 (대상 없음)",
              (cdir / "yolo" / "A02.txt").exists()
              and not (cdir / "yolo" / "A02.txt").read_text(encoding="utf-8").strip())
        check("박스 수가 보존된다", info["boxes"] == 2, f"{info['boxes']}")
        raw_kept = ing / "_raw_export" / "annotator_C" / "obj_train_data" / "images" / "A01.txt"
        check("원본은 그대로 보존된다 (번호도 원본 그대로)",
              raw_kept.exists()
              and raw_kept.read_text(encoding="utf-8").split()[0] == "4")
        strays = [p for p in cdir.rglob("*.txt")
                  if (cdir / "yolo").resolve() not in p.resolve().parents]
        check("라벨러 폴더 안에 원본 txt 가 남지 않는다 "
              "(남으면 agreement.py 가 정규화본을 덮어쓴다)",
              not strays, f"{[str(x.relative_to(cdir)) for x in strays]}")

        # 실제로 agreement.py 가 정규화된 값을 읽는지 — 폴더를 통째로 준다
        shutil.copytree(cdir, ing / "annotator_D")
        rc9, out9, _, err9 = run_agreement([cdir, ing / "annotator_D"])
        check("agreement.py 가 정규화된 클래스로 읽는다",
              rc9 == 0 and "한류형 전력퓨즈" in out9,
              [l.strip() for l in out9.splitlines() if "전력퓨즈" in l or "철심부" in l])

    finally:
        for p, data in backup.items():
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)
        shutil.rmtree(tmp, ignore_errors=True)

    n = len(RESULTS)
    bad_n = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{'='*60}\n검사 {n}건 · 실패 {bad_n}건")
    if bad_n:
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  FAIL  {name}   {detail}")
    print("실제 30장·라벨러 폴더·보고서: 수정하지 않았다 (fixture 는 임시 폴더에서 삭제됨)")
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
