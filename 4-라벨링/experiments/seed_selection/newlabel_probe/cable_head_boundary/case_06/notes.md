# case_06 — A1_B1_P6_2022-06-17_IR1_00017

| 항목 | 값 |
|---|---|
| case_type | F_반대사례 |
| image_id | P6/A1_B1_P6_2022-06-17_IR1_00017 |
| image_path | `3-가공/P6-VCB반/A1_B1_P6_2022-06-17_IR1_00017.jpg` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | P6|A1_B1_2022-06-17_IR1_ |
| cluster_id | P6-C58956 |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | 2 |
| 기준 박스 bbox_xyxy | 0.7750,0.9283,0.9064,0.9995 |
| 기준 박스 면적비 | 0.00937 |

## selection_reason
작고 가로로 넓은 박스 하나가 OSD 컬러바에 겹쳐 있다. 종횡비 1.27 로 케이블헤드 전형(0.19)에서 크게 벗어난다. 화면의 다른 애자들은 미라벨.

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
