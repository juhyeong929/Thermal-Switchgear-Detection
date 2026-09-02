# 결정 초안 (drafts)

> **여기 있는 문서는 아직 결정이 아니다.** 사람이 승인해야 결정이 된다.

## 왜 초안 폴더를 따로 두는가

`open_questions.csv` 와 `reports/decisions/DEC-*.md` 는 **판정 기록**이다.
"누가 · 언제 · 무엇을 근거로 정했는가" 가 그 파일의 존재 이유이므로,
도구나 감사자가 대신 써 넣으면 그 기록의 의미가 사라진다.

그래서 정책 결정이 필요할 때는 **초안을 여기에 만들고**, 사람이 읽고 승인한 뒤에
직접 DEC 번호를 붙여 `reports/decisions/` 로 옮기고 `open_questions.csv` 를 닫는다.

## 승인 절차

```
1. 초안을 읽는다
2. 결정 내용이 맞으면 DEC 번호를 부여해 reports/decisions/DEC-0NN-*.md 로 옮긴다
   (초안 상단의 '승인란' 을 채운다 — 결정자·날짜)
3. open_questions.csv 의 해당 행을 닫는다 (status · owner 열)
4. data/labeling/review_log.csv 에 검수 행이 필요하면 추가한다
5. python scripts/run_all.py 로 산출물을 갱신한다
```

## 현재 초안

| 파일 | 대상 | 이미 코드에 반영된 것 | 남은 것 |
|---|---|---|---|
| `NQ-15-panel-disclosure.md` | 반 정보 공개 | 반별 CVAT task · 반별 지표 산출 | DEC 번호 부여 · OQ 닫기 |
| `NQ-13-unit-unknown-seed-policy.md` | UNKNOWN 7종 시드 수요 유지 | 시드 수요 유지 · 존재 근거 집계 | DEC 번호 부여 · OQ 상태 갱신 |
| `C2-trial-round-separation.md` | v1/v2 회차 분리 | `trial_versions.csv` · 회차별 C-2 | DEC 번호 부여 |

**코드에 이미 반영됐다는 것과 결정이 승인됐다는 것은 다르다.**
반영은 되돌릴 수 있고, 되돌릴 때 근거가 필요하다. 그 근거가 이 초안이다.
