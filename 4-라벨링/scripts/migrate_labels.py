"""기존 26개 스키마 라벨을 v2 28개 스키마로 승계하고, 승계가 온전한지 검증한다.

정본 소스만 옮긴다 (audit_labels.py 의 겹침 분석 결과):
  A3검수완료 = _p1only (757파일 동일, 상이 0)  -> P1
  _p3        = IR1_3반 (66파일 동일, 상이 0)   -> P3
  _p4                                          -> P4

안전장치
  1. 원본은 읽기만 한다. 먼저 data/backup 으로 통째 복사한 뒤 변환한다.
  2. 변환 결과는 새 경로(data/labeling/reviewed)에 쓴다. pilot 을 덮어쓰지 않는다.
  3. 박스 좌표는 건드리지 않는다. 바뀌는 것은 class id 뿐이다.
  4. 매핑이 확정되지 않은 박스(split-unresolved)는 변환하지 않고 보류 목록에 남긴다.

출력: data/backup/<source>/...                       원본 스냅샷
      data/labeling/reviewed/<source>/...            v2 라벨
      reports/data_audit/migration_verification.csv  클래스별 승계 대조표
      reports/data_audit/migration_unresolved.csv    보류 박스 (있으면)
"""

import csv
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
from schemas import classes_v1_26 as v1  # noqa: E402

# (소스명, pilot 상대경로, 라벨 txt 가 들어 있는 하위 경로)
CANONICAL_SOURCES = [
    ("P1_A3검수완료", "A3 검수완료"),
    ("P3__p3",        "_p3"),
    ("P4__p4",        "_p4"),
]
SKIP_NAMES = {"train.txt", "val.txt", "test.txt", "classes.txt", "obj.names"}
PANEL_RE = re.compile(r"_(P\d+)_")


def label_files(root):
    for f in sorted(root.rglob("*.txt")):
        if f.name in SKIP_NAMES or f.name.startswith("._"):
            continue
        yield f


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    paths.BACKUP.mkdir(parents=True, exist_ok=True)
    out_root = paths.LABELING / "reviewed"
    out_root.mkdir(parents=True, exist_ok=True)

    before = Counter()      # (source, old_id) -> 박스 수
    after = Counter()       # (source, new_id) -> 박스 수
    unresolved = []
    n_files = 0

    for src_name, rel in CANONICAL_SOURCES:
        src = paths.PILOT / rel
        if not src.exists():
            print(f"  [건너뜀] {rel} 경로 없음")
            continue

        # 1) 원본 스냅샷 — 이후 어떤 작업을 해도 되돌아올 수 있게 한다.
        bak = paths.BACKUP / src_name
        if bak.exists():
            shutil.rmtree(bak)
        shutil.copytree(src, bak)

        # 2) 변환
        dst = out_root / src_name
        dst.mkdir(parents=True, exist_ok=True)
        for f in label_files(src):
            panel = PANEL_RE.search(f.stem)
            panel_id = panel.group(1) if panel else None
            lines_out = []
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                p = line.split()
                if len(p) < 5:
                    continue
                try:
                    old = int(float(p[0]))
                except ValueError:
                    continue
                before[(src_name, old)] += 1
                new = v1.new_id(old, panel_id)
                if new is None:
                    unresolved.append({
                        "source": src_name, "file": f.name, "panel_id": panel_id or "",
                        "old_class_id": old,
                        "old_class_ko": v1.OLD_BY_ID[old][1],
                        "reason": "split 대상이나 해당 반의 v2 대응이 정의되지 않음",
                    })
                    continue
                after[(src_name, new)] += 1
                lines_out.append(" ".join([str(new)] + p[1:5]))
            (dst / f.name).write_text(
                "\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")
            n_files += 1

    # 3) 검증표 — 구 클래스별 박스 수와 v2 클래스별 박스 수를 나란히 놓는다.
    rows = []
    for (src, old), n in sorted(before.items()):
        new = v1.new_id(old, None)
        c = v2.BY_ID[new] if new is not None else None
        rows.append({
            "source": src,
            "old_class_id": old, "old_class_ko": v1.OLD_BY_ID[old][1],
            "boxes_before": n,
            "new_class_id": c.class_id if c else "",
            "new_guide_no": c.guide_no if c else "",
            "new_class_ko": c.canonical_name if c else "(보류)",
            "boxes_after": after.get((src, new), 0) if new is not None else 0,
            "migration_type": v1.MIGRATION[old][1],
            "match": "OK" if (new is not None and after.get((src, new), 0) >= n) else "확인필요",
        })

    paths.AUDIT.mkdir(parents=True, exist_ok=True)
    vpath = paths.AUDIT / "migration_verification.csv"
    with vpath.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    upath = paths.AUDIT / "migration_unresolved.csv"
    with upath.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["source", "file", "panel_id",
                                           "old_class_id", "old_class_ko", "reason"])
        w.writeheader()
        w.writerows(unresolved)

    tb, ta = sum(before.values()), sum(after.values())
    print(f"라벨 파일 {n_files}개 변환")
    print(f"  변환 전 박스 {tb}")
    print(f"  변환 후 박스 {ta}")
    print(f"  보류(미변환) {len(unresolved)}")
    print(f"  손실 {tb - ta - len(unresolved)}  <- 0 이어야 정상")
    print(f"\n원본 스냅샷 -> {paths.BACKUP}")
    print(f"v2 라벨     -> {out_root}")
    print(f"검증표      -> {vpath.name}, {upath.name}")


if __name__ == "__main__":
    main()
