# case_01 — A1_B2_P6_2022-05-12_IR1_00024

| 항목 | 값 |
|---|---|
| case_type | A_전형 |
| image_id | P6/A1_B2_P6_2022-05-12_IR1_00024 |
| image_path | `3-가공/P6-VCB반/A1_B2_P6_2022-05-12_IR1_00024.jpg` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | P6|A1_B2_2022-05-12_IR1_ |
| cluster_id | P6-C61593 |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | 1 |
| 기준 박스 bbox_xyxy | 0.3327,0.3614,0.4935,0.9975 |
| 기준 박스 면적비 | 0.10223 |

## selection_reason
단일 박스. 리브 적층부와 그 위 수직 도체를 함께 감쌌다. 상부 도체 포함 관행의 대표 사례.

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
