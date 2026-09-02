# case_05 — A2_B1_P6_2022-06-03_IR1_00062

| 항목 | 값 |
|---|---|
| case_type | E_중복박스 |
| image_id | P6/A2_B1_P6_2022-06-03_IR1_00062 |
| image_path | `3-가공/P6-VCB반/A2_B1_P6_2022-06-03_IR1_00062.jpg` |
| panel | P6-VCB반 |
| camera | IR1 |
| session | P6|A2_B1_2022-06-03_IR1_ |
| cluster_id | P6-C64507 |
| original_class_id | 15 (분기 접촉부) |
| v2_class_id | 13 (#14 케이블헤드) |
| 이미지 내 케이블헤드 박스 수 | 4 |
| 기준 박스 bbox_xyxy | 0.8671,0.4199,0.9546,0.8859 |
| 기준 박스 면적비 | 0.04076 |

## selection_reason
세 조 중 오른쪽 한 조에만 박스가 두 개 겹쳐 있다(box0 이 box3 안에 들어감). 같은 인스턴스 이중 라벨.

## 파일
- `original.png` — 박스 없는 원본 (3배 확대)
- `reference.png` — 기존 참고 라벨. **정답이 아니다.** 기존 관행 관찰용 (DEC-011)
- `variants.png` — 기준 박스와 기계적 변형 3종 (too_wide / too_narrow / wrong_split)

## 주의
기존 bbox 는 `reference` 등급이다. 이 사례에서 기존 bbox 가 옳다고 가정하지 않는다.
