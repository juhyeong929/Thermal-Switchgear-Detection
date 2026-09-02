"""변압기(Transformer) vs 변류기(CT) 를 IR 에서 구분할 수 있는가 — 검증 도구.

라벨링 PDF 9페이지 기준: "변압기 = 접촉부 선이 1개 / 변류기 = 접촉부 선이 2개".
이 기준이 320x240 IR 에서 실제로 관측 가능한지, 그리고 같은 프레임의 실화상에서는
보이는지를 나란히 놓고 사람이 판정하도록 시트를 만든다.

  python qa_tr_vs_ct.py sheet      판정용 시트 생성 (IR | IR확대 | 실화상 | 실화상확대)
  python qa_tr_vs_ct.py record     판정 결과 입력 서식 생성
  python qa_tr_vs_ct.py score      입력된 판정 집계

원본 데이터는 읽기만 한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import flir  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "out" / "qa_tr_ct"
W, H = 320, 240
KEY = {9: "변압기", 11: "변류기"}


def find_source(stem: str) -> Path | None:
    """3-가공 에서 원본 열화상 JPEG 을 찾는다 (내장 실화상을 꺼내기 위해)."""
    panel = stem.split("_")[2]
    for d in (ROOT / "3-가공").glob(f"{panel}-*"):
        for p in d.rglob(f"{stem}.jpg"):
            if not p.name.startswith("._"):
                return p
    return None


def build_sheet(n=16, seed=0, crop_pad=18):
    from PIL import Image, ImageDraw
    random.seed(seed)
    OUT.mkdir(parents=True, exist_ok=True)

    lab_dir = HERE / "_p4" / "labels"
    img_dir = HERE / "_p4" / "images"
    items = []
    for f in sorted(lab_dir.glob("*.txt")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            q = ln.split()
            if len(q) == 5 and int(q[0]) in KEY:
                c, cx, cy, w, h = int(q[0]), *map(float, q[1:])
                items.append((f.stem, c, cx, cy, w, h))
    tr = [i for i in items if i[1] == 9]
    ct = [i for i in items if i[1] == 11]
    print(f"라벨된 변압기 {len(tr)}개 / 변류기 {len(ct)}개")
    sel = tr + random.sample(ct, min(n - len(tr), len(ct)))
    random.shuffle(sel)

    rows = []
    CW = 240
    sheet = Image.new("RGB", (CW * 4, CW * len(sel)), "#101014")
    for i, (stem, c, cx, cy, w, h) in enumerate(sel):
        ir = Image.open(img_dir / f"{stem}.jpg").convert("RGB")
        x1, y1 = (cx - w/2) * W, (cy - h/2) * H
        x2, y2 = (cx + w/2) * W, (cy + h/2) * H
        box = (max(0, x1-crop_pad), max(0, y1-crop_pad),
               min(W, x2+crop_pad), min(H, y2+crop_pad))

        src = find_source(stem)
        vis = None
        if src:
            try:
                _t, visual, _m = flir.read(src)
                vis = Image.fromarray(visual)
            except Exception:
                vis = None

        ir_full = ir.copy()
        ImageDraw.Draw(ir_full).rectangle([x1, y1, x2, y2], outline="#FF3B3B", width=2)
        panes = [ir_full.resize((CW, CW)), ir.crop(box).resize((CW, CW), Image.LANCZOS)]
        if vis is not None:
            # 실화상은 열화상보다 화각이 1.53배 넓다 -> 같은 영역으로 맞춘다
            sw, sh = round(640/1.5325), round(480/1.5325)
            v = vis.resize((sw, sh), Image.BILINEAR)
            x0, y0 = (sw - W)//2 + (-5), (sh - H)//2 + 9
            v = v.crop((x0, y0, x0 + W, y0 + H))
            vf = v.copy()
            ImageDraw.Draw(vf).rectangle([x1, y1, x2, y2], outline="#FF3B3B", width=2)
            panes += [vf.resize((CW, CW)), v.crop(box).resize((CW, CW), Image.LANCZOS)]
        else:
            panes += [Image.new("RGB", (CW, CW), "#101014")] * 2

        for j, p in enumerate(panes):
            sheet.paste(p, (j * CW, i * CW))
        d = ImageDraw.Draw(sheet)
        d.text((4, i * CW + 4), f"#{i:02d}", fill="#FFFFFF")
        d.text((4, i * CW + CW - 14), stem[-16:], fill="#AAAAAA")
        rows.append({"idx": i, "stem": stem, "current_label": KEY[c],
                     "verdict": "", "reason": ""})

    p = OUT / "qa_sheet.png"
    sheet.save(p)
    with open(OUT / "qa_form.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=["idx", "stem", "current_label",
                                            "verdict", "reason"])
        wr.writeheader()
        wr.writerows(rows)
    print(f"\n시트 {len(sel)}건 -> {p}")
    print("   열 구성: IR 전체 | IR 확대 | 실화상 전체 | 실화상 확대")
    print(f"판정 서식 -> {OUT/'qa_form.csv'}")
    print("\n각 행을 보고 verdict 열에 다음 중 하나를 적으세요")
    print("   구분가능_변압기 / 구분가능_변류기 / 애매 / 구분불가")
    print("reason 열에는 근거를 적으세요 (예: 접촉부선2개, 명판보임, 애자만보임)")


def score():
    f = OUT / "qa_form.csv"
    if not f.exists():
        raise SystemExit(f"판정 서식이 없습니다: {f}")
    rows = [r for r in csv.DictReader(f.open(encoding="utf-8-sig")) if r["verdict"].strip()]
    if not rows:
        raise SystemExit("verdict 가 입력되지 않았습니다")
    import collections
    v = collections.Counter(r["verdict"].strip() for r in rows)
    print(f"판정 완료 {len(rows)}건")
    for k, n in v.most_common():
        print(f"   {k:<16} {n:3d}건 ({n/len(rows)*100:.0f}%)")
    ok = sum(n for k, n in v.items() if k.startswith("구분가능"))
    print(f"\n구분 가능 비율 {ok/len(rows)*100:.0f}%")
    print("   70% 미만이면 IR 단독으로는 두 클래스 분리가 성립하지 않는다고 본다")
    mismatch = [r for r in rows if r["verdict"].startswith("구분가능")
                and not r["verdict"].endswith(r["current_label"])]
    if mismatch:
        print(f"\n현재 라벨과 다른 판정 {len(mismatch)}건")
        for r in mismatch[:15]:
            print(f"   #{r['idx']:>2} {r['stem'][-16:]}  현재 {r['current_label']}"
                  f" -> {r['verdict']}  ({r['reason']})")
    reasons = collections.Counter(r["reason"].strip() for r in rows if r["reason"].strip())
    if reasons:
        print("\n사용된 근거")
        for k, n in reasons.most_common():
            print(f"   {k:<24} {n}건")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sheet", "score"])
    ap.add_argument("--n", type=int, default=16)
    a = ap.parse_args()
    if a.cmd == "sheet":
        build_sheet(a.n)
    else:
        score()
