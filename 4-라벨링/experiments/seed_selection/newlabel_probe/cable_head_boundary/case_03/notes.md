# case_03 — A1_B3_P6_2022-05-24_IR1_00041

| 항목 | 값 |
|---|---|
| case_type | E_경계불일치 |
| image_id | P6/A1_B3_P6_2022-05-24_IR1_00041 |
| image_path | `3-가공/P6-VCB반/A1_B3_P6_2022-05-24_IR1_00041.jpg` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | P6|A1_B3_2022-05-24_IR1_ |
| cluster_id | P6-C63106 |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | 2 |
| 기준 박스 bbox_xyxy | 0.0339,0.1823,0.1255,0.3229 |
| 기준 박스 면적비 | 0.01288 |

## selection_reason
같은 프레임·같은 종류인데 왼쪽은 리브 적층부만(높이 0.141), 가운데는 상부 도체까지(높이 0.347). 높이비 2.47 로 387개 중 최대 편차.

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
