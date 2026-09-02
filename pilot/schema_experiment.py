"""라벨링 스키마 A / B / C 를 같은 데이터·같은 세션 분할로 비교한다.

  안 A  변압기와 변류기를 별도 클래스로 유지
  안 B  둘을 상위 장비 클래스 하나로 통합
  안 C  장비 대신 진단 포인트(접촉부) 중심

대상은 MOF 계열인 P3-MOF반 + P4-MOF&PT반. 세션이 4개라 세션 단위 분할이 가능하다.
분할은 세 실험에서 동일하게 고정한다 (스키마만 바뀌고 데이터는 같음).

  python schema_experiment.py --epochs 40
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"

# 원본 26 스키마 인덱스
TR, TR_C, CT, CT_C, MOF_F = 9, 10, 11, 13, 12

SCHEMAS = {
    # 안 A: 원본 유지. 변압기/변류기/각 접촉부/MOF퓨즈
    "A_separate": {TR: (0, "변압기"), CT: (1, "변류기"),
                   TR_C: (2, "변압기 접촉부"), CT_C: (3, "변류기 접촉부"),
                   MOF_F: (4, "MOF 1차측 전력퓨즈")},
    # 안 B: 변압기+변류기 -> 계기용변성기(통합), 접촉부도 통합
    "B_merged":   {TR: (0, "변성기(통합)"), CT: (0, "변성기(통합)"),
                   TR_C: (1, "변성기 접촉부(통합)"), CT_C: (1, "변성기 접촉부(통합)"),
                   MOF_F: (2, "MOF 1차측 전력퓨즈")},
    # 안 C: 진단 포인트만. 장비 본체는 학습하지 않는다
    "C_contacts": {TR_C: (0, "접촉부"), CT_C: (0, "접촉부"),
                   MOF_F: (1, "MOF 1차측 전력퓨즈")},
}


def gather():
    """P3 + P4 라벨을 모은다. 반환 {stem: [(cls, cx, cy, w, h)]}"""
    out = {}
    for d, only in ((DATA / "labels_ir_src", "P3"), (HERE / "_p4" / "labels", "P4")):
        for f in sorted(d.glob("*.txt")):
            if f.stem.split("_")[2] != only:
                continue
            bs = []
            for ln in f.read_text(encoding="utf-8").splitlines():
                q = ln.split()
                if len(q) == 5:
                    bs.append((int(q[0]), *map(float, q[1:])))
            if bs:
                out[f.stem] = bs
    return out


def img_path(stem):
    for p in (DATA / "ir" / f"{stem}.jpg", HERE / "_p4" / "images" / f"{stem}.jpg"):
        if p.exists():
            return p
    return None


def split_sessions(stems, val_sessions):
    tr = [s for s in stems if "_".join(s.split("_")[:4]) not in val_sessions]
    va = [s for s in stems if "_".join(s.split("_")[:4]) in val_sessions]
    return tr, va


def build(tag, mapping, data, tr_stems, va_stems):
    root = HERE / "dataset" / f"schema_{tag}"
    if root.exists():
        shutil.rmtree(root)
    names = {}
    for _o, (n, ko) in mapping.items():
        names[n] = ko
    names = [names[i] for i in sorted(names)]

    kept = collections.Counter()
    for split, stems in (("train", tr_stems), ("val", va_stems)):
        (root/"images"/split).mkdir(parents=True, exist_ok=True)
        (root/"labels"/split).mkdir(parents=True, exist_ok=True)
        for s in stems:
            lines = []
            for c, cx, cy, w, h in data[s]:
                if c not in mapping:
                    continue
                nid = mapping[c][0]
                lines.append(f"{nid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                kept[(split, nid)] += 1
            if not lines:
                continue        # 해당 스키마에서 대상 없는 프레임은 제외
            ip = img_path(s)
            if ip is None:
                continue
            shutil.copy2(ip, root/"images"/split/f"{s}.jpg")
            (root/"labels"/split/f"{s}.txt").write_text("\n".join(lines)+"\n",
                                                        encoding="utf-8")
    (root/"data.yaml").write_text(
        f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\n\n"
        f"nc: {len(names)}\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(names)),
        encoding="utf-8")
    ntr = len(list((root/"images"/"train").glob("*.jpg")))
    nva = len(list((root/"images"/"val").glob("*.jpg")))
    print(f"  [{tag}] 학습 {ntr}장 / 검증 {nva}장   클래스 {len(names)}개: {names}")
    for i, n in enumerate(names):
        print(f"      {n:<22} train {kept[('train', i)]:5d} · val {kept[('val', i)]:5d}")
    return root, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--model", default="yolo11s.pt")
    args = ap.parse_args()

    data = gather()
    sess = collections.Counter("_".join(s.split("_")[:4]) for s in data)
    print("대상 데이터 (P3-MOF반 + P4-MOF&PT반)")
    for k, v in sorted(sess.items()):
        print(f"  {k:<26} {v:4d}장")
    # 검증 세션 고정: P4 의 한 세션 + P3 는 세션이 1개뿐이라 학습에 둔다
    val_sessions = {"A1_B1_P4_2022-06-03"}
    tr_stems, va_stems = split_sessions(sorted(data), val_sessions)
    print(f"\n검증 세션 고정: {sorted(val_sessions)}  (학습 {len(tr_stems)} / 검증 {len(va_stems)})")

    from ultralytics import YOLO
    results = {}
    for tag, mapping in SCHEMAS.items():
        print(f"\n{'='*72}\n{tag}\n{'='*72}")
        root, names = build(tag, mapping, data, tr_stems, va_stems)
        m = YOLO(args.model)
        m.train(data=str(root/"data.yaml"), epochs=args.epochs, imgsz=320, batch=8,
                project=str(HERE/"runs"), name=f"schema_{tag}", device="cpu",
                workers=0, seed=0, val=True, plots=False, verbose=False,
                hsv_h=0.0, hsv_s=0.3, hsv_v=0.4, degrees=5.0, translate=0.1,
                scale=0.4, fliplr=0.5, flipud=0.0, mosaic=0.5, erasing=0.0)
        r = YOLO(str(HERE/"runs"/f"schema_{tag}"/"weights"/"best.pt")).val(
            data=str(root/"data.yaml"), imgsz=320, device="cpu", workers=0,
            plots=False, verbose=False)
        per = {names[int(c)]: (float(r.box.p[i]), float(r.box.r[i]), float(r.box.ap50[i]))
               for i, c in enumerate(r.box.ap_class_index)}
        results[tag] = (float(r.box.map50), float(r.box.map), per)
        print(f"  -> mAP50 {r.box.map50:.3f}  mAP50-95 {r.box.map:.3f}")
        for n, (p, rc, a) in per.items():
            print(f"     {n:<22} P {p:.3f}  R {rc:.3f}  mAP50 {a:.3f}")

    print(f"\n{'='*72}\n스키마 비교 (동일 데이터·동일 세션 분할)\n{'='*72}")
    print(f"{'스키마':<14}{'mAP50':>9}{'mAP50-95':>11}   클래스별 mAP50")
    for tag, (m50, m, per) in results.items():
        detail = "  ".join(f"{n}:{a:.2f}" for n, (_p, _r, a) in per.items())
        print(f"{tag:<14}{m50:>9.3f}{m:>11.3f}   {detail}")


if __name__ == "__main__":
    main()
