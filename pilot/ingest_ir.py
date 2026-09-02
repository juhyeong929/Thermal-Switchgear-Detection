"""열화상에 직접 라벨링한 작업물을 들여온다.

CVAT/YOLO 로 **열화상에 직접** 그린 결과는 좌표가 이미 열화상 좌표계이므로 변환이
필요 없다. 실화상에 그려 변환하는 경로(transfer.py)와 섞이지 않게 별도 디렉터리
data/labels_ir_src 에 넣고, transfer.py 가 최종 data/labels_ir 를 만들 때 이쪽을
우선한다.

  python ingest_ir.py IR1_3반                       # YOLO 데이터셋 폴더
  python ingest_ir.py exports/D.zip                 # CVAT YOLO 1.1 zip
  python ingest_ir.py IR1_3반 --schema 16           # 예전 16클래스 라벨이면

원본 데이터는 읽기만 한다.
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import DISCOURAGED, KOREAN_BY_ID, MAP16TO26, NAMES  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
DST = DATA / "labels_ir_src"


def _ingest_cvat_xml(xmls, args):
    """CVAT for images 1.1 XML 을 들여온다. 라벨명은 우리 26 스키마로 이름 매핑한다."""
    import xml.etree.ElementTree as ET
    korean_to_id = {v: k for k, v in KOREAN_BY_ID.items()}
    lookup = {**korean_to_id, **{n: i for i, n in enumerate(NAMES)}}

    dst = Path(args.into)
    if args.clear and dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    ir_dir = DATA / "ir"

    cls = collections.Counter()
    n_file = n_box = n_bad = n_skip_empty = 0
    no_image = []
    for xf in xmls:
        root = ET.parse(xf).getroot()
        for im in root.findall("image"):
            stem = Path(im.get("name")).stem
            w = float(im.get("width")); h = float(im.get("height"))
            out = []
            for b in im.findall("box"):
                name = b.get("label")
                if name not in lookup:
                    n_bad += 1
                    continue
                cid = lookup[name]
                x1, y1 = float(b.get("xtl")), float(b.get("ytl"))
                x2, y2 = float(b.get("xbr")), float(b.get("ybr"))
                if x2 <= x1 or y2 <= y1:
                    n_bad += 1
                    continue
                out.append(f"{cid} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} "
                           f"{(x2-x1)/w:.6f} {(y2-y1)/h:.6f}")
                cls[cid] += 1
                n_box += 1
            if not out and not args.keep_empty:
                n_skip_empty += 1
                continue
            if not (ir_dir / f"{stem}.jpg").exists():
                no_image.append(stem)
            (dst / f"{stem}.txt").write_text("\n".join(out) + ("\n" if out else ""),
                                             encoding="utf-8")
            n_file += 1

    print(f"CVAT XML 라벨 {n_file}개 파일 / 박스 {n_box}개  -> {dst}")
    for cid, n in cls.most_common():
        print(f"    {cid:2d} {KOREAN_BY_ID[cid]:<18} {n:4d}")
    if n_skip_empty:
        print(f"  빈 라벨 {n_skip_empty}개 제외")
    if n_bad:
        print(f"  버린 박스 {n_bad}개 (모르는 클래스명 또는 좌표 오류)")
    if no_image:
        print(f"  경고: data/ir 에 이미지가 없는 라벨 {len(no_image)}개 (예: {no_image[:3]})")
    print("\n다음: python transfer.py")
    return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="YOLO 데이터셋 폴더 또는 CVAT YOLO 1.1 zip")
    ap.add_argument("--schema", choices=["auto", "26", "16"], default="auto",
                    help="auto = obj.names 를 읽어 이름으로 매핑 (권장). "
                         "부분 클래스만 담긴 export 도 안전하게 들어온다")
    ap.add_argument("--into", default=str(DST))
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--keep-empty", action="store_true",
                    help="빈 라벨도 들여온다. CVAT 는 미작업 프레임도 빈 txt 로 내보내므로, "
                         "'부품 없음을 확인한 사진'일 때만 켤 것. 미작업을 배경으로 학습시키면 "
                         "모델이 해당 부품을 배경으로 배운다.")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        raise SystemExit(f"없는 경로: {src}")
    tmp = None
    if src.is_file():
        tmp = Path(tempfile.mkdtemp(prefix="ingest_"))
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        root = tmp
    else:
        root = src

    try:
        txts = [p for p in root.rglob("*.txt")
                if p.name not in ("train.txt", "obj.names", "obj.data", "classes.txt",
                                  "val.txt", "test.txt")]
        xmls = [p for p in root.rglob("*.xml")]
        if not txts and xmls:
            return _ingest_cvat_xml(xmls, args)
        if not txts:
            raise SystemExit("라벨 txt 또는 CVAT xml 을 찾지 못했습니다")

        # obj.names 가 있으면 이름으로 매핑한다. 부분 클래스만 담긴 export 는
        # 인덱스가 우리 스키마와 다르므로 이름 매핑이 유일하게 안전한 방법이다.
        remap = None
        if args.schema == "auto":
            nf = next((p for p in root.rglob("obj.names")), None)
            if nf is None:
                print("obj.names 가 없어 26클래스 인덱스를 그대로 씁니다")
            else:
                src_names = [l.strip() for l in nf.read_text(encoding="utf-8").splitlines()
                             if l.strip()]
                korean_to_id = {v: k for k, v in KOREAN_BY_ID.items()}
                lookup = {**korean_to_id, **{n: i for i, n in enumerate(NAMES)}}
                missing = [n for n in src_names if n not in lookup]
                if missing:
                    raise SystemExit(f"우리 스키마에 없는 클래스명: {missing}")
                remap = {i: lookup[n] for i, n in enumerate(src_names)}
                if remap != {i: i for i in range(len(src_names))}:
                    print(f"클래스 {len(src_names)}개를 이름으로 재매핑합니다")
                else:
                    print(f"클래스 {len(src_names)}개, 인덱스 일치 확인")
        elif args.schema == "16":
            remap = MAP16TO26

        ir_dir = DATA / "ir"
        dst = Path(args.into)
        if args.clear and dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        cls = collections.Counter()
        n_file = n_box = n_bad = n_disc = n_skip_empty = 0
        no_image = []
        for t in sorted(txts):
            out = []
            for ln in t.read_text(encoding="utf-8").splitlines():
                p = ln.split()
                if len(p) < 5:
                    continue
                try:
                    cid = int(p[0])
                    v = [float(x) for x in p[1:5]]
                except ValueError:
                    n_bad += 1
                    continue
                if remap is not None:
                    if cid not in remap:
                        n_bad += 1
                        continue
                    cid = remap[cid]
                if not (0 <= cid < len(NAMES)) or any(not 0 <= x <= 1 for x in v) \
                        or v[2] <= 0 or v[3] <= 0:
                    n_bad += 1
                    continue
                if cid in DISCOURAGED:
                    n_disc += 1
                out.append(f"{cid} " + " ".join(f"{x:.6f}" for x in v))
                cls[cid] += 1
                n_box += 1
            if not out and not args.keep_empty:
                n_skip_empty += 1
                continue
            if not (ir_dir / f"{t.stem}.jpg").exists():
                no_image.append(t.stem)
            (dst / t.name).write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
            n_file += 1

        print(f"열화상 직접 라벨 {n_file}개 파일 / 박스 {n_box}개  -> {dst}")
        for cid, n in cls.most_common():
            print(f"    {cid:2d} {KOREAN_BY_ID[cid]:<18} {n:4d}")
        if n_skip_empty:
            print(f"  빈 라벨 {n_skip_empty}개 제외 (미작업으로 간주). "
                  "부품 없음을 확인한 사진이면 --keep-empty 로 포함하세요")
        if n_bad:
            print(f"  버린 줄 {n_bad}개 (형식·범위 오류)")
        if n_disc:
            print(f"  주의: PDF 에서 제외 판정된 클래스 박스 {n_disc}개 포함 "
                  "(부스바·케이블·ACB 접촉부). 학습 전 검토 필요")
        if no_image:
            print(f"  경고: data/ir 에 대응 이미지가 없는 라벨 {len(no_image)}개")
            print(f"        예: {no_image[:3]}")
            print("        select_pairs.py 로 해당 사진을 먼저 추출해야 학습에 쓰입니다")
        print("\n다음: python transfer.py  (실화상 라벨과 합쳐 data/labels_ir 를 만듭니다)")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
