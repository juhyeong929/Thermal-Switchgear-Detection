"""검수 이력 대장을 만들고 점검한다 — 인증 기준 C-4 의 비어 있던 칸.

왜 필요한가
    인증 기준(파이프라인 03 Quality Evidence)은 **라벨러·검수자·가이드라인 개정 기록**을
    전량 추적 가능하게 요구한다. 지금 라벨러 기록(누가·무엇을 Skip·몇 분)과 결정 이력(DEC)은
    있지만, **"누가 언제 무엇을 검수해서 어떻게 판정했는가"** 가 파일로 남아 있지 않다.

    DEC 문서는 *결정* 의 기록이지 *검수 행위* 의 기록이 아니다. 인증 심사에서는 둘을
    따로 묻는다 — "이 라벨을 누가 확인했습니까" 에 DEC 번호로 답할 수 없다.

무엇을 하는가
    1. `data/labeling/review_log.csv` 서식을 만든다 (이미 있으면 건드리지 않는다)
    2. **이미 산출물로 증거가 남아 있는 검수 행위**를 초안 행으로 채운다.
       날짜·범위·방법·산출물은 파일에서 읽어 채우고, **`reviewer` 는 비워 둔다.**
       사람 이름을 만들어 넣지 않는다 — 그건 기록이 아니라 위조다.
    3. 대장의 빈 칸을 점검해 무엇이 남았는지 보고한다

행 하나의 뜻
    "누가(reviewer) 언제(date) 무엇을(scope/target) 어떤 방법으로(method) 확인해서
     어떻게 판정했고(result) 근거는 어디 있는가(artifact/decision)"

사용
    python scripts/review_log.py            # 서식 생성 + 점검
    python scripts/review_log.py --check    # 점검만
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

LOG = paths.LABELING / "review_log.csv"
FIELDS = ["review_id", "date", "reviewer", "role", "scope", "target",
          "method", "n_items", "result", "artifact", "decision", "note"]

RESULTS = ["PASS", "FAIL", "PARTIAL", "PENDING"]

HEADER_NOTES = [
    "# reviewer 는 **실제 확인한 사람 이름**을 적는다. 비어 있으면 미검수로 센다",
    "# role: 1차검수 / 2차검수 / 교차검수 / 감사 / 승인",
    "# result: " + " / ".join(RESULTS),
    "# 아래 초안 행은 산출물이 이미 존재하는 검수 행위다. reviewer 칸만 채우면 된다",
]


def draft_rows():
    """산출물이 실제로 있는 검수 행위만 초안으로 만든다. 없는 것은 만들지 않는다."""
    rows = []

    def add(rid, date, scope, target, method, n, result, artifact, decision, note=""):
        rows.append({"review_id": rid, "date": date, "reviewer": "", "role": "감사",
                     "scope": scope, "target": target, "method": method,
                     "n_items": n, "result": result, "artifact": artifact,
                     "decision": decision, "note": note})

    def count(p, key=None):
        p = Path(p)
        if not p.exists():
            return None
        with p.open(encoding="utf-8-sig") as fh:
            rs = [r for r in csv.DictReader(fh)
                  if not str(list(r.values())[0]).startswith("#")]
        return len(rs)

    n = count(paths.AUDIT / "migration_verification.csv")
    if n:
        add("REV-001", "2026-08-27", "기존 라벨 승계", "정본 4,177박스 (P1·P3·P4)",
            "26->28 변환 전후 클래스별 박스 수 대조", n, "PASS",
            "reports/data_audit/migration_verification.csv", "DEC-003",
            "손실 0 · 보류 0")

    n = count(paths.AUDIT / "canonical_audit_detail.csv")
    if n:
        add("REV-002", "2026-08-28", "정본 라벨 규격 감사",
            "정본 4,177박스", "좌표 기반 규칙 위반 탐지 + 표본 육안", n, "PARTIAL",
            "reports/data_audit/canonical_audit_summary.csv", "DEC-016",
            "제외 클래스·후보 위반 0 · 같은 클래스 중복 20쌍 발견")

    n = count(paths.LABELING / "quarantine" / "canonical_quarantine.csv")
    if n:
        add("REV-003", "2026-08-28", "정본 위반 박스 격리",
            f"중복 20쌍 {n}행", "원본 무수정 + 격리 목록 등재", n, "PENDING",
            "data/labeling/quarantine/canonical_quarantine.csv", "DEC-017",
            "격리 해제는 사람 재검수 후")

    d = paths.PROJECT / "experiments" / "labeling_review"
    f = sorted((paths.REPORTS / "labeling").glob("diff_MCCB*.csv"))
    if f:
        with f[-1].open(encoding="utf-8-sig") as fh:
            rs = [r for r in csv.DictReader(fh) if not r["image"].startswith("#")]
        done = [r for r in rs if (r.get("verdict") or "").strip()]
        add("REV-004", "2026-08-31", "시험 라벨 vs 기존 라벨 차이 판정",
            f"A_MISSING {len([r for r in rs if r['kind']=='A_MISSING'])}건",
            "차이를 기하로 분해 후 육안 판정", len(done),
            "PASS" if done else "PENDING",
            f[-1].name, "-", "판정을 가른 축은 잘림이 아니라 면적")

    f = paths.AUDIT / "oq016" / "sample_pairs.csv"
    n = count(f)
    if n:
        with (paths.AUDIT / "oq016" / "visual_review.csv").open(
                encoding="utf-8-sig") as fh:
            done = sum(1 for r in csv.DictReader(fh)
                       if (r.get("verdict") or "").strip()
                       and not str(r.get("pair_id", "")).startswith("#"))
        add("REV-005", "2026-08-31", "학습셋 누수 표본 검증",
            f"근접 미달 교차 쌍 층화 표본 {n}쌍",
            "나란히 비교 후 동일 시야 여부 판정", done,
            "PASS" if done == n and n else "PENDING",
            "reports/data_audit/oq016/visual_review.csv", "DEC-018",
            "판정 전에는 분할 정책을 바꾸지 않는다")
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="생성 없이 점검만")
    a = ap.parse_args()

    created = False
    if not LOG.exists() and not a.check:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(FIELDS)
            for note in HEADER_NOTES:
                w.writerow([note] + [""] * (len(FIELDS) - 1))
            dw = csv.DictWriter(fh, fieldnames=FIELDS)
            dw.writerows(draft_rows())
        created = True

    if not LOG.exists():
        print("검수 대장이 없다. --check 없이 실행하면 만든다.")
        return 1

    with LOG.open(encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh)
                if not str(r["review_id"]).startswith("#") and r["review_id"].strip()]

    signed = [r for r in rows if (r.get("reviewer") or "").strip()]
    pending = [r for r in rows if (r.get("result") or "").strip() == "PENDING"]

    print(f"검수 대장 {'생성' if created else '점검'} — {LOG}")
    print(f"  기록 {len(rows)}건 · 검수자 서명 {len(signed)}건 · 판정 대기 {len(pending)}건\n")
    print(f"  {'ID':<9}{'날짜':<12}{'검수자':<10}{'결과':<9}{'범위'}")
    for r in rows:
        who = (r.get("reviewer") or "").strip() or "(미기재)"
        print(f"  {r['review_id']:<9}{r['date']:<12}{who:<10}"
              f"{r['result']:<9}{r['scope']}")

    if len(signed) < len(rows):
        print(f"\n  [인증 C-4] 검수자가 비어 있는 행 {len(rows)-len(signed)}건. "
              f"**이름을 채워야 '전량 추적 가능' 이 성립한다.**")
        print("  사람 이름은 만들어 넣지 않는다 — 실제 확인한 사람이 직접 적는다.")
    if pending:
        print(f"  판정 대기 {len(pending)}건: "
              f"{', '.join(r['review_id'] for r in pending)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
