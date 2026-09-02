"""STEP 10 — 시드셋 후보를 선정한다.

표본 풀은 STEP 08 의 **대표(독립) 이미지 38,957장**이다. 중복을 다시 보지 않는다.

층화 축 네 개
    반 (Panel)        수집 출처. 독립 도메인이라 합치지 않는다
    촬영 세션         같은 회차가 몰리면 특정 날짜 조건에 과적합된다
    카메라            IR1 은 단발 촬영, IR2·IR3 는 연속 촬영으로 성격이 다르다
    클래스 출현       28개 중 라벨 실적이 있는 것은 9개뿐이다

**반 비례 배분을 쓰지 않는다.** P1 이 대표의 40.4%지만 담당 클래스는 4종뿐이다.
비례로 뽑으면 400장 중 160장이 P1 이 되고, 다른 반의 클래스와 촬영 조건을 못 덮는다.
대신 **클래스 수요에서 반 할당량을 거꾸로 계산한다.**

클래스 수요
    기존 라벨 0건  -> NEED_UNSEEN 장   (실제 인스턴스가 있는지부터 확인해야 한다)
    기존 라벨 있음 -> NEED_SEEN 장
클래스는 반을 통해서만 접근 가능하므로, 각 클래스 수요를 그 클래스를 후보로 가진 반들에
나눠 주고, 반 할당량은 그 반이 떠안은 요구 중 최댓값으로 잡는다.
한 장이 그 반의 후보 클래스를 동시에 커버하기 때문이다.

반 안에서는 (세션, 카메라) 층에 비례 배분하되 한 층이 독식하지 않게 상한을 둔다.
층 안에서는 임베딩 최원점(farthest-point) 선택으로 서로 다른 장면을 고른다.
같은 조건이면 RGB 페어가 있는 쪽을 먼저 쓴다.

원본은 읽지도 옮기지도 않는다. 산출물은 후보 목록 CSV 뿐이다.

출력: data/labeling/seed/seed_candidates.csv
      reports/data_audit/seed_allocation.csv     반·클래스별 할당 근거
"""

import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schemas import paths  # noqa: E402
from schemas import classes_v2 as v2  # noqa: E402


def policy_signature(seen):
    """시드 선정에 영향을 주는 **정책 입력 전부**를 지문으로 만든다 (A-3).

    여기 들어가는 것이 바뀌면 시드를 다시 뽑아야 한다. 무엇이 들어가는지 명시적으로
    적어 두는 것이 요점이다 — 나중에 "이 지문이 왜 바뀌었지" 를 추적할 수 있어야 한다.

      · 상수        TARGET / NEED_UNSEEN / NEED_SEEN / STRATUM_CAP
      · 반별 후보   PANEL_CLASSES (DEC-021 같은 변경이 여기 들어온다)
      · 배포 여부   annotation_unit 확정 상태 (NQ-13 판정이 여기 들어온다)
      · 기존 실적   class_inventory 의 클래스별 인스턴스 수 (0건 여부가 수요를 가른다)
    """
    body = {
        "TARGET": TARGET, "NEED_UNSEEN": NEED_UNSEEN, "NEED_SEEN": NEED_SEEN,
        "STRATUM_CAP": STRATUM_CAP,
        "panel_classes": {p: sorted(cs) for p, cs in v2.PANEL_CLASSES.items()},
        "deployable": {p: sorted(v2.deployable(p)) for p in v2.PANEL_CLASSES},
        "excluded": sorted(v2.EXCLUDED),
        "seen_zero": sorted(c.class_name for c in v2.labelable_classes()
                            if seen.get(c.class_name, 0) == 0),
    }
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return {"policy_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
            "policy": body}


def manifest_hash(rows_out):
    """선정된 이미지 집합의 지문. 사람이 CSV 를 손으로 고치면 여기서 걸린다."""
    ids = sorted(r["image_id"] for r in rows_out)
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def load_prev(path):
    """덮어쓰기 전의 seed_candidates.csv. 없으면 빈 목록."""
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def classify_change(prev, now):
    """무엇이 바뀌었는지 분류한다 (A-3).

    METADATA_ONLY 가 안전한 변경이다 — 이미지 목록이 그대로이므로 시험셋 계보와
    이미 배포된 작업이 유지된다. IMAGE_SET_CHANGED 는 후속 조치가 필요하다.
    """
    po = {r["image_id"]: r for r in prev}
    no = {r["image_id"]: r for r in now}
    added, removed = sorted(set(no) - set(po)), sorted(set(po) - set(no))
    common = set(no) & set(po)
    # CSV 는 전부 문자열로 돌아오므로 형을 맞춰 비교한다.
    # 이걸 빼면 int 0 과 문자열 "0" 이 달라 보여 전 행이 변경으로 잡힌다.
    cols = defaultdict(list)
    for i in sorted(common):
        for k in no[i]:
            if str(po[i].get(k, "")) != str(no[i][k]):
                cols[k].append(i)
    if not prev:
        kind = "FIRST_RUN"
    elif added or removed:
        kind = "IMAGE_SET_CHANGED"
    elif cols:
        kind = "METADATA_ONLY"
    else:
        kind = "NO_CHANGE"
    return {"kind": kind, "added": added, "removed": removed,
            "common": len(common), "prev": len(prev), "now": len(now),
            "changed_columns": dict(cols)}


def write_regen_diff(d):
    f = paths.AUDIT / "seed_regen_diff.csv"
    with f.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "value", "detail"])
        w.writerow(["change_kind", d["kind"], ""])
        w.writerow(["images_before", d["prev"], ""])
        w.writerow(["images_after", d["now"], ""])
        w.writerow(["images_common", d["common"], ""])
        w.writerow(["images_added", len(d["added"]), " ".join(d["added"][:20])])
        w.writerow(["images_removed", len(d["removed"]),
                    " ".join(d["removed"][:20])])
        for k, v in sorted(d["changed_columns"].items()):
            w.writerow([f"column_changed:{k}", len(v), " ".join(v[:10])])
    return f

TARGET = 400            # 시드셋 목표 장수 (파이프라인 04단계 권고 300~500)
NEED_UNSEEN = 20        # 기존 라벨 0건 클래스에 필요한 최소 장수
NEED_SEEN = 10          # 기존 라벨이 있는 클래스
STRATUM_CAP = 0.35      # 한 (세션,카메라) 층이 반 할당량에서 차지할 수 있는 최대 비율


def load():
    with (paths.DEDUP / "dedup_metadata.csv").open(encoding="utf-8-sig") as fh:
        reps = [r for r in csv.DictReader(fh) if r["is_representative"] == "1"]
    with (paths.METADATA / "image_inventory.csv").open(encoding="utf-8-sig") as fh:
        inv = {r["rel_path"]: r for r in csv.DictReader(fh) if r["kind"] == "IR"}
    with (paths.DEDUP / "embeddings_index.csv").open(encoding="utf-8-sig") as fh:
        row_of = {r["rel_path"]: int(r["row"]) for r in csv.DictReader(fh)}
    emb = np.load(paths.DEDUP / "embeddings.npy").astype(np.float32)
    with (paths.AUDIT / "class_inventory.csv").open(encoding="utf-8-sig") as fh:
        seen = {r["class_name"]: int(r["existing_instance_count"])
                for r in csv.DictReader(fh)}
    return reps, inv, row_of, emb, seen


def panel_quota(seen):
    """클래스 수요에서 반별 할당량을 역산한다."""
    need = {}
    for c in v2.CLASSES:
        if c.class_name in v2.EXCLUDED:
            continue                       # 어떤 반에서도 라벨링하지 않는다
        panels = v2.panels_of(c.class_name)
        if not panels:
            continue                       # 현존 10개 반의 후보에 없는 클래스
        need[c.class_name] = (NEED_UNSEEN if seen.get(c.class_name, 0) == 0
                              else NEED_SEEN)

    demand = defaultdict(dict)             # 반 -> {클래스: 요구 장수}
    for cname, n in need.items():
        ps = v2.panels_of(cname)
        per = -(-n // len(ps))             # 올림 나눗셈
        for p in ps:
            demand[p][cname] = per

    # 한 장이 그 반의 후보 클래스를 동시에 커버하므로, 반 할당량은 최댓값이면 충분하다.
    raw = {p: max(d.values()) for p, d in demand.items()}
    scale = TARGET / sum(raw.values())
    quota = {p: max(8, round(n * scale)) for p, n in raw.items()}
    return quota, demand, need


def farthest_point(cands, emb, row_of, k, prefer):
    """서로 최대한 다른 것 k 장을 고른다. prefer 가 True 인 것을 시작점으로 삼는다."""
    if len(cands) <= k:
        return list(cands)
    rows = np.array([row_of[c["rel_path"]] for c in cands])
    X = emb[rows]
    start = next((i for i, c in enumerate(cands) if prefer(c)), 0)
    picked = [start]
    # 이미 고른 것들과의 최대 유사도. 이 값이 가장 낮은 것을 다음으로 고른다.
    best = X @ X[start]
    while len(picked) < k:
        best[picked] = 2.0
        nxt = int(np.argmin(best))
        picked.append(nxt)
        best = np.minimum(best, X @ X[nxt])
    return [cands[i] for i in picked]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    reps, inv, row_of, emb, seen = load()
    quota, demand, need = panel_quota(seen)

    print(f"대표 풀 {len(reps):,}장 / 목표 {TARGET}장")
    print(f"라벨 대상 클래스 {len(need)}종 "
          f"(라벨 0건 {sum(1 for c in need if seen.get(c, 0) == 0)}종)")

    by_panel = defaultdict(list)
    for r in reps:
        by_panel[r["panel_id"]].append(r)
    pid2folder = {p.split("-")[0]: p for p in v2.PANEL_CLASSES}

    picked = []
    for pid, rows in sorted(by_panel.items(), key=lambda x: -len(x[1])):
        folder = pid2folder[pid]
        q = quota.get(folder, 0)
        if q == 0:
            continue
        strata = defaultdict(list)
        for r in rows:
            strata[(r["session_key"], inv[r["rel_path"]]["camera"])].append(r)

        # 층 크기에 비례 배분하되 상한을 건다. 한 회차가 반을 독식하지 않게.
        #
        # 층 수가 할당량보다 많을 수 있다 (P9 는 (세션,카메라) 조합이 37개다).
        # 그럴 때는 모든 층에 1장씩 줄 수 없으므로 0장인 층이 생긴다. 큰 층부터 채운다.
        total = sum(len(v) for v in strata.values())
        cap = max(1, int(q * STRATUM_CAP))
        order = sorted(strata, key=lambda k: -len(strata[k]))
        alloc = {k: min(cap, len(strata[k]), max(1, round(q * len(strata[k]) / total)))
                 for k in order}

        # 총량을 q 에 맞춘다. 한 바퀴 돌아 변화가 없으면 멈춘다 (무한 루프 방지).
        def total_alloc():
            return sum(alloc.values())

        while total_alloc() > q:
            changed = False
            for k in reversed(order):          # 작은 층부터 깎는다
                if total_alloc() <= q:
                    break
                if alloc[k] > 0:
                    alloc[k] -= 1
                    changed = True
            if not changed:
                break
        while total_alloc() < q:
            changed = False
            for k in order:                    # 큰 층부터 채운다
                if total_alloc() >= q:
                    break
                if alloc[k] < min(cap, len(strata[k])):
                    alloc[k] += 1
                    changed = True
            if not changed:
                break

        for k, n in alloc.items():
            if n <= 0:
                continue
            sel = farthest_point(strata[k], emb, row_of, n,
                                 lambda c: c["has_rgb_pair"] == "1")
            picked += [(folder, r) for r in sel]

    # --- 후보 목록 ----------------------------------------------------------
    out_dir = paths.LABELING / "seed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "seed_candidates.csv"
    # 덮어쓰기 **전에** 읽는다. 쓴 뒤에 읽으면 항상 자기 자신과 비교하게 된다.
    prev = load_prev(out)
    rows_out = []
    for folder, r in picked:
        m = inv[r["rel_path"]]
        cands = v2.labelable(folder)
        unseen = [c for c in cands if seen.get(c, 0) == 0]
        hold = [c for c in cands if c in v2.CLASSES_ON_HOLD]
        if unseen:
            reason, prio = "라벨 0건 클래스 확인", "High"
        elif folder in v2.PANEL_CLASSES_PROVISIONAL:
            reason, prio = "후보 잠정 반 검증", "High"
        elif r["has_rgb_pair"] == "1":
            reason, prio = "RGB 페어 보유(교차검증)", "Medium"
        else:
            reason, prio = "반·촬영조건 대표", "Medium"
        rows_out.append({
            "panel": folder, "panel_id": r["panel_id"],
            "camera": m["camera"], "session": r["session_key"],
            "target_classes": " ".join(v2.BY_NAME[c].canonical_name for c in cands),
            "unseen_classes": " ".join(v2.BY_NAME[c].canonical_name for c in unseen),
            "image_id": r["image_id"], "rel_path": r["rel_path"],
            "cluster_id": r["cluster_id"], "cluster_size": r["cluster_size"],
            "has_rgb_pair": r["has_rgb_pair"],
            "reason": reason, "priority": prio,
            "panel_provisional": int(folder in v2.PANEL_CLASSES_PROVISIONAL),
            "class_on_hold": " ".join(v2.BY_NAME[c].canonical_name for c in hold),
        })
    rows_out.sort(key=lambda r: (r["priority"] != "High", r["panel_id"], r["session"]))
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)

    # --- 할당 근거표 --------------------------------------------------------
    apath = paths.AUDIT / "seed_allocation.csv"
    got = defaultdict(int)
    for r in rows_out:
        got[r["panel"]] += 1
    with apath.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["panel", "pool_representatives", "quota", "selected",
                    "labelable_classes", "unseen_classes", "provisional",
                    "driving_class", "driving_need"])
        for folder in v2.PANEL_CLASSES:
            pid = folder.split("-")[0]
            lab = v2.labelable(folder)
            uns = [c for c in lab if seen.get(c, 0) == 0]
            d = demand.get(folder, {})
            drive = max(d, key=d.get) if d else ""
            w.writerow([folder, len(by_panel.get(pid, [])), quota.get(folder, 0),
                        got.get(folder, 0), len(lab), len(uns),
                        int(folder in v2.PANEL_CLASSES_PROVISIONAL),
                        v2.BY_NAME[drive].canonical_name if drive else "",
                        d.get(drive, "")])

    print(f"\n{'반':<16}{'풀':>8}{'할당':>6}{'선정':>6}{'클래스':>7}{'라벨0건':>8}")
    for folder in v2.PANEL_CLASSES:
        pid = folder.split("-")[0]
        lab = v2.labelable(folder)
        uns = [c for c in lab if seen.get(c, 0) == 0]
        mark = "*" if folder in v2.PANEL_CLASSES_PROVISIONAL else " "
        print(f"{folder+mark:<16}{len(by_panel.get(pid,[])):>8,}"
              f"{quota.get(folder,0):>6}{got.get(folder,0):>6}"
              f"{len(lab):>7}{len(uns):>8}")
    print(f"{'합계':<16}{len(reps):>8,}{sum(quota.values()):>6}{len(rows_out):>6}")

    cov = defaultdict(int)
    for r in rows_out:
        for c in v2.labelable(r["panel"]):
            cov[c] += 1
    missing = [c for c in need if cov.get(c, 0) == 0]
    print(f"\n라벨 대상 클래스 {len(need)}종 중 시드에 후보로 걸린 것 "
          f"{len(need)-len(missing)}종")
    if missing:
        print("  미포함:", ", ".join(v2.BY_NAME[c].canonical_name for c in missing))
    low = sorted(((n, c) for c, n in cov.items() if c in need))[:5]
    print("  최소 커버 클래스:",
          ", ".join(f"{v2.BY_NAME[c].canonical_name}({n})" for n, c in low))
    print(f"\nRGB 페어 보유 {sum(1 for r in rows_out if r['has_rgb_pair']=='1')}장")

    # ---- 재생성 diff (A-3) --------------------------------------------------
    # 덮어쓰기 **전에** 이전 상태를 읽어 무엇이 바뀌는지 분류한다.
    # "정책만 바뀌고 이미지는 그대로" 와 "이미지 목록까지 바뀜" 은 후속 영향이 전혀 다르다.
    diff = classify_change(prev, rows_out)
    write_regen_diff(diff)

    # ---- 정책 지문 (A-3) ----------------------------------------------------
    # 이 시드가 **어느 정책으로 뽑혔는지**를 파일에 남긴다.
    # DEC 로 반 후보나 annotation unit 을 바꾸면 지문이 달라지므로,
    # status_check.py 가 "정책은 바뀌었는데 시드는 그대로" 를 자동으로 잡는다.
    # 초판 감사에서 seed_candidates.csv 가 DEC-021 이전 상태로 남아 있었던 사고의 재발 방지.
    sig = policy_signature(seen)
    sig["image_id_sha256"] = manifest_hash(rows_out)
    sig["images"] = len(rows_out)
    sig["generated_at"] = date.today().isoformat()
    spath = paths.LABELING / "seed" / "seed_policy.json"
    spath.write_text(json.dumps(sig, ensure_ascii=False, indent=2,
                                sort_keys=True) + "\n", encoding="utf-8")
    print(f"정책 지문 {sig['policy_sha256'][:12]}… · 이미지 지문 "
          f"{sig['image_id_sha256'][:12]}…")

    print(f"\n재생성 diff: **{diff['kind']}**")
    print(f"  이미지 {diff['prev']} -> {diff['now']} "
          f"(공통 {diff['common']} · 추가 {len(diff['added'])} · "
          f"삭제 {len(diff['removed'])})")
    if diff["changed_columns"]:
        for k, v in sorted(diff["changed_columns"].items()):
            print(f"  열 변경  {k}: {len(v)}행")
    if diff["kind"] == "IMAGE_SET_CHANGED":
        print("  [주의] 이미지 목록이 바뀌었다. 후속 확인이 필요하다 —")
        print("         · 시험셋 A군이 여전히 시드 안에 있는가 (status_check [5-1])")
        print("         · 이미 배포된 작업이 있다면 그 계보를 다시 적어야 한다")
    elif diff["kind"] == "METADATA_ONLY":
        print("  이미지 목록은 그대로다. 작업 정의(반별 후보 목록)만 갱신됐다 —")
        print("  이미 배포된 시험셋 계보는 유지된다.")
    print(f"-> {out}\n-> {apath.name}\n-> {spath.name}\n-> seed_regen_diff.csv")


if __name__ == "__main__":
    main()
