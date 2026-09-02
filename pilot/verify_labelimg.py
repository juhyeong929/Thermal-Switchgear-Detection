"""패치된 labelImg 이 실제로 도는지 offscreen Qt 로 검증한다.

import 만 해보는 것으로는 부족하다 (그것 때문에 한 번 놓쳤다). 실제로 터졌던 경로를
직접 호출한다: 그리기 중 미리보기 사각형, 십자선 커서, 박스 라벨 텍스트, 휠 스크롤, 줌.

  python verify_labelimg.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
IMG_DIR = HERE / "data" / "rgb"

from PyQt5.QtCore import QPoint, QPointF, Qt          # noqa: E402
from PyQt5.QtGui import QPixmap                        # noqa: E402
from PyQt5.QtWidgets import QApplication               # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name):
    def deco(fn):
        try:
            fn()
            results.append((name, True, ""))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
        return fn
    return deco


def main():
    imgs = sorted(IMG_DIR.glob("*.jpg"))
    if not imgs:
        raise SystemExit(f"검증용 이미지가 없습니다: {IMG_DIR}")

    app = QApplication(sys.argv[:1])
    from libs.canvas import Canvas
    from libs.shape import Shape
    import labelImg.labelImg as L

    canvas = Canvas()
    pix = QPixmap(str(imgs[0]))
    canvas.load_pixmap(pix)
    canvas.resize(pix.size())

    @check("박스 라벨 텍스트 (shape.paint -> drawText)")
    def _shape():
        Shape.paint_label = True
        s = Shape(label="mccb")
        for p in [QPointF(10.5, 20.5), QPointF(90.5, 20.5),
                  QPointF(90.5, 80.5), QPointF(10.5, 80.5)]:
            s.add_point(p)
        s.close()
        s.scale = 1.3          # float scale -> pen width / font size 경로
        canvas.shapes = [s]
        canvas.grab()          # paintEvent 실행

    @check("십자선 커서 (canvas.paintEvent -> drawLine)")
    def _crosshair():
        canvas.set_editing(False)              # CREATE 모드
        canvas.prev_point = QPointF(123.7, 88.3)
        canvas.grab()

    @check("그리기 중 미리보기 사각형 (canvas.paintEvent -> drawRect)")
    def _rect():
        canvas.set_editing(False)
        cur = Shape()
        cur.add_point(QPointF(20.5, 30.5))
        canvas.current = cur
        canvas.line.points = [QPointF(20.5, 30.5), QPointF(140.25, 110.75)]
        canvas.grab()
        canvas.current = None

    @check("MainWindow 생성")
    def _win():
        global win
        win = L.MainWindow(default_filename=str(imgs[0]),
                           default_prefdef_class_file=str(HERE / "data" / "classes_labelimg.txt"),
                           default_save_dir=str(HERE / "data" / "labels_ir"))
        win.resize(1000, 700)
        win.show()
        app.processEvents()

    @check("휠 스크롤 (scroll_request)")
    def _scroll():
        win.scroll_request(120, Qt.Horizontal)
        win.scroll_request(-120, Qt.Vertical)
        app.processEvents()

    @check("줌 (zoom_request / add_zoom / set_zoom)")
    def _zoom():
        win.zoom_request(120)
        win.zoom_request(-120)
        win.add_zoom(7.5)
        app.processEvents()

    @check("전체 창 렌더 (모든 paintEvent)")
    def _render():
        win.canvas.grab()
        win.grab()
        app.processEvents()

    print("\n검증 결과")
    ok = 0
    for name, passed, err in results:
        print(f"  [{'통과' if passed else '실패'}] {name}")
        if err:
            print(f"           {err}")
        ok += passed
    print(f"\n{ok}/{len(results)} 통과")
    if ok != len(results):
        print("실패한 경로가 있습니다. fix_labelimg.py 의 패치 목록을 보강해야 합니다.")
        sys.exit(1)
    print("터졌던 경로가 모두 통과했습니다. 실제 GUI 로 작업 가능합니다.")


if __name__ == "__main__":
    main()
