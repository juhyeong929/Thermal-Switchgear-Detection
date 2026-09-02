"""OQ-009 — 정본(canonical) 라벨 감사. **READ-ONLY.**

목적은 하나다.

    현재 canonical 라벨이 현재 규격서와 일치하는가?

**규격을 기준으로 라벨을 감사한다.** 그 반대가 아니다.
라벨과 규격이 어긋나면 라벨을 문제로 기록하고, 규격서를 라벨에 맞춰 고치지 않는다.

라벨 파일을 읽기만 한다. 수정·추가·삭제하지 않는다.

판정 상태
    PASS            규칙을 지켰다
    FAIL            명백히 어겼다
    SUSPECT         어긴 것으로 보이나 좌표만으로 확정할 수 없다
    UNDETERMINABLE  좌표만으로는 판정 자체가 불가능하다
    NOT_APPLICABLE  그 규칙이 이 대상에 해당하지 않는다

출력: reports/data_audit/canonical_audit_summary.csv   규칙별 요약
      reports/data_audit/canonical_audit_detail.csv    개별 지적 사항
      reports/data_audit/canonical_class_audit.csv     클래스별 감사
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import labeling_rules as rules  # noqa: E402

PANEL_RE = re.compile(r"_(P\d+)_")
SKIPNAME = {"train.txt", "val.txt", "classes.txt", "obj.names"}
EDGE_EPS = 0.004        # 프레임 접촉으로 볼 여유 (320px 기준 약 1.3px)
DUP_IOU = 0.60          # 같은 클래스 중첩 의심 하한
CONTAIN_TOL = 0.01      # 포함관계 판정 여유
CANDIDATE_SMALL = 0.003  # 규격서의 candidate_threshold. 공식 임계값이 아니다

PID2PANEL = {p.split("-")[0]: p for p in v2.PANEL_CLASSES}


def load_canonical():
    """{(panel_id, stem): [(cls, cx, cy, w, h), ...]} — 승계된 v2 정본."""
    out = {}
    for f in sorted((paths.LABELING / "reviewed").rglob("*.txt")):
        if f.name in SKIPNAME:
            continue
        m = PANEL_RE.search(f.stem)
        pid = m.group(1) if m else "?"
        bs = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                bs.append((int(p[0]), *[float(x) for x in p[1:5]]))
        out[(pid, f.stem)] = bs
    return out


def xyxy(b):
    _, cx, cy, w, h = b
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def iou(a, b):
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1-ax0)*(ay1-ay0) + (bx1-bx0)*(by1-by0) - inter
    return inter / ua if ua > 0 else 0.0


def contains(a, b, tol=CONTAIN_TOL):
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    return (ax0 - tol <= bx0 and ay0 - tol <= by0
            and ax1 + tol >= bx1 and ay1 + tol >= by1)


def edges(b):
    x0, y0, x1, y1 = xyxy(b)
    return {"top": y0 <= EDGE_EPS, "bottom": y1 >= 1 - EDGE_EPS,
            "left": x0 <= EDGE_EPS, "right": x1 >= 1 - EDGE_EPS}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    data = load_canonical()
    total = sum(len(v) for v in data.values())
    print(f"감사 대상 정본 {total:,} bbox / {len(data):,} 이미지 "
          f"/ 반 {len({p for p, _ in data})}개\n")

    detail = []          # 개별 지적 사항
    def add(stem, pid, idx, cls_id, rule, status, reason, extra=""):
        detail.append({
            "panel_id": pid, "image": stem, "box_index": idx,
            "class_id": cls_id,
            "class_name": v2.BY_ID[cls_id].canonical_name if cls_id in v2.BY_ID else "?",
            "audit_rule": rule, "status": status, "reason": reason, "detail": extra,
        })

    # ---------- 규칙별 카운터 ----------
    R = defaultdict(lambda: Counter())

    for (pid, stem), boxes in data.items():
        panel = PID2PANEL.get(pid, "")
        allowed = set(v2.PANEL_CLASSES.get(panel, []))

        for i, b in enumerate(boxes):
            cid = b[0]
            cname = v2.BY_ID[cid].class_name if cid in v2.BY_ID else "?"
            area = b[3] * b[4]

            # --- 규칙 1. 항상 제외 클래스가 라벨됐는가 ---
            if cname in rules.ALWAYS_EXCLUDED:
                R["제외 클래스 라벨"]["FAIL"] += 1
                add(stem, pid, i, cid, "제외 클래스 라벨", "FAIL",
                    "어떤 반에서도 라벨링하지 않기로 한 클래스다")
            else:
                R["제외 클래스 라벨"]["PASS"] += 1

            # --- 규칙 2. 그 반의 후보 클래스인가 ---
            if not panel:
                R["반 후보 클래스"]["UNDETERMINABLE"] += 1
            elif cname in allowed:
                R["반 후보 클래스"]["PASS"] += 1
            else:
                R["반 후보 클래스"]["FAIL"] += 1
                add(stem, pid, i, cid, "반 후보 클래스", "FAIL",
                    f"{panel} 의 후보 목록에 없는 클래스",
                    f"후보: {', '.join(sorted(allowed))}")

            # --- 규칙 3. 초소형 (공식 임계값 없음 — candidate 만 표시) ---
            if area < CANDIDATE_SMALL:
                R["초소형(candidate)"]["SUSPECT"] += 1
                add(stem, pid, i, cid, "초소형(candidate)", "SUSPECT",
                    f"정규화 면적 {area:.5f} < candidate_threshold {CANDIDATE_SMALL}",
                    "공식 임계값이 아니다. 식별 가능성 기준이므로 좌표만으로 확정 불가")
            else:
                # 공식 임계값이 없으므로 PASS/FAIL 로 세지 않는다.
                # 준수율을 내면 "임계값이 있는 규칙"처럼 읽혀 오해를 부른다.
                R["초소형(candidate)"]["NOT_APPLICABLE"] += 1

            # --- 규칙 4. 잘림 30% — 좌표만으로는 판정 불가 ---
            e = edges(b)
            n_edge = sum(e.values())
            if n_edge == 0:
                R["잘림 30% 규칙"]["NOT_APPLICABLE"] += 1
            else:
                R["잘림 30% 규칙"]["UNDETERMINABLE"] += 1
                if n_edge >= 2:
                    add(stem, pid, i, cid, "잘림 30% 규칙", "UNDETERMINABLE",
                        f"프레임 {n_edge}변 접촉 — 원래 면적을 알 수 없어 30% 판정 불가",
                        " ".join(k for k, v in e.items() if v))

        # --- 규칙 5. 같은 클래스 중복 / 포함 ---
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] != b[0]:
                    R["다른 클래스 겹침"]["NOT_APPLICABLE"] += 1
                    continue
                v = iou(a, b)
                if contains(a, b) or contains(b, a):
                    R["같은 클래스 중복"]["FAIL"] += 1
                    add(stem, pid, f"{i}+{j}", a[0], "같은 클래스 중복", "FAIL",
                        "한 박스가 다른 박스를 완전히 포함한다 — 같은 인스턴스 이중 라벨",
                        f"IoU {v:.3f}")
                elif v >= DUP_IOU:
                    R["같은 클래스 중복"]["SUSPECT"] += 1
                    add(stem, pid, f"{i}+{j}", a[0], "같은 클래스 중복", "SUSPECT",
                        f"같은 클래스 IoU {v:.3f} — 같은 인스턴스인지 좌표만으로 확정 불가",
                        "나란한 동종 부품이 겹쳐 보이는 경우일 수 있다")
                else:
                    R["같은 클래스 중복"]["PASS"] += 1

    # ---------- 클래스별 감사 ----------
    per_cls = defaultdict(lambda: {"n": 0, "area": [], "ar": [], "edge": 0,
                                   "small": 0, "panels": Counter()})
    for (pid, stem), boxes in data.items():
        for b in boxes:
            d = per_cls[b[0]]
            d["n"] += 1
            d["area"].append(b[3] * b[4])
            d["ar"].append(b[3] / max(b[4], 1e-9))
            d["panels"][pid] += 1
            if any(edges(b).values()):
                d["edge"] += 1
            if b[3] * b[4] < CANDIDATE_SMALL:
                d["small"] += 1

    # 이미지당 인스턴스 수 — annotation_unit 준수 정황
    per_img = defaultdict(list)
    for (pid, stem), boxes in data.items():
        c = Counter(b[0] for b in boxes)
        for cid, n in c.items():
            per_img[cid].append(n)

    cls_rows = []
    for cid, d in sorted(per_cls.items()):
        c = v2.BY_ID[cid]
        unit = v2.annotation_unit(c.class_name)
        a = np.array(d["area"])
        counts = per_img[cid]
        # annotation_unit 감사 — 좌표만으로는 '접속점 하나인가'를 확정할 수 없다
        if unit == v2.UNIT_UNKNOWN:
            status, why = "NOT_AUDITABLE", "annotation_unit 미확정 — 감사 기준이 없다"
        elif unit == v2.CONTACT_POINT:
            status = "SUSPECT" if np.median(counts) < 2 else "CONSISTENT"
            why = (f"장당 중앙 {np.median(counts):.0f}개. "
                   "접속점 단위라면 한 장에 여러 개가 나오는 것이 정상이다. "
                   "개별 접속점 대응 여부는 좌표만으로 확정 불가")
        else:
            status, why = "NOT_AUDITABLE", "좌표만으로 부품 단위 준수를 판정할 수 없다"
        cls_rows.append({
            "class_id": cid, "class_name": c.canonical_name,
            "annotation_unit": unit, "boxes": d["n"],
            "panels": " ".join(f"{k}:{v}" for k, v in sorted(d["panels"].items())),
            "area_p01": round(float(np.percentile(a, 1)), 5),
            "area_p05": round(float(np.percentile(a, 5)), 5),
            "area_median": round(float(np.median(a)), 5),
            "area_p95": round(float(np.percentile(a, 95)), 5),
            "aspect_median": round(float(np.median(d["ar"])), 3),
            "small_candidate": d["small"],
            "edge_touch": d["edge"],
            "per_image_median": int(np.median(counts)),
            "per_image_max": int(max(counts)),
            "unit_audit_status": status, "unit_audit_reason": why,
        })

    # ---------- 산출물 ----------
    paths.AUDIT.mkdir(parents=True, exist_ok=True)

    sum_rows = []
    for rule, c in R.items():
        tot = sum(c.values())
        sum_rows.append({
            "audit_rule": rule, "checked": tot,
            "PASS": c["PASS"], "FAIL": c["FAIL"], "SUSPECT": c["SUSPECT"],
            "UNDETERMINABLE": c["UNDETERMINABLE"],
            "NOT_APPLICABLE": c["NOT_APPLICABLE"],
            "판정가능 분모": c["PASS"] + c["FAIL"],
            "판정가능 준수율": (f"{c['PASS']/(c['PASS']+c['FAIL']):.4f}"
                          if c["PASS"] + c["FAIL"] else ""),
            "비고": ("공식 임계값 없음 — PASS/FAIL 로 세지 않는다"
                    if rule.startswith("초소형") else
                    "좌표만으로 판정 불가 — 규칙의 성질"
                    if rule.startswith("잘림") else
                    "다른 클래스끼리의 겹침은 규격상 정상"
                    if rule.startswith("다른 클래스") else ""),
        })
    for name, rows in (("canonical_audit_summary.csv", sum_rows),
                       ("canonical_audit_detail.csv", detail),
                       ("canonical_class_audit.csv", cls_rows)):
        p = paths.AUDIT / name
        with p.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    # ---------- 콘솔 ----------
    print(f"{'규칙':<20}{'검사':>8}{'PASS':>8}{'FAIL':>7}{'SUSPECT':>9}"
          f"{'판정불가':>9}{'해당없음':>9}")
    for r in sum_rows:
        print(f"{r['audit_rule']:<20}{r['checked']:>8,}{r['PASS']:>8,}"
              f"{r['FAIL']:>7,}{r['SUSPECT']:>9,}"
              f"{r['UNDETERMINABLE']:>9,}{r['NOT_APPLICABLE']:>9,}")

    print(f"\n{'클래스':<20}{'단위':<15}{'박스':>6}{'장당':>5}{'면적p05':>9}"
          f"{'초소형':>7}{'접촉':>6}  단위감사")
    for r in cls_rows:
        print(f"{r['class_name']:<20}{r['annotation_unit']:<15}{r['boxes']:>6,}"
              f"{r['per_image_median']:>5}{r['area_p05']:>9.4f}"
              f"{r['small_candidate']:>7}{r['edge_touch']:>6}  {r['unit_audit_status']}")

    fails = [d for d in detail if d["status"] == "FAIL"]
    print(f"\n명백한 위반(FAIL) {len(fails)}건")
    for r, n in Counter(d["audit_rule"] for d in fails).most_common():
        print(f"  {r:<20}{n}")
    print(f"의심(SUSPECT) {sum(1 for d in detail if d['status']=='SUSPECT')}건")
    print(f"판정 불가 {sum(1 for d in detail if d['status']=='UNDETERMINABLE')}건")
    print(f"\n-> canonical_audit_summary/detail/class_audit.csv")


if __name__ == "__main__":
    main()
