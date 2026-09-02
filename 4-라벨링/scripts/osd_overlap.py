"""OQ-010 — FLIR OSD 영역이 기존 라벨과 얼마나 겹치는지 **측정만** 한다.

**마스킹 여부는 결정하지 않는다.** 지금 필요한 것은 "OSD 를 가리면 라벨이 몇 개
망가지는가"라는 수치이지, 가릴지 말지에 대한 판단이 아니다. 판단은 사람이 한다.

방법
    1. experiments/dedup/osd_freq.npy — 표본 600장에서 픽셀별 엣지 출현 빈도.
       정지 오버레이는 매 장 같은 자리에 엣지가 서므로 빈도가 높다.
    2. 임계값 하나를 고르지 않고 **여러 값으로 훑는다(sensitivity sweep)**.
       근거 없는 단일 임계값을 새로 만들지 않기 위해서다.
    3. 정본 라벨 박스와 겹치는 면적 비율을 계산한다.

주의 — 이 측정의 한계
    · osd_freq 는 "엣지가 자주 서는 자리"이지 "OSD 임이 확인된 자리"가 아니다.
      부품이 늘 같은 위치에 있는 경우도 빈도가 높게 나온다.
    · 240x320 격자로 정규화 좌표를 매핑한다. 촬영 해상도/화각이 섞여 있으면
      정규화 좌표에서 OSD 위치가 어긋난다. 그래서 해상도 동일성을 먼저 확인한다.

출력: reports/data_audit/osd_overlap_sweep.csv    임계값별 전체 요약
      reports/data_audit/osd_overlap_boxes.csv    임계값 기준값에서 겹친 박스 목록
      reports/data_audit/osd_overlap_by_class.csv 클래스별
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import classes_v2 as v2  # noqa: E402
from schemas import paths  # noqa: E402

FREQ = paths.PROJECT / "experiments" / "dedup" / "osd_freq.npy"
# 훑을 임계값. 하나를 고르지 않는다 — 어디서 결론이 바뀌는지 보이는 게 목적이다
SWEEP = (0.10, 0.20, 0.30, 0.40, 0.50)
# 보고 기준으로 쓸 값. "기준"이지 "확정"이 아니다
REPORT_AT = 0.30
# 박스 면적 중 OSD 가 차지하는 비율의 구간
BANDS = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50)
SKIPNAME = {"classes.txt"}

# OSD 영역 (320x240 좌표 기준).
#
# **OQ-010 에 기록했던 영역 목록은 틀렸다.** 처음에는 화면 네 귀퉁이만 OSD 로 보고
# 나머지를 "OSD 아님"으로 분류했는데, 마스크를 그려 눈으로 보니
# (experiments/dedup/osd_mask_check.png) 화면 한가운데를 가로지르던 선은 오탐이 아니라
# **FLIR 측정영역 박스 테두리**였다. 즉 OSD 는 가장자리에만 있지 않다.
#
# 테두리 좌표 실측 (freq>=0.30 에서 한 줄에 40픽셀 이상 뭉친 행/열):
#     가로선 y=36(0.150) x 16~279 · y=200(0.833) x 112~283
#     세로선 x=34(0.106) y  8~196 · x=283(0.884) y  68~200
BOX_X = (34, 283)      # 측정영역 박스 좌·우 변
BOX_Y = (36, 200)      # 측정영역 박스 상·하 변
BOX_TOL = 2            # 선 두께 여유 (픽셀)

REGIONS = {
    "우측 컬러바·온도축": lambda x, y: x >= 268,
    "좌상 최대·최소값": lambda x, y: (x < 122) & (y < 74),
    "좌하 로고·방사율": lambda x, y: (x < 116) & (y >= 190),
    "상단 띠": lambda x, y: y < 22,
    "측정영역 박스 테두리": lambda x, y: (
        (np.minimum(np.abs(x - BOX_X[0]), np.abs(x - BOX_X[1])) <= BOX_TOL)
        | (np.minimum(np.abs(y - BOX_Y[0]), np.abs(y - BOX_Y[1])) <= BOX_TOL)),
}


def region_mask(shape):
    """선언된 OSD 후보 영역의 합집합. 320x240 기준 좌표를 격자에 맞춰 늘린다."""
    H, W = shape
    yy, xx = np.mgrid[0:H, 0:W]
    x = xx * 320.0 / W
    y = yy * 240.0 / H
    m = np.zeros(shape, bool)
    for fn in REGIONS.values():
        m |= fn(x, y)
    return m
import re  # noqa: E402
PANEL_RE = re.compile(r"(P\d+)")


def load_canonical():
    """[(panel_id, stem, box_index, cls, cx, cy, w, h)] — 승계된 v2 정본."""
    out = []
    for f in sorted((paths.LABELING / "reviewed").rglob("*.txt")):
        if f.name in SKIPNAME:
            continue
        m = PANEL_RE.search(f.stem)
        pid = m.group(1) if m else "?"
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            p = line.split()
            if len(p) >= 5:
                out.append((pid, f.stem, i, int(p[0]),
                            *[float(x) for x in p[1:5]]))
    return out


def box_osd_ratio(mask, cx, cy, w, h):
    """박스 면적 중 OSD 마스크가 차지하는 비율. 정규화 좌표 -> 격자 인덱스."""
    H, W = mask.shape
    x0 = int(np.floor(max(0.0, cx - w / 2) * W))
    x1 = int(np.ceil(min(1.0, cx + w / 2) * W))
    y0 = int(np.floor(max(0.0, cy - h / 2) * H))
    y1 = int(np.ceil(min(1.0, cy + h / 2) * H))
    x1 = max(x1, x0 + 1)
    y1 = max(y1, y0 + 1)
    sub = mask[y0:y1, x0:x1]
    return float(sub.mean()), int(sub.sum())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not FREQ.exists():
        sys.exit("osd_freq.npy 가 없다.")
    freq = np.load(FREQ)
    boxes = load_canonical()
    names = {c.class_id: c.class_name for c in v2.CLASSES}

    print("OQ-010 — OSD 영역과 정본 라벨의 중첩 측정 (마스킹 결정 아님)")
    print()
    print(f"빈도맵 {freq.shape[0]}x{freq.shape[1]} · 정본 박스 {len(boxes):,}개 · "
          f"이미지 {len({(b[0], b[1]) for b in boxes}):,}장")
    print()

    reg = region_mask(freq.shape)
    print("빈도 마스크가 실제로 OSD 자리에 모여 있는가")
    print(f"  {'임계값':>7}{'마스크':>9}{'영역 안':>9}{'영역 밖(=OSD 아님)':>20}")
    for t in SWEEP:
        m = freq >= t
        n = int(m.sum())
        ins = int((m & reg).sum())
        print(f"  {t:>7.2f}{n:>9,}{ins:>9,}"
              f"{(n-ins):>12,} ({(n-ins)/n if n else 0:.1%})")
    worst = max(((freq >= t).sum() - ((freq >= t) & reg).sum())
                / max(int((freq >= t).sum()), 1) for t in SWEEP)
    print()
    if worst == 0:
        print("  -> 모든 임계값에서 빈도 마스크가 100% OSD 영역 안에 들어온다.")
        print("     즉 빈도맵의 고빈도 픽셀은 전부 OSD 다. 두 마스크는 같아진다.")
    else:
        print(f"  -> 영역 밖 픽셀이 최대 {worst:.1%} 섞인다. `영역결합` 행을 쓴다.")
    print()

    sweep = []
    per_box_at = []
    variants = ([(t, freq >= t, "빈도만") for t in SWEEP]
                + [(t, (freq >= t) & reg, "영역결합") for t in SWEEP])
    for t, mask, kind in variants:
        touched = 0
        band = Counter()
        for pid, stem, bi, cls, cx, cy, w, h in boxes:
            r, npx = box_osd_ratio(mask, cx, cy, w, h)
            if r > 0:
                touched += 1
            for lo in reversed(BANDS):
                if r > lo:
                    band[lo] += 1
                    break
            if kind == "영역결합" and abs(t - REPORT_AT) < 1e-9 and r > 0:
                per_box_at.append({
                    "panel_id": pid, "image": stem, "box_index": bi,
                    "class_id": cls, "class_name": names.get(cls, "?"),
                    "osd_area_ratio": f"{r:.4f}", "osd_pixels": npx,
                    "threshold": t,
                })
        sweep.append({
            "mask_kind": kind,
            "freq_threshold": t,
            "osd_pixels": int(mask.sum()),
            "osd_pct_of_frame": f"{mask.mean():.4f}",
            "boxes_touched": touched,
            "boxes_total": len(boxes),
            "touched_pct": f"{touched/len(boxes):.4f}",
            **{f"ratio_gt_{int(lo*100)}pct": band[lo] for lo in BANDS if lo > 0},
        })

    print(f"{'마스크':<10}{'임계값':>7}{'OSD 픽셀':>10}{'화면 비율':>10}"
          f"{'겹친 박스':>10}{'비율':>8}{'>1%':>7}{'>5%':>7}{'>10%':>7}"
          f"{'>25%':>7}{'>50%':>7}")
    for s in sweep:
        print(f"{s['mask_kind']:<10}{s['freq_threshold']:>7.2f}{s['osd_pixels']:>10,}"
              f"{float(s['osd_pct_of_frame'])*100:>8.2f}%{s['boxes_touched']:>10,}"
              f"{float(s['touched_pct'])*100:>7.1f}%"
              f"{s['ratio_gt_1pct']:>7,}{s['ratio_gt_5pct']:>7,}"
              f"{s['ratio_gt_10pct']:>7,}{s['ratio_gt_25pct']:>7,}"
              f"{s['ratio_gt_50pct']:>7,}")

    by_cls = defaultdict(lambda: [0, 0])
    tot_cls = Counter()
    for pid, stem, bi, cls, cx, cy, w, h in boxes:
        tot_cls[cls] += 1
    for r in per_box_at:
        by_cls[r["class_id"]][0] += 1
        if float(r["osd_area_ratio"]) > 0.10:
            by_cls[r["class_id"]][1] += 1

    cls_rows = []
    for cls, (t1, t10) in sorted(by_cls.items(), key=lambda x: -x[1][0]):
        cls_rows.append({
            "class_id": cls, "class_name": names.get(cls, "?"),
            "boxes_total": tot_cls[cls], "touched": t1,
            "touched_pct": f"{t1/tot_cls[cls]:.4f}",
            "ratio_gt_10pct": t10,
            "threshold": REPORT_AT,
        })
    print()
    print(f"클래스별 (임계값 {REPORT_AT} 기준)")
    print(f"  {'클래스':<20}{'전체':>8}{'겹침':>8}{'비율':>8}{'>10%':>7}")
    for r in cls_rows[:12]:
        print(f"  {r['class_name']:<20}{r['boxes_total']:>8,}{r['touched']:>8,}"
              f"{float(r['touched_pct'])*100:>7.1f}%{r['ratio_gt_10pct']:>7,}")

    paths.AUDIT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("osd_overlap_sweep.csv", sweep),
                       ("osd_overlap_boxes.csv", per_box_at),
                       ("osd_overlap_by_class.csv", cls_rows)):
        if not rows:
            continue
        with (paths.AUDIT / name).open("w", newline="",
                                       encoding="utf-8-sig") as fh:
            w_ = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w_.writeheader()
            w_.writerows(rows)

    print()
    print("**마스킹 여부는 결정하지 않았다.** 측정값만 기록했다 -> OQ-010")
    print(f"-> {paths.AUDIT}")


if __name__ == "__main__":
    main()
