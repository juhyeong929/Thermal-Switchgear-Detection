"""실화상 -> 열화상 정합 상수를 전 세션에 걸쳐 재보정한다.

MSX 합성 덕분에 열화상에도 가시광 윤곽선이 구워져 있다. 두 에지맵의 정규화 상호상관
(NCC)을 배율 x 이동량 격자에서 최대화해 상수를 찾는다. 이동량 탐색은 FFT로 한 번에
처리한다.

결과는 calibration.json 으로 저장된다. 원본 데이터는 읽기만 한다.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import flir  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IR_W, IR_H = 320, 240

# 열화상에 구워진 FLIR UI — 정합·온도집계에서 제외한다.
# 이미지 80장의 화소별 이미지간 표준편차와 검은 박스 영역을 실측해 얻은 좌표다
# (고정 UI 는 이미지가 달라도 변하지 않으므로 표준편차가 낮다).
#   컬러바        x 304~315
#   우측 숫자     (278,4)-(316,25) / (278,214)-(316,235)
#   좌상단 max    (4,4)-(98,25)
#   좌하단 로고   (4,219)-(56,235)
# 각 1~2px 여유를 뒀다. 전체 화소의 11.5% 를 차지한다.
OSD_BOXES = [
    (302, 0, 318, 240),      # 팔레트 컬러바
    (276, 2, 318, 27),       # 우측 상단 온도 숫자
    (276, 212, 318, 237),    # 우측 하단 온도 숫자
    (2, 2, 100, 27),         # 좌측 상단 max 온도 표시
    (2, 217, 58, 237),       # 좌측 하단 FLIR 로고
]


def osd_mask(w=IR_W, h=IR_H) -> np.ndarray:
    m = np.ones((h, w), np.float32)
    for x0, y0, x1, y1 in OSD_BOXES:
        m[y0:y1, x0:x1] = 0.0
    return m


def edge_map(img: Image.Image) -> np.ndarray:
    e = np.asarray(img.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    e[:2], e[-2:], e[:, :2], e[:, -2:] = 0, 0, 0, 0     # FIND_EDGES 테두리 아티팩트 제거
    return e


def _fft_ncc(template: np.ndarray, mask: np.ndarray, image: np.ndarray):
    """template(마스킹·평균제거)을 image 위에서 슬라이딩하며 NCC 최대점을 찾는다."""
    th, tw = template.shape
    ih, iw = image.shape
    if ih < th or iw < tw:
        return None
    fh, fw = ih, iw
    F_img = np.fft.rfft2(image, s=(fh, fw))

    def corr(kernel):
        k = np.zeros((fh, fw), np.float32)
        k[:th, :tw] = kernel[::-1, ::-1]
        return np.fft.irfft2(F_img * np.fft.rfft2(k, s=(fh, fw)), s=(fh, fw))

    num = corr(template)                       # sum(img * template)
    s1 = corr(mask)                            # 창 내 img 합
    s2 = np.fft.irfft2(np.fft.rfft2(image ** 2, s=(fh, fw))
                       * np.fft.rfft2(np.pad(mask[::-1, ::-1], ((0, fh - th), (0, fw - tw))),
                                      s=(fh, fw)), s=(fh, fw))
    n = float(mask.sum())
    var = s2 - s1 ** 2 / n
    valid = slice(th - 1, ih), slice(tw - 1, iw)
    num_v, var_v = num[valid], var[valid]
    denom = np.sqrt(np.maximum(var_v, 1e-6)) * np.sqrt(float((template ** 2).sum()))
    ncc = np.where(var_v > 1e-3, num_v / np.maximum(denom, 1e-9), -1.0)
    idx = int(np.argmax(ncc))
    y, x = divmod(idx, ncc.shape[1])
    return float(ncc[y, x]), x, y


def solve_pair(ir_path: Path, scales) -> dict | None:
    try:
        _, visual, meta = flir.read(ir_path)
    except Exception:
        return None
    ir_img = Image.open(ir_path)
    if ir_img.size != (IR_W, IR_H):
        return None

    mask = osd_mask()
    tmpl = edge_map(ir_img) * mask
    tmpl = (tmpl - tmpl[mask > 0].mean()) * mask
    vis_img = Image.fromarray(visual)

    best = None
    for s in scales:
        vw, vh = int(round(vis_img.width / s)), int(round(vis_img.height / s))
        if vw < IR_W or vh < IR_H:
            continue
        vis_e = edge_map(vis_img.resize((vw, vh), Image.BILINEAR))
        r = _fft_ncc(tmpl, mask, vis_e)
        if r is None:
            continue
        ncc, x0, y0 = r
        # 중앙 정렬 기준 이동량으로 환산
        dx = x0 - (vw - IR_W) // 2
        dy = y0 - (vh - IR_H) // 2
        if best is None or ncc > best["ncc"]:
            best = {"ncc": ncc, "scale": float(s), "dx": int(dx), "dy": int(dy)}
    if best:
        best.update(file=ir_path.name, session=ir_path.parents[1].name,
                    meta_real2ir=round(meta.real2ir, 4), meta_offset=list(meta.offset))
    return best


def main(per_session=4, seed=0):
    random.seed(seed)
    sessions = sorted(p for p in ROOT.glob("1-수집/*/*/열화상") if p.is_dir())
    scales = np.arange(1.40, 1.66, 0.005)

    results = []
    for sess in sessions:
        files = sorted(sess.glob("*.jpg"))
        for f in random.sample(files, min(per_session, len(files))):
            r = solve_pair(f, scales)
            if r:
                results.append(r)
                print(f"  {r['session'][:22]:<24} {r['file'][:34]:<36} "
                      f"scale={r['scale']:.3f} shift=({r['dx']:+d},{r['dy']:+d}) NCC={r['ncc']:.3f}")

    if not results:
        raise SystemExit("보정 표본 없음")

    good = [r for r in results if r["ncc"] >= 0.25]          # 저상관 표본은 중앙값 산출에서 제외
    use = good if len(good) >= 8 else results
    scale = float(np.median([r["scale"] for r in use]))
    dx = int(np.median([r["dx"] for r in use]))
    dy = int(np.median([r["dy"] for r in use]))

    cal = {
        "scale": round(scale, 4), "dx": dx, "dy": dy,
        "ir_size": [IR_W, IR_H], "visual_size": [640, 480],
        "osd_boxes_ir": OSD_BOXES,
        "n_samples": len(results), "n_used": len(use),
        "scale_iqr": [float(np.percentile([r["scale"] for r in use], 25)),
                      float(np.percentile([r["scale"] for r in use], 75))],
        "dx_spread": [int(min(r["dx"] for r in use)), int(max(r["dx"] for r in use))],
        "dy_spread": [int(min(r["dy"] for r in use)), int(max(r["dy"] for r in use))],
        "ncc_median": round(float(np.median([r["ncc"] for r in use])), 3),
        "samples": results,
    }
    out = Path(__file__).parent / "calibration.json"
    out.write_text(json.dumps(cal, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n표본 {len(results)}개 중 {len(use)}개 사용 (NCC >= 0.25)")
    print(f"  scale = {cal['scale']}   IQR {cal['scale_iqr'][0]:.3f} ~ {cal['scale_iqr'][1]:.3f}")
    print(f"  shift = ({dx:+d}, {dy:+d})  범위 dx {cal['dx_spread']}  dy {cal['dy_spread']}")
    print(f"  NCC 중앙값 {cal['ncc_median']}")
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
