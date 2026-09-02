"""파일럿용 100쌍을 반(盤)별 층화 추출해 pilot/data 로 내보낸다.

실화상 원본을 두 가지 중에서 고를 수 있다.

  --rgb-source prealigned (기본)
      3-가공 의 <stem>_rgb_image.jpg (320x240). 이 파일은 3-가공 을 만들 때 이미
      열화상 FOV 로 정합해 저장된 것이다. 12개 반 전수 확인 결과 열화상과 에지 NCC
      중앙값 0.667 로 맞아 있으므로, 라벨 좌표를 정규화 상태로 그대로 옮기면 된다.
      좌표 변환이 필요 없어 실패 지점이 하나 줄어든다.

  --rgb-source embedded
      열화상 JPEG 내부에 들어 있는 640x480 실화상 (= 1-수집/*/실화상 과 동일).
      화각이 열화상보다 1.53 배 넓으므로 transfer.py 의 보정 변환이 필요하다.
      해상도가 1.3 배 높아 작은 부품의 박스 경계를 조금 더 정밀하게 잡을 수 있다.

내보내는 것
  data/rgb/<stem>.jpg   실화상 (위 선택에 따라 320x240 또는 640x480)
  data/ir/<stem>.jpg    320x240 열화상
  data/temp/<stem>.npy  240x320 float32 섭씨 온도맵
  data/index.csv        선정 목록, 온도 통계, rgb_source 기록

원본(3-가공, 1-수집)은 읽기만 하며 이동·삭제하지 않는다.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
import flir  # noqa: E402
from calibrate import osd_mask  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).parent / "data"

# pilot: 파이프라인 검증용 100장 (반별 최소 5장 + 보유량 비례)
QUOTA_PILOT = {
    "P1-TR반": 17, "P9-MCCB반": 11, "P6-VCB반": 11, "P2-LBS&LA반": 8,
    "P8-ACB반": 8, "P4-MOF&PT반": 8, "P5-PF&PT반": 8, "P13-기타": 6,
    "P10-ACB&MCCB반": 6, "P3-MOF반": 6, "P7-VCB&CT반": 6, "P11-CNCV반": 5,
}

# full: 클래스당 박스 50개를 채우기 위한 분량 (총 290장).
# 실측 산출률(out/box_rate.json)을 근거로 하고, 아직 라벨이 없어 산출률을 모르는
# 클래스(LBS·LA·VCB 접촉부·CT·변류기·MOF퓨즈·콘덴서)는 상별 1~2개로 보수적으로 가정했다.
QUOTA_FULL = {
    "P2-LBS&LA반": 35,      # LBS, LBS 1차측, 한류형 전력퓨즈, LA — 4개 클래스가 여기만
    "P3-MOF반": 30,         # 변압기, 변류기, MOF 1차측 전력퓨즈
    "P4-MOF&PT반": 30,      # 위 + PT
    "P7-VCB&CT반": 30,      # VCB 접촉부, CT
    "P10-ACB&MCCB반": 30,   # 콘덴서, MCCB
    "P1-TR반": 25,          # 에폭시 1.6/장, 몰드변압기 접촉부 1.6/장 (실측)
    "P5-PF&PT반": 25,       # PT 1.6/장 (실측), 전력퓨즈
    "P6-VCB반": 25,         # 분기 접촉부 2.6/장 (실측), VCB 접촉부
    "P9-MCCB반": 20,        # MCCB 2.5/장 (실측)
    "P8-ACB반": 15,
    "P13-기타": 15,
    "P11-CNCV반": 10,       # 전체 보유량이 17쌍뿐
}
QUOTAS = {"pilot": QUOTA_PILOT, "full": QUOTA_FULL}


def main(seed=0, rgb_source="prealigned", target="pilot"):
    random.seed(seed)
    quota_table = QUOTAS[target]
    for d in ("rgb", "ir", "temp", "labels_rgb", "labels_ir"):
        (DATA / d).mkdir(parents=True, exist_ok=True)
    mask = osd_mask() > 0

    # 이미 라벨이 있는 사진은 분량과 무관하게 반드시 포함한다.
    # 그렇지 않으면 재추출 때 이미지가 빠져 기존 라벨이 고아가 된다.
    already = {f.stem
               for d in ("labels_rgb", "labels_ir_src")
               for f in (DATA / d).glob("*.txt") if f.name != "classes.txt"}
    if already:
        print(f"  기존 라벨 {len(already)}개는 분량과 별도로 항상 포함합니다")

    rows = []
    for panel, quota in quota_table.items():
        pool = sorted(p for p in (ROOT / "3-가공" / panel).rglob("*_IR1_*.jpg")
                      if not p.name.endswith("_rgb_image.jpg")
                      and not p.name.startswith("._"))      # macOS AppleDouble 잔재 제외
        if not pool:
            print(f"  {panel}: 대상 없음, 건너뜀")
            continue
        keep_first = [p for p in pool if p.stem in already]
        pool = [p for p in pool if p.stem not in already]
        # 세션이 한쪽에 몰리지 않도록 촬영일 단위로 고르게 섞는다
        by_date = {}
        for p in pool:
            by_date.setdefault(p.stem.split("_")[3], []).append(p)
        for v in by_date.values():
            random.shuffle(v)
        picked, dates = list(keep_first), sorted(by_date)
        quota = max(quota, len(keep_first))
        while len(picked) < min(quota, len(pool) + len(keep_first)):
            progressed = False
            for d in dates:
                if by_date[d] and len(picked) < quota:
                    picked.append(by_date[d].pop())
                    progressed = True
            if not progressed:
                break

        for p in picked:
            try:
                temp, visual, meta = flir.read(p)
            except Exception as e:
                print(f"  건너뜀 {p.name}: {e}")
                continue
            stem = p.stem
            if rgb_source == "prealigned":
                pre = p.with_name(f"{stem}_rgb_image.jpg")
                if not pre.exists():
                    print(f"  건너뜀 {p.name}: 정합된 실화상 짝이 없음")
                    continue
                Image.open(pre).convert("RGB").save(DATA / "rgb" / f"{stem}.jpg", quality=95)
            else:
                Image.fromarray(visual).save(DATA / "rgb" / f"{stem}.jpg", quality=95)
            Image.open(p).convert("RGB").save(DATA / "ir" / f"{stem}.jpg", quality=95)
            np.save(DATA / "temp" / f"{stem}.npy", temp)

            t = temp[mask]
            t = t[np.isfinite(t)]
            med = float(np.median(t))
            rows.append({
                "stem": stem, "panel": panel,
                "site": stem.split("_")[0], "building": stem.split("_")[1],
                "date": stem.split("_")[3],
                "t_med": round(med, 2), "t_max": round(float(t.max()), 2),
                "dT_max": round(float(t.max()) - med, 2),
                "camera": meta.model, "rgb_source": rgb_source,
                "source": str(p.relative_to(ROOT)),
            })

    # 이전 실행 잔재 제거 — 라벨링 대상이 index.csv 와 정확히 일치해야 한다.
    # 지우는 것은 pilot/data 안의 사본뿐이며 원본은 건드리지 않는다.
    keep = {r["stem"] for r in rows}
    removed = 0
    for sub, ext in (("rgb", ".jpg"), ("ir", ".jpg"), ("temp", ".npy")):
        for f in (DATA / sub).glob("*" + ext):
            if f.stem not in keep:
                f.unlink()
                removed += 1
    if removed:
        print(f"  이전 실행 잔재 사본 {removed}개 제거 (원본 아님)")

    with open(DATA / "index.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    dt = np.array([r["dT_max"] for r in rows])
    print(f"\n{len(rows)}쌍 추출 -> {DATA}")
    for panel in quota_table:
        n = sum(1 for r in rows if r["panel"] == panel)
        print(f"  {panel:<16} {n:3d}장")
    print(f"\n촬영일 {len(set(r['date'] for r in rows))}종, 현장 {len(set(r['site'] for r in rows))}곳")
    print(f"dT_max  중앙값 {np.median(dt):.1f} K · p90 {np.percentile(dt, 90):.1f} K · 최대 {dt.max():.1f} K")
    print(f"dT >= 15 K (이상 의심): {int((dt >= 15).sum())}장")
    (DATA / "index.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rgb-source", choices=["prealigned", "embedded"], default="prealigned")
    ap.add_argument("--target", choices=["pilot", "full"], default="pilot",
                    help="pilot=100장(파이프라인 검증) / full=290장(클래스당 50박스)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    main(seed=a.seed, rgb_source=a.rgb_source, target=a.target)
