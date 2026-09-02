"""탐지 결과 + 온도맵 -> 부품 단위 이상 발열 판정.

파이프라인의 마지막 단계다. hotspot.py 가 '뜨거운 영역'만 찾는 것과 달리, 여기서는
탐지된 부품에 온도를 붙이므로 두 가지가 가능해진다.

  1) 조명·히터 같은 설비 외 발열체를 자동으로 배제한다 (부품으로 탐지되지 않으므로)
  2) 같은 프레임 안 동종 부품끼리 비교하는 상간(相間) 판정을 할 수 있다.
     열화 진단의 표준 방법이고, 부하·주변온도 영향을 상쇄한다.

판정 기준 (NETA 계열)
  dT_phase >= 15 K   동종 부품 대비 이상 -> 조치 권고
  dT_phase >= 40 K   심각, 즉시 조치
  dT_amb   >= 40 K   주변 대비 심각 (동종 부품이 하나뿐일 때의 대체 기준)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from calibrate import osd_mask  # noqa: E402
from classes import KOREAN_BY_ID, NAMES  # noqa: E402
from thresholds import judge as judge_rule, rule_for, AMBIENT_METHOD  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "out"
T_RANGE_MAX = 250.0

COLORS = {"심각": "#FF2D2D", "이상": "#FFA22D", "주의": "#FFE95C", "정상": "#5BE8A5"}


def judge(dt_phase: float | None, dt_amb: float) -> tuple[str, str]:
    """반환 (판정, 사용된 근거)."""
    if dt_phase is not None:
        if dt_phase >= 40:
            return "심각", f"동종 대비 +{dt_phase:.1f}K"
        if dt_phase >= 15:
            return "이상", f"동종 대비 +{dt_phase:.1f}K"
        if dt_phase >= 5:
            return "주의", f"동종 대비 +{dt_phase:.1f}K"
    if dt_amb >= 40:
        return "심각", f"주변 대비 +{dt_amb:.1f}K"
    if dt_amb >= 15:
        return "이상", f"주변 대비 +{dt_amb:.1f}K"
    if dt_amb >= 5:
        return "주의", f"주변 대비 +{dt_amb:.1f}K"
    return "정상", f"주변 대비 +{dt_amb:.1f}K"


# 박스 안 유효화소가 이보다 적으면 p99 가 사실상 최대값 한두 개로 결정되어
# 온도가 노이즈에 좌우된다. 같은 부품도 촬영거리에 따라 화소수가 6배 이상 차이나므로
# (근거리 1000px^2 vs 원거리 165px^2) 거리 정보 대신 이 값으로 신뢰도를 표시한다.
MIN_PX_RELIABLE = 200


def ambient_of(temp: np.ndarray, mask: np.ndarray) -> float:
    """프레임 대기온도 추정 — 최저 10% 화소의 평균.

    장면 중앙값을 쓰면 설비가 화면을 가득 채울 때 중앙값 자체가 설비 온도가 되어
    상승분이 왜곡된다. P1반 757장 비교에서 세션 내 변동이 가장 작은 방식을 골랐다.
    """
    v = temp[mask & np.isfinite(temp)]
    if v.size == 0:
        return float("nan")
    return float(v[v <= np.percentile(v, 10)].mean())


def box_temperature(temp: np.ndarray, mask: np.ndarray, box) -> dict | None:
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(temp.shape[1], x2), min(temp.shape[0], y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    sub = temp[y1:y2, x1:x2]
    sub_mask = mask[y1:y2, x1:x2] & np.isfinite(sub)
    vals = sub[sub_mask]
    if vals.size < 4:
        return None
    return {
        "t_p99": float(np.percentile(vals, 99)),   # 단일 화소 노이즈에 덜 민감
        "t_max": float(vals.max()),
        "t_mean": float(vals.mean()),
        "n_px": int(vals.size),
        "low_confidence": bool(vals.size < MIN_PX_RELIABLE),
        "over_range": bool(vals.max() > T_RANGE_MAX),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(HERE / "runs" / "v11n_320" / "weights" / "best.pt"))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--draw", type=int, default=12, help="주석 이미지 저장 장수")
    ap.add_argument("--from-labels", default=None, metavar="DIR",
                    help="모델 대신 열화상 라벨을 탐지로 사용한다. "
                         "완벽한 탐지기를 가정했을 때의 판정 상한을 준다.")
    ap.add_argument("--tag", default="", help="출력 파일명 접두어 (예: smoke_)")
    args = ap.parse_args()
    tag = args.tag

    model = None
    label_dir = Path(args.from_labels) if args.from_labels else None
    if label_dir is None:
        weights = Path(args.weights)
        if not weights.exists():
            raise SystemExit(f"가중치가 없습니다: {weights}\n먼저 train.py 를 실행하세요.")
        from ultralytics import YOLO
        model = YOLO(str(weights))
    elif not label_dir.is_dir():
        raise SystemExit(f"라벨 디렉터리가 없습니다: {label_dir}")

    OUT.mkdir(exist_ok=True)
    (OUT / f"{tag}annotated").mkdir(exist_ok=True)
    index = {r["stem"]: r for r in json.loads((DATA / "index.json").read_text(encoding="utf-8"))}
    mask = osd_mask() > 0

    rows, drawn = [], 0
    for stem, rec in index.items():
        img_path = DATA / "ir" / f"{stem}.jpg"
        temp = np.load(DATA / "temp" / f"{stem}.npy")
        ref = ambient_of(temp, mask)

        if model is not None:
            res = model.predict(str(img_path), conf=args.conf, verbose=False)[0]
            raw = [(int(b.cls.item()), float(b.conf.item()), b.xyxy[0].tolist())
                   for b in res.boxes]
        else:
            lf = label_dir / f"{stem}.txt"
            raw = []
            if lf.exists():
                H, W = temp.shape
                for line in lf.read_text(encoding="utf-8").splitlines():
                    p = line.split()
                    if len(p) < 5:
                        continue
                    cx, cy, bw, bh = map(float, p[1:5])
                    raw.append((int(p[0]), 1.0,
                                [(cx - bw / 2) * W, (cy - bh / 2) * H,
                                 (cx + bw / 2) * W, (cy + bh / 2) * H]))

        dets = []
        for cls, conf, box in raw:
            stats = box_temperature(temp, mask, box)
            if stats is None:
                continue
            dets.append({"cls": cls, "name": NAMES[cls], "korean": KOREAN_BY_ID[cls],
                         "conf": conf, "box": [round(v, 1) for v in box], **stats})

        # 부품별 기준 적용 — thresholds.py
        by_cls = {}
        for d in dets:
            by_cls.setdefault(d["cls"], []).append(d["t_p99"])
        for d in dets:
            same = by_cls[d["cls"]]
            peer = float(np.median(same)) if len(same) >= 2 else None
            d["dT_amb"] = round(d["t_p99"] - ref, 1)
            d["dT_phase"] = round(d["t_p99"] - peer, 1) if peer is not None else None
            d["rule"] = rule_for(d["korean"])["method"]
            d["verdict"], d["basis"] = judge_rule(d["korean"], d["t_p99"], ref, peer)
            if d["low_confidence"] and d["verdict"] != "정상":
                d["basis"] += f" (화소 {d['n_px']}개, 신뢰도 낮음)"

        worst = max(dets, key=lambda d: ["정상", "주의", "이상", "심각"].index(d["verdict"]),
                    default=None) if dets else None
        rows.append({"stem": stem, "panel": rec["panel"], "t_ambient": round(ref, 1),
                     "n_det": len(dets),
                     "verdict": worst["verdict"] if worst else "탐지없음",
                     "worst_part": worst["korean"] if worst else "",
                     "worst_temp": round(worst["t_p99"], 1) if worst else "",
                     "basis": worst["basis"] if worst else "",
                     "dets": dets})

        if drawn < args.draw and worst and worst["verdict"] in ("이상", "심각"):
            im = Image.open(img_path).convert("RGB")
            d0 = ImageDraw.Draw(im)
            for d in dets:
                c = COLORS[d["verdict"]]
                d0.rectangle(d["box"], outline=c, width=2)
                d0.text((d["box"][0] + 2, max(0, d["box"][1] - 11)),
                        f"{d['name']} {d['t_p99']:.0f}C", fill=c)
            im.save(OUT / f"{tag}annotated" / f"{stem}.png")
            drawn += 1

    with open(OUT / f"{tag}component_report.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in rows[0] if k != "dets"])
        w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k != "dets"})
    (OUT / f"{tag}component_report.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    n_det = sum(r["n_det"] for r in rows)
    print(f"프레임 {len(rows)}장, 부품 탐지 {n_det}건 (conf >= {args.conf})\n")
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    for v in ("심각", "이상", "주의", "정상", "탐지없음"):
        if v in counts:
            print(f"  {v:<5} {counts[v]:3d}장")

    bad = [r for r in rows if r["verdict"] in ("이상", "심각")]
    if bad:
        print(f"\n조치 대상 {len(bad)}건")
        print(f"  {'파일':<44}{'부품':<16}{'온도':>7}  근거")
        for r in sorted(bad, key=lambda r: -float(r["worst_temp"]))[:20]:
            print(f"  {r['stem']:<44}{r['worst_part']:<16}{float(r['worst_temp']):6.1f}C  {r['basis']}")
    print(f"\n-> {OUT / (tag + 'component_report.csv')}")
    print(f"-> {OUT / (tag + 'annotated')} (주석 이미지 {drawn}장)")


if __name__ == "__main__":
    main()
