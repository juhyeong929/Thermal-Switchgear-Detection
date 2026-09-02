"""labelImg 1.8.6 을 PyQt5 5.15.11 / Python 3.13 에서 돌게 만드는 패치.

labelImg 는 2021년 이후 유지되지 않는다. 당시 PyQt5 는 float 인자를 int 로 암묵 변환해
줬지만 현재 버전은 TypeError 를 낸다. 좌표 계산이 나눗셈을 쓰므로 그리기·스크롤·줌 경로
전부에서 터진다.

설치된 labelImg 패키지 파일만 수정한다. 열화상 원본 데이터와 pilot/data 는 건드리지 않는다.
같은 파일을 여러 번 실행해도 안전하며(.bak 은 최초 1회만 생성), --restore 로 되돌린다.

  python fix_labelimg.py            패치 적용
  python fix_labelimg.py --restore  원상 복구
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (모듈 상대경로, 원본 문자열, 교체 문자열, 설명)
PATCHES = [
    ("labelImg/labelImg.py",
     "        bar.setValue(bar.value() + bar.singleStep() * units)",
     "        bar.setValue(int(bar.value() + bar.singleStep() * units))",
     "휠 스크롤 (scroll_request)"),

    ("labelImg/labelImg.py",
     "        self.zoom_mode = self.MANUAL_ZOOM\n        self.zoom_widget.setValue(value)",
     "        self.zoom_mode = self.MANUAL_ZOOM\n        self.zoom_widget.setValue(int(value))",
     "줌 설정 (set_zoom)"),

    ("labelImg/labelImg.py",
     "        h_bar.setValue(new_h_bar_value)\n        v_bar.setValue(new_v_bar_value)",
     "        h_bar.setValue(int(new_h_bar_value))\n        v_bar.setValue(int(new_v_bar_value))",
     "줌 시 스크롤 위치 (zoom_request)"),

    ("libs/canvas.py",
     "            p.drawRect(left_top.x(), left_top.y(), rect_width, rect_height)",
     "            p.drawRect(int(left_top.x()), int(left_top.y()),\n"
     "                       int(rect_width), int(rect_height))",
     "박스 그리는 중 미리보기 사각형"),

    ("libs/canvas.py",
     "            p.drawLine(self.prev_point.x(), 0, self.prev_point.x(), self.pixmap.height())\n"
     "            p.drawLine(0, self.prev_point.y(), self.pixmap.width(), self.prev_point.y())",
     "            px, py = int(self.prev_point.x()), int(self.prev_point.y())\n"
     "            p.drawLine(px, 0, px, int(self.pixmap.height()))\n"
     "            p.drawLine(0, py, int(self.pixmap.width()), py)",
     "십자선 커서 (crosshair)"),

    ("libs/shape.py",
     "                    painter.drawText(min_x, min_y, self.label)",
     "                    painter.drawText(int(min_x), int(min_y), self.label)",
     "박스 라벨 텍스트"),

    ("libs/shape.py",
     "                    font.setPointSize(self.label_font_size)",
     "                    font.setPointSize(int(self.label_font_size))",
     "라벨 글자 크기"),
]


def site_packages() -> Path:
    import labelImg
    return Path(labelImg.__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true", help=".bak 으로 되돌린다")
    args = ap.parse_args()

    try:
        root = site_packages()
    except ImportError:
        raise SystemExit("labelImg 가 설치되어 있지 않습니다:  pip install labelImg")

    if args.restore:
        n = 0
        for rel in sorted({p[0] for p in PATCHES}):
            bak = root / (rel + ".bak")
            if bak.exists():
                shutil.copy2(bak, root / rel)
                n += 1
                print(f"  복구 {rel}")
        print(f"{n}개 파일 복구 완료" if n else "복구할 .bak 이 없습니다")
        return

    print(f"대상: {root}\n")
    applied = already = failed = 0
    for rel, old, new, desc in PATCHES:
        path = root / rel
        if not path.exists():
            print(f"  [없음]   {rel} — 파일 없음")
            failed += 1
            continue
        bak = root / (rel + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)

        text = path.read_text(encoding="utf-8")
        if new in text:
            print(f"  [이미됨] {desc}")
            already += 1
            continue
        if old not in text:
            print(f"  [불일치] {desc} — 원본 코드가 예상과 다릅니다. 수동 확인 필요")
            failed += 1
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  [적용]   {desc}")
        applied += 1

    # 캐시된 바이트코드가 남아 있으면 수정이 반영되지 않는다
    for cache in root.rglob("__pycache__"):
        if cache.parent.name in ("labelImg", "libs"):
            shutil.rmtree(cache, ignore_errors=True)

    print(f"\n적용 {applied} · 이미적용 {already} · 실패 {failed}")
    if failed:
        print("실패 항목이 있습니다. labelImg 버전이 1.8.6 인지 확인하세요.")
        sys.exit(1)

    # 문법 검증
    import py_compile
    for rel in sorted({p[0] for p in PATCHES}):
        py_compile.compile(str(root / rel), doraise=True)
    print("문법 검증 통과")
    print("\n다시 실행하세요:")
    print("  python -m labelImg.labelImg data/rgb data/classes_labelimg.txt data/labels_rgb")


if __name__ == "__main__":
    main()
