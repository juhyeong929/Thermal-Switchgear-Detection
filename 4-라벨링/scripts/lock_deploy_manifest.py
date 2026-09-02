"""시험 회차의 **입력판을 고정**한다 — 파일 목록 + SHA-256.

왜 필요한가
------------
지침서 v2 는 10개 반을 전부 담은 한 문서다. 회차가 끝난 뒤 다른 반의 정책이 바뀌면
문서가 달라지고, "D/E 가 작업한 v2" 와 "최종 v2" 가 같은 문서가 아니게 된다.
측정 조건이 바뀌지 않아도 **판본 동일성**이 깨지면 결과를 재현할 수 없다.

그래서 회차 시작 전에 그 회차가 받은 파일과 해시를 박아 둔다. 나중에 정책이 바뀌어도
`--verify` 로 "그때 그 파일이었는가" 를 다시 확인할 수 있다.

  round 2 (D/E) — guide v2.0   P1 · P3 · P4 · P6 · P9
    NQ-18(인입선로 접촉부)은 P5 전용이고 이 회차에 P5 가 없다. 회신 결과가
    이 회차의 클래스 목록·task·측정 대상을 바꾸지 않는다. 그래서 회신을 기다리지
    않고 여기서 잠근다. 회신 뒤의 P5 변경은 v2.1 로 간다.

사용
    python scripts/lock_deploy_manifest.py            잠근다 (덮어쓰기 전 확인)
    python scripts/lock_deploy_manifest.py --verify   지금 파일이 잠근 것과 같은가
"""

import argparse
import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402

ROUND = 2
GUIDE_VERSION = "v2.0"
PANELS = ["P1-TR반", "P3-MOF반", "P4-MOF&PT반", "P6-VCB반", "P9-MCCB반"]

TRIAL = paths.LABELING / "draft" / "trial"
LAB = paths.REPORTS / "labeling"
GEN = LAB / "generated"
OUT = GEN / f"deploy_manifest_round{ROUND}.csv"


def files():
    """이 회차의 입력이 되는 파일. 역할별로 묶어 둔다."""
    yield "정책 원본", paths.SCHEMAS / "classes_v2.py"
    yield "정책 원본", paths.SCHEMAS / "labeling_rules.py"

    yield "라벨러 배포", LAB / "annotator_guide_v2.md"
    yield "라벨러 배포", LAB / "trial_instructions.md"
    yield "라벨러 배포", LAB / "bounding_box_boundary_spec.md"
    yield "라벨러 배포", GEN / "panel_class_table.md"
    for p in PANELS:
        yield "라벨러 배포", LAB / "class_reference" / f"{p}.md"

    for p in PANELS:
        pid = v2.panel_id(p)
        yield "CVAT 설정", GEN / "cvat_labels" / f"{pid}.json"
        yield "CVAT 설정", GEN / "cvat_labels" / f"{pid}.names"
    yield "CVAT 설정", TRIAL / "cvat_labels.json"
    yield "CVAT 설정", TRIAL / "classes.txt"

    yield "배포본", TRIAL / "manifest.csv"

    yield "검수자", LAB / "deploy_checklist_D_E.md"
    yield "검수자", LAB / "escalation.txt"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_sha(folder, pattern="*.jpg"):
    """폴더 안 파일 집합의 지문. 이름과 내용이 모두 같아야 같은 값이 나온다."""
    h = hashlib.sha256()
    items = sorted(folder.glob(pattern), key=lambda p: p.name)
    for p in items:
        h.update(p.name.encode("utf-8"))
        h.update(sha(p).encode("ascii"))
    return h.hexdigest(), len(items)


def collect():
    rows, missing = [], []
    for role, path in files():
        if not path.exists():
            missing.append(path)
            continue
        rows.append({
            "role": role,
            "path": path.relative_to(paths.PROJECT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha(path),
        })
    for role, folder, pat in [("배포본", TRIAL / "images", "*.jpg"),
                              ("배포본", TRIAL / "reference_rgb", "*.jpg")]:
        digest, n = dir_sha(folder, pat)
        rows.append({
            "role": role,
            "path": folder.relative_to(paths.PROJECT).as_posix() + f"/ ({n}개)",
            "bytes": sum(p.stat().st_size for p in folder.glob(pat)),
            "sha256": digest,
        })
    return rows, missing


FIELDS = ["role", "path", "bytes", "sha256"]


def read_locked():
    if not OUT.exists():
        return None
    with OUT.open(encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh)
                if not (r.get("role") or "").startswith("#")]


def verify(rows):
    locked = read_locked()
    if locked is None:
        print(f"잠긴 manifest 가 없다: {OUT}")
        return 1
    now = {r["path"]: r["sha256"] for r in rows}
    was = {r["path"]: r["sha256"] for r in locked}
    changed = sorted(p for p in was if p in now and was[p] != now[p])
    gone = sorted(set(was) - set(now))
    added = sorted(set(now) - set(was))
    for label, items in [("바뀐 파일", changed), ("없어진 파일", gone),
                         ("잠근 뒤 늘어난 파일", added)]:
        if items:
            print(f"{label} {len(items)}건")
            for p in items:
                print(f"    {p}")
    if not (changed or gone or added):
        print(f"round {ROUND} · guide {GUIDE_VERSION} — {len(was)}개 항목 전부 일치")
        return 0
    print(f"\nround {ROUND} 의 입력판이 잠근 상태와 다르다. "
          f"회차 조건이 바뀌었는지 확인한다.")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="잠근 manifest 와 현재 파일이 같은지만 확인한다 (쓰기 없음)")
    ap.add_argument("--force", action="store_true",
                    help="이미 잠긴 manifest 를 덮어쓴다")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    rows, missing = collect()
    if missing:
        print("배포 입력 파일이 없다 — 잠글 수 없다:")
        for p in missing:
            print(f"    {p}")
        return 1

    if a.verify:
        return verify(rows)

    if OUT.exists() and not a.force:
        print(f"이미 잠겨 있다: {OUT}")
        print("회차 입력판은 한 번만 잠근다. 다시 잠그려면 --force 를 준다.")
        print("(정책이 바뀌었다면 덮어쓰지 말고 새 판본 번호로 회차를 나눈다)")
        return verify(rows)

    total = hashlib.sha256(
        "".join(f"{r['path']}:{r['sha256']}" for r in rows).encode("utf-8")).hexdigest()
    head = [
        {"role": f"# round {ROUND} 배포 입력판 고정 — guide {GUIDE_VERSION}", "path": "", "bytes": "", "sha256": ""},
        {"role": f"# 대상 반: {' '.join(PANELS)} (P5 없음 — NQ-18 무관)", "path": "", "bytes": "", "sha256": ""},
        {"role": "# 검증: python scripts/lock_deploy_manifest.py --verify", "path": "", "bytes": "", "sha256": ""},
        {"role": "# manifest_sha256", "path": "", "bytes": "", "sha256": total},
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(head + rows)

    print(f"round {ROUND} · guide {GUIDE_VERSION} 입력판 고정 — {len(rows)}개 항목")
    for role in ["정책 원본", "라벨러 배포", "CVAT 설정", "배포본", "검수자"]:
        n = sum(1 for r in rows if r["role"] == role)
        print(f"  {role:<10}{n}개")
    print(f"  manifest_sha256  {total}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
