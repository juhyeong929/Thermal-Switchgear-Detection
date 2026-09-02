"""OQ-006 / 접촉부 계열 경계 — 사례 분석.

**원본과 기존 라벨을 수정하지 않는다.** 읽기만 하고 시각 자료는 experiments 아래에 새로 만든다.

접촉부는 클래스가 여러 개다. 하나에서 관찰한 규칙을 전부에 일반화하지 않기 위해
**정본(P1/P3/P4)과 참고(P9)를 나눠서** 따로 집계한다.

  canonical  몰드변압기 접촉부 · 변압기 접촉부 · 변류기 접촉부   (P1/P3/P4)
  reference  MCCB 접촉부 · ACB 접촉부                          (P9)

출력: reports/data_audit/contact_boundary_stats.csv
      reports/data_audit/contact_case_index.csv
      experiments/.../contact_boundary/*.png
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

OUT = (paths.PROJECT / "experiments" / "seed_selection" / "newlabel_probe"
       / "contact_boundary")
PANEL_RE = re.compile(r"_(P\d+)_")
SKIP = {"train.txt", "val.txt", "classes.txt", "obj.names"}
SCALE = 3

# v2 class_id 기준 접촉부 계열
CONTACT_IDS = {
    2: "몰드변압기 접촉부", 4: "LBS 1차측 접촉부", 12: "분기 접촉부",
    14: "VCB 접촉부", 19: "인입선로 접촉부", 22: "LBS 2차측 접촉부",
    23: "변압기 접촉부", 24: "변류기 접촉부", 25: "CT 접촉부",
    26: "ACB 접촉부", 27: "MCCB 접촉부",
}
# 각 접촉부가 붙어 있는 '본체' 클래스 — 본체 대비 크기를 재기 위함
BODY_OF = {2: 1, 23: 7, 24: 8, 27: 18, 26: None, 14: None}


def load_canonical():
    """승계된 v2 정본 라벨 (P1/P3/P4)."""
    out = defaultdict(list)
    for f in (paths.LABELING / "reviewed").rglob("*.txt"):
        if f.name in SKIP:
            continue
        m = PANEL_RE.search(f.stem)
        pid = m.group(1) if m else "?"
        boxes = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                boxes.append((int(p[0]), *[float(x) for x in p[1:5]]))
        if boxes:
            out[(pid, f.stem)] = boxes
    return out


def load_reference_p9():
    """참고 라벨 P9 — 구 26 스키마를 v2 id 로 읽어들이기만 한다 (파일은 그대로)."""
    from schemas import classes_v1_26 as v1
    src = paths.PILOT / "9ban_existing_labels" / "obj_train_data"
    out = {}
    for f in sorted(src.glob("*.txt")):
        if f.name in SKIP:
            continue
        boxes = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            new = v1.new_id(int(float(p[0])), "P9")
            if new is None:
                continue
            boxes.append((new, *[float(x) for x in p[1:5]]))
        if boxes:
            out[("P9", f.stem)] = boxes
    return out


def stats(boxes):
    if not boxes:
        return {}
    w = np.array([b[3] for b in boxes])
    h = np.array([b[4] for b in boxes])
    a = w * h
    return {
        "n": len(boxes),
        "area_median": round(float(np.median(a)), 5),
        "area_p05": round(float(np.percentile(a, 5)), 5),
        "area_p95": round(float(np.percentile(a, 95)), 5),
        "aspect_median": round(float(np.median(w / np.maximum(h, 1e-9))), 3),
        "aspect_iqr": round(float(np.percentile(w / np.maximum(h, 1e-9), 75)
                                 - np.percentile(w / np.maximum(h, 1e-9), 25)), 3),
    }


def render(img_path, boxes, dst, title=""):
    im = cv2.imdecode(np.frombuffer(img_path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        return False
    im = cv2.resize(im, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    H, W = im.shape[:2]
    for cid, cx, cy, w, h in boxes:
        col = (255, 255, 0) if cid in CONTACT_IDS else (0, 200, 0)
        cv2.rectangle(im, (int((cx - w / 2) * W), int((cy - h / 2) * H)),
                      (int((cx + w / 2) * W), int((cy + h / 2) * H)), col, 2)
    if title:
        cv2.rectangle(im, (0, 0), (W - 1, 26), (0, 0, 0), -1)
        cv2.putText(im, title, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", im)[1].tofile(str(dst))
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    canon = load_canonical()
    ref = load_reference_p9()

    rows = []
    for grade, data in (("canonical", canon), ("reference", ref)):
        per = defaultdict(list)
        for (pid, stem), boxes in data.items():
            for b in boxes:
                if b[0] in CONTACT_IDS:
                    per[(pid, b[0])].append(b)
        for (pid, cid), bs in sorted(per.items()):
            s = stats(bs)
            # 본체 대비 크기 — 본체 클래스가 같은 이미지에 있을 때만
            body = BODY_OF.get(cid)
            ratios = []
            if body is not None:
                for (p2, stem), boxes in data.items():
                    if p2 != pid:
                        continue
                    bodies = [x for x in boxes if x[0] == body]
                    conts = [x for x in boxes if x[0] == cid]
                    if not bodies or not conts:
                        continue
                    ba = max(x[3] * x[4] for x in bodies)
                    for c in conts:
                        ratios.append((c[3] * c[4]) / max(ba, 1e-9))
            rows.append({
                "grade": grade, "panel_id": pid, "class_id": cid,
                "class_name": CONTACT_IDS[cid],
                **s,
                "body_class": v2.BY_ID[body].canonical_name if body else "",
                "contact_vs_body_median": round(float(np.median(ratios)), 3) if ratios else "",
                "contact_vs_body_n": len(ratios),
            })

    # 이미지당 접촉부 박스 수 — '단자군 단위'인지 '개별 단자'인지의 신호
    per_img = []
    for grade, data in (("canonical", canon), ("reference", ref)):
        cnt = defaultdict(list)
        for (pid, stem), boxes in data.items():
            for cid in {b[0] for b in boxes if b[0] in CONTACT_IDS}:
                cnt[(pid, cid)].append(sum(1 for b in boxes if b[0] == cid))
        for (pid, cid), c in sorted(cnt.items()):
            per_img.append({
                "grade": grade, "panel_id": pid, "class_id": cid,
                "class_name": CONTACT_IDS[cid], "images": len(c),
                "per_image_median": int(np.median(c)),
                "per_image_p90": int(np.percentile(c, 90)),
                "per_image_max": int(max(c)),
            })

    with (paths.AUDIT / "contact_boundary_stats.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"{'등급':<10}{'반':<5}{'클래스':<16}{'n':>6}{'면적중앙':>9}{'종횡비':>7}"
          f"{'IQR':>7}{'본체대비':>9}")
    for r in rows:
        print(f"{r['grade']:<10}{r['panel_id']:<5}{r['class_name']:<16}{r['n']:>6}"
              f"{r['area_median']:>9.4f}{r['aspect_median']:>7.2f}{r['aspect_iqr']:>7.2f}"
              f"{str(r['contact_vs_body_median']):>9}")

    print(f"\n{'등급':<10}{'반':<5}{'클래스':<16}{'이미지':>7}{'장당중앙':>9}{'p90':>6}{'최대':>6}")
    for r in per_img:
        print(f"{r['grade']:<10}{r['panel_id']:<5}{r['class_name']:<16}{r['images']:>7}"
              f"{r['per_image_median']:>9}{r['per_image_p90']:>6}{r['per_image_max']:>6}")

    # ---- 사례 렌더 ----
    idx = []
    # P9 MCCB 계열 — 본체+단자군 패턴이 뚜렷한 장 (본체 1~3, 접촉부 2~6)
    cands = []
    for (pid, stem), boxes in ref.items():
        nb = sum(1 for b in boxes if b[0] == 18)
        nc = sum(1 for b in boxes if b[0] == 27)
        if 1 <= nb <= 3 and 2 <= nc <= 6:
            cands.append((abs(nc - nb * 2), stem, nb, nc, boxes))
    cands.sort()
    for i, (_, stem, nb, nc, boxes) in enumerate(cands[:3]):
        src = paths.PILOT / "9ban_existing_labels" / "obj_train_data" / f"{stem}.jpg"
        if render(src, boxes, OUT / f"p9_mccb_{i+1}.png",
                  f"P9 reference | MCCB {nb} + MCCB contact {nc}"):
            idx.append({"case": f"p9_mccb_{i+1}", "grade": "reference", "panel": "P9",
                        "stem": stem, "bodies": nb, "contacts": nc,
                        "note": "본체 1개 + 좌우 단자군 각 1개 패턴 확인용"})
    # P1 몰드변압기 접촉부 — 정본
    c1 = []
    for (pid, stem), boxes in canon.items():
        if pid != "P1":
            continue
        nc = sum(1 for b in boxes if b[0] == 2)
        nb = sum(1 for b in boxes if b[0] == 1)
        if nc >= 2 and nb >= 1:
            c1.append((-nc, stem, nb, nc, boxes))
    c1.sort()
    for i, (_, stem, nb, nc, boxes) in enumerate(c1[:3]):
        src = paths.BACKUP / "P1_A3검수완료"
        img = next((p for p in (paths.PROCESSED / "P1-TR반").rglob(f"{stem}.jpg")), None)
        if img and render(img, boxes, OUT / f"p1_mold_{i+1}.png",
                          f"P1 canonical | epoxy {nb} + mold TR contact {nc}"):
            idx.append({"case": f"p1_mold_{i+1}", "grade": "canonical", "panel": "P1",
                        "stem": stem, "bodies": nb, "contacts": nc,
                        "note": "정본 접촉부 관행 확인용"})
    # P3/P4 변류기 접촉부 — 정본
    c3 = []
    for (pid, stem), boxes in canon.items():
        if pid not in ("P3", "P4"):
            continue
        nc = sum(1 for b in boxes if b[0] == 24)
        if nc >= 2:
            c3.append((-nc, pid, stem, nc, boxes))
    c3.sort()
    for i, (_, pid, stem, nc, boxes) in enumerate(c3[:2]):
        folder = "P3-MOF반" if pid == "P3" else "P4-MOF&PT반"
        img = next((p for p in (paths.PROCESSED / folder).rglob(f"{stem}.jpg")), None)
        if img and render(img, boxes, OUT / f"{pid.lower()}_ct_{i+1}.png",
                          f"{pid} canonical | CT contact {nc}"):
            idx.append({"case": f"{pid.lower()}_ct_{i+1}", "grade": "canonical",
                        "panel": pid, "stem": stem, "bodies": "", "contacts": nc,
                        "note": "정본 변류기 접촉부 관행 확인용"})

    with (paths.AUDIT / "contact_case_index.csv").open(
            "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(idx[0]))
        w.writeheader()
        w.writerows(idx)
    print(f"\n사례 {len(idx)}건 -> {OUT}")
    for r in idx:
        print(f"  {r['case']:<14}{r['grade']:<10}{r['stem']}")


if __name__ == "__main__":
    main()
