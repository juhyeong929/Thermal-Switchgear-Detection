"""모델 예측을 CVAT 에 올릴 수 있는 YOLO 1.1 어노테이션 zip 으로 내보낸다.

CVAT 의 어노테이션 import 는 태스크 전체를 덮어쓴다. 그래서 예측분만 담아 올리면
이미 사람이 작업한 프레임의 라벨이 지워질 수 있다. 이를 막기 위해 이 스크립트는
**기존 사람 라벨 + 미작업분 예측**을 합쳐서 내보낸다. 그대로 import 하면 사람 작업은
그대로 남고 빈 프레임만 채워진다.

  python export_cvat_pred.py --weights runs/p1_scenarioA/weights/best.pt \
      --task IR1_1반 --out out/cvat/IR1_1반_preannot.zip

  --with-images 를 주면 이미지도 함께 담아 새 태스크를 만들 수 있다.

원본 데이터는 읽기만 한다.
"""
from __future__ import annotations

import argparse
import collections
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import OSD_BOXES  # noqa: E402
from classes import KOREAN_BY_ID, NAMES, PANEL_CLASSES  # noqa: E402
from predict import osd_overlap_ratio, panel_of  # noqa: E402

HERE = Path(__file__).parent


def write_cvat_xml(out: Path, imgs, body_for, label_names, used_labels):
    """CVAT for images 1.1 XML. 이미지 없이 어노테이션만 올릴 때 쓰는 네이티브 포맷."""
    from xml.sax.saxutils import escape
    from PIL import Image

    n_human = n_pred = n_empty = n_box = 0
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>",
             "  <version>1.1</version>", "  <meta>", "    <task>", "      <labels>"]
    for n in used_labels:
        parts += ["        <label>", f"          <name>{escape(n)}</name>",
                  "          <type>rectangle</type>", "          <attributes></attributes>",
                  "        </label>"]
    parts += ["      </labels>", "    </task>", "  </meta>"]

    for i, p in enumerate(imgs):
        w, h = Image.open(p).size
        body, kind = body_for(p.stem)
        lines = [l for l in body.splitlines() if l.strip()]
        if not lines:
            n_empty += 1
        elif kind == "human":
            n_human += 1
        else:
            n_pred += 1
        parts.append(f'  <image id="{i}" name="{escape(p.name)}" width="{w}" height="{h}">')
        for ln in lines:
            f = ln.split()
            if len(f) < 5:
                continue
            cid = int(f[0])
            cx, cy, bw, bh = (float(v) for v in f[1:5])
            x1 = max(0.0, (cx - bw/2) * w); y1 = max(0.0, (cy - bh/2) * h)
            x2 = min(float(w), (cx + bw/2) * w); y2 = min(float(h), (cy + bh/2) * h)
            parts.append(
                f'    <box label="{escape(label_names[cid])}" occluded="0" source="manual" '
                f'xtl="{x1:.2f}" ytl="{y1:.2f}" xbr="{x2:.2f}" ybr="{y2:.2f}" z_order="0">'
                "</box>")
            n_box += 1
        parts.append("  </image>")
    parts.append("</annotations>")
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return n_human, n_pred, n_empty, n_box


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--task", required=True,
                    help="CVAT export 폴더 (obj_train_data 가 있는 곳). 예: IR1_1반")
    ap.add_argument("--out", default=None)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--format", choices=["xml", "yolo"], default="xml",
                    help="xml = CVAT for images 1.1 (어노테이션만 올릴 때 권장). "
                         "yolo = YOLO 1.1 (이미지가 함께 있어야 import 된다)")
    ap.add_argument("--with-images", action="store_true",
                    help="yolo 포맷에서 이미지를 함께 담는다. CVAT YOLO 임포터는 "
                         "이미지가 없으면 'No media data found' 로 실패한다")
    ap.add_argument("--no-panel-filter", action="store_true")
    ap.add_argument("--osd-max", type=float, default=0.4)
    ap.add_argument("--overwrite-human", action="store_true",
                    help="사람이 그린 라벨도 예측으로 덮는다. 기본은 보존")
    ap.add_argument("--only-sessions", nargs="*", default=None,
                    help="이 세션들에만 예측을 넣는다. 예: A2_B1_P1_2022-06-03")
    ap.add_argument("--classes", nargs="*", default=None,
                    help="예측에 넣을 클래스(한글명). 지정하면 나머지는 비워 둔다")
    ap.add_argument("--sessions", choices=["started", "all"], default="started",
                    help="started = 사람이 이미 작업한 세션의 미라벨 프레임에만 예측을 넣는다. "
                         "본 적 없는 세션은 예측 품질이 나빠 검수가 오히려 손해라 비워 둔다.")
    args = ap.parse_args()

    task = Path(args.task)
    # CVAT export 는 obj_train_data 가 한 단계 더 중첩되는 경우가 있다. jpg 가 실제로
    # 들어 있는 디렉터리를 찾는다.
    cands = [d for d in task.rglob("obj_train_data") if d.is_dir() and any(d.glob("*.jpg"))]
    if not cands:
        raise SystemExit(f"이미지가 든 obj_train_data 를 찾지 못했습니다: {task}")
    src = max(cands, key=lambda d: len(list(d.glob("*.jpg"))))
    if src != task / "obj_train_data":
        print(f"이미지 디렉터리: {src.relative_to(task)}")
    weights = Path(args.weights)
    if not weights.exists():
        raise SystemExit(f"가중치가 없습니다: {weights}")

    # CVAT 는 라벨을 이름으로 매칭한다. 우리 내부 키(영문)를 그대로 쓰면 매칭에 실패하거나
    # 프로젝트에 새 라벨이 생긴다. 태스크가 내보낸 obj.names 를 그대로 되돌려준다.
    # 출력 라벨명은 항상 한글 26개 기준. 태스크 obj.names 가 부분집합이어도 인덱스는
    # 우리 스키마를 쓰고, XML meta 에는 실제로 등장한 라벨만 선언한다
    # (등록되지 않은 라벨을 선언하면 CVAT 가 import 를 거부한다).
    out_names = [KOREAN_BY_ID[i] for i in range(len(NAMES))]
    tnf = next((p for p in task.rglob("obj.names")), None)
    if tnf:
        tn = [l.strip() for l in tnf.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"태스크 obj.names 클래스 {len(tn)}개 (예: {tn[:3]})")

    src_labels = {f.stem: None for f in src.glob("*.txt")}   # 존재 확인용
    task_idx_to_ours = None
    if tnf:
        korean_to_id = {v: k for k, v in KOREAN_BY_ID.items()}
        lookup = {**korean_to_id, **{n: i for i, n in enumerate(NAMES)}}
        miss = [n for n in tn if n not in lookup]
        if miss:
            raise SystemExit(f"우리 스키마에 없는 클래스명: {miss}")
        task_idx_to_ours = {i: lookup[n] for i, n in enumerate(tn)}

    imgs = sorted(src.glob("*.jpg"))
    human = {}
    for f in src.glob("*.txt"):
        out = []
        for ln in f.read_text(encoding="utf-8").splitlines():
            q = ln.split()
            if len(q) < 5:
                continue
            cid = int(q[0])
            if task_idx_to_ours is not None:      # 태스크 인덱스 -> 우리 26 스키마
                cid = task_idx_to_ours.get(cid, cid)
            out.append(f"{cid} " + " ".join(q[1:5]))
        if out:
            human[f.stem] = "\n".join(out) + "\n"
    todo = [p for p in imgs if args.overwrite_human or p.stem not in human]
    skipped_sessions = []
    if args.only_sessions:
        want = set(args.only_sessions)
        todo = [p for p in todo if "_".join(p.stem.split("_")[:4]) in want]
        print(f"지정 세션에만 예측: {', '.join(sorted(want))}")
    elif args.sessions == "started":
        started = {"_".join(s.split("_")[:4]) for s in human}
        before = len(todo)
        todo = [p for p in todo if "_".join(p.stem.split("_")[:4]) in started]
        skipped_sessions = sorted({"_".join(p.stem.split("_")[:4]) for p in imgs
                                   if "_".join(p.stem.split("_")[:4]) not in started})
        if before != len(todo):
            print(f"미착수 세션 {len(skipped_sessions)}개({before-len(todo)}장)는 예측을 넣지 않습니다:")
            for s in skipped_sessions:
                print(f"   {s}")
    print(f"프레임 {len(imgs)}장 · 사람 라벨 {len(human)}장 · 예측 대상 {len(todo)}장")

    from ultralytics import YOLO
    model = YOLO(str(weights))

    class_filter = None
    if args.classes:
        korean_to_id = {v: k for k, v in KOREAN_BY_ID.items()}
        bad = [c for c in args.classes if c not in korean_to_id]
        if bad:
            raise SystemExit(f"모르는 클래스명: {bad}")
        class_filter = {korean_to_id[c] for c in args.classes}
        print(f"예측 클래스 제한: {', '.join(args.classes)}")

    pred, cls_count = {}, collections.Counter()
    dropped_panel = dropped_osd = dropped_cls = 0
    for p in todo:
        r = model.predict(str(p), conf=args.conf, imgsz=320, device="cpu", verbose=False)[0]
        h, w = r.orig_shape
        allowed = None
        if not args.no_panel_filter:
            panel = panel_of(p.stem)
            if panel:
                allowed = {NAMES.index(c) for c in PANEL_CLASSES.get(panel, []) if c in NAMES}
        lines = []
        for b in r.boxes:
            cid = int(b.cls.item())
            box = b.xyxy[0].tolist()
            if allowed is not None and cid not in allowed:
                dropped_panel += 1
                continue
            if class_filter is not None and cid not in class_filter:
                dropped_cls += 1
                continue
            if osd_overlap_ratio(box, w, h) >= args.osd_max:
                dropped_osd += 1
                continue
            x1, y1, x2, y2 = box
            lines.append(f"{cid} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} "
                         f"{(x2-x1)/w:.6f} {(y2-y1)/h:.6f}")
            cls_count[cid] += 1
        pred[p.stem] = "\n".join(lines) + ("\n" if lines else "")

    ext = "zip" if args.format == "yolo" else "xml"
    out = Path(args.out) if args.out else \
        HERE / "out" / "cvat" / f"{task.name}_preannot.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)

    def body_for(stem):
        if stem in human and not args.overwrite_human:
            return human[stem], "human"
        return pred.get(stem, ""), "pred"

    if args.format == "xml":
        used = set()
        for p_ in imgs:
            b_, _k = body_for(p_.stem)
            for ln_ in b_.splitlines():
                q_ = ln_.split()
                if len(q_) >= 5:
                    used.add(out_names[int(q_[0])])
        used_labels = [n for n in out_names if n in used]
        n_human, n_pred, n_empty, n_box = write_cvat_xml(out, imgs, body_for, out_names, used_labels)
        print(f"\n-> {out}  ({out.stat().st_size/1e6:.2f} MB, CVAT for images 1.1)")
        print(f"   사람 라벨 보존 {n_human}장 · 예측 채움 {n_pred}장 · 빈 프레임 {n_empty}장")
        print(f"   총 박스 {n_box}개 "
              f"(반 후보와 달라 버림 {dropped_panel}, 클래스 제한 {dropped_cls}, "
              f"오버레이 겹쳐 버림 {dropped_osd})")
        for cid, n in cls_count.most_common():
            print(f"     {KOREAN_BY_ID[cid]:<20} {n:4d}")
        print("\nCVAT 에 올리는 방법")
        print("  태스크 > Actions > Upload annotations > 'CVAT for images 1.1' > 이 xml")
        print("  이미지가 필요 없는 포맷이라 어노테이션만 올라갑니다.")
        print("  사람 라벨이 함께 들어 있어 덮어써도 기존 작업이 보존됩니다.")
        print("\n검수 후:  Export annotations > YOLO 1.1 -> python ingest_ir.py <내려받은.zip>")
        return

    if not args.with_images:
        print("\n주의: YOLO 1.1 은 이미지가 없으면 CVAT 가 'No media data found' 로 거부합니다.")
        print("      --with-images 를 붙이거나 --format xml 을 쓰세요.")
    n_human = n_pred = n_empty = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("obj.data", f"classes = {len(out_names)}\ntrain = data/train.txt\n"
                               "names = data/obj.names\nbackup = backup/\n")
        z.writestr("obj.names", "\n".join(out_names) + "\n")
        z.writestr("train.txt",
                   "\n".join(f"data/obj_train_data/{p.name}" for p in imgs) + "\n")
        for p in imgs:
            if p.stem in human and not args.overwrite_human:
                body = human[p.stem]; n_human += 1
            else:
                body = pred.get(p.stem, "")
                if body.strip():
                    n_pred += 1
                else:
                    n_empty += 1
            z.writestr(f"obj_train_data/{p.stem}.txt", body)
            if args.with_images:
                z.write(p, f"obj_train_data/{p.name}")

    print(f"\n-> {out}  ({out.stat().st_size/1e6:.1f} MB)")
    print(f"   사람 라벨 보존 {n_human}장 · 예측 채움 {n_pred}장 · 여전히 빈 프레임 {n_empty}장")
    print(f"   예측 박스 {sum(cls_count.values())}개 "
          f"(반 후보와 달라 버림 {dropped_panel}, 클래스 제한 {dropped_cls}, "
              f"오버레이 겹쳐 버림 {dropped_osd})")
    for cid, n in cls_count.most_common():
        print(f"     {KOREAN_BY_ID[cid]:<20} {n:4d}")

    print("\nCVAT 에 올리는 방법")
    print("  기존 태스크에 얹기:  태스크 > Actions > Upload annotations > YOLO 1.1 > 이 zip")
    print("    사람 라벨이 함께 들어 있으므로 덮어써도 기존 작업이 보존됩니다.")
    print("  새 태스크로 만들기:  --with-images 로 다시 뽑아 이미지까지 포함")
    print("\n검수 후:  Export annotations > YOLO 1.1 -> python ingest_ir.py <내려받은.zip>")


if __name__ == "__main__":
    main()
