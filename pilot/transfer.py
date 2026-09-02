"""실화상 좌표계 <-> 열화상 좌표계 박스 전이.

calibrate.py 가 구한 상수를 써서 닫힌 식으로 변환한다. 실화상에 박스를 한 번 그리면
열화상 라벨은 계산으로 나온다.

  visual(640x480) --(1/scale 축소, 중앙정렬 후 shift 만큼 이동)--> ir(320x240)

원본 데이터는 건드리지 않는다. labels_rgb/ 를 읽어 labels_ir/ 에 쓴다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
CAL = json.loads((HERE / "calibration.json").read_text(encoding="utf-8"))

SCALE = CAL["scale"]
DX, DY = CAL["dx"], CAL["dy"]
IR_W, IR_H = CAL["ir_size"]
VIS_W, VIS_H = CAL["visual_size"]

# 축소된 실화상 크기와, 그 안에서 열화상이 잘라내는 좌상단 원점
_SW, _SH = round(VIS_W / SCALE), round(VIS_H / SCALE)
_X0 = (_SW - IR_W) // 2 + DX
_Y0 = (_SH - IR_H) // 2 + DY


def visual_to_ir(x: float, y: float) -> tuple[float, float]:
    return x / SCALE - _X0, y / SCALE - _Y0


def ir_to_visual(x: float, y: float) -> tuple[float, float]:
    return (x + _X0) * SCALE, (y + _Y0) * SCALE


def visual_box_to_ir(box_xyxy, clip=True):
    """실화상 픽셀 박스 -> 열화상 픽셀 박스. 화면 밖으로 완전히 나가면 None."""
    x1, y1, x2, y2 = box_xyxy
    ax1, ay1 = visual_to_ir(x1, y1)
    ax2, ay2 = visual_to_ir(x2, y2)
    if clip:
        cx1, cy1 = max(0.0, ax1), max(0.0, ay1)
        cx2, cy2 = min(float(IR_W), ax2), min(float(IR_H), ay2)
        if cx2 - cx1 < 2 or cy2 - cy1 < 2:
            return None
        # 잘려나간 비율이 과하면 학습에 해로우므로 버린다
        if (cx2 - cx1) * (cy2 - cy1) < 0.35 * max((ax2 - ax1) * (ay2 - ay1), 1e-6):
            return None
        return cx1, cy1, cx2, cy2
    return ax1, ay1, ax2, ay2


def label_files(directory: Path) -> list[Path]:
    """라벨 txt 목록. labelImg 가 저장 폴더에 함께 떨어뜨리는 classes.txt 는 제외한다."""
    return sorted(p for p in Path(directory).glob("*.txt") if p.name != "classes.txt")


def _yolo_to_xyxy(cx, cy, w, h, W, H):
    return (cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H


def _xyxy_to_yolo(x1, y1, x2, y2, W, H):
    return ((x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H)


def convert_label_file(src: Path, dst: Path) -> tuple[int, int]:
    """YOLO txt (실화상 정규화) -> YOLO txt (열화상 정규화). 반환 (전이 성공, 탈락)."""
    kept, dropped = [], 0
    for line in src.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls, cx, cy, w, h = int(parts[0]), *map(float, parts[1:5])
        box = visual_box_to_ir(_yolo_to_xyxy(cx, cy, w, h, VIS_W, VIS_H))
        if box is None:
            dropped += 1
            continue
        ncx, ncy, nw, nh = _xyxy_to_yolo(*box, IR_W, IR_H)
        kept.append(f"{cls} {ncx:.6f} {ncy:.6f} {nw:.6f} {nh:.6f}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return len(kept), dropped


def detect_source() -> str:
    """data/index.json 에 기록된 실화상 출처를 읽는다."""
    idx = HERE / "data" / "index.json"
    if idx.exists():
        rows = json.loads(idx.read_text(encoding="utf-8"))
        if rows and rows[0].get("rgb_source"):
            return rows[0]["rgb_source"]
    return "embedded"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["prealigned", "embedded", "auto"], default="auto",
                    help="prealigned = 3-가공 rgb_image (변환 불필요), "
                         "embedded = 640x480 내장 실화상 (보정 변환 필요)")
    args = ap.parse_args()
    source = detect_source() if args.source == "auto" else args.source

    src_dir = HERE / "data" / "labels_rgb"
    dst_dir = HERE / "data" / "labels_ir"
    files = label_files(src_dir)
    if not files:
        print(f"라벨이 없습니다: {src_dir}")
        print("실화상(data/rgb)에 먼저 박스를 그린 뒤 다시 실행하세요.")
        return 1

    dst_dir.mkdir(parents=True, exist_ok=True)

    # 열화상에 직접 그린 라벨은 이미 열화상 좌표계다. 변환하지 않고 그대로 쓰며,
    # 같은 사진이 양쪽에 있으면 직접 그린 쪽을 우선한다.
    native_dir = HERE / "data" / "labels_ir_src"
    native = {f.stem: f.read_text(encoding="utf-8") for f in label_files(native_dir)} \
        if native_dir.is_dir() else {}

    if source == "prealigned":
        # 3-가공 의 rgb_image 는 이미 열화상 FOV 에 정합되어 있으므로
        # 정규화 좌표를 그대로 쓴다. 변환하면 오히려 어긋난다.
        tot = 0
        for f in files:
            if f.stem in native:
                continue
            text = f.read_text(encoding="utf-8")
            (dst_dir / f.name).write_text(text, encoding="utf-8")
            tot += sum(1 for ln in text.splitlines() if len(ln.split()) >= 5)
        print(f"실화상 라벨 {len(files)}개 중 {len(files)-sum(1 for f in files if f.stem in native)}"
              f"개 복사 (정합된 실화상이라 좌표 변환 없음), 박스 {tot}개")
        _merge_native(native, dst_dir)
        print(f"  -> {dst_dir}")
        return 0

    tot_k = tot_d = 0
    for f in files:
        if f.stem in native:
            continue
        k, d = convert_label_file(f, dst_dir / f.name)
        tot_k += k
        tot_d += d
    print(f"실화상 라벨 전이 완료: 박스 {tot_k}개 생성, "
          f"{tot_d}개 탈락(열화상 화각 밖 또는 65% 이상 잘림)")
    print(f"  사용 상수 scale={SCALE} shift=({DX:+d},{DY:+d})")
    _merge_native(native, dst_dir)
    print(f"  -> {dst_dir}")
    return 0


def _merge_native(native: dict[str, str], dst_dir: Path):
    if not native:
        return
    n_box = 0
    for stem, text in native.items():
        (dst_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
        n_box += sum(1 for ln in text.splitlines() if len(ln.split()) >= 5)
    print(f"열화상 직접 라벨 {len(native)}개 파일 / 박스 {n_box}개 병합 (변환 없음, 우선 적용)")


if __name__ == "__main__":
    sys.exit(main())
