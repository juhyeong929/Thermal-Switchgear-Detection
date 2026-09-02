"""시험 라벨링 세트(20~30장) 선정 — 규칙 검증용.

목적은 모델 성능이 아니라 **라벨러 간 규칙 일치도**다.
그래서 "쉬운 이미지"를 고르지 않는다. 지금까지 발견한 **실패 유형을 의도적으로 넣는다.**

두 갈래로 뽑는다.

  A. 본 대상군 (시드 400장에서)  — 실제로 라벨링할 데이터. 라벨이 없다.
     단위가 확정된 클래스를 담당하는 반에서 뽑아 4개 클래스를 덮는다.

  B. 난이도 표적군 (기존 라벨 보유 이미지에서) — 실패 유형이 **측정으로 확인된** 이미지.
     truncated / 작은 객체 / 다른 클래스 겹침 / 같은 클래스 밀집.
     기존 라벨은 라벨러에게 보여주지 않는다. 나중에 대조용으로만 쓴다.

**원본과 기존 라벨을 수정하지 않는다.** 목록 CSV 만 만든다.

출력: data/labeling/seed/trial_set.csv
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import classes_v1_26 as v1  # noqa: E402

TARGET_A = 18          # 본 대상군
TARGET_B = 12          # 난이도 표적군
EDGE_EPS = 0.004
TINY = 0.0015
SKIP = {"train.txt", "classes.txt", "obj.names"}
PANEL_RE = re.compile(r"_(P\d+)_")


def xyxy(b):
    _, cx, cy, w, h = b
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def edges(b):
    x0, y0, x1, y1 = xyxy(b)
    return sum([x0 <= EDGE_EPS, y0 <= EDGE_EPS, x1 >= 1 - EDGE_EPS, y1 >= 1 - EDGE_EPS])


def iou(a, b):
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1-ax0)*(ay1-ay0) + (bx1-bx0)*(by1-by0) - inter
    return inter / ua if ua > 0 else 0.0


def load_labeled():
    """정본 + 참고. v2 class_id 로 통일해 읽기만 한다."""
    out = {}
    for f in (paths.LABELING / "reviewed").rglob("*.txt"):
        if f.name in SKIP:
            continue
        bs = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                bs.append((int(p[0]), *[float(x) for x in p[1:5]]))
        if bs:
            m = PANEL_RE.search(f.stem)
            out[f.stem] = ("canonical", m.group(1) if m else "?", bs, None)
    for tag, rel, pid in (("P6", "6ban_existing_labels", "P6"),
                          ("P9", "9ban_existing_labels", "P9")):
        d = paths.PILOT / rel / "obj_train_data"
        for f in sorted(d.glob("*.txt")):
            if f.name in SKIP:
                continue
            bs = []
            for line in f.read_text(encoding="utf-8").splitlines():
                p = line.split()
                if len(p) < 5:
                    continue
                n = v1.new_id(int(float(p[0])), pid)
                if n is not None:
                    bs.append((n, *[float(x) for x in p[1:5]]))
            if bs:
                out[f.stem] = ("reference", pid, bs, d / f"{f.stem}.jpg")
    return out


def difficulty(bs):
    """이 이미지가 어떤 실패 유형을 품고 있는가."""
    flags = []
    if any(edges(b) >= 2 for b in bs):
        flags.append("잘림-2변이상")
    elif sum(1 for b in bs if edges(b) == 1) >= 2:
        flags.append("잘림-1변다수")
    if any(b[3] * b[4] < TINY for b in bs):
        flags.append("작은객체")
    cross = same = False
    for i, a in enumerate(bs):
        for b in bs[i+1:]:
            if iou(a, b) < 0.15:
                continue
            if a[0] == b[0]:
                same = True
            else:
                cross = True
    if cross:
        flags.append("다른클래스겹침")
    if same:
        flags.append("같은클래스겹침")
    cnt = defaultdict(int)
    for b in bs:
        cnt[b[0]] += 1
    if max(cnt.values()) >= 6:
        flags.append("같은클래스밀집")
    return flags


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    # ---- A. 본 대상군 — 시드 400장에서 ----
    with (paths.LABELING / "seed" / "seed_candidates.csv").open(
            encoding="utf-8-sig") as fh:
        seed = list(csv.DictReader(fh))

    # 단위가 확정된 대표 클래스를 담당하는 반 위주로 덮는다
    want = {
        "P1-TR반": ("몰드변압기 접촉부", 4),
        "P3-MOF반": ("변류기 접촉부", 3),
        "P4-MOF&PT반": ("변류기 접촉부", 3),
        "P6-VCB반": ("케이블헤드", 4),
        "P9-MCCB반": ("MCCB 접촉부", 4),
    }
    rows = []
    for panel, (cls, n) in want.items():
        pool = [r for r in seed if r["panel"] == panel]
        # 촬영 세션이 겹치지 않게, RGB 페어 보유를 우선
        pool.sort(key=lambda r: (r["has_rgb_pair"] != "1", r["session"]))
        seen_ses = set()
        for r in pool:
            if len(seen_ses) >= n and r["session"] in seen_ses:
                continue
            if r["session"] in seen_ses:
                continue
            seen_ses.add(r["session"])
            rows.append({
                "group": "A_본대상", "case_id": f"A{len(rows)+1:02d}",
                "panel": panel, "panel_id": r["panel_id"], "camera": r["camera"],
                "session": r["session"], "image_id": r["image_id"],
                "rel_path": r["rel_path"], "source": "3-가공",
                "has_rgb_pair": r["has_rgb_pair"],
                "target_class": cls,
                "difficulty_flags": "",
                "existing_label": "없음",
                "reason": f"{cls} 단위 검증 · 시드 후보",
            })
            if len(seen_ses) >= n:
                break

    # ---- B. 난이도 표적군 — 실패 유형이 측정된 이미지에서 ----
    labeled = load_labeled()
    buckets = defaultdict(list)
    for stem, (grade, pid, bs, jpg) in labeled.items():
        for f in difficulty(bs):
            buckets[f].append((stem, grade, pid, bs, jpg))

    quota = {"잘림-2변이상": 3, "작은객체": 3, "다른클래스겹침": 3,
             "같은클래스겹침": 1, "같은클래스밀집": 2}
    used = set()
    for flag, n in quota.items():
        picked = 0
        for stem, grade, pid, bs, jpg in sorted(buckets.get(flag, [])):
            if stem in used:
                continue
            used.add(stem)
            picked += 1
            classes = sorted({v2.BY_ID[b[0]].canonical_name for b in bs})
            rows.append({
                "group": "B_난이도", "case_id": f"B{picked:02d}_{flag}",
                "panel": next((p for p in v2.PANEL_CLASSES
                               if p.startswith(pid + "-")), pid),
                "panel_id": pid, "camera": "IR1",
                "session": "", "image_id": stem,
                "rel_path": str(jpg.relative_to(paths.PILOT)) if jpg else "",
                "source": "pilot(참고)" if grade == "reference" else "3-가공(정본)",
                "has_rgb_pair": "",
                "target_class": " / ".join(classes),
                "difficulty_flags": " ".join(difficulty(bs)),
                "existing_label": f"{grade} {len(bs)}박스 (라벨러에게 비공개)",
                "reason": f"실패 유형 {flag} 이 측정으로 확인된 이미지",
            })
            if picked >= n:
                break

    out = paths.LABELING / "seed" / "trial_set.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    a = [r for r in rows if r["group"] == "A_본대상"]
    b = [r for r in rows if r["group"] == "B_난이도"]
    print(f"시험 라벨링 세트 {len(rows)}장  (A 본대상 {len(a)} / B 난이도 {len(b)})\n")
    print(f"{'구분':<10}{'반':<16}{'대상 클래스':<28}{'난이도':<26}")
    for r in rows:
        print(f"{r['case_id']:<10}{r['panel']:<16}{r['target_class'][:26]:<28}"
              f"{r['difficulty_flags']:<26}")
    print(f"\n덮은 실패 유형: "
          f"{sorted({f for r in b for f in r['difficulty_flags'].split()})}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
