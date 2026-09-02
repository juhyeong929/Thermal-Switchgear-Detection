"""OQ-013 — 정본의 규격 위반 박스를 **격리 목록**으로 분리한다.

정본 파일은 수정하지 않는다. 어느 박스가 정답인지 사람이 재검수하지 않은 상태에서
하나를 지우면 근거 없는 수정이 하나 더 늘어날 뿐이다.

    canonical_original  (그대로 둔다)
            ↓ audit
    위반 박스 식별
            ↓
    QUARANTINE 목록에 등재
            ↓
    학습셋 만들 때만 제외

학습셋 구축 스크립트가 `load_quarantine()` 을 불러 제외 대상을 걸러 쓴다.

출력: data/labeling/quarantine/canonical_quarantine.csv
"""

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

QDIR = paths.LABELING / "quarantine"
QFILE = QDIR / "canonical_quarantine.csv"

# 격리 사유 — 사유마다 해제 조건이 다르다
REASONS = {
    "duplicate_same_instance":
        "같은 인스턴스에 박스가 두 개. 어느 쪽이 옳은지 사람이 재검수해야 한다",
}


def load_quarantine():
    """{(image_stem, box_index)} — 학습셋에서 제외할 박스.

    box_index 는 정본 txt 파일의 줄 번호(0-base)다.
    `status != 해제` 인 행만 실제로 제외한다.
    """
    out = set()
    if not QFILE.exists():
        return out
    with QFILE.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r.get("status") or "").strip() == "해제":
                continue
            try:
                out.add((r["image"].strip(), int(r["box_index"])))
            except (KeyError, ValueError):
                continue
    return out


REVIEW = paths.REPORTS / "labeling" / "quarantine_review.csv"

# 판정 문구 -> 어느 박스를 남기는가. 판정표의 small_box / big_box 열이 가리킨다.
KEEP_BY_VERDICT = {"큰쪽_유지": "big_box", "작은쪽_유지": "small_box"}
REVIEWER_DEFAULT = "김주형"          # REV-003 검수자 (review_log.csv)


def load_verdicts():
    """사람 판정을 (이미지, '3+5') -> {keep 박스번호, verdict, pair_id} 로 읽는다.

    `둘다_제외` 는 남길 박스가 없으므로 keep 을 -1 로 둔다 (양쪽 제외확정).
    `둘다_유효` · `판단불가` 는 판정이 서지 않은 것이므로 등재하지 않는다 —
    미판정으로 남겨야 다음 검수에서 다시 걸린다.
    """
    out = {}
    if not REVIEW.exists():
        return out
    with REVIEW.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            pid = (r.get("pair_id") or "").strip()
            v = (r.get("verdict") or "").strip()
            if not pid or pid.startswith("#") or not v:
                continue
            if v == "둘다_제외":
                keep = -1
            elif v in KEEP_BY_VERDICT:
                try:
                    keep = int(r[KEEP_BY_VERDICT[v]])
                except (KeyError, ValueError):
                    continue
            else:
                continue                      # 둘다_유효 · 판단불가 -> 미판정 유지
            out[(r["image"].strip(), r["boxes"].strip())] = {
                "keep": keep, "verdict": v, "pair_id": pid,
                "reviewer": (r.get("reviewer") or "").strip() or REVIEWER_DEFAULT,
            }
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    src = paths.AUDIT / "canonical_audit_detail.csv"
    if not src.exists():
        sys.exit("canonical_audit_detail.csv 가 없다. scripts/canonical_audit.py 를 먼저 실행한다.")

    with src.open(encoding="utf-8-sig") as fh:
        detail = list(csv.DictReader(fh))

    # ---- 사람 판정을 먼저 읽는다 (REV-003 · DEC-022) ------------------------
    # 이 스크립트는 생성기이지만 `status` · `resolved_by` · `resolution` 은
    # **사람이 넣은 값**이다. 그냥 덮어쓰면 검수 이력이 사라진다.
    # 실제로 2026-09-01 파이프라인 재실행에서 20쌍 판정이 초기화되는 사고가 났다.
    # 판정의 원천은 reports/labeling/quarantine_review.csv 하나뿐이므로
    # 매번 거기서 다시 적용한다 — 사람 손으로 CSV 를 고치지 않아도 되게 만든다.
    verdicts = load_verdicts()
    if verdicts:
        print(f"사람 판정 {len(verdicts)}쌍을 quarantine_review.csv 에서 읽었다")
    else:
        print("[주의] quarantine_review.csv 에 판정이 없다 — 전부 미판정으로 등재한다")

    rows = []
    for d in detail:
        if d["status"] != "FAIL":
            continue
        if d["audit_rule"] != "같은 클래스 중복":
            continue
        # box_index 가 "3+5" 형태다. 두 박스 모두 등재한다 —
        # 어느 쪽이 옳은지 모르므로 한쪽만 고르지 않는다.
        v = verdicts.get((d["image"], d["box_index"]))
        for bi in d["box_index"].split("+"):
            st, who, res = "QUARANTINE_PENDING_REVIEW", "", ""
            if v:
                st = "해제" if int(bi) == v["keep"] else "제외확정"
                who, res = v["reviewer"], f"{v['verdict']} (REV-003 · {v['pair_id']})"
            rows.append({
                "image": d["image"], "box_index": int(bi),
                "panel_id": d["panel_id"],
                "class_id": d["class_id"], "class_name": d["class_name"],
                "quarantine_reason": "duplicate_same_instance",
                "detail": f"{d['reason']} ({d['detail']})",
                "pair_with": d["box_index"],
                "status": st, "resolved_by": who, "resolution": res,
                "source_audit": "DEC-016",
            })

    QDIR.mkdir(parents=True, exist_ok=True)
    with QFILE.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    imgs = len({r["image"] for r in rows})
    # 쌍은 (이미지, 박스쌍) 으로 세야 한다. 문자열만 보면 다른 이미지의 "3+5" 가 합쳐진다
    pairs = len({(r["image"], r["pair_with"]) for r in rows})
    uniq = len({(r["image"], r["box_index"]) for r in rows})
    print(f"격리 등재 {pairs} 쌍 / 박스 {len(rows)}행 "
          f"(고유 박스 {uniq} — 한 박스가 두 쌍에 걸친 경우가 있다) / {imgs} 이미지")
    print(f"  반별   {dict(Counter(r['panel_id'] for r in rows))}")
    print(f"  클래스 {dict(Counter(r['class_name'] for r in rows))}")
    st = Counter(r["status"] for r in rows)
    cleared = {(r["image"], r["box_index"]) for r in rows if r["status"] == "해제"}
    print(f"\n상태  {dict(st)}")
    print(f"  고유 박스 {uniq} 중 해제 {len(cleared)} · 제외확정 {uniq - len(cleared)}")
    print(f"  학습 대상 박스: 4,177 -> {4177 - (uniq - len(cleared)):,} (DEC-022)")
    if st.get("QUARANTINE_PENDING_REVIEW"):
        print("  미판정이 남아 있다. 두 박스를 모두 등재했으므로 사람이 옳은 쪽을 정한다 —")
        print("  판정은 quarantine_review.csv 의 verdict 열에 적는다. 이 파일을 손으로 고치지 않는다.")
    else:
        print("  전건 판정 완료. 판정 원천은 reports/labeling/quarantine_review.csv 다.")
    print("  **이 파일은 생성물이다.** status 를 직접 편집하지 말 것 —")
    print("  다음 파이프라인 실행에서 덮어써진다. 판정은 quarantine_review.csv 에 넣는다.")
    print(f"\n정본 파일은 수정하지 않았다. -> {QFILE}")


if __name__ == "__main__":
    main()
