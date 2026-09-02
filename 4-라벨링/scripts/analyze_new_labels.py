"""신규 반입 라벨(6ban / 9ban)을 분석한다. **라벨을 수정하지 않는다. 읽기만 한다.**

목적은 승계가 아니라 파악이다. 기존 정본(P1/P3/P4)과 무엇이 어떻게 다른지,
경계 규칙(OQ-006) 확정에 쓸 수 있는 사례가 무엇인지 뽑는다.

출력: reports/data_audit/newlabels_summary.csv     소스별 요약
      reports/data_audit/newlabels_class_dist.csv  클래스별 분포
      reports/data_audit/newlabels_boxstats.csv    클래스별 박스 기하 통계
      reports/data_audit/newlabels_edge_cases.csv  프레임 접촉·초소형·중첩 사례
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
from schemas import classes_v1_26 as v1  # noqa: E402

SOURCES = [("6ban", "6ban_existing_labels"), ("9ban", "9ban_existing_labels")]
SKIP = {"train.txt", "val.txt", "classes.txt", "obj.names"}
PANEL_RE = re.compile(r"_(P\d+)_")

EDGE_EPS = 0.004      # 정규화 좌표에서 프레임 경계로 볼 여유 (320px 기준 약 1.3px)
TINY_AREA = 0.0015    # 전체 면적 대비 이 미만이면 '초소형'
IOU_OVERLAP = 0.60    # 같은 클래스끼리 이 이상 겹치면 경계 구분이 어려운 사례


def load_source(rel):
    root = paths.PILOT / rel
    names = []
    n = root / "obj.names"
    if n.exists():
        names = [x.strip() for x in n.read_text(encoding="utf-8").splitlines() if x.strip()]
    recs = {}
    for f in sorted(root.rglob("*.txt")):
        if f.name in SKIP:
            continue
        boxes = []
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            try:
                boxes.append((int(float(p[0])), *[float(x) for x in p[1:5]]))
            except ValueError:
                continue
        recs[f.stem] = boxes
    imgs = {f.stem for f in root.rglob("*.jpg")}
    return names, recs, imgs


def xyxy(b):
    _, cx, cy, w, h = b
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def iou(a, b):
    ax0, ay0, ax1, ay1 = xyxy(a)
    bx0, by0, bx1, by1 = xyxy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def edges_touched(b):
    x0, y0, x1, y1 = xyxy(b)
    return sum([x0 <= EDGE_EPS, y0 <= EDGE_EPS,
                x1 >= 1 - EDGE_EPS, y1 >= 1 - EDGE_EPS])


def canonical_reference():
    """기존 정본(P1/P3/P4) v2 라벨을 같은 형식으로 읽어 비교 기준을 만든다."""
    recs = defaultdict(list)
    for f in (paths.LABELING / "reviewed").rglob("*.txt"):
        if f.name in SKIP:
            continue
        m = PANEL_RE.search(f.stem)
        pid = m.group(1) if m else "?"
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                recs[pid].append((int(p[0]), *[float(x) for x in p[1:5]]))
    return recs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    paths.AUDIT.mkdir(parents=True, exist_ok=True)

    # 중복 제거 메타 — 이 이미지들이 대표인지 중복인지 확인한다
    dd = {}
    p = paths.DEDUP / "dedup_metadata.csv"
    if p.exists():
        with p.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                dd[Path(r["rel_path"]).stem] = r

    summary, dist_rows, box_rows, edge_rows = [], [], [], []
    all_boxes = {}

    for tag, rel in SOURCES:
        names, recs, imgs = load_source(rel)
        panels = Counter(PANEL_RE.search(s).group(1) if PANEL_RE.search(s) else "?"
                         for s in recs)
        cls = Counter(b[0] for v in recs.values() for b in v)
        nbox = sum(len(v) for v in recs.values())
        empty = sum(1 for v in recs.values() if not v)
        all_boxes[tag] = recs

        # 스키마가 pilot 26개와 같은지
        same_schema = names == [v1.OLD_BY_ID[i][1] for i in range(26)]

        in_dd = sum(1 for s in recs if s in dd)
        as_rep = sum(1 for s in recs if dd.get(s, {}).get("is_representative") == "1")
        sessions = {dd[s]["session_key"] for s in recs if s in dd}

        summary.append({
            "source": tag, "rel_path": rel,
            "label_files": len(recs), "image_files": len(imgs),
            "empty_label_files": empty, "boxes": nbox,
            "boxes_per_image": round(nbox / max(1, len(recs) - empty), 2),
            "panels": " ".join(f"{k}:{v}" for k, v in sorted(panels.items())),
            "distinct_class_ids": len(cls),
            "class_ids_used": " ".join(str(c) for c in sorted(cls)),
            "schema_matches_pilot26": int(same_schema),
            "in_dedup_index": in_dd,
            "is_representative": as_rep,
            "capture_sessions": len(sessions),
        })

        for cid, n in sorted(cls.items()):
            old_key, old_ko = v1.OLD_BY_ID[cid]
            newname, kind, _ = v1.MIGRATION[cid]
            pid = max(panels, key=panels.get)
            if kind == "split":
                target = v1.SPLIT_BY_PANEL.get(pid)
                new_ko = v2.BY_NAME[target].canonical_name if target else "(미정)"
                new_id = v2.BY_NAME[target].class_id if target else ""
            else:
                new_ko = v2.BY_NAME[newname].canonical_name
                new_id = v2.BY_NAME[newname].class_id
            folder = next((f for f in v2.PANEL_CLASSES if f.startswith(pid + "-")), "")
            allowed = (newname in v2.PANEL_CLASSES.get(folder, [])
                       if kind != "split" else target in v2.PANEL_CLASSES.get(folder, []))
            dist_rows.append({
                "source": tag, "panel": pid, "old_class_id": cid,
                "old_class_ko": old_ko, "boxes": n,
                "share": f"{n/nbox:.3f}",
                "images_with_it": sum(1 for v in recs.values()
                                      if any(b[0] == cid for b in v)),
                "v2_class_id": new_id, "v2_class_ko": new_ko,
                "migration_type": kind,
                "in_v2_panel_candidates": int(bool(allowed)),
            })

        # 박스 기하 통계
        per_cls = defaultdict(list)
        for v in recs.values():
            for b in v:
                per_cls[b[0]].append(b)
        for cid, bs in sorted(per_cls.items()):
            w = np.array([b[3] for b in bs])
            h = np.array([b[4] for b in bs])
            a = w * h
            ar = w / np.maximum(h, 1e-9)
            box_rows.append({
                "source": tag, "old_class_id": cid,
                "old_class_ko": v1.OLD_BY_ID[cid][1], "n": len(bs),
                "area_median": round(float(np.median(a)), 5),
                "area_p05": round(float(np.percentile(a, 5)), 5),
                "area_p95": round(float(np.percentile(a, 95)), 5),
                "aspect_median": round(float(np.median(ar)), 3),
                "aspect_iqr": round(float(np.percentile(ar, 75) - np.percentile(ar, 25)), 3),
                "tiny_boxes": int((a < TINY_AREA).sum()),
                "edge_touch_any": sum(1 for b in bs if edges_touched(b) >= 1),
                "edge_touch_2plus": sum(1 for b in bs if edges_touched(b) >= 2),
            })

        # 경계 사례
        for stem, v in recs.items():
            for i, b in enumerate(v):
                e = edges_touched(b)
                area = b[3] * b[4]
                flags = []
                if e >= 1:
                    flags.append(f"프레임접촉x{e}")
                if area < TINY_AREA:
                    flags.append("초소형")
                for j, c in enumerate(v):
                    if j <= i or c[0] != b[0]:
                        continue
                    if iou(b, c) >= IOU_OVERLAP:
                        flags.append("동일클래스중첩")
                        break
                if flags:
                    edge_rows.append({
                        "source": tag, "image": stem,
                        "old_class_id": b[0], "old_class_ko": v1.OLD_BY_ID[b[0]][1],
                        "cx": round(b[1], 4), "cy": round(b[2], 4),
                        "w": round(b[3], 4), "h": round(b[4], 4),
                        "area": round(area, 5), "edges_touched": e,
                        "flags": " ".join(flags),
                        "is_representative": dd.get(stem, {}).get("is_representative", ""),
                    })

    def dump(name, rows, fields=None):
        pth = paths.AUDIT / name
        with pth.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields or list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return pth

    dump("newlabels_summary.csv", summary)
    dump("newlabels_class_dist.csv", dist_rows)
    dump("newlabels_boxstats.csv", box_rows)
    dump("newlabels_edge_cases.csv", edge_rows)

    # ---------------- 콘솔 리포트 ----------------
    print("=" * 70)
    print("1~3. 소스 개요")
    print("=" * 70)
    for s in summary:
        print(f"\n[{s['source']}]  {s['rel_path']}")
        print(f"  반          {s['panels']}")
        print(f"  이미지      {s['image_files']}  라벨파일 {s['label_files']}  "
              f"(빈 파일 {s['empty_label_files']})")
        print(f"  bbox        {s['boxes']}  (장당 {s['boxes_per_image']})")
        print(f"  클래스 ID   {s['class_ids_used']}  ({s['distinct_class_ids']}종)")
        print(f"  26스키마 일치 {'예' if s['schema_matches_pilot26'] else '아니오'}")
        print(f"  중복분석 색인 {s['in_dedup_index']}/{s['label_files']}  "
              f"그중 대표 {s['is_representative']}  촬영세션 {s['capture_sessions']}")

    print("\n" + "=" * 70)
    print("4~5. v2 매핑과 반 후보 적합성")
    print("=" * 70)
    print(f"{'src':<5}{'반':<5}{'구 클래스':<18}{'박스':>6}{'비중':>7}  -> "
          f"{'v2 클래스':<18}{'유형':<9}{'반 후보':>7}")
    for r in dist_rows:
        ok = "O" if r["in_v2_panel_candidates"] else "X"
        print(f"{r['source']:<5}{r['panel']:<5}{r['old_class_ko']:<18}"
              f"{r['boxes']:>6}{float(r['share'])*100:>6.1f}%  -> "
              f"{r['v2_class_ko']:<18}{r['migration_type']:<9}{ok:>7}")

    print("\n" + "=" * 70)
    print("6. 박스 기하 (정규화 면적·종횡비)")
    print("=" * 70)
    print(f"{'src':<5}{'클래스':<18}{'n':>5}{'면적중앙':>9}{'p05':>8}{'p95':>8}"
          f"{'종횡비':>7}{'IQR':>7}{'초소형':>7}{'접촉':>6}")
    for r in box_rows:
        print(f"{r['source']:<5}{r['old_class_ko']:<18}{r['n']:>5}"
              f"{r['area_median']:>9.4f}{r['area_p05']:>8.4f}{r['area_p95']:>8.4f}"
              f"{r['aspect_median']:>7.2f}{r['aspect_iqr']:>7.2f}"
              f"{r['tiny_boxes']:>7}{r['edge_touch_any']:>6}")

    print("\n" + "=" * 70)
    print("7~8. 경계 사례")
    print("=" * 70)
    fl = Counter(f for r in edge_rows for f in r["flags"].split())
    for k, n in fl.most_common():
        print(f"  {k:<18}{n:>6}")
    print(f"  사례가 있는 이미지 {len({r['image'] for r in edge_rows})}장 "
          f"/ 전체 {sum(s['label_files'] for s in summary)}장")

    # ---------------- 9. 정본과 비교 ----------------
    print("\n" + "=" * 70)
    print("9. 기존 정본(P1/P3/P4)과 비교")
    print("=" * 70)
    ref = canonical_reference()
    print(f"{'집합':<12}{'박스':>7}{'면적중앙':>10}{'p95':>9}{'종횡비중앙':>10}"
          f"{'프레임접촉':>9}{'초소형':>8}")
    rows_cmp = []
    for pid, bs in sorted(ref.items()):
        rows_cmp.append((f"정본 {pid}", bs))
    for tag, recs in all_boxes.items():
        rows_cmp.append((f"신규 {tag}", [b for v in recs.values() for b in v]))
    for label, bs in rows_cmp:
        if not bs:
            continue
        w = np.array([b[3] for b in bs])
        h = np.array([b[4] for b in bs])
        a = w * h
        ar = w / np.maximum(h, 1e-9)
        et = sum(1 for b in bs if edges_touched(b) >= 1)
        print(f"{label:<12}{len(bs):>7}{np.median(a):>10.4f}"
              f"{np.percentile(a,95):>9.4f}{np.median(ar):>10.2f}"
              f"{et/len(bs)*100:>8.1f}%{int((a<TINY_AREA).sum()):>8}")

    print(f"\n-> reports/data_audit/newlabels_*.csv 4종")


if __name__ == "__main__":
    main()
