"""데이터셋 전수 감사 — 추측 없이 실제 파일에서 읽은 값만 출력한다.

  python audit_dataset.py

확인 항목
  라벨 소스별 인벤토리 / 클래스별 이미지·박스 수 / 세션·날짜·현장 분포
  train-val 분할 구성과 세션 누수 여부 / 클래스 불균형
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID  # noqa: E402

HERE = Path(__file__).parent
W, H = 320, 240

SOURCES = {
    "P1반 IR1 (A1·A2·A3 검수완료)": HERE / "_p1only" / "labels",
    "P4반 IR1 1차검수본": HERE / "_p4" / "labels",
    "누적 labels_ir_src (P1+P3)": HERE / "data" / "labels_ir_src",
    "학습셋 data/labels_ir": HERE / "data" / "labels_ir",
}


def read(d: Path):
    """반환: {stem: [(cls, cx, cy, w, h), ...]}"""
    out = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.txt")):
        if f.name == "classes.txt":
            continue
        bs = []
        for ln in f.read_text(encoding="utf-8").splitlines():
            q = ln.split()
            if len(q) == 5:
                bs.append((int(q[0]), *map(float, q[1:])))
        out[f.stem] = bs
    return out


def sess_of(stem):
    return "_".join(stem.split("_")[:4])


def site_of(stem):
    return stem.split("_")[0]


def panel_of(stem):
    return stem.split("_")[2]


def section(title):
    print(f"\n{'='*78}\n{title}\n{'='*78}")


def main():
    section("1. 라벨 소스별 인벤토리")
    for tag, d in SOURCES.items():
        data = read(d)
        nb = sum(len(v) for v in data.values())
        empty = sum(1 for v in data.values() if not v)
        print(f"  {tag}")
        print(f"     경로 {d.relative_to(HERE) if d.is_relative_to(HERE) else d}")
        print(f"     파일 {len(data)}개 · 박스 {nb}개 · 빈 라벨 {empty}개")

    section("2. 클래스별 이미지 수 / 박스 수  (P1 전용 + P4 1차)")
    merged = {}
    merged.update({k: v for k, v in read(SOURCES["P1반 IR1 (A1·A2·A3 검수완료)"]).items()})
    p4 = read(SOURCES["P4반 IR1 1차검수본"])
    for k, v in p4.items():
        merged[k] = v
    box = collections.Counter()
    img = collections.defaultdict(set)
    for s, bs in merged.items():
        for c, *_ in bs:
            box[c] += 1
            img[c].add(s)
    print(f"  {'클래스':<22}{'박스':>7}{'이미지':>8}{'장당':>8}{'비율':>8}")
    tot = sum(box.values())
    for c, n in box.most_common():
        print(f"  {KOREAN_BY_ID[c]:<22}{n:>7}{len(img[c]):>8}"
              f"{n/len(img[c]):>8.2f}{n/tot*100:>7.1f}%")
    print(f"  {'합계':<22}{tot:>7}{len(merged):>8}")
    if box:
        mx, mn = max(box.values()), min(box.values())
        print(f"\n  클래스 불균형: 최대 {mx} / 최소 {mn} = {mx/max(mn,1):.0f}배")

    section("3. Transformer / CT / 접촉부 분포  (핵심 쟁점)")
    KEY = {9: "변압기", 10: "변압기 접촉부", 11: "변류기", 13: "변류기 접촉부"}
    per_panel = collections.defaultdict(collections.Counter)
    per_sess = collections.defaultdict(collections.Counter)
    cooccur = collections.Counter()
    for s, bs in merged.items():
        cs = {c for c, *_ in bs if c in KEY}
        if 9 in cs and 11 in cs:
            cooccur["변압기+변류기 동시"] += 1
        for c, *_ in bs:
            if c in KEY:
                per_panel[panel_of(s)][c] += 1
                per_sess[sess_of(s)][c] += 1
    print(f"  {'반':<8}" + "".join(f"{v:>16}" for v in KEY.values()))
    for pan in sorted(per_panel):
        print(f"  {pan:<8}" + "".join(f"{per_panel[pan][c]:>16}" for c in KEY))
    print(f"\n  같은 사진에 변압기와 변류기가 함께 있는 장수: "
          f"{cooccur['변압기+변류기 동시']}장")
    print("\n  세션별")
    print(f"  {'세션':<26}" + "".join(f"{v:>14}" for v in KEY.values()))
    for sk in sorted(per_sess):
        print(f"  {sk:<26}" + "".join(f"{per_sess[sk][c]:>14}" for c in KEY))

    section("4. 박스 크기 — 변압기 vs 변류기 형태 비교")
    geo = collections.defaultdict(list)
    for s, bs in merged.items():
        for c, cx, cy, w, h in bs:
            if c in KEY:
                geo[c].append((w*W, h*H, cx, cy))
    print(f"  {'클래스':<16}{'n':>5}{'가로중앙':>10}{'세로중앙':>10}{'면적비':>9}"
          f"{'종횡비':>9}{'중심x':>8}{'중심y':>8}")
    for c in KEY:
        a = np.array(geo[c]) if geo[c] else None
        if a is None or len(a) == 0:
            print(f"  {KEY[c]:<16}{0:>5}   (없음)")
            continue
        print(f"  {KEY[c]:<16}{len(a):>5}{np.median(a[:,0]):>10.0f}{np.median(a[:,1]):>10.0f}"
              f"{np.median(a[:,0]*a[:,1])/(W*H)*100:>8.1f}%"
              f"{np.median(a[:,0]/a[:,1]):>9.2f}{np.median(a[:,2]):>8.2f}{np.median(a[:,3]):>8.2f}")

    section("5. 촬영 세션 / 날짜 / 현장 분포")
    sess = collections.Counter(sess_of(s) for s in merged)
    site = collections.Counter(site_of(s) for s in merged)
    date = collections.Counter(s.split("_")[3] for s in merged)
    print(f"  세션 {len(sess)}개 · 현장 {len(site)}곳 · 촬영일 {len(date)}종")
    for k, v in sorted(sess.items()):
        print(f"     {k:<26} {v:4d}장")
    print(f"  현장: {dict(site)}")
    print(f"  촬영일: {dict(sorted(date.items()))}")

    section("6. 현재 train/val 구성과 세션 누수")
    root = HERE / "dataset" / "ir"
    if not root.is_dir():
        print("  dataset/ir 없음")
        return
    for sp in ("train", "val"):
        stems = [p.stem for p in (root/"images"/sp).glob("*.jpg")]
        c = collections.Counter()
        for st in stems:
            f = root/"labels"/sp/f"{st}.txt"
            if f.exists():
                for ln in f.read_text(encoding="utf-8").splitlines():
                    q = ln.split()
                    if len(q) == 5:
                        c[int(q[0])] += 1
        ss = collections.Counter(sess_of(s) for s in stems)
        print(f"  [{sp}] {len(stems)}장 · 박스 {sum(c.values())} · 세션 {len(ss)}개")
        for k, v in sorted(ss.items()):
            print(f"       {k:<26} {v:4d}장")
        for k, v in c.most_common():
            print(f"       {KOREAN_BY_ID[k]:<22} {v:5d}")
    tr = {sess_of(p.stem) for p in (root/"images"/"train").glob("*.jpg")}
    va = {sess_of(p.stem) for p in (root/"images"/"val").glob("*.jpg")}
    both = tr & va
    print(f"\n  train·val 양쪽에 걸친 세션: {len(both)}개 {sorted(both) if both else ''}")
    print("  -> " + ("세션 누수 있음. 검증 점수가 부풀려진다" if both
                     else "세션 누수 없음"))
    trs = {p.stem for p in (root/"images"/"train").glob("*.jpg")}
    vas = {p.stem for p in (root/"images"/"val").glob("*.jpg")}
    print(f"  동일 파일 중복: {len(trs & vas)}건")


if __name__ == "__main__":
    main()
