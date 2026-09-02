"""접촉부(진단 포인트) 전용 모델을 만들고 미라벨 세션에 제안을 뽑는다.

접촉부는 20x54 px 수준으로 작아 탐지 난이도가 높다. 그래서 제안을 뽑기 전에
**다른 세션에 얼마나 통하는지** 먼저 측정한다.

  1단계  P3-MOF반(178박스)으로 학습 -> P4 05-12(41박스)로 검증
         = 반도 세션도 다른 조건. 여기서 나온 수치가 현실적인 기대치다.
  2단계  P3 + P4 05-12 전부로 학습 -> P4 06-03 / 06-17 (77장) 에 제안

접촉부 종류(변압기/변류기)는 구분하지 않고 하나의 '접촉부' 클래스로 다룬다.
원본 라벨은 읽기만 하고, 제안은 별도 디렉터리에 쓴다.

  python contact_proposals.py --epochs 60
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

HERE = Path(__file__).parent
DATA = HERE / "data"
CONTACT_SRC = {10, 13}          # 변압기 접촉부, 변류기 접촉부 -> 통합
W, H = 320, 240


def img_path(stem):
    for p in (DATA / "ir" / f"{stem}.jpg", HERE / "_p4" / "images" / f"{stem}.jpg"):
        if p.exists():
            return p
    return None


def gather():
    """{stem: [(cx,cy,w,h)]} — 접촉부만."""
    out = {}
    for d in (DATA / "labels_ir_src", HERE / "_p4" / "labels"):
        for f in sorted(d.glob("*.txt")):
            pan = f.stem.split("_")[2]
            if pan not in ("P3", "P4"):
                continue
            bs = []
            for ln in f.read_text(encoding="utf-8").splitlines():
                q = ln.split()
                if len(q) == 5 and int(q[0]) in CONTACT_SRC:
                    bs.append(tuple(map(float, q[1:])))
            if bs and img_path(f.stem):
                out[f.stem] = bs
    return out


def build(tag, tr, va, data):
    root = HERE / "dataset" / f"contact_{tag}"
    if root.exists():
        shutil.rmtree(root)
    for split, stems in (("train", tr), ("val", va)):
        (root/"images"/split).mkdir(parents=True, exist_ok=True)
        (root/"labels"/split).mkdir(parents=True, exist_ok=True)
        for s in stems:
            shutil.copy2(img_path(s), root/"images"/split/f"{s}.jpg")
            (root/"labels"/split/f"{s}.txt").write_text(
                "\n".join(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
                          for cx, cy, w, h in data[s]) + "\n", encoding="utf-8")
    (root/"data.yaml").write_text(
        f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\n\n"
        "nc: 1\nnames:\n  0: 접촉부\n", encoding="utf-8")
    nb_tr = sum(len(data[s]) for s in tr)
    nb_va = sum(len(data[s]) for s in va)
    print(f"  [{tag}] 학습 {len(tr)}장/{nb_tr}박스 · 검증 {len(va)}장/{nb_va}박스")
    return root


def train(root, name, epochs, model="yolo11s.pt"):
    from ultralytics import YOLO
    m = YOLO(model)
    m.train(data=str(root/"data.yaml"), epochs=epochs, imgsz=320, batch=8,
            project=str(HERE/"runs"), name=name, device="cpu", workers=0, seed=0,
            val=True, plots=False, verbose=False,
            hsv_h=0.0, hsv_s=0.3, hsv_v=0.4, degrees=5.0, translate=0.1,
            scale=0.4, fliplr=0.5, flipud=0.0, mosaic=0.5, erasing=0.0)
    return HERE/"runs"/name/"weights"/"best.pt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    args = ap.parse_args()

    data = gather()
    sess = collections.defaultdict(list)
    for s in data:
        sess["_".join(s.split("_")[:4])].append(s)
    print("접촉부 라벨 보유 세션")
    for k in sorted(sess):
        print(f"  {k:<26} {len(sess[k]):3d}장 / {sum(len(data[s]) for s in sess[k]):4d}박스")

    p3 = [s for s in data if s.split("_")[2] == "P3"]
    p4a = [s for s in data if s.startswith("A1_B1_P4_2022-05-12")]

    print(f"\n{'='*72}\n1단계: P3 학습 -> P4 05-12 검증 (반·세션 모두 다름)\n{'='*72}")
    root = build("stage1", p3, p4a, data)
    w = train(root, "contact_stage1", args.epochs)
    from ultralytics import YOLO
    r = YOLO(str(w)).val(data=str(root/"data.yaml"), imgsz=320, device="cpu",
                         workers=0, plots=False, verbose=False)
    print(f"  P {r.box.mp:.3f}  R {r.box.mr:.3f}  mAP50 {r.box.map50:.3f}  "
          f"mAP50-95 {r.box.map:.3f}")
    tp_est = r.box.mr
    print(f"  -> 다른 반·다른 세션에서 접촉부 재현율 {tp_est:.0%}")

    print(f"\n{'='*72}\n2단계: P3 + P4 05-12 전부 학습 -> 미라벨 세션에 제안\n{'='*72}")
    allstems = p3 + p4a
    va = p4a[: max(1, len(p4a)//5)]          # 체크포인트 선택용 최소 val
    tr = [s for s in allstems if s not in va]
    root2 = build("stage2", tr, va, data)
    w2 = train(root2, "contact_stage2", args.epochs)

    targets = sorted(p.stem for p in (HERE/"_p4"/"images").glob("*.jpg")
                     if p.stem.split("_")[3] in ("2022-06-03", "2022-06-17"))
    print(f"\n제안 대상 {len(targets)}장 (P4 06-03 / 06-17)")
    out = HERE / "out" / "assist_contacts"
    (out/"proposals").mkdir(parents=True, exist_ok=True)
    m = YOLO(str(w2))
    items = []
    cnt = collections.Counter()
    for stem in targets:
        r1 = m.predict(str(img_path(stem)), conf=0.20, imgsz=320,
                       device="cpu", verbose=False)[0]
        h0, w0 = r1.orig_shape
        lines, bs = [], []
        for b in r1.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            conf = float(b.conf.item())
            lines.append(f"13 {(x1+x2)/2/w0:.6f} {(y1+y2)/2/h0:.6f} "
                         f"{(x2-x1)/w0:.6f} {(y2-y1)/h0:.6f}")
            bs.append((x1, y1, x2, y2, conf))
        (out/"proposals"/f"{stem}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        items.append((stem, (w0, h0), bs))
        cnt[len(bs)] += 1

    from xml.sax.saxutils import escape
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>",
             "  <version>1.1</version>", "  <meta>", "    <task>", "      <labels>",
             "        <label>", "          <name>변류기 접촉부</name>",
             "          <type>rectangle</type>", "          <attributes></attributes>",
             "        </label>", "      </labels>", "    </task>", "  </meta>"]
    for i, (stem, (w0, h0), bs) in enumerate(items):
        parts.append(f'  <image id="{i}" name="{escape(stem)}.jpg" width="{w0}" height="{h0}">')
        for x1, y1, x2, y2, _c in bs:
            parts.append(f'    <box label="변류기 접촉부" occluded="0" source="auto" '
                         f'xtl="{x1:.2f}" ytl="{y1:.2f}" xbr="{x2:.2f}" ybr="{y2:.2f}" '
                         f'z_order="0"></box>')
        parts.append("  </image>")
    parts.append("</annotations>")
    (out/"proposals.xml").write_text("\n".join(parts)+"\n", encoding="utf-8")

    nbox = sum(len(b) for _s, _wh, b in items)
    nwith = sum(1 for _s, _wh, b in items if b)
    print(f"  박스가 나온 사진 {nwith}/{len(targets)}장 · 총 제안 {nbox}개 "
          f"(장당 {nbox/max(nwith,1):.1f})")
    print(f"  장당 개수 분포: {dict(sorted(cnt.items()))}")
    print(f"\n-> {out}/proposals.xml   (CVAT 'CVAT for images 1.1' 업로드)")
    print(f"-> {out}/proposals/       (YOLO txt)")
    print("\n참고: 기존 라벨의 접촉부 장당 개수는 P3 2.9 / P4 2.6 이었다.")


if __name__ == "__main__":
    main()
