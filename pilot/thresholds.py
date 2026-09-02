"""부품별 이상 발열 판정 기준.

일괄 임계(주변 대비 15K/40K)는 폐기한다. 부품마다 정상 온도대가 다르기 때문이다.
실제로 그 기준을 쓰면 몰드변압기 철심부 634개 중 600개(95%)가 이상으로 찍혔는데,
도메인 기준으로는 전부 정상이다.

각 항목에 **근거**를 명시한다. '미확정'은 아직 근거가 없다는 뜻이며, 추정으로
채우지 않는다. 현장 전문가 확인 후 채워야 할 자리다.

판정 방식 세 가지
  ABS    절대온도 기준. 부품 자체의 허용 온도가 정해져 있는 경우
  PHASE  같은 프레임 내 동종 부품(3상) 간 비교. 부하·주변온도 영향이 상쇄된다
  AMB    대기온도 대비 상승분. 위 둘을 쓸 수 없을 때의 대체 수단
"""
from __future__ import annotations

# 대기온도 추정: 프레임 내 최저 10% 화소의 평균.
# 근거 — P1반 757장으로 5개 후보를 비교한 결과 세션 내 변동이 가장 작았다
#        (최저10%평균 1.17K < p05 1.26 < p10 1.29 < p25 1.40 < 중앙값 1.49).
#        실제 대기온도는 한 세션 안에서 거의 일정하므로 변동이 작은 추정이 낫다.
# 한계 — 함체 내부에 온습도 센서를 달면 그 값으로 대체해야 한다 (회의록 지시사항).
AMBIENT_METHOD = "coldest10_mean"

# (판정방식, 주의, 이상, 심각, 근거)
#   ABS   단위 °C  절대온도
#   PHASE 단위 K   동종 부품 중앙값 대비 상승
#   AMB   단위 K   대기온도 대비 상승
RULES = {
    "철심부": dict(
        method="ABS", caution=110.0, warn=120.0, critical=140.0,
        source="회의록 2026-08-19 업체 기술고문 — 정상 작동 시 110~120°C 정상 범위. "
               "심각선 140°C 는 미확정(임시)"),

    "몰드변압기 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="NETA 계열 상간 비교 관행 + P3-MOF반 변류기 접촉부 178개 실측으로 "
               "정상 상간 편차 상한 3.6K 확인 (5K 임계에 여유 있음)"),
    "변류기 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="위와 동일. 실측 기준선 확보된 유일한 클래스"),
    "변압기 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="접촉부 공통 기준 적용"),
    "분기 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="접촉부 공통 기준 적용"),
    "LBS 1차측 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="접촉부 공통 기준 적용"),
    "VCB 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="접촉부 공통 기준 적용"),
    "MCCB 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="접촉부 공통 기준 적용"),
    "CT 접촉부": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="접촉부 공통 기준 적용"),

    # 퓨즈류 — 회의록: 열은 몸통이 아니라 접촉부(홀더-링크 접점)에서 발생.
    # 몸통 자체의 임계는 근거가 없어 상간 비교만 적용한다.
    "전력퓨즈": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="회의록 — 열은 접촉부에서 발생. 몸통 절대 임계는 미확정"),
    "한류형 전력퓨즈": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="위와 동일"),
    "MOF 1차측 전력퓨즈": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="위와 동일. 회의록에서 이 퓨즈는 비한류형으로 정정됨"),

    # 권선 — 회의록: 접촉부 위주로 확인하라는 지시. 절대 임계 미확정.
    # 3상이 모두 보이므로 상간 비교를 주 기준으로 쓴다.
    "에폭시 표면": dict(
        method="PHASE", caution=5.0, warn=15.0, critical=40.0,
        source="회의록 — 권선보다 접촉부 위주 확인. 몰드변압기 권선 절대 허용온도 "
               "미확정 (절연 등급에 따라 다름). 상간 비교로 대체"),

    # 본체류 — 절대 임계 근거 없음
    "변압기": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
                 source="미확정 — 임시값. 본체 박스는 배경 비중이 커 신뢰도 낮음"),
    "변류기": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
                 source="미확정 — 임시값"),
    "PT": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
               source="미확정 — 임시값"),
    "LBS": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
                source="회의록 — 기계 메커니즘 부분은 열이 안 남. 퓨즈부에서만 발열"),
    "LA": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
               source="미확정 — 임시값"),
    "CT": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
               source="미확정 — 임시값"),
    "콘덴서": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
                source="미확정 — 임시값"),
    "MCCB": dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
                 source="미확정 — 임시값"),
}

DEFAULT = dict(method="AMB", caution=15.0, warn=30.0, critical=50.0,
               source="미확정 — 기본값")

LEVELS = ["정상", "주의", "이상", "심각"]


def rule_for(korean_name: str) -> dict:
    return RULES.get(korean_name, DEFAULT)


def judge(korean_name: str, t_p99: float, ambient: float,
          peer_median: float | None) -> tuple[str, str]:
    """반환 (판정, 근거 문자열).

    t_p99       박스 내 상위 1% 온도 (°C)
    ambient     프레임 대기온도 추정 (°C)
    peer_median 같은 프레임 동종 부품의 t_p99 중앙값. 없으면 None
    """
    r = rule_for(korean_name)
    m = r["method"]

    if m == "PHASE":
        if peer_median is None:
            # 동종 부품이 하나뿐이면 상간 비교 불가 -> 대기 대비로 대체하되 표시한다
            d = t_p99 - ambient
            lv = _level(d, 15.0, 30.0, 50.0)
            return lv, f"주변 대비 +{d:.1f}K (동종 부품 1개, 상간비교 불가)"
        d = t_p99 - peer_median
        return _level(d, r["caution"], r["warn"], r["critical"]), f"동종 대비 +{d:.1f}K"

    if m == "ABS":
        return _level(t_p99, r["caution"], r["warn"], r["critical"]), f"절대 {t_p99:.1f}°C"

    d = t_p99 - ambient
    return _level(d, r["caution"], r["warn"], r["critical"]), f"주변 대비 +{d:.1f}K"


def _level(v, caution, warn, critical) -> str:
    if v >= critical:
        return "심각"
    if v >= warn:
        return "이상"
    if v >= caution:
        return "주의"
    return "정상"


def print_table():
    import sys, io
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"대기온도 추정: {AMBIENT_METHOD}\n")
    print(f"{'클래스':<20}{'방식':>6}{'주의':>8}{'이상':>8}{'심각':>8}  근거")
    for k, v in RULES.items():
        unit = "°C" if v["method"] == "ABS" else "K"
        print(f"{k:<20}{v['method']:>6}{v['caution']:>7.0f}{unit}"
              f"{v['warn']:>7.0f}{unit}{v['critical']:>7.0f}{unit}  {v['source'][:52]}")
    n_undef = sum(1 for v in RULES.values() if "미확정" in v["source"])
    print(f"\n총 {len(RULES)}개 중 근거 미확정 {n_undef}개 — 현장 확인 필요")


if __name__ == "__main__":
    print_table()
