"""현장 지침 HTML 에 반별 식별 참조 카드를 **직접 박아 넣는다.**

라벨러는 저장소에 접근할 수 없다. 지침서가 `reports/labeling/class_reference/...` 같은
파일 경로를 가리키면 그들에게는 없는 것이나 마찬가지다.
그래서 가이드 참조 사진을 data URI 로 페이지 안에 넣고, Skip 기록 서식도 페이지에 적는다.

이미지 출처는 가이드 v2 HTML 에서 추출해 둔 것이며, **원본 HTML 은 읽지도 않는다**
(이미 experiments/seed_selection/guide_images 에 뽑혀 있다).

이 스크립트는 `annotator_guide_v1.html` 의 자리표시 주석을 실제 내용으로 바꾼다.
여러 번 돌려도 결과가 같다 (자리표시가 없으면 기존 블록을 통째로 교체).
"""

import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402
import build_class_reference as R  # noqa: E402

GUIDE_HTML = paths.REPORTS / "labeling" / "annotator_guide_v1.html"
IMG_DIR = paths.PROJECT / "experiments" / "seed_selection" / "guide_images"

START = "<!-- REFCARDS:START -->"
END = "<!-- REFCARDS:END -->"


def data_uri(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_cards():
    files = {p.name[:2]: p for p in IMG_DIR.glob("*.jpg")}
    used = {}          # 같은 사진을 여러 반이 쓰면 한 번만 인코딩한다
    blocks = []

    for panel, refs in R.GUIDE_MAP.items():
        cands = [c for c in v2.labelable(panel) if v2.unit_confirmed(c)]
        held = [c for c in v2.labelable(panel) if not v2.unit_confirmed(c)]

        rows = []
        for c in cands:
            cls = v2.BY_NAME[c]
            hint = cls.description or cls.notes or ""
            rows.append(
                f'<tr><td>{esc(cls.canonical_name)}</td>'
                f'<td><span class="u">{v2.annotation_unit(c)}</span><br>'
                f'{esc(v2.UNIT_DESC[v2.annotation_unit(c)])}</td>'
                f'<td>{esc(hint) or "—"}</td></tr>')

        held_html = ""
        if held:
            held_html = ('<p class="hold">이번에 그리지 않음 — '
                         + " · ".join(esc(v2.BY_NAME[c].canonical_name) for c in held)
                         + " (세는 단위 미확정)</p>")

        figs = []
        for num, cap in refs:
            p = files.get(num)
            if not p:
                continue
            if num not in used:
                used[num] = data_uri(p)
            figs.append(
                f'<figure class="ref"><img src="{used[num]}" alt="{esc(cap)}" loading="lazy">'
                f'<figcaption>{esc(cap)}</figcaption></figure>')

        blocks.append(f'''<details class="card">
  <summary><span class="pn">{esc(panel)}</span>
    <span class="cnt">{len(cands)}종</span></summary>
  <div class="cardbody">
    <div class="tbl"><div class="scroll"><table>
      <thead><tr><th>그리는 것</th><th>세는 단위</th><th>가이드 설명</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table></div></div>
    {held_html}
    <div class="figs">{"".join(figs)}</div>
  </div>
</details>''')

    n_img = len(used)
    intro = f'''<p>
  가이드의 <strong>색상 박스 사진</strong>이 어느 것이 무슨 부품인지 알려줍니다.
  <strong>이 프로젝트의 공식 식별 근거</strong>이며, 아래에 반별로 모아 두었습니다
  (참조 사진 {n_img}장). 자기 반을 눌러 펼치세요.
</p>'''
    return START + "\n" + intro + "\n" + "\n".join(blocks) + "\n" + END


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t = GUIDE_HTML.read_text(encoding="utf-8")
    cards = build_cards()

    if START in t and END in t:
        t = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: cards,
                   t, flags=re.S)
        how = "기존 블록 교체"
    else:
        sys.exit("자리표시 주석이 없다. 먼저 HTML 에 REFCARDS:START/END 를 넣는다.")

    GUIDE_HTML.write_text(t, encoding="utf-8")
    print(f"참조 카드 삽입 ({how})")
    print(f"  반 {len(R.GUIDE_MAP)}개 · 이미지 {cards.count('data:image/jpeg')}개 참조")
    print(f"  파일 크기 {len(t.encode())/1048576:.2f} MB")


if __name__ == "__main__":
    main()
