"""교수님 보고서의 '방법' 절을 만든다.

결과 숫자만 적으면 "어떻게 했는가"에 답할 수 없다. 절차·파라미터·판정 근거·검증 방법을
함께 적는다. **파라미터는 실제 스크립트의 상수를 import 해서 쓴다.** 문서와 코드가
어긋나지 않게 하기 위함이다.

`build_professor_report.py` 가 이 모듈의 함수를 불러 01_data_inventory.md 에 끼워 넣는다.
"""

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from schemas import paths  # noqa: E402

# 실제 스크립트의 상수를 그대로 가져온다 (문서-코드 불일치 방지)
import dedup_a_hash as A        # noqa: E402
import dedup_b_candidates as B  # noqa: E402
import dedup_d_cluster as D     # noqa: E402
import seed_select as S         # noqa: E402
import trial_labelset_select as T  # noqa: E402


def _read(p):
    p = Path(p)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _tbl(head, rows, align=None):
    al = align or ["---"] * len(head)
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "|".join(al) + "|"]
                     + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def _n(x):
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return str(x)


# ---------------------------------------------------------------------------

def funnel_section():
    f = _read(paths.AUDIT / "selection_funnel.csv")
    if not f:
        return ""
    rows = [[r["stage"], _n(r["kept"]),
             f"−{_n(r['removed'])}" if r["removed"] != "0" else "—",
             r["removal_reason"], r["doc"] or "—"] for r in f]
    return f"""## 원본에서 시험셋까지 — 무엇이 왜 빠졌나

**어느 단계에서도 원본 파일을 삭제하지 않았다.** 제외는 전부 목록상의 제외다.

{_tbl(["단계", "남은 장수", "제외", "제외 사유", "근거"], rows,
      ["---", "---:", "---:", "---", "---"])}

제외의 성격이 단계마다 다르다.

- **01~03** 은 대상이 아니라서 뺐다 (범위 밖 반 · 이미지 아닌 파일 · 실화상)
- **04 근접중복** 은 같은 장면이라 대표 1장만 남긴 것이다. 나머지는 `cluster_id` 로
  대표와 묶여 있어, 대표에 그린 라벨을 나중에 전파할 수 있다
- **05~06** 은 **폐기가 아니라 미선정**이다. 시드 400장과 독립 이미지 38,957장은
  그대로 남아 본 라벨링에서 쓴다

→ 상세: `reports/labeling/selection_rationale.md`"""


def dedup_section():
    """중복 제거 — 방법과 결과."""
    dedup = _read(paths.AUDIT / "dedup_summary.csv")
    calib = _read(paths.AUDIT / "dedup_calibration.csv")
    if not dedup:
        return ("## 중복 제거\n\n아직 실행하지 않았다. "
                "실질 라벨링 물량은 이 단계 이후에 확정된다.")

    tot = next((r for r in dedup if r["panel_id"] == "TOTAL"), None)
    body = [[r["panel_id"], _n(r["images"]), _n(r["clusters"]),
             f"{float(r['reduction_rate'])*100:.1f}%"]
            for r in dedup if r["panel_id"] != "TOTAL"]
    if tot:
        body.append(["**합계**", f"**{_n(tot['images'])}**",
                     f"**{_n(tot['clusters'])}**",
                     f"**{float(tot['reduction_rate'])*100:.1f}%**"])

    c = calib[0] if calib else {}
    n_img = int(tot["images"]) if tot else 0
    allpairs = n_img * (n_img - 1) // 2

    # 카메라별 축소율
    cam = _read(paths.AUDIT / "dedup_camera_summary.csv")
    cam_tbl = ""
    if cam:
        cam_tbl = "\n\n" + _tbl(
            ["카메라", "전체", "대표", "축소율"],
            [[r["camera"], _n(r["images"]), _n(r["representatives"]),
              f"{float(r['reduction_rate'])*100:.1f}%"] for r in cam],
            ["---", "---:", "---:", "---:"])

    rule = ""
    if c:
        rule = f"""
### 채택한 판정 규칙

```
해밍거리 <= {c['ham_max']}  이고  코사인 유사도 >= {c['cos_min']}   ->  같은 장면으로 병합
그 밖                                                  ->  병합하지 않음
```

두 지문을 **동시에** 만족해야 한다. 격자 탐색
(해밍 {D.HAM_GRID[0]}~{D.HAM_GRID[-1]} × 코사인 {D.COS_GRID[0]}~{D.COS_GRID[-1]}) 전 과정은
`reports/data_audit/dedup_calibration.csv` 에 남겼다.

{_tbl(["지표", "값"], [
    ["재현율", f"{float(c['recall'])*100:.1f}%"],
    ["정밀도", f"{float(c['precision'])*100:.1f}%"],
    ["오병합 — 같은 회차의 다른 구간", f"**{float(c['false_merge_hard'])*100:.1f}%**"],
    ["오병합 — 다른 건물", f"{float(c['false_merge_easy'])*100:.1f}%"],
], ["---", "---:"])}

동점일 때는 F1 이 아니라 **어려운 음성의 오병합률이 낮은 쪽**을 골랐다.
오병합은 곧 데이터 손실이고, 과소병합은 라벨링 후보가 조금 늘어날 뿐이다."""

    return f"""## 중복 제거 — 방법

### 왜 전수 비교를 하지 않았나

{_n(n_img)}장을 모두 짝지으면 약 **{allpairs/1e8:.0f}억 쌍**이다. 계산이 불가능하고
필요하지도 않다. 값싼 지문으로 후보를 좁힌 뒤, 좁혀진 후보에만 비싼 계산을 적용했다.

### 4단계 절차

**1단계 — 완전 동일 파일 (exact)**
파일 바이트의 SHA-256 을 비교했다. 결과는 **223장(0.2%)** 뿐이었다.
바이트가 같은 중복은 사실상 없고, 문제는 근접 중복이라는 것이 여기서 드러났다.

**2단계 — pHash 로 후보 축소**
각 이미지를 {A.DCT_SIZE}×{A.DCT_SIZE} 그레이스케일로 줄이고 DCT-II 를 적용한 뒤,
좌상단 {A.HASH_SIZE}×{A.HASH_SIZE} 저주파 계수를 중앙값 기준으로 이진화해
{A.HASH_SIZE*A.HASH_SIZE}bit 해시를 만들었다. DC 성분(전체 밝기)은 중앙값 계산에서 뺐다 —
열화상은 온도 범위에 따라 전체 밝기가 크게 변하기 때문이다.
외부 패키지(imagehash)를 쓰지 않고 직접 구현해 의존을 늘리지 않았다.

**3단계 — LSH 밴딩으로 후보쌍 생성**
{A.HASH_SIZE*A.HASH_SIZE}bit 해시를 {B.BAND_BITS}bit 씩 {B.N_BANDS}개 밴드로 쪼개고,
**한 밴드라도 완전히 일치하는 쌍**만 후보로 올렸다. 해밍거리가 작은 쌍은 어느 한 밴드가
통째로 일치할 확률이 높으므로, 가까운 쌍을 놓치지 않으면서 비교량을 크게 줄인다.

후보는 **같은 반 안에서만** 만들었다. 반은 독립 데이터 도메인이라 서로 다른 반을 한
클러스터로 묶지 않는다. 반면 **촬영 회차는 넘나들게 두었다** — 같은 설비를 다른 회차에
다시 찍은 것이야말로 train/val 누수의 주범이라, 반드시 같은 클러스터에 들어가야 한다.

결과: 약 {allpairs/1e8:.0f}억 쌍 → **683,349 후보쌍**. 약 {allpairs//683349:,}분의 1.

**4단계 — 임베딩으로 후보쌍 검증**
pHash 는 저주파 구조만 본다. 촬영 위치가 조금 다르거나 온도 스케일이 달라 색이 뒤집힌
경우를 가르기 어렵다. 그래서 후보쌍에 대해 임베딩 코사인 유사도를 추가로 쟀다.

ImageNet 사전학습 **ResNet18** 의 penultimate 512차원을 L2 정규화해 썼다. 열화상 전용
모델은 아니지만, 여기서 필요한 것은 "같은 장면인가"의 상대 비교이지 부품 인식이 아니다.
후보쌍에 등장하는 이미지가 전체의 94%라 어차피 대부분을 계산하게 되므로 **전량 계산**해
저장했고, 시드셋의 다양성 표집에 그대로 재사용했다.

### 임계값을 어떻게 정했나 — 가장 중요한 부분

임계값을 손으로 정하지 않았다. **pHash·임베딩과 무관한 정답셋**으로 보정했다.
정답은 파일명 메타데이터에서만 나오므로 두 지문 어느 쪽과도 독립이다.

{_tbl(["정답셋", "정의", "근거"], [
    ["POSITIVE", "같은 반·같은 촬영 세션의 연속 프레임 (seq 차이 1)", "같은 장면일 수밖에 없다"],
    ["NEG-hard", f"같은 반·같은 세션이지만 seq 가 {D.FAR_SEQ:,} 이상 떨어짐", "같은 회차의 다른 구간"],
    ["NEG-easy", "같은 반이지만 다른 건물", "물리적으로 다른 설비"],
])}

각 {D.GT_N}쌍. 실측 분포는 다음과 같았다.

{_tbl(["정답셋", "해밍 중앙값", "코사인 중앙값", "코사인 75%tile"], [
    ["POSITIVE", "4", "0.982", "0.989"],
    ["**NEG-hard**", "30", "**0.841**", "**0.882**"],
    ["NEG-easy", "30", "0.744", "0.806"],
], ["---", "---:", "---:", "---:"])}
{rule}

### 1차 시도의 실패와 수정 — 기록에 남긴다

첫 실행은 **union-find 단일연결**로 묶었고, 정답셋의 음성을 "다른 건물"만으로 구성했다.
결과는 `실질 독립 이미지 11,322장` 이었으나 **무효였다.**

가장 큰 클러스터가 **41,063장** — P1-TR반 45,721장의 89.9%가 한 덩어리였고, 표본을 열어
보니 몰드변압기 전경·부스바 접촉부·애자·차단기가 한 클러스터에 섞여 있었다.

원인 두 가지.

1. **음성이 너무 쉬웠다.** "다른 건물"만으로 임계값을 고르면 한없이 느슨해진다.
   실제 위험은 같은 회차에 찍은 다른 부위를 묶는 것인데 그 경우가 정답셋에 없었다.
   그래서 코사인 하한이 0.80 으로 뽑혔고, NEG-hard 의 4분의 1(75%tile 0.882)이 통과했다.
2. **단일연결은 연쇄된다.** A~B, B~C, C~D 가 각각 통과하면 A 와 D 가 전혀 달라도 한
   클러스터가 된다. 연속 촬영 데이터는 프레임이 조금씩 이어지므로 세션 전체가 이어붙는다.

수정: 정답셋에 **NEG-hard** 를 추가하고, 클러스터링을 **리더(대표) 방식**으로 바꿨다.
촬영 순서대로 훑으며 리더를 세우고, 뒤 프레임은 **이미 정해진 리더와 직접 비슷할 때만**
그 리더에 붙는다. 멤버끼리는 이어붙지 않으므로 연쇄가 원천적으로 생기지 않는다.

{_tbl(["", "1차 (union-find · 쉬운 음성만)", "2차 (리더 · NEG-hard 포함)"], [
    ["판정 규칙", "해밍≤0 또는 (≤16 & 코사인≥0.80)", "해밍≤22 **이고** 코사인≥0.93"],
    ["최대 클러스터", "**41,063**", "**84**"],
    ["상위 10 클러스터 점유", "68.6%", "0.5%"],
    ["실질 독립 이미지", "11,322 (무효)", "**38,957**"],
])}

### 대표 이미지를 어떻게 골랐나

리더 방식에서는 먼저 훑은 프레임이 리더가 된다. 그래서 훑는 순서로 대표를 통제했다.

```
정렬 키 = (반, 촬영 세션, RGB 페어 없음, seq)
```

세션 안에서 **RGB 페어가 있는 프레임을 먼저** 훑는다. 그 프레임이 리더가 되어 대표
이미지에 실화상이 딸려 오고, 경계 판단과 교차 검증에 쓸 수 있다.
실측 효과 — RGB 페어를 가진 IR 2,657장 중 **2,491장(93.8%)이 대표로 올라갔다.**

### 결과를 어떻게 검증했나

숫자만 보고 넘기지 않고 표본을 열어 **양방향**으로 확인했다.

- **클러스터 내부** — 중간 크기(8~30) 클러스터 3개 표본. 멤버가 전부 같은 장면이고
  프레임 간 미세한 이동만 있었다. 과병합 없음
- **경계 미달 쌍** — 규칙을 아슬아슬하게 통과하지 못한 쌍(해밍≤22, 코사인 0.90~0.93)
  93,613건 중 표본 4쌍. 실제로 서로 다른 시야였다. 과소병합 아님

### 결과

원본은 한 장도 삭제하지 않았다. 클러스터 정보만 메타데이터로 남겼다.

{_tbl(["반", "이미지", "독립 클러스터", "축소율"], body, ["---", "---:", "---:", "---:"])}
{cam_tbl}

IR1 은 거의 줄지 않았다(6.6%). 한 장씩 의도적으로 찍은 촬영이라 중복이 원래 없다.
IR2·IR3 는 연속 촬영이라 3분의 2가 근접 중복이었다.
**이 차이가 시드 표집에서 카메라를 층으로 잡아야 하는 이유다.**

→ 상세: `DEC-008-dedup-method.md` · 재현: `scripts/dedup_a_hash.py` ~ `dedup_d_cluster.py`"""


def seed_section():
    """시드셋 선정 — 방법과 결과."""
    alloc = _read(paths.AUDIT / "seed_allocation.csv")
    seed = _read(paths.LABELING / "seed" / "seed_candidates.csv")
    if not alloc:
        return "## 시드셋 후보\n\n아직 선정하지 않았다."

    rows = [[r["panel"], _n(r["pool_representatives"]), r["quota"], r["selected"],
             r["labelable_classes"], r["unseen_classes"], r["driving_class"],
             "잠정" if r["provisional"] == "1" else ""] for r in alloc]
    ses = len({r["session"] for r in seed})
    rgb = sum(1 for r in seed if r["has_rgb_pair"] == "1")
    cams = {}
    for r in seed:
        cams[r["camera"]] = cams.get(r["camera"], 0) + 1

    return f"""## 시드셋 선정 — 방법

표본 풀은 중복 제거 후 **대표(독립) 이미지**다. 중복을 다시 보지 않는다.
목표는 {S.TARGET}장 (파이프라인 04단계 권고 300~500).

### 왜 반 비례 배분을 쓰지 않았나

P1-TR반은 대표 이미지의 **40.4%**(15,746장)다. 비례로 뽑으면 {S.TARGET}장 중 약 162장이
P1 이 된다. 그런데 **P1 이 담당하는 라벨 대상 클래스는 4종뿐**이다.
반면 P7-VCB&CT반은 대표가 562장(1.4%)인데 담당 클래스 3종이 **전부 기존 라벨 0건**이다.

비례 배분은 "이미지가 많은 반"을 대표하지, **"확인해야 할 클래스"를 대표하지 않는다.**

### 클래스 수요에서 반 할당량을 역산

**1단계 — 클래스별 수요**
```
기존 라벨 0건  -> {S.NEED_UNSEEN}장    (실제 인스턴스가 있는지부터 확인해야 한다)
기존 라벨 있음 -> {S.NEED_SEEN}장
```
라벨 대상 25종(가공 21 + 주의 4). 제외 3종은 뺀다. 이 중 **16종이 기존 라벨 0건**이다.

**2단계 — 반 할당량 역산**
클래스는 반을 통해서만 접근할 수 있다. 각 클래스 수요를 그 클래스를 후보로 가진 반들에
나눠 준 뒤, 반 할당량은 그 반이 떠안은 요구 중 **최댓값**으로 잡았다.
한 장이 그 반의 후보 클래스를 동시에 커버하기 때문이다.

**3단계 — 반 안에서 (촬영세션 × 카메라) 층화**
층 크기에 비례 배분하되 **한 층이 반 할당량의 {S.STRATUM_CAP:.0%}를 넘지 못하게** 상한을 뒀다.
한 회차·한 카메라 조건에 과적합되지 않게 하기 위함이다.
층 수가 할당량보다 많을 수 있어(P9 는 조합이 37개인데 할당 21장) 0장인 층이 생기며,
큰 층부터 채운다.

**4단계 — 층 안에서 최원점(farthest-point) 선택**
임베딩 코사인 유사도 기준으로 **서로 가장 먼 것**부터 골랐다. 중복 제거 단계에서 계산해
둔 ResNet18 임베딩을 그대로 재사용했다. 같은 조건이면 RGB 페어가 있는 쪽을 시작점으로 삼았다.

### 결과

{_tbl(["반", "대표 풀", "할당", "선정", "라벨대상 클래스", "라벨0건", "할당 주도 클래스", ""],
      rows, ["---", "---:", "---:", "---:", "---:", "---:", "---", "---"])}

**P1 은 풀의 40.4%지만 시드의 7.5%만 가져간다. P7 은 풀의 1.4%지만 15.3%를 가져간다.**
의도한 결과다.

선정 **{_n(len(seed))}장** · 촬영 세션 {ses}개 ·
카메라 {" / ".join(f"{k} {v}" for k, v in sorted(cams.items()))} · RGB 페어 보유 {rgb}장.
**라벨 대상 25종이 전부 시드 후보에 걸렸다.**

### 이 선정의 약점

P3-MOF반은 후보 5종이 전부 다른 반(P4)에도 있어 수요 역산에서 가장 낮은 할당(15장)을
받았다. 그런데 P3 는 후보 클래스 자체가 미확정인 반이다.
**검증이 가장 필요한 반이 표본을 가장 적게 받는 구조다.** 설계를 바꾸지 않고 기록만 남겼다.

→ 상세: `DEC-010-seed-selection.md` · 재현: `scripts/seed_select.py`"""


def trial_section():
    """1차 시험셋 30장 — 방법."""
    trial = _read(paths.LABELING / "seed" / "trial_set.csv")
    cov = _read(paths.AUDIT / "trial_session_coverage.csv")
    if not trial:
        return ""
    a = [r for r in trial if r["group"] == "A_본대상"]
    b = [r for r in trial if r["group"] == "B_난이도"]
    from collections import Counter, defaultdict
    bflag = Counter(r["case_id"].split("_", 1)[1] for r in b if "_" in r["case_id"])
    per = defaultdict(lambda: [0, 0])
    for r in cov:
        per[r["panel"]][0] += 1
        if r["selected_for_trial"] == "1":
            per[r["panel"]][1] += 1
    covrows = [[k, v[0], v[1], v[0] - v[1]] for k, v in sorted(per.items())
               if v[1] > 0]

    return f"""## 1차 시험셋 30장 — 방법

시드 {S.TARGET}장을 바로 라벨링하지 않고, 먼저 {T.TARGET_A + T.TARGET_B}장으로
**규칙이 실제로 통하는지** 확인한다. 목적은 모델 성능이 아니라 **라벨러 간 일치도**다.
그래서 쉬운 이미지를 고르지 않고 **지금까지 발견한 실패 유형을 의도적으로 넣었다.**

### A군 {len(a)}장 — 단위 검증

단위가 갈렸던 4개 클래스를 담당하는 반에서만 뽑았다.
**세션이 겹치지 않게 한 세션당 1장**씩 — 한 회차·한 조명 조건에 몰리면 그 조건에서만
통하는 규칙을 검증하게 된다. 세션 안에서는 RGB 페어 보유를 우선했다.

{_tbl(["반", "촬영 세션", "선정", "미선정"], covrows, ["---", "---:", "---:", "---:"])}

미선정 세션은 **할당량 초과이지 탈락이 아니다.** 해당 이미지는 시드 {S.TARGET}장에 남아
본 라벨링에서 쓴다.

### B군 {len(b)}장 — 실패 유형 표적

A군만으로는 실패가 일어나는 상황을 못 덮는다. 그래서 기존 라벨 좌표로 실패 유형이
**측정된** 이미지를 따로 넣었다. **눈으로 고르지 않고 좌표 계산으로 걸렀다.**

{_tbl(["실패 유형", "판정 기준", "장수"], [
    ["잘림-2변이상", f"박스가 프레임 2변 이상에 접함 (여유 {T.EDGE_EPS})", bflag.get("잘림-2변이상", 0)],
    ["작은객체", f"정규화 면적 < {T.TINY}", bflag.get("작은객체", 0)],
    ["다른클래스겹침", f"다른 클래스 박스와 IoU ≥ 0.15", bflag.get("다른클래스겹침", 0)],
    ["같은클래스겹침", f"같은 클래스 박스와 IoU ≥ 0.15", bflag.get("같은클래스겹침", 0)],
    ["같은클래스밀집", "한 클래스가 한 프레임에 6개 이상", bflag.get("같은클래스밀집", 0)],
], ["---", "---", "---:"])}

### 편향 방지 두 가지

1. **기존 라벨을 배포본에서 뺐다.** B군 12장은 과거 라벨이 있지만 보고 따라 그리면
   일치도 측정이 무의미해진다. 배포 스크립트가 매번 라벨 파일 유출을 검사한다
2. **파일명을 바꿨다.** 원본 파일명(`A1_B1_P9_2022-05-12_IR1_00027`)에는 현장·건물·반·
   날짜가 그대로 들어 있어 "P9 니까 MCCB 겠지" 하고 앞서 판단할 여지가 있다.
   `A01.jpg` 형태로 바꾸고 원본 대응은 검수자용 manifest 에만 뒀다

### 이 시험이 덮지 못하는 것

**18개 라벨 대상 중 4종만 집중 검증한다.** 나머지 14종(부품 하나를 통째로 그리는 계열)은
단위 논란이 없어 제외했고, **이번 시험에서 검증되지 않는다.**
1차 결과에서 문제가 드러난 규칙만 2차 시험셋에 넣는다.

→ 상세: `reports/labeling/selection_rationale.md` ·
재현: `scripts/trial_labelset_select.py` · `trial_set_export.py`"""
