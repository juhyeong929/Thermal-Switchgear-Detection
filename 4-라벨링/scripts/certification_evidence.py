"""인증 대비 — **품질 지표 5종에 대한 증거를 파일에서 집계**한다.

기준은 우리가 만든 것이 아니다. `수배전반_열화상_라벨링_파이프라인.html` 03 Quality Evidence
절에 적힌 것을 그대로 쓴다. 국가 AI 학습데이터 구축사업(과기정통부·NIA) 기준으로 품질
검증을 마친 유사 도메인 선례(AI Hub 열화상 카메라 이미지, dataSetSn=235)를 참고 기준선으로
삼는다.

    C-1 라벨링 오류율      오류 보고 수 / 전체 데이터 수      종료 시 0 에 수렴
    C-2 라벨러 간 일치도    mIoU(박스) / Cohen's Kappa(클래스)  **Kappa 0.8 이상**
    C-3 클래스 균형        클래스별 인스턴스 수 분포          시드 기준 클래스당 최소 30~50
    C-4 검수 이력          라벨러·검수자·가이드 개정 기록      **전량 추적 가능**
    C-5 모델 성능(참고선)   mAP@IoU 0.5                       **70% 이상** (선례 실측 83.8%)

이 스크립트가 하는 것
    각 지표마다 **지금 무엇을 댈 수 있고 무엇이 비어 있는지**를 파일에서 세어 표로 만든다.
    충족을 선언하지 않는다 — `상태` 는 측정 결과이지 판정이 아니다.

무엇을 하지 않는가
    **숫자를 만들어내지 않는다.** 아직 재지 못한 지표는 `미측정` 으로 두고 무엇이 있어야
    잴 수 있는지 적는다. 인증 심사에서 가장 위험한 것은 빈 칸이 아니라 **채워 넣은 추정치**다.

출력
    reports/certification/evidence.csv     지표별 현재값·목표·상태·근거
    reports/certification/gaps.csv         아직 댈 수 없는 증거와 필요한 것
    reports/certification/README.md        읽는 문서

사용
    python scripts/certification_evidence.py
"""

import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

OUT = paths.REPORTS / "certification"
TRIAL = paths.LABELING / "draft" / "trial"

KAPPA_TARGET = 0.80
SEED_CLASS_MIN = 30          # 시드 기준 클래스당 최소 (30~50 중 하한)
MAP_FLOOR = 0.70


def read(p):
    p = Path(p)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def latest(pattern):
    """같은 이름의 날짜별 파일 중 가장 최근 것."""
    fs = sorted((paths.REPORTS / "labeling").glob(pattern))
    return fs[-1] if fs else None


# ---------------------------------------------------------------------------
def c1_error_rate():
    """오류 보고 수 / 전체. '오류' 는 감사에서 실제로 지적된 것만 센다."""
    mig = read(paths.AUDIT / "migration_verification.csv")
    total = sum(int(r["boxes_after"]) for r in mig)
    # 격리됐다가 **판정에서 정상으로 해제된 박스는 오류가 아니다.**
    # 판정 전에는 전부 오류로 세었으므로 이 값이 줄어드는 것이 '0 에 수렴' 의 첫 근거다.
    q = read(paths.LABELING / "quarantine" / "canonical_quarantine.csv")
    all_q = {(r["image"], r["box_index"]) for r in q}
    cleared = {(r["image"], r["box_index"]) for r in q
               if (r.get("status") or "").strip() == "해제"}
    q_boxes = len(all_q - cleared)
    n_reviewed = len(cleared)

    # 시험에서 사람이 '기존이_이상함' 으로 지적한 건
    human = 0
    f = latest("diff_*_*.csv")
    if f:
        human = sum(1 for r in read(f) if (r.get("verdict") or "").strip() == "기존이_이상함")

    rate = (q_boxes + human) / total if total else None
    return {
        "id": "C-1", "metric": "라벨링 오류율",
        "target": "종료 시 0 에 수렴",
        "value": f"{rate:.2%}" if rate is not None else "미측정",
        "detail": (f"확정 오류 {q_boxes}박스 + 시험 지적 {human}건 / 정본 {total:,}박스"
                   + (f" | 격리 {len(all_q)}박스 중 {n_reviewed}박스는 재검수에서 "
                      f"정상으로 해제됐다 (REV-003)" if n_reviewed else "")),
        "status": ("측정됨 · 재검수로 감소 (첫 추세)" if n_reviewed
                   else "측정됨 · 감소 추세 확인 필요"),
        "evidence": "quarantine/canonical_quarantine.csv · DEC-016 · DEC-017",
    }, total


def trial_rounds():
    """시험 회차 등록부. **회차마다 운영조건이 다르므로 값을 섞지 않는다** (C-2 결정).

    v1 은 반 정보 비공개, v2 는 공개다. 두 회차의 Kappa 를 하나로 평균하면
    무엇을 측정한 값인지 말할 수 없게 된다.
    """
    out = []
    for r in read(TRIAL / "trial_versions.csv"):
        rd = (r.get("round") or "").strip()
        if not rd or rd.startswith("#"):
            continue
        out.append(r)
    return out


def c2_agreement():
    """Kappa 0.8 이상. **라벨러 간** 이 원문이다 — 기존 라벨 대조로 대신할 수 없다.

    회차(guide_version)별로 따로 낸다. v2 결과가 v1 값을 덮어쓰지 않는다.
    """
    subs = [d.name for d in sorted(TRIAL.glob("annotator_*"))
            if (d / "yolo").is_dir() and any((d / "yolo").glob("*.txt"))]

    # ---- 회차별 산출 ----
    rounds = trial_rounds()
    per_round = []
    for r in rounds:
        name = r.get("agreement_csv", "").strip()
        f_ = (paths.REPORTS / "labeling" / name) if name else None
        ks = []
        if f_ and f_.exists():
            ks = [float(x["kappa"]) for x in read(f_)
                  if x.get("class_name") == "(전체)" and x.get("kappa")]
        per_round.append({
            "round": r.get("round", ""), "version": r.get("guide_version", ""),
            "status": r.get("status", ""), "panel": r.get("panel_disclosed", ""),
            "n": len([a for a in (r.get("annotators") or "").split() if a]),
            "kappa": (sum(ks) / len(ks)) if ks else None, "pairs": len(ks),
        })

    inter = None
    f = latest("agreement_2*.csv")
    if f:
        rows = [r for r in read(f) if r.get("class_name") == "(전체)"]
        if rows:
            ks = [float(r["kappa"]) for r in rows if r.get("kappa")]
            inter = sum(ks) / len(ks) if ks else None

    ref = None
    f2 = latest("agreement_vs_existing_*.csv")
    if f2:
        rows = [r for r in read(f2) if r.get("class_name") == "(전체)" and r.get("kappa")]
        if rows:
            ref = float(rows[0]["kappa"])

    # Kappa 는 **짝지어진 박스에서만** 계산된다. 짝이 안 지어진 박스는 들어가지 않는다.
    # 그 비율을 함께 내지 않으면 "Kappa 0.86 충족" 이 좁은 기반 위의 값임을 감춘다.
    #
    # **쌍마다 따로 계산한다.** 전체 박스를 분모로 쓰면 라벨러가 셋 이상일 때
    # 한 박스가 여러 쌍에서 짝지어져 비율이 1 을 넘는다 (3명에서 1.43 이 나왔다).
    def _boxes(d, skips):
        y = d / "yolo"
        out = {}
        for t in (y.glob("*.txt") if y.is_dir() else []):
            if t.stem in skips:
                continue
            out[t.stem] = sum(1 for l in t.read_text(encoding="utf-8").splitlines()
                              if len(l.split()) >= 5)
        return out

    def _skips(d):
        return {r["case_id"].strip() for r in read(d / "skip_log.csv")
                if (r.get("case_id") or "").strip()
                and not (r.get("annotator") or "").startswith("#")
                and (r.get("scope") or "image").strip() == "image"}

    cov = None
    if f:
        covs = []
        for r in [x for x in read(f) if x.get("class_name") == "(전체)"]:
            try:
                na, nb = [x.strip() for x in r["pair"].split(" vs ")]
                m = int(r["matched_boxes"])
            except (KeyError, ValueError):
                continue
            da, db = TRIAL / na, TRIAL / nb
            sk = _skips(da) | _skips(db)          # 한쪽이라도 Skip 이면 비교에서 빠진다
            ba, bb = _boxes(da, sk), _boxes(db, sk)
            common = set(ba) & set(bb)
            denom = sum(ba[k] for k in common) + sum(bb[k] for k in common)
            if denom:
                covs.append(m * 2 / denom)
        cov = min(covs) if covs else None          # 가장 좁은 기반을 대표값으로 쓴다

    # 반별 편차 — pooled 값을 단독 인증 근거로 읽지 못하게 주의문을 **자동 병기**한다 (C-2)
    skew = ""
    pf = latest("agreement_by_panel_*.csv")
    if pf:
        pr = [r for r in read(pf) if r.get("kappa")]
        warned = [r for r in pr if (r.get("interpretation_warning") or "").strip()]
        am = sum(int(r["matched_boxes"]) for r in pr) or 1
        covs = [float(r["paired_coverage"]) for r in pr
                if (r.get("paired_coverage") or "").strip()]
        parts = [f"반별 산출 {len(pr)}건"]
        if covs:
            parts.append(f"paired coverage {min(covs):.0%}~{max(covs):.0%}")
        if warned:
            tm = sum(int(r["matched_boxes"]) for r in warned)
            kinds = sorted({k.split(" —")[0].strip()
                            for r in warned
                            for k in r["interpretation_warning"].split(" · ")})
            parts.append(f"**해석 주의 반이 짝지어진 박스의 {tm / am:.0%}** "
                         f"({' / '.join(kinds)})")
        skew = " | 반별: " + " · ".join(parts) + \
               " — pooled 값을 단독 인증 근거로 읽지 않는다"

    done = [r for r in per_round if r["kappa"] is not None]
    if done:
        val = " / ".join(f"{r['version']} {r['kappa']:.3f}({r['n']}인)" for r in done)
        # 회차가 하나뿐이면 그것은 **기준선(baseline)** 이지 최종 인증값이 아니다.
        # v1 은 반 정보 비공개 조건이었고 운영조건이 바뀌었으므로, 최종 판단은
        # v2 의 panel-stratified 결과를 중심으로 한다 (C2-trial-round-separation).
        pend = [r for r in per_round if r["kappa"] is None]
        if pend:
            st = ("**baseline 확보** — " if all(r["kappa"] >= KAPPA_TARGET for r in done)
                  else "**baseline 미달** — ")
            st += (f"{done[-1]['version']} 기준선이며 최종 인증값이 아니다 · 대기: "
                   + ", ".join(f"{r['version']}({r['status']})" for r in pend))
        else:
            st = ("충족" if all(r["kappa"] >= KAPPA_TARGET for r in done) else "미달")
            st += " — **회차별 값이며 합산하지 않는다**"
        if cov is not None and cov < 0.9:
            st += f" · 기반 주의 — 짝지어진 박스만 계산 (전체 박스의 {cov:.0%})"
    elif inter is not None:            # 등록부가 없을 때의 하위 호환
        val = f"Kappa {inter:.3f} (라벨러 {len(subs)}명)"
        st = "충족" if inter >= KAPPA_TARGET else "미달"
    else:
        val = "미측정"
        st = f"**측정 불가** — 제출 라벨러 {len(subs)}명. 2명 이상 필요"

    det = " | ".join(
        f"{r['version']}: " + (f"Kappa {r['kappa']:.3f}" if r["kappa"] is not None
                               else "미측정")
        + f" · {r['n']}인 · 반정보 {r['panel']} · {r['status']}"
        for r in per_round) or f"라벨러 간: {val}"
    det += skew
    if ref is not None:
        det += f" | 참고(기존 라벨 대조): Kappa {ref:.3f} — **인증 지표를 대신하지 않는다**"
    return {
        "id": "C-2", "metric": "라벨러 간 일치도",
        "target": f"Kappa {KAPPA_TARGET} 이상 (+ mIoU 병기) · 회차별",
        "value": val, "detail": det, "status": st,
        "evidence": ("trial_versions.csv · agreement_*.csv · "
                     "agreement_by_panel_*.csv"),
    }


def c3_class_balance():
    """시드 기준 클래스당 최소 30~50 인스턴스."""
    mig = read(paths.AUDIT / "migration_verification.csv")
    per = Counter()
    for r in mig:
        per[r["new_class_ko"]] += int(r["boxes_after"])
    labelable = [c.canonical_name for c in v2.labelable_classes()
                 if v2.unit_confirmed(c.class_name)]
    met = [n for n in labelable if per.get(n, 0) >= SEED_CLASS_MIN]
    zero = [n for n in labelable if per.get(n, 0) == 0]

    # 시드 400장은 아직 라벨링 전이다 — 실측이 아니라 '배분 설계' 만 있다
    alloc = read(paths.AUDIT / "seed_allocation.csv")
    return {
        "id": "C-3", "metric": "클래스 균형",
        "target": f"시드 기준 클래스당 최소 {SEED_CLASS_MIN}~50 인스턴스",
        "value": f"정본 기준 {len(met)}/{len(labelable)}종 충족",
        "detail": (f"정본에 인스턴스가 0 인 라벨 대상 {len(zero)}종: "
                   f"{', '.join(zero[:8])}{' …' if len(zero) > 8 else ''} | "
                   f"시드 400장은 **라벨링 전** 이라 실측 없음 "
                   f"(배분 설계만 존재 · 반 {len(alloc)}개)"),
        "status": "**미측정** — 시드 라벨링 완료 후 확정",
        "evidence": "migration_verification.csv · seed_allocation.csv",
    }


def c4_traceability():
    """전량 추적 가능. 있으면 되는 게 아니라 **연결되는지**를 본다."""
    checks = []

    def chk(name, ok, detail):
        checks.append({"항목": name, "상태": "확보" if ok else "미확보", "내용": detail})

    mig = read(paths.AUDIT / "migration_verification.csv")
    loss = all(r["match"] == "OK" for r in mig) if mig else False
    chk("기존 라벨 승계 계보", loss,
        f"26->28 변환 {len(mig)}행 · 손실 0 · 소스별 대조" if mig else "없음")

    prov = read(paths.AUDIT / "trial_provenance.csv")
    chk("시험셋 장별 선정 계보", bool(prov),
        f"{len(prov)}행 — 왜 이 반/이 장인가·무엇을 버렸나·알려진 약점")

    funnel = read(paths.AUDIT / "selection_funnel.csv")
    chk("선정 단계별 제외 근거", bool(funnel), f"{len(funnel)}행")

    decs = sorted(paths.DECISIONS.glob("DEC-*.md"))
    chk("결정 이력", bool(decs),
        f"{len(decs)}건 — 문제/선택지/이유/근거/영향 형식")

    logs = sorted((paths.PROJECT / "logs").glob("*.md"))
    chk("작업 로그", bool(logs), f"{len(logs)}일 · FACT/INFERENCE/DECISION 표시")

    oq = read(paths.AUDIT / "open_questions.csv")
    chk("미해소 항목 등록", bool(oq),
        f"{len(oq)}건 · 열림 {sum(1 for r in oq if r['status'] != '닫힘')}")

    # 라벨러 기록 — 누가·언제·무엇을 못 했는가
    who, sk, tl = [], 0, 0
    for d in sorted(TRIAL.glob("annotator_*")):
        if not (d / "yolo").is_dir() or not any((d / "yolo").glob("*.txt")):
            continue
        who.append(d.name)
        sk += len([r for r in read(d / "skip_log.csv")
                   if not (r.get("annotator") or "").startswith("#")])
        tl += len([r for r in read(d / "time_log.csv")
                   if not (r.get("annotator") or "").startswith("#")])
    chk("라벨러별 작업 기록", bool(who),
        f"제출 {len(who)}명 · Skip 사유 {sk}행 · 작업시간 {tl}행")

    ver = (paths.REPORTS / "labeling" / "annotator_guide_v1.md").exists()
    chk("가이드라인 판본", ver, "지침서 v1 (버전·개정 사유는 DEC 로 추적)")

    # 검수 대장 — 있는 것과 **서명된 것**은 다르다
    rl = read(paths.LABELING / "review_log.csv")
    rl = [r for r in rl if (r.get("review_id") or "").strip()
          and not r["review_id"].startswith("#")]
    signed = [r for r in rl if (r.get("reviewer") or "").strip()]
    pend = [r for r in rl if (r.get("result") or "").strip() == "PENDING"]
    chk("검수 대장", bool(rl), f"{len(rl)}건 등재 · 판정 대기 {len(pend)}건")
    chk("검수자 서명", bool(rl) and len(signed) == len(rl),
        f"{len(signed)}/{len(rl)}건 — 비어 있으면 '전량 추적 가능' 이 성립하지 않는다")

    ok = sum(1 for c in checks if c["상태"] == "확보")
    missing = [c["항목"] for c in checks if c["상태"] != "확보"]

    # 상태는 계산한다. 문구를 손으로 적으면 파일이 바뀌어도 그대로 남는다.
    if missing:
        status = f"부분 확보 — 미확보: {', '.join(missing)}"
    elif pend:
        # 서명이 다 됐어도 판정이 남아 있으면 이력이 닫힌 것이 아니다
        status = (f"서명 완료 · **판정 대기 {len(pend)}건** "
                  f"({', '.join(r['review_id'] for r in pend)})")
    else:
        status = "충족"
    return {
        "id": "C-4", "metric": "검수 이력",
        "target": "라벨러·검수자·가이드 개정 기록 전량 추적 가능",
        "value": f"{ok}/{len(checks)} 항목 확보 · 서명 {len(signed)}/{len(rl)}",
        "detail": " · ".join(f"{c['항목']}({c['상태']})" for c in checks),
        "status": status,
        "evidence": "review_log.csv · migration_verification · trial_provenance · decisions",
    }, checks


def c5_map():
    runs = list((paths.PROJECT / "experiments" / "baseline").glob("*"))
    return {
        "id": "C-5", "metric": "모델 성능 (참고 기준선)",
        "target": f"mAP@IoU 0.5 >= {MAP_FLOOR:.0%} "
                  f"(선례 EfficientDet-D0 실측 83.8%)",
        "value": "미측정",
        "detail": ("베이스라인 학습 미착수. 라벨 규칙이 확정되기 전 학습하면 "
                   "그 수치가 무엇의 성능인지 말할 수 없다"),
        "status": "**미측정** — STEP 12 후반",
        "evidence": f"experiments/baseline/ (현재 {len(runs)}개)",
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    c1, total = c1_error_rate()
    c4, checks = c4_traceability()
    rows = [c1, c2_agreement(), c3_class_balance(), c4, c5_map()]

    with (OUT / "evidence.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "metric", "target", "value",
                                           "detail", "status", "evidence"])
        w.writeheader(); w.writerows(rows)
    with (OUT / "traceability.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["항목", "상태", "내용"])
        w.writeheader(); w.writerows(checks)

    gaps = []
    for r in rows:
        # 충족이 아닌 것은 전부 격차다. '측정 불가' 를 빠뜨리면 가장 중요한 항목이 사라진다
        if not r["status"].startswith("충족"):
            gaps.append({"id": r["id"], "metric": r["metric"],
                         "무엇이 없나": r["status"].replace("**", ""),
                         "무엇이 있어야 하나": {
                             "C-1": "라벨링 진행에 따른 오류율 추이 (지금은 1시점)",
                             "C-2": "라벨러 2명 이상의 독립 라벨 결과",
                             "C-3": "시드 400장 라벨링 완료 후 클래스별 인스턴스 실측",
                             "C-4": ("REV-003(정본 격리 20쌍) · REV-005(누수 표본 101쌍) "
                                     "판정 완료"),
                             "C-5": "규칙 확정 후 베이스라인 학습 + mAP 측정",
                         }.get(r["id"], "")})
    with (OUT / "gaps.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "metric", "무엇이 없나", "무엇이 있어야 하나"])
        w.writeheader(); w.writerows(gaps)

    print(f"인증 대비 품질 지표 — {date.today().isoformat()}")
    print("기준: 파이프라인 문서 03 Quality Evidence (국가 AI 학습데이터 구축사업 참고선)\n")
    for r in rows:
        print(f"[{r['id']}] {r['metric']}")
        print(f"      목표  {r['target']}")
        print(f"      현재  {r['value']}")
        print(f"      상태  {r['status']}")
        print(f"      {r['detail']}\n")
    print(f"추적성 세부 {len(checks)}항목:")
    for c in checks:
        mark = "O" if c["상태"] == "확보" else "X"
        print(f"  [{mark}] {c['항목']:<20}{c['내용']}")
    print(f"\n미충족·미측정 {len(gaps)}건 -> gaps.csv")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
