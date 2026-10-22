# -*- coding: utf-8 -*-
"""홈페이지(bandouni33.github.io)용 공개 데이터 내보내기 — 2026-10-18 사용자 승인(홈페이지 구축, 별도 공개 저장소).

앱 저장소는 **공개해도 되는 값만** site_data/data.json 으로 내보내고, 사이트 저장소가 그 파일을 읽어
정적 페이지를 만든다(사이트 저장소엔 비밀키가 없다).

담는 것(모두 이미 앱·SNS에 공개되는 값):
  - 회차별 공식 당첨번호(DB = 공식 값만, 캡처 번호는 넣지 않음)
  - 로또신령 조합 회차 성적 = 앱 자동조합 '회차별 당첨번호 배출' 표와 같은 출처(combo_round_stats, 확정된 회차만, 1~4등)
  - 다음 회차 신령 타로(주간 카드와 같은 함수 cards.tarot_for_round)
  - 볼 색(ball_style 단일 기준점), 설치·설명서·채널 링크(social_links 단일 기준점)
담지 않는 것: 회원·주문·결제·토큰 등 그 밖의 모든 것.

실행: python -m weekly_content.site_export --out site_data
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA = 1


def draw_date(rnd: int) -> str:
    return (dt.date(2002, 12, 7) + dt.timedelta(weeks=rnd - 1)).isoformat()


def build_data(draws: list[dict], round_stats: list[dict], now: dt.datetime | None = None) -> dict:
    import ball_style
    import social_links
    from weekly_content import cards

    now = now or dt.datetime.now(dt.timezone.utc)
    latest = max(d["draw_round"] for d in draws)
    # 주간 카드 4번·문구와 같은 카드: cards.tarot_for_round(최신 회차) = '다음 회차를 기다리며' 뽑은 카드
    tarot = cards.tarot_for_round(latest)
    from weekly_content import number_story as ns

    by_round = {d["draw_round"]: {"nums": d["numbers"]} for d in draws}
    ms = ns.members(by_round, latest)
    return {
        "schema": SCHEMA,
        "generated_at": now.isoformat(timespec="seconds"),
        "latest_round": latest,
        "draws": [[d["draw_round"], draw_date(d["draw_round"]), *sorted(d["numbers"]), d["bonus"]]
                  for d in sorted(draws, key=lambda x: -x["draw_round"])],
        "our_stats": [{"round": s["draw_round"], "rank": [s["rank_1"], s["rank_2"], s["rank_3"], s["rank_4"]]}
                      for s in round_stats if s.get("finalized_at")],
        "tarot": {"round": latest + 1, "key": tarot["key"], "name": tarot["name"], "name_en": tarot["name_en"],
                  "line": tarot["line"], "image": f"tarot/{tarot['image'].relative_to(ROOT / 'tarot').as_posix()}"},
        "members": ms,
        "headline": ns.headline(by_round, latest, ms),
        "question": ns.question(by_round, latest),
        "answer": ns.answer(by_round, latest),
        "balls": {str(n): {"fill": ball_style.ball_fill(n), "text": ball_style.ball_text_color(n)}
                  for n in range(1, 46)},
        "links": {"play": social_links.store_link("homepage", medium="web", campaign="site"),
                  "manual": social_links.MANUAL_URL,
                  "manual_posts": [{"title": t, "url": u} for t, u in social_links.MANUAL_POSTS],
                  "channels": [{"name": c["name"], "url": c["url"], "color": c["color"]}
                               for c in social_links.active_channels()]},
        # 2026-10-22(사용자 지시 "항상 일치·통일"): 홈페이지 사용설명서는 앱 사용설명서(manual_ui)를 그대로 옮긴다 — 문구 단일 출처.
        "manual": manual_export(),
    }


def manual_export() -> dict:
    """앱 사용설명서 내용(항목·개인정보 고지·맺음말) — 앱 화면과 같은 함수에서 꺼낸다."""
    import manual_ui
    from legal_notices import MANUAL_PRIVACY_NOTICE
    keys = ("no", "icon", "title", "badge", "summary", "steps", "price", "notes")
    return {"sections": [{k: s[k] for k in keys} for s in manual_ui.manual_sections()],
            "privacy": MANUAL_PRIVACY_NOTICE,
            "footer": manual_ui.MANUAL_FOOTER_TEXT}


TALISMAN_KEEP = 12   # 홈페이지 회차 부적 — 최근 N회차만 새로 그린다(이미 있으면 건너뜀, 같은 번호면 같은 그림)


def export_talismans(data: dict, out: Path, keep: int = TALISMAN_KEEP) -> list[Path]:
    """회차 부적 JPG(site_data/talisman/<회차>.jpg) — 주간 게시의 부적과 같은 함수(weekly_content.talisman)."""
    from weekly_content import number_story, talisman

    out.mkdir(parents=True, exist_ok=True)
    draws = {r[0]: {"nums": r[2:8], "bonus": r[8]} for r in data["draws"]}
    made = []
    for r in sorted(draws, reverse=True)[:keep]:
        p = out / f"{r}.jpg"
        if p.exists():
            continue
        im = talisman.build(r, draws[r]["nums"], draws[r]["bonus"], star_line=number_story.headline(draws, r)["title"],
                            date_text=draw_date(r).replace("-", "."))
        im.convert("RGB").resize((720, 900)).save(p, quality=84, optimize=True)
        made.append(p)
    data["talismans"] = sorted(int(p.stem) for p in out.glob("*.jpg"))
    return made


def export_results(data: dict, out: Path, keep: int = TALISMAN_KEEP) -> None:
    """회차 공식 결과(등수별·1등 판매점) — 최신 회차가 없으면 동행복권에서 받아 저장, 홈페이지엔 최근 N회차만 싣는다."""
    from weekly_content import round_result

    out.mkdir(parents=True, exist_ok=True)
    latest = data["latest_round"]
    p = out / f"{latest}.json"
    if not p.exists():
        res = round_result.fetch(latest)
        if res:
            p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    files = sorted(out.glob("*.json"), key=lambda x: -int(x.stem))[:keep]
    data["results"] = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in files}


def export(out_dir: Path) -> Path:
    import draw_results_db as db
    import marketing_db as mdb

    db.init_draw_results_table()
    mdb.init_marketing_tables()
    data = build_data(db.get_all_draw_results(), mdb.get_round_stats_snapshot(limit=400))
    out_dir.mkdir(parents=True, exist_ok=True)
    export_talismans(data, out_dir / "talisman")
    export_results(data, out_dir / "results")
    path = out_dir / "data.json"
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


if __name__ == "__main__":
    import traceback

    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "site_data"
    try:
        p = export(out)
        print(f"[내보내기] {p} ({p.stat().st_size // 1024} KB)")
        code = 0
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
