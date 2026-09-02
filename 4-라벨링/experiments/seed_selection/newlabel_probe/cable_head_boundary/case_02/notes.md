# case_02 — A2_B1_P6_2022-06-03_IR1_00079

| 항목 | 값 |
|---|---|
| case_type | A_전형·상단잘림 |
| image_id | P6/A2_B1_P6_2022-06-03_IR1_00079 |
| image_path | `3-가공/P6-VCB반/A2_B1_P6_2022-06-03_IR1_00079.jpg` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | P6|A2_B1_2022-06-03_IR1_ |
| cluster_id | P6-C64537 |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | 2 |
| 기준 박스 bbox_xyxy | 0.0338,0.1034,0.1991,0.6897 |
| 기준 박스 면적비 | 0.09688 |

## selection_reason
좌우 두 개가 같은 방식으로 잡혔다. 리브 적층부와 상부 캡까지 포함하고 하부 도체는 제외했다. 둘 다 상단이 프레임에 잘렸다.

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
