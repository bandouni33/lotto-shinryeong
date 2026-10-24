# -*- coding: utf-8 -*-
"""결과 정리(2차) 게시 조건 — 로또신령 조합 1·2등 배출일 때만(2026-10-24 사용자 지시)."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weekly_content import result_post as rp  # noqa: E402

RES = {"round": 1247, "ranks": [{"rank": 1, "count": 10, "amount": 2_000_000_000}] +
       [{"rank": k, "count": 100 * k, "amount": 10000} for k in range(2, 6)],
       "first_kinds": {"자동": 6, "수동": 4}, "first_regions": [("서울", 3)],
       "first_shops": [{"region": "서울", "name": "가게", "kind": "자동"}], "sales": 100}


def _run(monkeypatch, tmp_path, snapshot):
    monkeypatch.setitem(sys.modules, "marketing_db", types.SimpleNamespace(get_round_stats_snapshot=lambda limit=10: snapshot))
    monkeypatch.setitem(sys.modules, "draw_results_db", types.SimpleNamespace(get_latest_draw_round=lambda: 1247))
    from weekly_content import round_result
    monkeypatch.setattr(round_result, "fetch", lambda rnd: dict(RES))
    monkeypatch.setattr(sys, "argv", ["x", "--out", str(tmp_path)])
    return rp.main()


def row(r1, r2, fin="2026-10-24"):
    return [{"draw_round": 1247, "rank_1": r1, "rank_2": r2, "rank_3": 5, "rank_4": 9, "rank_5": 99, "finalized_at": fin}]


def test_skip_when_no_first_or_second(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, row(0, 0)) == 4
    assert not list(tmp_path.glob("*.png"))


def test_wait_when_not_finalized(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, row(1, 0, fin=None)) == 3


def test_build_with_ours_when_second_prize(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, row(0, 2)) == 0
    import json
    caps = json.loads((tmp_path / "1247_captions.json").read_text(encoding="utf-8"))
    assert "1등 0개 · 2등 2개 · 3등 5개" in caps["facebook"] and "3등 5개" in caps["threads"]
    assert "참고·재미용" not in caps["facebook"]
