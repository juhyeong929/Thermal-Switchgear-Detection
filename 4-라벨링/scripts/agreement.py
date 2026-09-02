"""라벨러 간 일치도 측정 — 시험 라벨링(30장) 검증용.

목적은 모델 성능이 아니라 **"여러 명이 같은 이미지를 보고 같은 객체를 비슷한 단위와
경계로 라벨하는가"** 다. 그래서 세 가지를 나눠 잰다.

  1. 개수 일치   같은 이미지·같은 클래스에서 박스 개수가 같은가
                 -> annotation unit 이 통했는지를 본다. 단위가 어긋나면 여기서 터진다
  2. 경계 일치   짝지어진 박스의 IoU (mIoU)
                 -> 경계 규칙이 통했는지를 본다
  3. 클래스 일치 짝지어진 박스의 클래스가 같은가 (Cohen's Kappa)
                 -> 클래스 정의가 통했는지를 본다

**annotation_unit 이 UNKNOWN 인 클래스는 채점하지 않는다.** 이번 시험에서 그리지 말라고
했으므로 성공·실패를 판단할 대상이 아니다. 그려져 있으면 NOT_SCORED 로 따로 센다.

Skip 도 함께 집계한다. **Skip 이 몰린 항목이 곧 고쳐야 할 규칙이다.**

사용:
    python scripts/agreement.py <라벨러A 폴더> <라벨러B 폴더> [<라벨러C> ...]

각 폴더는 YOLO txt 를 담고 있어야 하며 파일명(stem)이 이미지와 같아야 한다.
빈 파일 = **대상 없음**(그릴 것이 정말 없었다).

Skip 은 `skip_log.csv` 한 곳에만 적는다. 도구가 그 파일을 읽는다.
  scope=image   그 이미지 전체를 못 하겠다  -> 일치도 비교에서 뺀다
  scope=object  일부만 못 하겠다            -> 나머지는 그대로 비교한다

빈 파일과 Skip 은 다르다. **"그릴 게 없다" 와 "모르겠다" 를 섞으면 안 된다.**

작업시간도 함께 읽는다 (`time_log.csv`). 일치도와 달리 이것은 규칙의 품질 지표가
아니라 **본 작업 물량 산정의 유일한 근거**다. 30장에 얼마나 걸렸는지를 모르면
400장·38,957장의 소요를 추정할 수 없다. 기록이 없으면 그 칸만 비워 두고 넘어간다.

**반별로도 따로 낸다** (A-1 · NQ-15 결정). 반 정보를 라벨러에게 공개하기로 했으므로
후보가 좁은 반(P7 은 1종, P5·P9 는 2종)에서는 클래스 일치가 쉬워진다. 전체 평균만 보면
그 반이 지표를 밀어 올리는 것을 알 수 없다. 그래서 **전체 지표는 그대로 두고 반별 지표를
별도 파일로 추가**한다 — 기존 출력의 열·행은 바뀌지 않는다(재현성 증거 보존).

출력: reports/labeling/agreement_<날짜>.csv          쌍별·클래스별 결과 (형식 불변)
      reports/labeling/agreement_by_panel_<날짜>.csv 쌍별×반별 결과 (A-1)
      reports/labeling/trial_time_<날짜>.csv         라벨러별 작업시간
"""

import csv
import sys
from collections import defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

IOU_MATCH = 0.5      # 이 이상이면 같은 객체를 가리킨 것으로 본다
# 반별 값을 **해석할 때 주의하라고 자동으로 붙이는** 기준 (C-2 지표 정의).
# 판정 기준이 아니라 주의 문구를 붙이는 기준이다 — 값을 깎거나 버리지 않는다.
THIN_PANEL = 2       # 배포 클래스가 이 이하면 클래스 선택지가 좁다
MIN_IMAGES = 5       # 비교 장수가 이 미만이면 표본 부족
MIN_COVERAGE = 0.70  # paired coverage 가 이 미만이면 기반이 좁다
# 단위 미확정 클래스 — 이번 시험 대상이 아니므로 채점에서 뺀다
NOT_SCORED = {c.class_id for c in v2.CLASSES
              if not v2.unit_confirmed(c.class_name)}
# 어떤 반에서도 그리지 않기로 한 클래스. 그려져 있으면 채점 제외가 아니라 **규칙 위반**이다
FORBIDDEN = {c.class_id for c in v2.CLASSES if c.label_status == v2.EXCLUDE}
SKIP = {"train.txt", "classes.txt", "obj.names"}
SEED_TARGET = 400        # 본 seed 라벨링 물량 (STEP 11) — 소요 추정의 분자


def panel_of_case():
    """case_id -> panel_id. 반별 집계용 (A-1).

    출처는 시험셋 명세 하나뿐이다. 없으면 반별 집계를 건너뛴다 —
    없는 정보를 파일명에서 추측하지 않는다.
    """
    out = {}
    for f in (paths.LABELING / "seed" / "trial_set.csv",
              paths.AUDIT / "trial_provenance.csv"):
        if not f.exists():
            continue
        with f.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                cid = (r.get("case_id") or "").strip()
                pan = (r.get("panel") or "").strip()
                if cid and pan:
                    out.setdefault(cid, pan.split("-", 1)[0])
    return out


def load_skip_log(folder):
    """skip_log.csv 를 읽는다. 작업 폴더 또는 그 상위(공용)에 있을 수 있다.

    돌려주는 것
      image_skips  {case_id}        이미지 전체 Skip -> 비교에서 뺀다
      rows         [사유 행]        집계·보고용 (object 단위 포함)
    """
    d = Path(folder)
    name = d.name
    image_skips, rows = set(), []
    for cand in (d / "skip_log.csv", d.parent / "skip_log.csv"):
        if not cand.exists():
            continue
        with cand.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                who = (r.get("annotator") or "").strip()
                if who.startswith("#") or not (r.get("case_id") or "").strip():
                    continue                      # 주석·빈 줄
            # 공용 파일이면 자기 이름의 행만 가져온다
                if cand.parent == d.parent and who and who != name:
                    continue
                rows.append(r)
                if (r.get("scope") or "image").strip() == "image":
                    image_skips.add(r["case_id"].strip())
        break                                     # 작업 폴더 것이 우선
    return image_skips, rows


def load_time_log(folder):
    """time_log.csv 를 읽어 (총 분, 끝낸 장수, 구간 수) 를 돌려준다.

    minutes 가 적혀 있으면 그 값을 쓰고, 없으면 start/end(HH:MM) 로 계산한다.
    자정을 넘긴 구간은 다음 날로 본다. 기록이 없으면 (None, 0, 0).
    """
    f = Path(folder) / "time_log.csv"
    if not f.exists():
        return None, 0, 0
    total, cases, spans = 0.0, 0, 0
    with f.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            who = (r.get("annotator") or "").strip()
            if who.startswith("#"):
                continue                          # 주석·예시 줄
            m = (r.get("minutes") or "").strip()
            mins = None
            if m:
                try:
                    mins = float(m)
                except ValueError:
                    mins = None
            if mins is None:
                st, en = (r.get("start") or "").strip(), (r.get("end") or "").strip()
                if ":" in st and ":" in en:
                    try:
                        h1, m1 = (int(x) for x in st.split(":")[:2])
                        h2, m2 = (int(x) for x in en.split(":")[:2])
                        mins = (h2 * 60 + m2) - (h1 * 60 + m1)
                        if mins < 0:
                            mins += 24 * 60       # 자정을 넘긴 구간
                    except ValueError:
                        mins = None
            if mins is None:
                continue
            total += mins
            spans += 1
            c = (r.get("cases_done") or "").strip()
            if c.isdigit():
                cases += int(c)
    return (total if spans else None), cases, spans


def load(folder):
    """{stem: [(cls, cx, cy, w, h), ...]} · 이미지 Skip 집합 · Skip 사유 행."""
    d = Path(folder)
    boxes = {}
    for f in sorted(d.rglob("*.txt")):
        if f.name in SKIP or f.name == "skip_log.csv":
            continue
        bs = []
        for line in f.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) >= 5:
                bs.append((int(float(p[0])), *[float(x) for x in p[1:5]]))
        boxes[f.stem] = bs
    skipped, rows = load_skip_log(folder)
    # 예전 방식(.skip 빈 파일)도 받아 준다
    for f in d.rglob("*.skip"):
        skipped.add(f.stem)
    return boxes, skipped, rows


def iou(a, b):
    def xy(t):
        _, cx, cy, w, h = t
        return cx - w/2, cy - h/2, cx + w/2, cy + h/2
    ax0, ay0, ax1, ay1 = xy(a)
    bx0, by0, bx1, by1 = xy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1-ax0)*(ay1-ay0) + (bx1-bx0)*(by1-by0) - inter
    return inter / ua if ua > 0 else 0.0


def greedy_match(A, B):
    """IoU 가 큰 쌍부터 1:1 로 짝짓는다. 클래스는 보지 않는다 (클래스 일치를 따로 재려고)."""
    pairs = sorted(((iou(a, b), i, j) for i, a in enumerate(A) for j, b in enumerate(B)),
                   reverse=True)
    ua, ub, out = set(), set(), []
    for v, i, j in pairs:
        if v < IOU_MATCH or i in ua or j in ub:
            continue
        ua.add(i); ub.add(j); out.append((i, j, v))
    return out, [i for i in range(len(A)) if i not in ua], \
        [j for j in range(len(B)) if j not in ub]


def kappa(pairs):
    """Cohen's Kappa — 짝지어진 박스의 클래스 일치."""
    if not pairs:
        return float("nan")
    a = [p[0] for p in pairs]
    b = [p[1] for p in pairs]
    labels = sorted(set(a) | set(b))
    n = len(pairs)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(l)/n) * (b.count(l)/n) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        sys.exit(__doc__)

    people, times = {}, {}
    for folder in sys.argv[1:]:
        name = Path(folder).name
        people[name] = load(folder)
        times[name] = load_time_log(folder)
        b, sk, rows = people[name]
        obj = sum(1 for r in rows if (r.get("scope") or "image") == "object")
        mins = times[name][0]
        t = f"  작업시간 {mins:.0f}분" if mins else "  작업시간 —"
        print(f"{name:<16} 라벨 파일 {len(b)}  이미지Skip {len(sk)}  객체Skip {obj}{t}")

    PANEL_OF = panel_of_case()
    rows, panel_rows = [], []
    for na, nb in combinations(people, 2):
        (A, sa, _), (B, sb, _) = people[na], people[nb]
        common = sorted(set(A) & set(B))
        ious, cls_pairs = [], []
        cnt_same = cnt_tot = 0
        per_class = defaultdict(lambda: {"iou": [], "a": 0, "b": 0, "matched": 0})
        # 반별 누적 (A-1). 전체 지표와 **같은 계산**을 반 단위로 한 번 더 담는다.
        per_panel = defaultdict(lambda: {"iou": [], "cls": [], "same": 0, "tot": 0,
                                         "compared": 0, "skipped": 0,
                                         "skip_a": 0, "skip_b": 0,
                                         "na": 0, "nb": 0})

        compared = 0
        not_scored = defaultdict(int)
        forbidden = defaultdict(int)
        for stem in common:
            pan = PANEL_OF.get(stem, "(미상)")
            if stem in sa:
                per_panel[pan]["skip_a"] += 1
            if stem in sb:
                per_panel[pan]["skip_b"] += 1
            if stem in sa or stem in sb:      # 한쪽이라도 Skip 이면 비교하지 않는다
                per_panel[pan]["skipped"] += 1
                continue
            compared += 1
            per_panel[pan]["compared"] += 1
            # 단위 미확정 클래스는 채점 대상이 아니다.
            # 제외 클래스가 그려져 있으면 그건 채점 제외가 아니라 규칙 위반이다.
            for who, src in ((na, A[stem]), (nb, B[stem])):
                for bx in src:
                    if bx[0] in FORBIDDEN:
                        forbidden[(who, bx[0])] += 1
                    elif bx[0] in NOT_SCORED:
                        not_scored[bx[0]] += 1
            skipset = NOT_SCORED | FORBIDDEN
            av = [bx for bx in A[stem] if bx[0] not in skipset]
            bv = [bx for bx in B[stem] if bx[0] not in skipset]
            # paired coverage 의 분모 — 채점 대상 박스 수 (짝이 안 지어진 것 포함)
            per_panel[pan]["na"] += len(av)
            per_panel[pan]["nb"] += len(bv)
            m, only_a, only_b = greedy_match(av, bv)
            for i, j, v in m:
                ious.append(v)
                cls_pairs.append((av[i][0], bv[j][0]))
                per_panel[pan]["iou"].append(v)
                per_panel[pan]["cls"].append((av[i][0], bv[j][0]))
                if av[i][0] == bv[j][0]:
                    per_class[av[i][0]]["iou"].append(v)
                    per_class[av[i][0]]["matched"] += 1
            for cid in {b[0] for b in av}:
                per_class[cid]["a"] += sum(1 for b in av if b[0] == cid)
            for cid in {b[0] for b in bv}:
                per_class[cid]["b"] += sum(1 for b in bv if b[0] == cid)
            # 개수 일치 — 클래스별로 개수가 같은가
            ca = defaultdict(int); cb = defaultdict(int)
            for b in av:
                ca[b[0]] += 1
            for b in bv:
                cb[b[0]] += 1
            for cid in set(ca) | set(cb):
                cnt_tot += 1
                per_panel[pan]["tot"] += 1
                if ca[cid] == cb[cid]:
                    cnt_same += 1
                    per_panel[pan]["same"] += 1

        miou = float(np.mean(ious)) if ious else float("nan")
        k = kappa(cls_pairs)
        # 반별 행 — 전체 행과 같은 정의로 계산한다
        for pan, d in sorted(per_panel.items()):
            dep = (len(v2.deployable(v2.BY_PANEL_ID[pan]))
                   if pan in v2.BY_PANEL_ID else "")
            denom = d["na"] + d["nb"]
            warn = []
            if isinstance(dep, int) and dep <= THIN_PANEL:
                warn.append(f"후보 {dep}종 — 클래스 선택지가 좁아 Kappa 가 높게 나온다")
            if d["compared"] and d["compared"] < MIN_IMAGES:
                warn.append(f"비교 {d['compared']}장 — 표본 부족")
            if denom and (2 * len(d["iou"]) / denom) < MIN_COVERAGE:
                warn.append("paired coverage 낮음 — 짝이 안 지어진 박스가 많다")
            panel_rows.append({
                "pair": f"{na} vs {nb}", "panel_id": pan,
                "deployable_classes": dep,
                "images_compared": d["compared"], "images_skipped": d["skipped"],
                "skip_a": d["skip_a"], "skip_b": d["skip_b"],
                "boxes_a": d["na"], "boxes_b": d["nb"],
                "matched_boxes": len(d["iou"]),
                # 짝지어진 박스 비율. Kappa 가 **얼마나 좁은 기반 위의 값인지**를 말한다
                "paired_coverage": (round(2 * len(d["iou"]) / denom, 4)
                                    if denom else ""),
                "mIoU": round(float(np.mean(d["iou"])), 4) if d["iou"] else "",
                "kappa": round(kappa(d["cls"]), 4) if d["cls"] else "",
                "count_agreement": (round(d["same"] / d["tot"], 4)
                                    if d["tot"] else ""),
                "interpretation_warning": " · ".join(warn),
            })
        rows.append({
            "pair": f"{na} vs {nb}", "class_name": "(전체)",
            "images_compared": compared, "images_skipped": len(common) - compared,
            "matched_boxes": len(ious),
            "mIoU": round(miou, 4) if ious else "",
            "kappa": round(k, 4) if cls_pairs else "",
            "count_agreement": round(cnt_same / cnt_tot, 4) if cnt_tot else "",
            "skip_a": len(sa), "skip_b": len(sb),
        })
        for cid, d in sorted(per_class.items()):
            rows.append({
                "pair": f"{na} vs {nb}",
                "class_name": v2.BY_ID[cid].canonical_name,
                "images_compared": "", "images_skipped": "",
                "matched_boxes": d["matched"],
                "mIoU": round(float(np.mean(d["iou"])), 4) if d["iou"] else "",
                "kappa": "", "count_agreement": "",
                "skip_a": "", "skip_b": "",
            })

        print(f"\n=== {na} vs {nb} ===")
        print(f"  비교한 이미지 {compared}/{len(common)} "
              f"(Skip 으로 제외 {len(common)-compared})  짝지어진 박스 {len(ious)}")
        print(f"  개수 일치율 {cnt_same/cnt_tot:.1%}" if cnt_tot else "  개수 일치율 —")
        print(f"  mIoU  {miou:.3f}" if ious else "  mIoU  —")
        print(f"  Kappa {k:.3f}" if cls_pairs else "  Kappa —")
        if not_scored:
            names = ", ".join(f"{v2.BY_ID[c].canonical_name} {n}"
                              for c, n in sorted(not_scored.items()))
            print(f"  NOT_SCORED (단위 미확정 — 이번 시험 대상 아님): {names}")
        if forbidden:
            print("  [규칙 위반] 그리지 말아야 할 제외 클래스가 그려졌다")
            for (who, c), n in sorted(forbidden.items()):
                print(f"      {who:<16}{v2.BY_ID[c].canonical_name:<12}{n}건")
        print(f"  {'클래스':<20}{'짝':>5}{'mIoU':>8}{'A개수':>7}{'B개수':>7}")
        for cid, d in sorted(per_class.items(), key=lambda x: -x[1]["a"]):
            mi = f"{np.mean(d['iou']):.3f}" if d["iou"] else "—"
            print(f"  {v2.BY_ID[cid].canonical_name:<20}{d['matched']:>5}{mi:>8}"
                  f"{d['a']:>7}{d['b']:>7}")

    out = paths.REPORTS / "labeling" / f"agreement_{date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- 반별 지표 (A-1) — 별도 파일. 위 파일의 형식은 건드리지 않는다 ----
    pout = None
    if panel_rows:
        pout = (paths.REPORTS / "labeling"
                / f"agreement_by_panel_{date.today().isoformat()}.csv")
        with pout.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(panel_rows[0]))
            w.writeheader()
            w.writerows(panel_rows)
        print("\n반별 지표 — 후보가 좁은 반은 일치가 쉬우므로 평균과 같이 읽지 않는다")
        print(f"  {'쌍':<34}{'반':<5}{'후보':>4}{'비교':>4}{'Skip':>6}{'짝':>5}"
              f"{'기반':>7}{'mIoU':>8}{'Kappa':>8}{'개수':>8}")
        for r in panel_rows:
            print(f"  {r['pair']:<34}{r['panel_id']:<5}"
                  f"{str(r['deployable_classes']):>4}{r['images_compared']:>4}"
                  f"{str(r['skip_a']) + '/' + str(r['skip_b']):>6}"
                  f"{r['matched_boxes']:>5}"
                  f"{(str(round(r['paired_coverage'] * 100)) + '%') if r['paired_coverage'] != '' else '—':>7}"
                  f"{str(r['mIoU']):>8}{str(r['kappa']):>8}"
                  f"{str(r['count_agreement']):>8}"
                  f"{'  !' if r['interpretation_warning'] else ''}")
        warned = [r for r in panel_rows if r["interpretation_warning"]]
        if warned:
            print("\n  ! 해석 주의 — 이 반의 값을 전체 대표값으로 읽지 않는다")
            seen_w = set()
            for r in warned:
                k = (r["panel_id"], r["interpretation_warning"])
                if k in seen_w:
                    continue
                seen_w.add(k)
                print(f"      {r['panel_id']:<5}{r['interpretation_warning']}")
            tm = sum(r["matched_boxes"] for r in warned)
            am = sum(r["matched_boxes"] for r in panel_rows)
            if am:
                print(f"      -> 주의 대상 반이 짝지어진 박스의 {tm / am:.0%} 를 차지한다.")
                print("         전체 Kappa 는 이 반들의 값에 크게 좌우된다.")

    # ---- Skip 집계 — 무엇을 고쳐야 하는지 알려주는 부분 ----
    allskip = defaultdict(list)
    reasons = defaultdict(lambda: defaultdict(int))   # 사유 -> 클래스 -> 건수
    reason_tot = defaultdict(int)
    for name, (_, sk, srows) in people.items():
        for s in sk:
            allskip[s].append(name)
        for r in srows:
            why = (r.get("skip_reason") or "other").strip() or "other"
            cls = (r.get("class_if_known") or "").strip() or "(미상)"
            reasons[why][cls] += 1
            reason_tot[why] += 1

    if reason_tot:
        print("\nSkip 사유별 집계 — 고치는 방법이 사유마다 다르다")
        todo = {"rule_unclear": "규칙을 고친다",
                "not_visible":  "규칙대로 Skip 이 정답. 고칠 것 없음",
                "unknown_part": "참조 자료·교육을 보강한다",
                "other":        "메모를 읽고 판단한다"}
        for why, n in sorted(reason_tot.items(), key=lambda x: -x[1]):
            print(f"  {why:<14}{n:>4}건   -> {todo.get(why, '분류 없음')}")
            for cls, c in sorted(reasons[why].items(), key=lambda x: -x[1])[:5]:
                print(f"      {cls:<24}{c}")

    if allskip:
        print(f"\n이미지 전체 Skip {len(allskip)}장 "
              f"(여러 명이 함께 Skip 한 것이 곧 규칙 문제다)")
        for s, who in sorted(allskip.items(), key=lambda x: -len(x[1]))[:15]:
            print(f"  {s:<40}{len(who)}명  {' '.join(who)}")


    # ---- 작업시간 — 본 작업 물량 산정용. 규칙 품질과는 별개다 ----
    trows = []
    for name, (mins, cases, spans) in sorted(times.items()):
        n_img = cases or len(people[name][0])      # cases_done 이 비면 라벨 파일 수로 센다
        per = (mins / n_img) if (mins and n_img) else None
        trows.append({
            "annotator": name,
            "total_minutes": round(mins, 1) if mins else "",
            "images": n_img,
            "min_per_image": round(per, 2) if per else "",
            "spans": spans,
            f"est_minutes_for_{SEED_TARGET}": round(per * SEED_TARGET) if per else "",
        })
    have = [r for r in trows if r["total_minutes"] != ""]
    if have:
        tout = paths.REPORTS / "labeling" / f"trial_time_{date.today().isoformat()}.csv"
        with tout.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(trows[0]))
            w.writeheader(); w.writerows(trows)
        print("\n작업시간 — 규칙 품질이 아니라 본 작업 물량 산정용이다")
        print(f"  {'라벨러':<16}{'총분':>7}{'장수':>6}{'분/장':>8}")
        for r in trows:
            print(f"  {r['annotator']:<16}{str(r['total_minutes']):>7}"
                  f"{r['images']:>6}{str(r['min_per_image']):>8}")
        pv = [r["min_per_image"] for r in have if r["min_per_image"] != ""]
        if pv:
            avg = float(np.mean(pv))
            print(f"  평균 {avg:.2f}분/장  ->  {SEED_TARGET}장 추정 "
                  f"{avg*SEED_TARGET/60:.1f}시간 (1인 기준)")
        if len(have) < len(trows):
            miss = [r["annotator"] for r in trows if r["total_minutes"] == ""]
            print(f"  [주의] 시간 기록이 없는 라벨러 {len(miss)}명: {', '.join(miss)} "
                  f"— 평균을 전체로 일반화하지 않는다")
        print(f"  -> {tout}")
    else:
        print("\n작업시간 기록 없음 (annotator_*/time_log.csv 가 비어 있다) "
              "— 본 작업 소요는 추정하지 않는다")

    print(f"\n-> {out}")
    print("목표치 — Kappa 0.8 이상 (파이프라인 03 품질 지표)")


if __name__ == "__main__":
    main()
