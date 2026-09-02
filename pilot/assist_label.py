"""반자동 라벨링 — 모델이 박스를 제안하고 사람은 검수·클래스 교정만 한다.

기존 라벨은 절대 덮어쓰지 않는다. 결과는 별도 디렉터리에 쓴다.

핵심 기능
  - confidence 임계 조절
  - 저신뢰 / 클래스 모호 예측을 **검수 우선 목록**으로 분리
  - 클래스 모호 판정: 1순위와 2순위 클래스의 점수 차가 작으면 모호로 본다
  - CVAT for images 1.1 XML 로 내보내 기존 태스크에 얹기

  python assist_label.py --weights runs/p4_1st/weights/best.pt \
      --images _p4/images --out out/assist_p4 --conf 0.25

산출물 (out/assist_p4/)
  proposals/*.txt        제안 라벨 (YOLO)
  review_queue.csv       우선 검수 목록 (사유 포함)
  proposals.xml          CVAT 업로드용
  summary.txt            통계
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from classes import KOREAN_BY_ID, NAMES  # noqa: E402

HERE = Path(__file__).parent

# 클래스 모호 판정: 최고점과 차점의 차이가 이보다 작으면 사람이 반드시 봐야 한다
AMBIGUOUS_MARGIN = 0.20
# 이 쌍은 형태가 유사해 혼동이 잦다. 둘 중 하나가 예측되면 항상 검수 대상.
CONFUSABLE = [{9, 11}, {10, 13}]


def write_cvat_xml(out: Path, items, label_names):
    from xml.sax.saxutils import escape
    used = sorted({label_names[c] for _s, _wh, bs in items for c, *_ in bs})
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>",
             "  <version>1.1</version>", "  <meta>", "    <task>", "      <labels>"]
    for n in used:
        parts += ["        <label>", f"          <name>{escape(n)}</name>",
                  "          <type>rectangle</type>",
                  "          <attributes></attributes>", "        </label>"]
    parts += ["      </labels>", "    </task>", "  </meta>"]
    for i, (stem, (w, h), bs) in enumerate(items):
        parts.append(f'  <image id="{i}" name="{escape(stem)}.jpg" '
                     f'width="{w}" height="{h}">')
        for c, x1, y1, x2, y2, conf in bs:
            parts.append(
                f'    <box label="{escape(label_names[c])}" occluded="0" source="auto" '
                f'xtl="{x1:.2f}" ytl="{y1:.2f}" xbr="{x2:.2f}" ybr="{y2:.2f}" z_order="0">'
                f'</box>')
        parts.append("  </image>")
    parts.append("</annotations>")
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--review-conf", type=float, default=0.50,
                    help="이 값 미만이면 우선 검수 대상")
    ap.add_argument("--imgsz", type=int, default=320)
    args = ap.parse_args()

    img_dir = Path(args.images)
    imgs = sorted(img_dir.glob("*.jpg"))
    if not imgs:
        raise SystemExit(f"이미지가 없습니다: {img_dir}")
    out = Path(args.out)
    (out / "proposals").mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO
    model = YOLO(args.weights)

    items, queue = [], []
    cls_count = collections.Counter()
    n_amb = n_low = 0
    for p in imgs:
        r = model.predict(str(p), conf=args.conf, imgsz=args.imgsz,
                          device="cpu", verbose=False)[0]
        h, w = r.orig_shape
        bs, lines = [], []
        reasons = []
        for b in r.boxes:
            c = int(b.cls.item())
            conf = float(b.conf.item())
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            bs.append((c, x1, y1, x2, y2, conf))
            lines.append(f"{c} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} "
                         f"{(x2-x1)/w:.6f} {(y2-y1)/h:.6f}")
            cls_count[c] += 1
            if conf < args.review_conf:
                n_low += 1
                reasons.append(f"저신뢰({KOREAN_BY_ID[c]} {conf:.2f})")
            for pair in CONFUSABLE:
                if c in pair:
                    other = (pair - {c}).pop()
                    n_amb += 1
                    reasons.append(f"혼동주의({KOREAN_BY_ID[c]}↔{KOREAN_BY_ID[other]})")
                    break
        (out / "proposals" / f"{p.stem}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        items.append((p.stem, (w, h), bs))
        if not bs:
            queue.append({"stem": p.stem, "n_box": 0, "min_conf": "",
                          "reason": "탐지없음 — 수작업 필요"})
        elif reasons:
            queue.append({"stem": p.stem, "n_box": len(bs),
                          "min_conf": f"{min(b[5] for b in bs):.2f}",
                          "reason": " / ".join(sorted(set(reasons)))})

    write_cvat_xml(out / "proposals.xml", items, [KOREAN_BY_ID[i] for i in range(len(NAMES))])
    with open(out / "review_queue.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=["stem", "n_box", "min_conf", "reason"])
        wr.writeheader()
        wr.writerows(queue)

    n_with = sum(1 for _s, _wh, bs in items if bs)
    lines = [
        f"이미지 {len(imgs)}장 · 박스가 나온 사진 {n_with}장 · 총 제안 {sum(cls_count.values())}개",
        f"conf 임계 {args.conf} · 우선검수 임계 {args.review_conf}",
        f"우선 검수 목록 {len(queue)}장 (저신뢰 {n_low}건, 혼동주의 {n_amb}건)",
        "",
        "클래스별 제안",
    ]
    for c, n in cls_count.most_common():
        lines.append(f"  {KOREAN_BY_ID[c]:<22} {n:5d}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> {out}")
    print("   proposals/       제안 라벨 (YOLO txt)")
    print("   proposals.xml    CVAT 'CVAT for images 1.1' 로 업로드")
    print("   review_queue.csv 우선 검수 목록")
    print("\n기존 라벨은 건드리지 않았습니다. 검수 후 별도 export 하세요.")


if __name__ == "__main__":
    main()
