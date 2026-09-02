"""검증용 시각화 시트를 만든다.

  qa_sheet.py align     실화상을 열화상 좌표계로 변환해 겹쳐본다 (정합 상수 검증)
  qa_sheet.py hotspot   라벨 없는 이상 발열 탐지 결과를 그려본다
  qa_sheet.py labels    전이된 열화상 라벨을 그려본다 (라벨 작성 후)

out/ 아래에 PNG로 저장한다. 원본은 읽기만 한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import transfer  # noqa: E402
from classes import KOREAN_BY_ID, NAMES  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"
IR_W, IR_H = transfer.IR_W, transfer.IR_H

PALETTE = ["#E23B2E", "#F0A32B", "#2FA37C", "#3F7BD6", "#9B59B6", "#16A3B8",
           "#D7539B", "#6D8B22", "#C0713A", "#4E5D94"]


def _warp_visual(vis: Image.Image) -> Image.Image:
    """실화상을 열화상 좌표계로 맞춘다.

    3-가공 의 rgb_image 는 이미 정합되어 있으므로 크기만 맞추면 되고,
    640x480 내장 실화상은 보정 변환이 필요하다.
    """
    if transfer.detect_source() == "prealigned":
        return vis.resize((IR_W, IR_H), Image.BILINEAR)
    sw, sh = transfer._SW, transfer._SH
    v = vis.resize((sw, sh), Image.BILINEAR)
    return v.crop((transfer._X0, transfer._Y0, transfer._X0 + IR_W, transfer._Y0 + IR_H))


def sheet_align(n=6):
    stems = [r["stem"] for r in json.loads((DATA / "index.json").read_text(encoding="utf-8"))][:n]
    sheet = Image.new("RGB", (IR_W * 3, IR_H * len(stems)), "black")
    for i, stem in enumerate(stems):
        ir = Image.open(DATA / "ir" / f"{stem}.jpg").convert("RGB")
        warped = _warp_visual(Image.open(DATA / "rgb" / f"{stem}.jpg").convert("RGB"))
        sheet.paste(ir, (0, i * IR_H))
        sheet.paste(warped, (IR_W, i * IR_H))
        sheet.paste(Image.blend(ir, warped, 0.5), (IR_W * 2, i * IR_H))
    p = OUT / "qa_align.png"
    sheet.save(p)
    print(f"열화상 | 변환된 실화상 | 50% 합성  -> {p}")
    print("3열의 윤곽선이 겹쳐 보이면 정합 상수가 맞는 것이다.")


def sheet_hotspot(n=8):
    rows = json.loads((OUT / "hotspots.json").read_text(encoding="utf-8"))
    rows = sorted(rows, key=lambda r: -r["dT"])[:n]
    sheet = Image.new("RGB", (IR_W * 2, IR_H * len(rows)), "black")
    for i, r in enumerate(rows):
        ir = Image.open(DATA / "ir" / f"{r['stem']}.jpg").convert("RGB")
        rgb = _warp_visual(Image.open(DATA / "rgb" / f"{r['stem']}.jpg").convert("RGB"))
        d = ImageDraw.Draw(ir)
        for b in r["blobs"][:6]:
            color = {"심각": "#FF2D2D", "이상": "#FFA22D", "주의": "#FFE95C"}.get(b["verdict"], "#8ED9FF")
            d.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline=color, width=2)
            d.text((b["x1"] + 2, max(0, b["y1"] - 11)), f"{b['t_peak']:.0f}C dT{b['dT']:.0f}", fill=color)
        d.text((4, IR_H - 13), f"{r['panel']} ref {r['t_ref']:.1f}C", fill="#FFFFFF")
        sheet.paste(ir, (0, i * IR_H))
        sheet.paste(rgb, (IR_W, i * IR_H))
    p = OUT / "qa_hotspot.png"
    sheet.save(p)
    print(f"이상 발열 상위 {len(rows)}장  -> {p}")


def sheet_labels(n=8):
    lab_dir = DATA / "labels_ir"
    files = transfer.label_files(lab_dir)
    if not files:
        print("전이된 라벨이 없습니다. 먼저 transfer.py 를 실행하세요.")
        return
    files = files[:n]
    rgb_w, rgb_h = Image.open(DATA / "rgb" / f"{files[0].stem}.jpg").size
    row_h = max(rgb_h, IR_H)
    sheet = Image.new("RGB", (rgb_w + IR_W, row_h * len(files)), "black")
    for i, f in enumerate(files):
        stem = f.stem
        rgb = Image.open(DATA / "rgb" / f"{stem}.jpg").convert("RGB")
        ir = Image.open(DATA / "ir" / f"{stem}.jpg").convert("RGB")
        dr, di = ImageDraw.Draw(rgb), ImageDraw.Draw(ir)
        src = DATA / "labels_rgb" / f.name
        for line in src.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            cid = int(p[0])
            color = PALETTE[cid % len(PALETTE)]
            x1, y1, x2, y2 = transfer._yolo_to_xyxy(*map(float, p[1:5]), rgb.width, rgb.height)
            dr.rectangle([x1, y1, x2, y2], outline=color, width=2)
            dr.text((x1 + 2, max(0, y1 - 11)), NAMES[cid], fill=color)
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            cid = int(p[0])
            color = PALETTE[cid % len(PALETTE)]
            x1, y1, x2, y2 = transfer._yolo_to_xyxy(*map(float, p[1:5]), IR_W, IR_H)
            di.rectangle([x1, y1, x2, y2], outline=color, width=2)
        sheet.paste(rgb, (0, i * row_h))
        sheet.paste(ir, (rgb_w, i * row_h))
    p = OUT / "qa_labels.png"
    sheet.save(p)
    print(f"실화상 원본 라벨 | 전이된 열화상 라벨  -> {p}")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "align"
    {"align": sheet_align, "hotspot": sheet_hotspot, "labels": sheet_labels}[mode]()
