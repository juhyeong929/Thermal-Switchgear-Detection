"""CVAT 에서 내보낸 YOLO 결과를 파이프라인으로 들여온다.

CVAT 의 Export annotations -> "YOLO 1.1" 로 받은 zip(또는 압축 해제 폴더)을 넣으면
라벨 txt 를 꺼내 지정한 디렉터리에 넣는다. 클래스 순서가 우리 정의와 다르면
obj.names 를 읽어 자동으로 다시 매핑한다.

  # 담당자별로 따로 받아 교차검증에 쓴다
  python cvat_import.py exports/A.zip --into annot/A
  python cvat_import.py exports/B.zip --into annot/B

  # 최종 병합본을 학습에 쓴다
  python cvat_import.py exports/final.zip --into data/labels_rgb

정합된 실화상을 쓰므로 좌표 변환은 필요 없다. 원본 데이터는 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import NAMES  # noqa: E402

HERE = Path(__file__).parent


def unpack(src: Path) -> tuple[Path, Path | None]:
    if src.is_dir():
        return src, None
    tmp = Path(tempfile.mkdtemp(prefix="cvat_"))
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)
    return tmp, tmp


def find_names(root: Path) -> list[str] | None:
    for p in root.rglob("obj.names"):
        return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export", help="CVAT YOLO 1.1 zip 또는 폴더")
    ap.add_argument("--into", required=True, help="라벨을 넣을 디렉터리")
    ap.add_argument("--clear", action="store_true", help="대상 디렉터리를 먼저 비운다")
    args = ap.parse_args()

    src = Path(args.export)
    if not src.exists():
        raise SystemExit(f"없는 경로: {src}")
    root, tmp = unpack(src)

    try:
        src_names = find_names(root)
        remap = None
        if src_names and src_names != NAMES:
            missing = [n for n in src_names if n not in NAMES]
            if missing:
                raise SystemExit(
                    f"우리 클래스 정의에 없는 이름이 있습니다: {missing}\n"
                    "CVAT 프로젝트의 클래스명을 out/cvat/labels.json 과 맞추세요.")
            remap = {i: NAMES.index(n) for i, n in enumerate(src_names)}
            print(f"클래스 순서가 달라 재매핑합니다 ({len(remap)}개)")
        elif src_names:
            print("클래스 순서 일치")
        else:
            print("주의: obj.names 를 찾지 못했습니다. 클래스 순서가 같다고 가정합니다")

        txts = [p for p in root.rglob("*.txt")
                if p.name not in ("train.txt", "obj.names", "obj.data", "classes.txt")]
        if not txts:
            raise SystemExit("라벨 txt 를 찾지 못했습니다. YOLO 1.1 포맷으로 내보냈는지 확인하세요")

        dst = Path(args.into)
        if args.clear and dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        n_file = n_box = n_bad = n_empty = 0
        for t in sorted(txts):
            out = []
            for ln in t.read_text(encoding="utf-8").splitlines():
                parts = ln.split()
                if len(parts) < 5:
                    continue
                try:
                    cid = int(parts[0])
                    vals = [float(x) for x in parts[1:5]]
                except ValueError:
                    n_bad += 1
                    continue
                if remap is not None:
                    if cid not in remap:
                        n_bad += 1
                        continue
                    cid = remap[cid]
                if not (0 <= cid < len(NAMES)) or any(not 0 <= v <= 1 for v in vals) \
                        or vals[2] <= 0 or vals[3] <= 0:
                    n_bad += 1
                    continue
                out.append(f"{cid} " + " ".join(f"{v:.6f}" for v in vals))
                n_box += 1
            (dst / t.name).write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
            n_file += 1
            if not out:
                n_empty += 1

        print(f"\n라벨 파일 {n_file}개 / 박스 {n_box}개  -> {dst}")
        print(f"  빈 파일 {n_empty}개 (부품 없음으로 판단된 사진)")
        if n_bad:
            print(f"  버린 줄 {n_bad}개 (형식·범위 오류)")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
