"""CVAT YOLO 1.1 export 를 회수 규격으로 정규화한다. **원본은 보존한다.**

왜 필요한가 — 실측으로 확인한 사실
    CVAT 의 YOLO 1.1 export 는 **그 프로젝트의 라벨 목록 순서로 0부터 다시 번호를 매긴다.**
    우리 `classes.txt` 는 v2 class_id(= 가이드번호 − 1)를 지키려고 쓰지 않는 자리에
    `__사용안함_N` 을 넣어 둔 성긴 번호 체계다. CVAT 은 그 자리표시자를 모른다.

        classes.txt   ... 케이블헤드=13 ... 콘덴서=17 MCCB=18 ... MCCB 접촉부=27
        obj.names     ... 케이블헤드=11 ... 콘덴서=14 MCCB=15 ... MCCB 접촉부=17

    즉 **CVAT 을 쓰는 한 id 는 반드시 어긋난다.** 프로젝트를 다시 만들어도 마찬가지다.
    좌표와 개수는 멀쩡하므로 손실은 없고, 이름으로 되돌리면 정확히 복원된다.
    (`pilot/cvat_import.py` 가 쓰던 방식과 같다.)

무엇을 하는가
    1. 원본 export 를 `_raw_export/<라벨러>/` 로 옮겨 그대로 보존한다
       **라벨러 폴더 밖이다.** 안에 두면 `agreement.py` 가 같은 이름의 txt 를 둘 다 읽어
       정규화본을 덮어쓴다 (실측으로 확인한 사고다)
    2. `obj.names` 로 **이름 -> classes.txt 줄 번호** 를 복원해 `yolo/*.txt` 를 새로 쓴다
    3. 박스 수가 원본과 같은지, `yolo/` 밖에 txt 가 남지 않았는지 확인한다

    `agreement.py` 는 수정하지 않는다. 정규화된 `yolo/` 를 그대로 읽으면 된다.

무엇을 하지 않는가
    **이름이 `classes.txt` 에 없으면 아무것도 쓰지 않고 멈춘다.** 모르는 클래스를
    임의의 번호에 넣지 않는다. 라벨 목록이 잘못된 프로젝트라는 뜻이므로 사람이 봐야 한다.

사용
    python scripts/trial_ingest.py data/labeling/draft/trial/annotator_A
    python scripts/trial_ingest.py --all          # annotator_A ~ E 중 export 가 있는 것 전부
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402

TRIAL = paths.LABELING / "draft" / "trial"
# 원본 export 는 **라벨러 폴더 밖**에 둔다.
#   agreement.py 는 작업 폴더를 rglob("*.txt") 하므로, 원본을 폴더 안에 두면
#   같은 이름(A01.txt)이 둘이 되어 정규화본을 덮어쓴다. 실측으로 확인한 사고다.
#   폴더 밖으로 빼면 구조적으로 불가능해진다 — agreement.py 는 여전히 무수정.
RAW_ROOT = TRIAL / "_raw_export"
ANNOTATORS = ["annotator_A", "annotator_B", "annotator_C", "annotator_D", "annotator_E"]
NOT_LABEL = {"obj.names", "train.txt", "classes.txt", "obj.data"}


def find_export(d):
    """`obj.names` 가 있는 폴더가 곧 export 뿌리다. 압축을 어떻게 풀었든 찾아낸다.

    이미 옮겨 둔 원본(`_raw_export/<이름>`)을 먼저 본다. 다시 돌려도 결과가 같아야 한다.
    """
    for base in (RAW_ROOT / d.name, d / "yolo_raw", d / "yolo", d, d / "cvat"):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("obj.names")):
            return p.parent
    return None


def stray_labels(d):
    """`yolo/` **바로 아래**가 아닌 곳에 남은 txt.

    agreement.py 는 작업 폴더를 rglob 하므로 같은 stem 이 둘이면 정규화본을 덮어쓴다.
    `yolo/` 밖뿐 아니라 **`yolo/` 안에 중첩된 원본도 같은 사고를 낸다** —
    annotator_D 가 export 를 `yolo/annotator_D/obj_train_data/...` 로 풀어 넣어
    실제로 확인됐다. 그래서 부모가 정확히 `yolo/` 인 것만 정상으로 본다.
    """
    ydir = (d / "yolo").resolve()
    out = []
    for p in sorted(d.rglob("*.txt")):
        if p.name in NOT_LABEL:
            continue
        if p.resolve().parent != ydir:
            out.append(p)
    return out


def load_names(export_root):
    return [l.strip() for l in (export_root / "obj.names").read_text(
        encoding="utf-8").splitlines() if l.strip()]


def nospace(s):
    """공백을 모두 뺀 이름. 라벨러가 CVAT 에 손으로 클래스를 추가할 때
    'VCB 접촉부' 를 'VCB접촉부' 로 적는 일이 실제로 있었다."""
    return "".join(s.split())


def load_class_index():
    """classes.txt: 줄 번호가 곧 class_id. 자리표시자도 한 줄로 센다."""
    lines = (TRIAL / "classes.txt").read_text(encoding="utf-8").splitlines()
    name2id = {n.strip(): i for i, n in enumerate(lines) if n.strip()}
    return name2id, lines


def loose_index(name2id):
    """공백을 뺀 이름 -> class_id. 공백만 빼서 겹치는 이름이 있으면 쓰지 않는다."""
    loose = {}
    for n, i in name2id.items():
        k = nospace(n)
        if k in loose:
            return {}                     # 모호하면 느슨한 대조를 포기한다
        loose[k] = i
    return loose


def ingest(d, dry_run=False):
    """돌려주는 것: (성공 여부, 요약 dict)."""
    d = Path(d)
    info = {"annotator": d.name, "remapped": [], "images": 0, "boxes": 0,
            "empty": 0, "problems": [], "whitespace_matched": []}

    export = find_export(d)
    if export is None:
        info["problems"].append("obj.names 를 찾지 못했다 — export 를 풀어 넣었는지 확인")
        return False, info

    names = load_names(export)
    name2id, class_lines = load_class_index()

    # 공백만 다른 이름은 이어 준다. 다만 **조용히 넘기지 않고** 보고에 남긴다.
    loose = loose_index(name2id)
    for n in names:
        if n not in name2id and nospace(n) in loose:
            name2id[n] = loose[nospace(n)]
            info["whitespace_matched"].append((n, class_lines[loose[nospace(n)]].strip()))

    # 이름이 하나라도 모르면 **아무것도 쓰지 않는다**
    unknown = [n for n in names if n not in name2id]
    # 태그 전용 라벨(촬영유형)은 박스로 나오지 않으므로 실제 사용 여부로 판단한다
    raw_files = [p for p in sorted(export.rglob("*.txt")) if p.name not in NOT_LABEL]
    used = set()
    for p in raw_files:
        for line in p.read_text(encoding="utf-8").splitlines():
            t = line.split()
            if len(t) >= 5:
                used.add(int(float(t[0])))
    unknown_used = [n for n in unknown if n in {names[i] for i in used if i < len(names)}]
    if unknown_used:
        info["problems"].append(
            f"classes.txt 에 없는 클래스가 실제로 그려졌다: {', '.join(unknown_used)}")
        return False, info
    if unknown:
        info["unused_unknown"] = unknown      # 선언만 되고 안 쓰인 라벨 (촬영유형 등)

    bad_id = sorted(i for i in used if i >= len(names))
    if bad_id:
        info["problems"].append(f"obj.names 범위를 벗어난 class_id: {bad_id}")
        return False, info

    remap = {i: name2id[n] for i, n in enumerate(names) if n in name2id}
    info["remapped"] = [(i, names[i], remap[i]) for i in sorted(used)
                        if remap.get(i) != i]

    # ---- 원본 보존 — 라벨러 폴더 **밖**으로 뺀다 ----
    raw_dir = RAW_ROOT / d.name
    ydir = d / "yolo"
    info["raw_dir"] = raw_dir
    if raw_dir.resolve() not in (export.resolve(), *export.parents):
        if raw_dir.exists():
            info["problems"].append(
                f"{raw_dir} 가 이미 있는데 다른 곳에서 export 를 찾았다 — 사람이 확인")
            return False, info
        if not dry_run:
            raw_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(export), str(raw_dir))    # 원본은 이 뒤로 읽기만 한다
            export = raw_dir
            raw_files = [p for p in sorted(export.rglob("*.txt"))
                         if p.name not in NOT_LABEL]
            # 옮기고 남은 빈 껍데기 폴더 정리 (yolo/annotator_A 같은 중간 폴더)
            for leftover in sorted(d.rglob("*"), reverse=True):
                if leftover.is_dir() and not any(leftover.iterdir()):
                    leftover.rmdir()
            ydir.mkdir(exist_ok=True)

    # ---- 정규화본 쓰기 ----
    src_boxes = 0
    out = {}
    for p in raw_files:
        lines = []
        for line in p.read_text(encoding="utf-8").splitlines():
            t = line.split()
            if len(t) < 5:
                continue
            src_boxes += 1
            lines.append(" ".join([str(remap[int(float(t[0]))])] + t[1:5]))
        out[p.stem] = lines

    info["images"] = len(out)
    info["boxes"] = sum(len(v) for v in out.values())
    info["empty"] = sum(1 for v in out.values() if not v)

    if info["boxes"] != src_boxes:
        info["problems"].append(f"박스 수가 달라졌다: {src_boxes} -> {info['boxes']}")
        return False, info

    if not dry_run:
        ydir.mkdir(exist_ok=True)
        for stem, lines in out.items():
            (ydir / f"{stem}.txt").write_text(
                ("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    # yolo/ 밖에 txt 가 남아 있으면 agreement.py 가 정규화본을 덮어쓴다
    if not dry_run:
        stray = stray_labels(d)
        if stray:
            info["problems"].append(
                "yolo/ 밖에 라벨 txt 가 남아 있다 (agreement.py 가 덮어쓴다): "
                + ", ".join(str(x.relative_to(d)) for x in stray[:5]))
            return False, info

    # 30장과 대조 — 없는 장 / 모르는 장
    expected = {p.stem for p in (TRIAL / "images").glob("*.jpg")}
    if expected:
        info["missing"] = sorted(expected - set(out))
        info["extra"] = sorted(set(out) - expected)
    return True, info


def report(info):
    print(f"\n=== {info['annotator']} ===")
    if info["problems"]:
        for p in info["problems"]:
            print(f"  [실패] {p}")
        return
    print(f"  이미지 {info['images']}장 (빈 파일 {info['empty']}) · 박스 {info['boxes']}")
    if info["remapped"]:
        print(f"  class_id 복원 {len(info['remapped'])}종 "
              f"(CVAT 은 자기 라벨 순서로 0부터 다시 매긴다)")
        print(f"    {'obj.names':>9}  {'클래스':<18}{'classes.txt':>11}")
        for src, name, dst in info["remapped"]:
            print(f"    {src:>9}  {name:<18}{dst:>11}")
    else:
        print("  class_id 복원: 없음 (이미 classes.txt 와 같다)")
    if info.get("whitespace_matched"):
        for got, want in info["whitespace_matched"]:
            print(f"  [주의] 공백만 다른 라벨명을 이어 붙였다: "
                  f"'{got}' -> '{want}' (라벨러가 CVAT 에 손으로 추가한 것)")
    if info.get("unused_unknown"):
        print(f"  classes.txt 에 없지만 그려지지 않은 라벨: "
              f"{', '.join(info['unused_unknown'])} (태그 전용이면 정상)")
    if info.get("missing"):
        print(f"  [주의] 라벨 파일이 없는 장 {len(info['missing'])}: "
              f"{', '.join(info['missing'][:8])}"
              f"{' ...' if len(info['missing']) > 8 else ''}")
    if info.get("extra"):
        print(f"  [주의] 배포본에 없는 장: {', '.join(info['extra'])}")
    if info.get("raw_dir"):
        print(f"  원본 보존 -> {info['raw_dir']}  (라벨러 폴더 밖)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dirs", nargs="*", help="라벨러 폴더")
    ap.add_argument("--all", action="store_true", help="annotator_A ~ E 전부")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 무엇이 바뀌는지만 본다")
    a = ap.parse_args()

    targets = [TRIAL / x for x in ANNOTATORS] if a.all else [Path(x) for x in a.dirs]
    targets = [t for t in targets if t.is_dir()]
    if not targets:
        sys.exit("대상 폴더가 없다")

    fails = 0
    for d in targets:
        if a.all and find_export(d) is None:
            continue                       # 아직 제출 안 한 사람은 건너뛴다
        ok, info = ingest(d, a.dry_run)
        report(info)
        fails += 0 if ok else 1

    if a.dry_run:
        print("\n(dry-run — 아무것도 쓰지 않았다)")
    else:
        print(f"\n원본 export 는 {RAW_ROOT.name}/ 에 그대로 있다 (라벨러 폴더 밖). "
              f"정규화본은 yolo/*.txt")
        print("다음: python scripts/cvat_xml_to_attributes.py <폴더>")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
