"""정본 감사 — 표본 시각 검증. **READ-ONLY.**

수치만으로 결론내지 않는다. 지적된 유형마다 실제 이미지를 열어 확인한다.
**원본 이미지에 그리지 않는다.** 읽어서 메모리에서 그린 뒤 experiments 에 새로 저장한다.

출력: experiments/data_audit/canonical/*.png
      reports/data_audit/canonical_visual_index.csv
"""

import csv
import random
import re
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

OUT = paths.PROJECT / "experiments" / "data_audit" / "canonical"
SKIPNAME = {"train.txt", "val.txt", "classes.txt", "obj.names"}
PALETTE = [(0, 0, 255), (0, 200, 0), (255, 255, 0), (255, 0, 255),
           (0, 140, 255), (255, 128, 0), (128, 0, 255), (0, 255, 128)]


def load():
    inv = {}
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] == "IR":
                inv[Path(r["rel_path"]).stem] = paths.PROCESSED / r["rel_path"]
    lab = {}
    for f in (paths.LABELING / "reviewed").rglob("*.txt"):
        if f.name in SKIPNAME:
            continue
        bs = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                bs.append((int(p[0]), *[float(x) for x in p[1:5]]))
        lab[f.stem] = bs
    return inv, lab


def draw(inv, lab, stem, highlight=(), scale=3, title=""):
    src = inv.get(stem)
    if src is None or not src.exists():
        return None
    im = cv2.imdecode(np.frombuffer(src.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    im = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    H, W = im.shape[:2]
    for k, (c, cx, cy, w, h) in enumerate(lab[stem]):
        col = PALETTE[c % len(PALETTE)]
        hit = k in highlight
        cv2.rectangle(im, (int((cx-w/2)*W), int((cy-h/2)*H)),
                      (int((cx+w/2)*W), int((cy+h/2)*H)), col, 3 if hit else 1)
        tag = f"{k}" + ("!" if hit else "")
        cv2.putText(im, tag, (int((cx-w/2)*W)+3, int((cy-h/2)*H)+17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2 if hit else 1, cv2.LINE_AA)
    if title:
        cv2.rectangle(im, (0, 0), (W-1, 26), (0, 0, 0), -1)
        cv2.putText(im, title, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 255, 255), 1, cv2.LINE_AA)
    return im


def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", im)[1].tofile(str(path))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(4)
    inv, lab = load()
    with (paths.AUDIT / "canonical_audit_detail.csv").open(encoding="utf-8-sig") as fh:
        detail = list(csv.DictReader(fh))

    index = []

    def emit(kind, stem, hl, note, scale=3):
        im = draw(inv, lab, stem, hl, scale, f"{kind} | {stem}")
        if im is None:
            return
        p = OUT / f"{kind}_{len(index)+1:02d}_{stem}.png"
        save(im, p)
        index.append({"case_type": kind, "file": p.name, "image": stem,
                      "highlight_boxes": " ".join(map(str, hl)), "note": note})

    # 1) 같은 클래스 포함관계 (FAIL) — IoU 큰 순
    fails = [d for d in detail if d["status"] == "FAIL"]
    fails.sort(key=lambda d: -float(d["detail"].split()[-1]))
    for d in fails[:3]:
        hl = tuple(int(v) for v in d["box_index"].split("+"))
        emit("dup_FAIL", d["image"], hl, f"{d['class_name']} {d['detail']}")

    # 2) 같은 클래스 중첩 의심 (SUSPECT)
    sus = [d for d in detail
           if d["status"] == "SUSPECT" and d["audit_rule"] == "같은 클래스 중복"]
    for d in sus[:2]:
        hl = tuple(int(v) for v in d["box_index"].split("+"))
        emit("dup_SUSPECT", d["image"], hl, f"{d['class_name']} {d['detail']}")

    # 3) 초소형 — 가장 작은 것부터, 이미지 중복 없이
    tiny = [d for d in detail if d["audit_rule"] == "초소형(candidate)"]
    tiny.sort(key=lambda d: float(re.search(r"면적 ([\d.]+)", d["reason"]).group(1)))
    seen = set()
    for d in tiny:
        if d["image"] in seen:
            continue
        seen.add(d["image"])
        emit("tiny", d["image"], (int(d["box_index"]),),
             f"{d['class_name']} {d['reason'][:46]}", scale=4)
        if len(seen) >= 3:
            break

    # 4) 잘림 2변 이상 (UNDETERMINABLE)
    tr = [d for d in detail if d["audit_rule"] == "잘림 30% 규칙"]
    for d in tr[:2]:
        emit("truncated", d["image"], (int(d["box_index"]),),
             f"{d['class_name']} {d['detail']}")

    # 5) CONTACT_POINT 정상 대표 — 몰드변압기 접촉부·변류기 접촉부
    for cid, kind in ((2, "contactpoint_P1"), (24, "contactpoint_P3P4")):
        pool = [k for k, v in lab.items() if sum(1 for b in v if b[0] == cid) >= 3]
        if not pool:
            continue
        for stem in random.sample(pool, min(2, len(pool))):
            hl = tuple(i for i, b in enumerate(lab[stem]) if b[0] == cid)
            emit(kind, stem, hl,
                 f"{v2.BY_ID[cid].canonical_name} {len(hl)}개 — CONTACT_POINT 대표 사례")

    p = paths.AUDIT / "canonical_visual_index.csv"
    with p.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(index[0]))
        w.writeheader()
        w.writerows(index)

    print(f"표본 {len(index)}장 -> {OUT}")
    for r in index:
        print(f"  {r['case_type']:<18}{r['file']}")
    print(f"색인 -> {p.name}")


if __name__ == "__main__":
    main()
