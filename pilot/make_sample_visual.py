from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
W, H = 320, 240
COLS, CELL_W, CELL_H = 2, 480, 300
PALETTE = [(226, 59, 46), (240, 163, 43), (47, 163, 124), (63, 123, 214), (155, 89, 182)]
NAMES = {
    9: "transformer",
    10: "transformer_contact",
    11: "ct_transformer",
    12: "mof_fuse",
    13: "ct_transformer_contact",
    14: "pt",
}

try:
    FONT = ImageFont.truetype("arial.ttf", 14)
except OSError:
    FONT = ImageFont.load_default()


def draw_one(img_path: Path, label_path: Path) -> Image.Image:
    im = Image.open(img_path).convert("RGB").resize((W, H))
    d = ImageDraw.Draw(im)
    for line in label_path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        cid, cx, cy, bw, bh = int(p[0]), *map(float, p[1:5])
        x1, y1 = (cx - bw / 2) * W, (cy - bh / 2) * H
        x2, y2 = (cx + bw / 2) * W, (cy + bh / 2) * H
        color = PALETTE[cid % len(PALETTE)]
        d.rectangle((x1, y1, x2, y2), outline=color, width=3)
        text = NAMES.get(cid, str(cid))
        tb = d.textbbox((0, 0), text, font=FONT)
        d.rectangle((x1, max(0, y1 - (tb[3] - tb[1]) - 4), x1 + tb[2] + 6, max(0, y1 - 2)), fill=color)
        d.text((x1 + 3, max(0, y1 - (tb[3] - tb[1]) - 3)), text, fill="white", font=FONT)
    return im


def main():
    groups = [("IR2", ROOT / "sample_autolabel" / "IR2"), ("IR3", ROOT / "sample_autolabel" / "IR3")]
    entries = []
    for name, base in groups:
        for p in sorted((base / "images").glob("*.jpg")):
            entries.append((name, p, base / "labels" / f"{p.stem}.txt"))
    rows = (len(entries) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL_W, rows * CELL_H), "#151515")
    for i, (name, img, lab) in enumerate(entries):
        x, y = (i % COLS) * CELL_W, (i // COLS) * CELL_H
        tile = Image.new("RGB", (CELL_W, CELL_H), "#151515")
        tile.paste(draw_one(img, lab), (0, 28))
        d = ImageDraw.Draw(tile)
        n = sum(1 for line in lab.read_text(encoding="utf-8").splitlines() if len(line.split()) >= 5)
        d.text((4, 6), f"{name} | {img.name} | boxes: {n}", fill="white", font=FONT)
        sheet.paste(tile, (x, y))
    out = ROOT / "sample_autolabel" / "sample_visualization.png"
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
