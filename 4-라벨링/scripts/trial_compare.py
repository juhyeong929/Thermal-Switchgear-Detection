"""회차 간 비교표 — v1(A·B·C) 대비 v2(D·E) 가 실제로 나아졌는가.

왜 필요한가
    C-2 를 회차별로 분리하기로 했으므로(C2-trial-round-separation), 두 회차의 Kappa 를
    하나로 평균하지 않는다. 대신 **같은 항목을 나란히 놓고 전후를 본다.**

    "v2 가 좋아졌다" 를 pooled Kappa 하나로 말하면 안 된다. v2 에서는 지침서 개선과
    반 정보 공개가 **동시에** 들어가므로 두 효과가 섞인다. 그래서 반 공개 효과를
    직접 보여 주는 지표(**후보 밖 클래스 박스 수**)를 따로 낸다.

읽는 법
    후보 밖 클래스 박스 수   반 공개 효과의 직접 지표. v1 A3 / B23 / C3 였다
    count agreement         무엇을 그릴지가 통했는가. v1 에서 가장 낮았다
    paired coverage         Kappa 가 얼마나 좁은 기반 위의 값인가
    scope=object            v2 에서 문구를 강조했다. 0 이면 문구가 또 실패한 것이다
    panel-stratified Kappa  후보가 좁은 반이 전체를 밀어 올리는지

출력
    reports/labeling/trial_compare.md   회차 비교표
    reports/labeling/trial_compare.csv  같은 내용 (기계 판독용)

사용:
    python scripts/trial_compare.py
"""

import csv
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
LAB = paths.REPORTS / "labeling"
SKIP_TXT = {"classes.txt", "obj.names", "train.txt", "val.txt"}


def read(p):
    p = Path(p)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def rounds():
    out = []
    for r in read(TRIAL / "trial_versions.csv"):
        rd = (r.get("round") or "").strip()
        if rd and not rd.startswith("#"):
            out.append(r)
    return out


def annotators(r):
    return [a for a in (r.get("annotators") or "").split() if a]


def panel_of_case():
    out = {}
    for f in (paths.LABELING / "seed" / "trial_set.csv",
              paths.AUDIT / "trial_provenance.csv"):
        for x in read(f):
            cid, pan = (x.get("case_id") or "").strip(), (x.get("panel") or "").strip()
            if cid and pan:
                out.setdefault(cid, pan.split("-", 1)[0])
    return out


def per_annotator(who, panel_of):
    """라벨러 한 명의 실측치. 파일에서만 센다 — 손으로 적은 값을 쓰지 않는다."""
    d = TRIAL / who
    y = d / "yolo"
    boxes, out_of_scope, files = 0, 0, 0
    if y.is_dir():
        for p in y.glob("*.txt"):
            if p.name in SKIP_TXT:
                continue
            files += 1
            pan = panel_of.get(p.stem)
            allowed = set()
            if pan and pan in v2.BY_PANEL_ID:
                allowed = {v2.BY_NAME[c].class_id
                           for c in v2.deployable(v2.BY_PANEL_ID[pan])}
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.split()
                if len(s) < 5:
                    continue
                boxes += 1
                if allowed and int(float(s[0])) not in allowed:
                    out_of_scope += 1
    sk = [r for r in read(d / "skip_log.csv")
          if (r.get("case_id") or "").strip()
          and not (r.get("annotator") or "").startswith("#")]
    img_skip = sum(1 for r in sk if (r.get("scope") or "image").strip() == "image")
    obj_skip = sum(1 for r in sk if (r.get("scope") or "").strip() == "object")
    reasons = Counter((r.get("skip_reason") or "other").strip() for r in sk)
    mins = None
    for r in read(d / "time_log.csv"):
        if (r.get("annotator") or "").startswith("#"):
            continue
        m = (r.get("minutes") or "").strip()
        v = None
        if m:
            try:
                v = float(m)
            except ValueError:
                v = None
        if v is None:
            a, b = (r.get("start") or "").strip(), (r.get("end") or "").strip()
            if ":" in a and ":" in b:
                h1, m1 = (int(x) for x in a.split(":")[:2])
                h2, m2 = (int(x) for x in b.split(":")[:2])
                v = (h2 * 60 + m2) - (h1 * 60 + m1)
                if v < 0:
                    v += 1440
        if v is not None:
            mins = (mins or 0) + v
    return {"files": files, "boxes": boxes, "out_of_scope": out_of_scope,
            "img_skip": img_skip, "obj_skip": obj_skip, "minutes": mins,
            "reasons": reasons}


def pair_metrics(name):
    """회차의 agreement CSV 에서 쌍별 전체값을 읽는다."""
    rows = [r for r in read(LAB / name) if r.get("class_name") == "(전체)"] if name else []
    return rows


def panel_metrics(name):
    return read(LAB / name) if name else []


def fmt(vals, f="{:.3f}"):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "—"
    return " / ".join(f.format(v) for v in vals)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    panel_of = panel_of_case()
    rs = rounds()
    cols, data = [], {}

    for r in rs:
        ver = r.get("guide_version", "?")
        cols.append(ver)
        who = annotators(r)
        per = {w: per_annotator(w, panel_of) for w in who}
        pairs = pair_metrics((r.get("agreement_csv") or "").strip())
        pnl = panel_metrics((r.get("by_panel_csv") or "").strip()
                            or (f"agreement_by_panel_{(r.get('agreement_csv') or '')[-14:-4]}.csv"
                                if r.get("agreement_csv") else ""))
        ks = [float(x["kappa"]) for x in pairs if x.get("kappa")]
        mi = [float(x["mIoU"]) for x in pairs if x.get("mIoU")]
        ca = [float(x["count_agreement"]) for x in pairs if x.get("count_agreement")]
        cov = [float(x["paired_coverage"]) for x in pnl
               if (x.get("paired_coverage") or "").strip()]
        pk = defaultdict(list)
        for x in pnl:
            if x.get("kappa"):
                pk[x["panel_id"]].append(float(x["kappa"]))
        submitted = [w for w in who if per[w]["files"]]
        data[ver] = {
            "round": r.get("round", ""), "status": r.get("status", ""),
            "panel_disclosed": r.get("panel_disclosed", ""),
            "annotators": who, "submitted": submitted,
            "pooled_kappa": (st.mean(ks) if ks else None), "n_pairs": len(ks),
            "mIoU": (st.mean(mi) if mi else None),
            "count_agreement": (st.mean(ca) if ca else None),
            "coverage_min": (min(cov) if cov else None),
            "coverage_max": (max(cov) if cov else None),
            "panel_kappa": {k: (min(v), max(v)) for k, v in pk.items()},
            "per": per,
        }

    def row(label, fn):
        return [label] + [fn(data[c]) for c in cols]

    def joinper(d, key, f="{}"):
        if not d["submitted"]:
            return "—"
        return " / ".join(f.format(d["per"][w][key])
                          if d["per"][w][key] is not None else "—"
                          for w in d["submitted"])

    table = [
        row("회차", lambda d: f"round {d['round']} · {d['status']}"),
        row("반 정보 공개", lambda d: d["panel_disclosed"]),
        row("라벨러", lambda d: f"{'/'.join(x.replace('annotator_', '') for x in d['annotators'])}"
                               f" (제출 {len(d['submitted'])})"),
        row("pooled Kappa", lambda d: f"{d['pooled_kappa']:.3f} ({d['n_pairs']}쌍)"
                                      if d["pooled_kappa"] is not None else "미측정"),
        row("panel별 Kappa", lambda d: " · ".join(
            f"{k} {a:.2f}" if a == b else f"{k} {a:.2f}~{b:.2f}"
            for k, (a, b) in sorted(d["panel_kappa"].items())) or "—"),
        row("count agreement", lambda d: f"{d['count_agreement']:.1%}"
                                         if d["count_agreement"] is not None else "미측정"),
        row("mIoU", lambda d: f"{d['mIoU']:.3f}" if d["mIoU"] is not None else "미측정"),
        row("paired coverage", lambda d: f"{d['coverage_min']:.0%}~{d['coverage_max']:.0%}"
                                         if d["coverage_min"] is not None else "미측정"),
        row("박스 수", lambda d: joinper(d, "boxes")),
        row("**후보 밖 클래스 박스**", lambda d: joinper(d, "out_of_scope")),
        row("이미지 Skip", lambda d: joinper(d, "img_skip")),
        row("**scope=object**", lambda d: joinper(d, "obj_skip")),
        row("작업시간(분)", lambda d: joinper(d, "minutes", "{:.0f}")),
    ]

    L = ["# 시험 회차 비교 — v1 대비 v2",
         "",
         "> 자동 생성 · `scripts/trial_compare.py` · 숫자는 전부 파일에서 집계",
         "> **두 회차의 Kappa 를 합산하지 않는다.** 운영조건이 다르다 (반 정보 공개 여부).",
         "",
         "| 항목 | " + " | ".join(cols) + " |",
         "|---|" + "---|" * len(cols)]
    for t in table:
        L.append("| " + " | ".join(str(x) for x in t) + " |")
    L += ["",
          "## 읽는 법",
          "",
          "- **후보 밖 클래스 박스** — 반 정보 공개 효과의 직접 지표. "
          "v2 에서 줄지 않으면 반 공개만으로는 해결되지 않았다는 뜻이다.",
          "- **scope=object** — v1 에서 3/3 이 0 이었다. v2 에서도 0 이면 문구 문제가 아니라 "
          "구조 문제이므로 다른 방법을 찾아야 한다.",
          "- **count agreement** — '무엇을 그릴지' 가 통했는가. v1 에서 가장 약했다.",
          "- **paired coverage** — Kappa 의 기반 폭. 낮으면 Kappa 를 신뢰하지 않는다.",
          "- **panel별 Kappa** — 후보가 1~2종인 반의 높은 값이 pooled 를 밀어 올린다. "
          "pooled 만 보고 판단하지 않는다.",
          "",
          "## 주의 — v2 는 두 변경이 동시에 들어간다",
          "",
          "지침서 개선과 반 정보 공개가 함께 적용되므로 **개선 효과가 분리되지 않는다.**",
          "`후보 밖 클래스 박스` 는 반 공개 쪽, `count agreement` 와 `scope=object` 는 "
          "지침서 쪽 효과를 주로 반영한다고 보고 읽는다.",
          ""]
    (LAB / "trial_compare.md").write_text("\n".join(L), encoding="utf-8")
    with (LAB / "trial_compare.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["item"] + cols)
        w.writerows(table)

    print("시험 회차 비교")
    width = max(len(t[0]) for t in table) + 2
    print(f"  {'항목':<{width}}" + "".join(f"{c:<40}" for c in cols))
    for t in table:
        print(f"  {t[0]:<{width}}" + "".join(f"{str(x):<40}" for x in t[1:]))
    pend = [c for c in cols if data[c]["pooled_kappa"] is None]
    if pend:
        print(f"\n  {', '.join(pend)} 는 아직 회수 전이다. 회수 후 다시 실행한다.")
    print(f"\n-> {LAB / 'trial_compare.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
