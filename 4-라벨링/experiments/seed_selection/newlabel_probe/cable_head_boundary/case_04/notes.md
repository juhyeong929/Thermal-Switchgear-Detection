# case_04 — A1_B1_P6_2022-05-12_IR1_00048

| 항목 | 값 |
|---|---|
| case_type | E_중첩·불일치 |
| image_id | P6/A1_B1_P6_2022-05-12_IR1_00048 |
| image_path | `3-가공/P6-VCB반/A1_B1_P6_2022-05-12_IR1_00048.jpg` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | P6|A1_B1_2022-05-12_IR1_ |
| cluster_id | P6-C58910 |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | 2 |
| 기준 박스 bbox_xyxy | 0.6306,0.0252,0.9157,0.9041 |
| 기준 박스 면적비 | 0.25052 |

## selection_reason
왼쪽은 리브 적층부만 1개. 오른쪽은 상부까지 큰 박스 1개 + 엘보에 작은 박스 1개. 같은 구성에 박스 개수와 범위가 다르다.

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
