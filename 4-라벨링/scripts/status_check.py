"""지금 상태를 **파일에서 직접 읽어** 점검한다. 문서에 적힌 숫자를 믿지 않는다.

문서는 사람이 쓰다가 어긋난다. 이 스크립트는 실제 파일만 보고
`무엇이 준비됐고 · 누가 어디까지 냈고 · 무엇이 어긋났는지` 를 다시 센다.

검사 묶음
    1 배포본       30장 · 실화상 · classes.txt · CVAT 라벨 정의
    2 스키마       classes.txt 줄 번호 == v2 class_id (어긋나면 회수가 전부 틀어진다)
    3 라벨러 제출   yolo/ · cvat/ · skip_log · time_log · attributes.csv
    4 회수 위생     yolo/ 밖 라벨 txt 없음 · 원본 export 보존
    5 산출물       주요 CSV 존재 여부
    6 미해소       OPEN QUESTION 열림/닫힘 · 지금 라벨링을 막는 항목

출력: 화면 + reports/status/trial_status.csv
"""

import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
RAW_ROOT = TRIAL / "_raw_export"
ANNOTATORS = ["annotator_A", "annotator_B", "annotator_C", "annotator_D", "annotator_E"]
NOT_LABEL = {"obj.names", "train.txt", "classes.txt", "obj.data"}

ROWS = []


def note(group, item, value, verdict=""):
    ROWS.append({"group": group, "item": item, "value": value, "verdict": verdict})
    mark = f"  {verdict}" if verdict else ""
    print(f"  {item:<34}{value}{mark}")


def data_rows(path, key="annotator"):
    """주석(#)과 빈 줄을 뺀 실제 기록 행."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh)
                if not (r.get(key) or "").strip().startswith("#")
                and (r.get(key) or "").strip()]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"점검 {date.today().isoformat()} — 문서가 아니라 파일을 읽는다\n")

    # ---- 1 배포본 ----
    print("[1] 배포본")
    imgs = sorted(p.stem for p in (TRIAL / "images").glob("*.jpg"))
    note("배포본", "시험 이미지", f"{len(imgs)}장", "OK" if len(imgs) == 30 else "확인")
    rgb = len(list((TRIAL / "reference_rgb").glob("*.jpg")))
    note("배포본", "식별용 실화상", f"{rgb}장")
    labels_json = TRIAL / "cvat_labels.json"
    note("배포본", "CVAT 라벨 정의", "있음" if labels_json.exists() else "없음",
         "OK" if labels_json.exists() else "배포 전 필수")

    # ---- 2 스키마 ----
    print("\n[2] 스키마 일관성 — 어긋나면 회수가 전부 틀어진다")
    names = [n.strip() for n in (TRIAL / "classes.txt").read_text(
        encoding="utf-8").splitlines()]
    note("스키마", "classes.txt 줄 수", f"{len(names)} (v2 {len(v2.CLASSES)})",
         "OK" if len(names) == len(v2.CLASSES) else "불일치")
    bad = [c.canonical_name for c in v2.CLASSES
           if c.label_status != v2.EXCLUDE and v2.unit_confirmed(c.class_name)
           and names[c.class_id] != c.canonical_name]
    note("스키마", "줄 번호 == v2 class_id", "일치" if not bad else f"불일치 {bad}",
         "OK" if not bad else "FAIL")
    ph = sum(1 for n in names if n.startswith("__사용안함"))
    note("스키마", "자리표시자", f"{ph}개 · 사용 {len(names) - ph}종")

    # ---- 3 라벨러 제출 ----
    print("\n[3] 라벨러 제출")
    print(f"  {'':<12}{'yolo':>6}{'박스':>6}{'빈':>4}{'XML':>5}"
          f"{'Skip':>6}{'시간':>6}{'속성':>6}")
    submitted = []
    for who in ANNOTATORS:
        d = TRIAL / who
        if not d.is_dir():
            continue
        txts = [p for p in (d / "yolo").glob("*.txt")] if (d / "yolo").is_dir() else []
        boxes = empty = 0
        for p in txts:
            n = len([l for l in p.read_text(encoding="utf-8").splitlines()
                     if len(l.split()) >= 5])
            boxes += n
            empty += (n == 0)
        xml = "O" if any((d / "cvat").glob("*.xml")) else "-"
        sk = data_rows(d / "skip_log.csv")
        tl = data_rows(d / "time_log.csv")
        mins = 0
        for r in (tl or []):
            m = (r.get("minutes") or "").strip()
            if m.replace(".", "", 1).isdigit():
                mins += float(m)
            else:
                st, en = (r.get("start") or ""), (r.get("end") or "")
                if ":" in st and ":" in en:
                    h1, m1 = (int(x) for x in st.split(":")[:2])
                    h2, m2 = (int(x) for x in en.split(":")[:2])
                    mins += (h2 * 60 + m2 - h1 * 60 - m1) % (24 * 60)
        att = "O" if (d / "attributes.csv").exists() else "-"
        print(f"  {who:<12}{len(txts):>6}{boxes:>6}{empty:>4}{xml:>5}"
              f"{len(sk or []):>6}{(str(int(mins)) + '분') if mins else '-':>6}{att:>6}")
        ROWS.append({"group": "제출", "item": who,
                     "value": f"yolo {len(txts)} · 박스 {boxes} · 빈 {empty} · XML {xml} · "
                              f"Skip {len(sk or [])} · {int(mins)}분 · 속성 {att}",
                     "verdict": "제출" if txts else "미제출"})
        if txts:
            submitted.append(who)
    note("제출", "제출한 라벨러", f"{len(submitted)}/{len(ANNOTATORS)}",
         "일치도 계산 가능" if len(submitted) >= 2 else "2명 이상부터 일치도 계산")

    # ---- 4 회수 위생 ----
    print("\n[4] 회수 위생")

    # Skip 로그 정합성 — 잘못 적힌 case_id 와 '빈 파일인데 Skip 기록 없음' 은
    # 둘 다 조용히 지표를 왜곡한다. 전자는 그 Skip 이 무시되고,
    # 후자는 '대상 없음' 으로 비교에 들어간다.
    for who in submitted:
        d = TRIAL / who
        sk = data_rows(d / "skip_log.csv") or []
        ids = {r["case_id"].strip() for r in sk if (r.get("case_id") or "").strip()}
        unknown = sorted(ids - set(imgs))
        empt = {q.stem for q in (d / "yolo").glob("*.txt")
                if not q.read_text(encoding="utf-8").strip()}
        silent = sorted(empt - ids)
        if unknown:
            note("위생", f"{who} 배포본에 없는 case_id",
                 f"{len(unknown)}건 ({', '.join(unknown)})", "확인")
        if silent:
            note("위생", f"{who} 빈 파일인데 Skip 기록 없음",
                 f"{len(silent)}장 ({', '.join(silent[:4])}"
                 f"{' …' if len(silent) > 4 else ''}) — '대상 없음' 으로 비교된다", "확인")
        if not unknown and not silent:
            note("위생", f"{who} Skip 로그 정합성", "일치", "OK")

    stray = []
    for who in submitted:
        d = TRIAL / who
        ydir = (d / "yolo").resolve()
        stray += [p for p in d.rglob("*.txt")
                  if p.name not in NOT_LABEL and ydir not in p.resolve().parents]
    note("위생", "yolo/ 밖 라벨 txt",
         "없음" if not stray else f"{len(stray)}개 — agreement.py 가 덮어쓴다",
         "OK" if not stray else "FAIL")
    kept = [p.name for p in RAW_ROOT.iterdir()] if RAW_ROOT.is_dir() else []
    note("위생", "원본 export 보존", f"{len(kept)}명분 ({', '.join(kept) or '없음'})",
         "OK" if len(kept) == len(submitted) else "확인")
    for who in submitted:
        f = TRIAL / who / "attributes_unmatched.csv"
        n = len(list(csv.DictReader(f.open(encoding="utf-8-sig")))) if f.exists() else None
        if n is not None:
            note("위생", f"{who} XML↔YOLO 대응 실패", f"{n}건",
                 "OK" if n == 0 else "확인")

    # ---- 5 산출물 ----
    print("\n[5] 주요 산출물")
    for label, p in [
        ("이미지 인벤토리", paths.METADATA / "image_inventory.csv"),
        ("중복 제거 결과", paths.PROJECT / "data" / "dedup" / "dedup_metadata.csv"),
        ("시드 후보 400장", paths.LABELING / "seed" / "seed_candidates.csv"),
        ("시험셋 30장", paths.LABELING / "seed" / "trial_set.csv"),
        ("정본 격리 목록", paths.LABELING / "quarantine" / "canonical_quarantine.csv"),
        ("학습셋 분할", paths.PROJECT / "data" / "splits" / "image_split.csv"),
        ("라벨러 지침서", paths.REPORTS / "labeling" / "annotator_guide_v1.html"),
        ("회수 전달문", paths.REPORTS / "labeling" / "trial_instructions.md"),
    ]:
        note("산출물", label, "있음" if p.exists() else "없음",
             "OK" if p.exists() else "확인")

    # ---- 5-1 시드 정합성 (A-3) --------------------------------------------
    # "정책은 바뀌었는데 시드는 그대로" 를 자동으로 잡는다.
    # 초판 감사에서 seed_candidates.csv 가 DEC-021 이전 상태로 남아 있었다.
    # 원인은 run_all.py 에 seed_select.py 가 없어 정책 변경이 전파되지 않은 것이다.
    print("\n[5-1] 시드 정합성 — 정책 변경이 시드에 반영됐는가")
    import hashlib
    import json as _json
    sys.path.insert(0, str(paths.SCRIPTS))
    spath = paths.LABELING / "seed" / "seed_policy.json"
    cpath = paths.LABELING / "seed" / "seed_candidates.csv"
    if not spath.exists():
        note("시드", "정책 지문", "없음 — seed_select.py 를 실행한다", "FAIL")
    elif not cpath.exists():
        note("시드", "시드 후보 파일", "없음", "FAIL")
    else:
        stored = _json.loads(spath.read_text(encoding="utf-8"))
        import seed_select as ss
        with (paths.AUDIT / "class_inventory.csv").open(encoding="utf-8-sig") as fh:
            seen = {r["class_name"]: int(r["existing_instance_count"])
                    for r in csv.DictReader(fh)}
        now = ss.policy_signature(seen)
        same = now["policy_sha256"] == stored.get("policy_sha256")
        note("시드", "정책 지문 일치",
             "일치" if same else "**불일치 — 정책이 바뀌었다. seed_select.py 재실행 필요**",
             "OK" if same else "FAIL")
        if not same:
            op, np_ = stored.get("policy", {}), now["policy"]
            for k in sorted(set(op) | set(np_)):
                if op.get(k) != np_.get(k):
                    note("시드", f"  바뀐 정책 항목", k, "FAIL")

        with cpath.open(encoding="utf-8-sig") as fh:
            ids = sorted(r["image_id"] for r in csv.DictReader(fh))
        h = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()
        ok = h == stored.get("image_id_sha256")
        note("시드", "이미지 목록 지문",
             f"{len(ids)}장 · " + ("일치" if ok else "**불일치 — CSV 가 손으로 수정됐다**"),
             "OK" if ok else "FAIL")
        note("시드", "생성 시점", stored.get("generated_at", "?"))

        # 시험셋 30장이 여전히 시드 안에 있는가 (목록이 바뀌면 계보가 깨진다)
        tset = paths.LABELING / "seed" / "trial_set.csv"
        if tset.exists():
            with tset.open(encoding="utf-8-sig") as fh:
                a = [r for r in csv.DictReader(fh) if r.get("group") == "A_본대상"]
            miss = [r["case_id"] for r in a if r["image_id"] not in set(ids)]
            note("시드", "시험셋 A군 계보",
                 f"{len(a) - len(miss)}/{len(a)}장이 시드에 남아 있음"
                 + (f" · 이탈 {miss}" if miss else ""),
                 "OK" if not miss else "확인")

    # ---- 5-2 분석 전용 임계값이 새지 않았는가 (NQ-12) -----------------------
    # 0.003 은 **감사·분석 전용**이며 공식 threshold 로 승격하지 않았다
    # (labeling_rules.SMALL_OBJECT_SCOPE). 지침서에 수치가 들어가면
    # 뒤 라벨러가 앞사람과 다른 규칙을 본 것이 되어 회차 간 비교가 오염된다.
    print("\n[5-2] 분석 전용 임계값 유출 검사 (NQ-12)")
    from schemas import labeling_rules as rules
    th = str(rules.SMALL_OBJECT_CANDIDATE)
    targets = list((paths.REPORTS / "labeling" / "generated").glob("*"))
    targets += [paths.REPORTS / "labeling" / "annotator_guide_v1.md",
                paths.REPORTS / "labeling" / "trial_instructions.md",
                TRIAL / "classes.txt"]
    for g in sorted((paths.REPORTS / "labeling").glob("annotator_guide_v2*")):
        targets.append(g)
    leaked = []
    for t in targets:
        if not t.is_file():
            continue
        try:
            if th in t.read_text(encoding="utf-8"):
                leaked.append(t.name)
        except (UnicodeDecodeError, OSError):
            continue
    note("임계값", f"{th} 배포 문서 유출",
         "없음" if not leaked else f"**{', '.join(leaked)}**",
         "OK" if not leaked else "FAIL")
    note("임계값", "승격 상태", rules.SMALL_OBJECT_STATUS)

    # ---- 5-3 지침서 v2 배포 준비 ------------------------------------------
    # 라벨러가 막혔을 때 물어볼 곳이 없으면 각자 규칙을 만든다 — v1 의 실제 결함이었다.
    print("\n[5-3] 지침서 v2 배포 준비")
    gv2 = paths.REPORTS / "labeling" / "annotator_guide_v2.md"
    if not gv2.exists():
        note("지침서", "v2 생성", "없음 — build_guide_tables.py 를 실행한다", "확인")
    else:
        txt = gv2.read_text(encoding="utf-8")
        blanks = txt.count("<<채워 넣을 것")
        note("지침서", "v2 생성", "있음", "OK")
        note("지침서", "escalation 연락처",
             "기입 완료" if not blanks else f"**미기입 {blanks}곳 — 배포 금지**",
             "OK" if not blanks else "FAIL")
        # v2 §1 표가 현재 스키마와 같은지 (손으로 고쳐지지 않았는가)
        gen = paths.REPORTS / "labeling" / "generated" / "panel_class_table.md"
        if gen.exists():
            body = gen.read_text(encoding="utf-8").split("### 어떤 반에서도")[0]
            rowsq = [l for l in body.splitlines() if l.startswith("| P")]
            miss = [l.split("|")[1].strip() for l in rowsq if l not in txt]
            note("지침서", "v2 §1 표 ↔ 스키마",
                 "일치" if not miss else f"**불일치: {', '.join(miss)}**",
                 "OK" if not miss else "FAIL")

    # ---- 6 미해소 ----
    print("\n[6] 미해소 사항")
    with (paths.AUDIT / "open_questions.csv").open(encoding="utf-8-sig") as fh:
        oq = list(csv.DictReader(fh))
    op = [q for q in oq if q["status"] != "닫힘"]
    blk = [q for q in oq if q.get("blocks_current_labeling") == "YES"]
    note("미해소", "OPEN QUESTION", f"열림 {len(op)} / 닫힘 {len(oq) - len(op)}")
    note("미해소", "지금 라벨링을 막는 항목", f"{len(blk)}건",
         "OK" if not blk else "확인")
    note("미해소", "결정 문서", f"{len(list(paths.DECISIONS.glob('DEC-*.md')))}건")

    out = paths.REPORTS / "status" / "trial_status.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["group", "item", "value", "verdict"])
        w.writeheader()
        w.writerows(ROWS)
    bad_n = sum(1 for r in ROWS if r["verdict"] in ("FAIL", "확인"))
    print(f"\n-> {out}")
    print(f"확인이 필요한 항목 {bad_n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
