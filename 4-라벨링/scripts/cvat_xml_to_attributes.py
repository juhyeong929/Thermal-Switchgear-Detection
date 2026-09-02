"""CVAT for images 1.1 XML 에서 **bbox 속성만** 뽑아 attributes.csv 로 만든다.

왜 필요한가
    YOLO 1.1 txt 는 `<class_id> <cx> <cy> <w> <h>` 다섯 칸이 전부다. **속성 필드가 없다.**
    지침서 7항이 요구하는 truncated / occluded / ignore 와 이미지별 촬영유형은
    YOLO 로 회수하는 순간 사라진다. 그래서 XML 을 함께 보존하고 여기서 속성을 꺼낸다.

    일치도(개수·mIoU·Kappa)의 primary input 은 계속 YOLO 다. 이 스크립트는
    `agreement.py` 를 건드리지 않으며 별도 분석용 표만 만든다. (DEC-020)

무엇을 하지 않는가
    **XML 에 없는 속성을 만들어내지 않는다.** truncated 가 정의되지 않은 프로젝트에서
    받은 XML 이면 그 칸은 비운 채로 두고 경고한다. `false` 로 채우지 않는다.
    비어 있는 것과 "아니다" 는 다르다.

    **YOLO 줄 번호와 XML shape 순서가 같다고 가정하지 않는다.** YOLO 1.1 에는 shape id 가
    없으므로 두 포맷의 대응은 (이미지 · 클래스 · 좌표) 로 복원해야 한다. 그래서
    매칭 방법을 행마다 `match_method` 로 남긴다. 실패는 버리지 않고 따로 적는다.

사용
    python scripts/cvat_xml_to_attributes.py data/labeling/draft/trial/annotator_A
    python scripts/cvat_xml_to_attributes.py <폴더> --xml <경로> --yolo <폴더> --out <경로>

출력
    <폴더>/attributes.csv            매칭된 박스의 속성
    <폴더>/attributes_unmatched.csv  YOLO↔XML 대응에 실패한 것 (양방향 전부)
"""

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 같은 CVAT 작업에서 나온 두 export 이므로 좌표는 반올림 오차만큼만 다르다.
# 그 수준의 일치를 '동일 박스' 로 본다.
IOU_IDENTICAL = 0.999
# 여기까지는 같은 박스로 인정한다. agreement.py 의 IOU_MATCH 와 같은 값을 쓴다.
IOU_MATCH = 0.5

# 최소 필드. XML 에 없으면 **빈 칸으로 남긴다** (값을 만들지 않는다).
MIN_ATTRS = ["truncated", "occluded"]

SKIP_TXT = {"classes.txt", "obj.names", "train.txt"}


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------
def load_classes(trial_root):
    """classes.txt 의 **줄 번호가 곧 class_id** 다. 이름 -> id 로 뒤집는다.

    `__사용안함_N` 자리표시자도 그대로 센다. 지우면 뒤 번호가 전부 밀린다.
    """
    f = Path(trial_root) / "classes.txt"
    if not f.exists():
        return {}, []
    names = f.read_text(encoding="utf-8").splitlines()
    return {n.strip(): i for i, n in enumerate(names) if n.strip()}, names


def load_yolo(folder):
    """{stem: [(line_no, cls, cx, cy, w, h), ...]} — 빈 파일도 담는다."""
    out = {}
    for f in sorted(Path(folder).rglob("*.txt")):
        if f.name in SKIP_TXT:
            continue
        boxes = []
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            p = line.split()
            if len(p) >= 5:
                boxes.append((i, int(float(p[0])), *[float(x) for x in p[1:5]]))
        out[f.stem] = boxes            # 빈 파일 = '대상 없음' 이라는 정보다
    return out


def parse_xml(xml_path):
    """CVAT for images 1.1 -> ([이미지 dict], 선언된 속성 집합). 좌표는 정규화한다.

    occluded 는 CVAT **내장 필드**(box 태그의 속성)이고, truncated 는 라벨 정의에
    추가해야만 `<attribute>` 로 저장되는 **커스텀 속성**이다. 둘의 출처가 다르다.
    """
    root = ET.parse(xml_path).getroot()

    # 라벨 정의에 선언된 커스텀 속성 (선언만 되고 안 쓰였을 수도 있다)
    declared = set()
    for lab in root.iter("label"):
        for a in lab.iter("attribute"):
            n = a.findtext("name")
            if n:
                declared.add(n.strip())

    images = []
    for im in root.iter("image"):
        w = float(im.get("width") or 0)
        h = float(im.get("height") or 0)
        name = im.get("name") or ""
        rec = {"name": name, "stem": Path(name).stem, "w": w, "h": h,
               "boxes": [], "image_attrs": {}}

        # 이미지 단위 태그 (촬영유형 등)
        for tag in im.findall("tag"):
            for a in tag.findall("attribute"):
                rec["image_attrs"][(a.get("name") or "").strip()] = (a.text or "").strip()

        for idx, b in enumerate(im.findall("box")):
            x0, y0 = float(b.get("xtl")), float(b.get("ytl"))
            x1, y1 = float(b.get("xbr")), float(b.get("ybr"))
            attrs = {}
            for a in b.findall("attribute"):
                attrs[(a.get("name") or "").strip()] = (a.text or "").strip()
            # 내장 occluded 는 0/1 로 온다. 커스텀 attribute 로도 정의돼 있으면
            # 그쪽(사람이 직접 적은 값)을 우선한다.
            if "occluded" not in attrs:
                attrs["occluded"] = "true" if (b.get("occluded") or "0") == "1" else "false"
            rec["boxes"].append({
                "xml_index": idx,
                "label": (b.get("label") or "").strip(),
                "attrs": attrs,
                "norm": ((x0 + x1) / 2 / w, (y0 + y1) / 2 / h,
                         (x1 - x0) / w, (y1 - y0) / h) if w and h else None,
            })
        images.append(rec)
    return images, declared


# ---------------------------------------------------------------------------
# 매칭 — YOLO 줄 번호를 가정하지 않는다
# ---------------------------------------------------------------------------
def iou(a, b):
    def xy(t):
        cx, cy, w, h = t
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    ax0, ay0, ax1, ay1 = xy(a)
    bx0, by0, bx1, by1 = xy(b)
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def match_image(xml_boxes, yolo_boxes, name2id):
    """XML 박스 <-> YOLO 줄. 우선순위대로 3단계.

      1 exact_same_class   같은 클래스 · 좌표 동일 (같은 export 이므로 정상 경로)
      2 iou_same_class     같은 클래스 · IoU >= 0.5
      3 iou_class_mismatch 클래스는 다르지만 같은 자리 -> 매칭하되 **표시한다**

    돌려주는 것: ([(xml_box, yolo_box|None, method, iou)], 안 쓰인 yolo_box 목록)
    """
    used_y = set()
    result = {}

    def sweep(threshold, same_class, method):
        cands = []
        for xb in xml_boxes:
            if xb["xml_index"] in result or xb["norm"] is None:
                continue
            xid = name2id.get(xb["label"])
            for yb in yolo_boxes:
                if yb[0] in used_y:
                    continue
                if same_class and (xid is None or yb[1] != xid):
                    continue
                v = iou(xb["norm"], yb[2:])
                if v >= threshold:
                    cands.append((v, xb["xml_index"], yb[0]))
        for v, xi, yl in sorted(cands, reverse=True):
            if xi in result or yl in used_y:
                continue
            result[xi] = (yl, method, v)
            used_y.add(yl)

    sweep(IOU_IDENTICAL, True, "exact_same_class")
    sweep(IOU_MATCH, True, "iou_same_class")
    sweep(IOU_MATCH, False, "iou_class_mismatch")

    by_line = {yb[0]: yb for yb in yolo_boxes}
    pairs = []
    for xb in xml_boxes:
        if xb["xml_index"] in result:
            yl, method, v = result[xb["xml_index"]]
            pairs.append((xb, by_line[yl], method, v))
        else:
            pairs.append((xb, None, "unmatched", 0.0))
    leftover = [yb for yb in yolo_boxes if yb[0] not in used_y]
    return pairs, leftover


# ---------------------------------------------------------------------------
def convert(annotator_dir, xml=None, yolo=None, classes_dir=None, out=None):
    """돌려주는 것: (rows, unmatched, 요약 dict). CLI 와 테스트가 같은 경로를 쓴다."""
    d = Path(annotator_dir)
    xmls = [Path(xml)] if xml else (sorted((d / "cvat").glob("*.xml"))
                                    or sorted(d.glob("*.xml")))
    if not xmls:
        raise FileNotFoundError(f"CVAT XML 을 찾지 못했다: {d}/cvat/*.xml")

    ydir = Path(yolo) if yolo else ((d / "yolo") if (d / "yolo").is_dir() else d)
    name2id, class_names = load_classes(Path(classes_dir) if classes_dir else d.parent)
    if not name2id:
        raise FileNotFoundError(f"classes.txt 를 찾지 못했다: {classes_dir or d.parent}")

    yolo_boxes = load_yolo(ydir)
    rows, bad = [], []
    present, present_image = set(), set()      # 박스 속성과 이미지 속성은 섞지 않는다
    declared_all, unknown_labels = set(), set()
    n_xml_boxes, xml_stems = 0, set()

    def class_name_of(cid):
        return class_names[cid] if 0 <= cid < len(class_names) else str(cid)

    for xml_path in xmls:
        images, declared = parse_xml(xml_path)
        declared_all |= declared
        for im in images:
            stem = im["stem"]
            xml_stems.add(stem)
            n_xml_boxes += len(im["boxes"])
            # 이미지 태그(촬영유형 등)도 '실제로 쓰인 속성' 이다. 다만 박스 속성과
            # 한 통에 담으면 아무 박스도 갖지 않은 이름이 attr_ 열로 새어 나온다.
            present_image |= set(im["image_attrs"])
            for b in im["boxes"]:
                present |= set(b["attrs"])
                if b["label"] not in name2id:
                    unknown_labels.add(b["label"])

            if stem not in yolo_boxes:
                for b in im["boxes"]:
                    bad.append({"reason": "xml_box_no_yolo_file", "image_name": stem,
                                "xml_index": b["xml_index"], "yolo_line": "",
                                "class_name": b["label"], "best_iou": "",
                                "detail": f"{ydir.name}/{stem}.txt 없음"})
                continue

            pairs, leftover = match_image(im["boxes"], yolo_boxes[stem], name2id)
            for xb, yb, method, v in pairs:
                if yb is None:
                    bad.append({"reason": "xml_box_no_match", "image_name": stem,
                                "xml_index": xb["xml_index"], "yolo_line": "",
                                "class_name": xb["label"], "best_iou": "",
                                "detail": "같은 자리의 YOLO 박스를 찾지 못함"})
                    continue
                cid = name2id.get(xb["label"])
                row = {
                    "image_name": stem,
                    "bbox_id": f"{stem}#{xb['xml_index']}",
                    "class_id": yb[1] if cid is None else cid,
                    "class_name": xb["label"],
                    "yolo_line": yb[0],
                    "match_method": method,
                    "iou": round(v, 4),
                    "cx": round(yb[2], 6), "cy": round(yb[3], 6),
                    "w": round(yb[4], 6), "h": round(yb[5], 6),
                }
                if method == "iou_class_mismatch":
                    row["class_id_yolo"] = yb[1]
                row.update({f"attr_{k}": val for k, val in xb["attrs"].items()})
                row.update({f"image_{k}": val for k, val in im["image_attrs"].items()})
                rows.append(row)
            for yb in leftover:
                bad.append({"reason": "yolo_box_no_xml_match", "image_name": stem,
                            "xml_index": "", "yolo_line": yb[0],
                            "class_name": class_name_of(yb[1]), "best_iou": "",
                            "detail": "XML 에 대응 박스 없음"})

    for stem, boxes in yolo_boxes.items():
        if stem not in xml_stems and boxes:
            for yb in boxes:
                bad.append({"reason": "yolo_file_no_xml_image", "image_name": stem,
                            "xml_index": "", "yolo_line": yb[0],
                            "class_name": class_name_of(yb[1]), "best_iou": "",
                            "detail": "XML 에 이 이미지가 없음"})

    # ---- 열 구성. 최소 필드는 항상 넣되 **값은 만들어내지 않는다** ----
    base = ["image_name", "bbox_id", "class_id", "class_name",
            "yolo_line", "match_method", "iou", "cx", "cy", "w", "h"]
    if any("class_id_yolo" in r for r in rows):
        base.insert(4, "class_id_yolo")
    attr_cols = [f"attr_{k}" for k in MIN_ATTRS]
    attr_cols += sorted(f"attr_{k}" for k in present if k not in MIN_ATTRS)
    img_cols = sorted({k for r in rows for k in r
                       if k.startswith("image_") and k != "image_name"})
    fields = base + attr_cols + img_cols

    out_path = Path(out) if out else (d / "attributes.csv")
    unmatched_path = out_path.with_name("attributes_unmatched.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    with unmatched_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["reason", "image_name", "xml_index",
                                           "yolo_line", "class_name", "best_iou",
                                           "detail"])
        w.writeheader()
        w.writerows(bad)

    summary = {
        "xml_files": len(xmls), "images": len(xml_stems), "xml_boxes": n_xml_boxes,
        "yolo_files": len(yolo_boxes),
        "yolo_boxes": sum(len(v) for v in yolo_boxes.values()),
        "matched": len(rows), "unmatched": len(bad),
        "present_attrs": sorted(present),
        "present_image_attrs": sorted(present_image),
        "declared_attrs": sorted(declared_all),
        "missing_min_attrs": [k for k in MIN_ATTRS if k not in present],
        "unknown_labels": sorted(unknown_labels),
        "fields": fields, "out": out_path, "unmatched_out": unmatched_path,
    }
    return rows, bad, summary


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")   # 오류 메시지에도 한글이 들어간다
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("annotator_dir", help="예: data/labeling/draft/trial/annotator_A")
    ap.add_argument("--xml", help="기본값: <폴더>/cvat/*.xml 또는 <폴더>/*.xml")
    ap.add_argument("--yolo", help="기본값: <폴더>/yolo 가 있으면 그것, 없으면 <폴더>")
    ap.add_argument("--classes", help="classes.txt 가 있는 폴더. 기본값: <폴더>의 상위")
    ap.add_argument("--out", help="기본값: <폴더>/attributes.csv")
    a = ap.parse_args()

    if not Path(a.annotator_dir).is_dir():
        sys.exit(f"폴더가 없다: {a.annotator_dir}")
    try:
        rows, bad, s = convert(a.annotator_dir, a.xml, a.yolo, a.classes, a.out)
    except FileNotFoundError as e:
        sys.exit(str(e))

    print(f"XML {s['xml_files']}개 · 이미지 {s['images']}장 · XML 박스 {s['xml_boxes']}")
    print(f"YOLO 파일 {s['yolo_files']}개 · YOLO 박스 {s['yolo_boxes']}")
    print(f"매칭 {s['matched']} / 실패 {s['unmatched']}")
    for m in ("exact_same_class", "iou_same_class", "iou_class_mismatch"):
        n = sum(1 for r in rows if r["match_method"] == m)
        if n:
            mark = "  <- 클래스가 다르다. 확인 필요" if m == "iou_class_mismatch" else ""
            print(f"    {m:<20}{n}{mark}")
    if bad:
        print("  실패 사유별 (버리지 않고 attributes_unmatched.csv 에 전부 남긴다)")
        for r in sorted({b["reason"] for b in bad}):
            print(f"    {r:<24}{sum(1 for b in bad if b['reason'] == r)}")

    if s["missing_min_attrs"]:
        print(f"  [경고] XML 에 없는 속성: {', '.join(s['missing_min_attrs'])} — "
              f"빈 칸으로 둔다. 값을 만들어내지 않는다")
        print(f"          CVAT 라벨 정의에 속성이 없으면 저장되지 않는다. "
              f"cvat_labels_json.py 로 만든 정의를 쓴다")
    extra = [k for k in s["present_attrs"] if k not in MIN_ATTRS]
    if extra:
        print(f"  XML 에 실제로 있던 그 밖 속성: {', '.join(extra)}")
    if s["present_image_attrs"]:
        print(f"  이미지 단위 속성: {', '.join(s['present_image_attrs'])} "
              f"(박스가 있는 이미지만 표에 실린다)")
    seen = set(s["present_attrs"]) | set(s["present_image_attrs"])
    only_declared = [k for k in s["declared_attrs"] if k not in seen]
    if only_declared:
        print(f"  선언만 되고 한 번도 쓰이지 않은 속성: {', '.join(only_declared)}")
    if s["unknown_labels"]:
        print(f"  [경고] classes.txt 에 없는 라벨명: {', '.join(s['unknown_labels'])}")

    print(f"\n-> {s['out']}")
    print(f"-> {s['unmatched_out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
