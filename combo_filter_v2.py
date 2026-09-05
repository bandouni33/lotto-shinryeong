"""1차(7기본필터)+2차(5이격수)+4차(상중하/상위3위 절대수) 조합 생성 — 2026-09-05
검증 완료된 규칙 세트를 그대로 이식한 것. 회차 무관 고정 규칙(1차 378개+2차 48개)은
매주 다시 계산해도 150초 안팎이라 캐시 파일을 안 쓴다 — Streamlit Cloud는 재배포
시 로컬 파일이 사라지는 환경이라(이미 겪은 문제), 캐시에 의존하면 같은 함정에
다시 빠진다.

전출현번호/이웃수/후보패턴이웃수(AUTO) 3개 규칙만 매 회차 직전회차 데이터로
다시 계산한다. 4차 조건(상중하 0~4개, 상위1~3위 중 최소1개 포함)도 같은 격차
순위(gap_order)를 그대로 재사용한다.
"""

from __future__ import annotations

import itertools
import json
import os

import numpy as np

_DIR = os.path.dirname(__file__)
_STAGE1_FILE = os.path.join(_DIR, "combo_filter_rules_stage1.json")
_STAGE2_FILE = os.path.join(_DIR, "combo_filter_rules_stage2.json")

RECENT_WINDOW = 100
MAXGAP = 46


def _load_rules():
    with open(_STAGE1_FILE, encoding="utf-8") as f:
        stage1 = json.load(f)
    with open(_STAGE2_FILE, encoding="utf-8") as f:
        stage2 = json.load(f)
    static_rules = [r for r in stage1 if not r["is_auto"]]
    auto_rules = [r for r in stage1 if r["is_auto"]]
    return static_rules, auto_rules, stage2


def _all_combos() -> np.ndarray:
    return np.array(list(itertools.combinations(range(1, 46), 6)), dtype=np.int16)


def _onehot(combos: np.ndarray) -> np.ndarray:
    n = combos.shape[0]
    oh = np.zeros((n, 45), dtype=np.int8)
    rows = np.repeat(np.arange(n), 6)
    cols = combos.flatten() - 1
    oh[rows, cols] = 1
    return oh


def _targets_to_vec(targets) -> np.ndarray:
    v = np.zeros(45, dtype=np.int8)
    for t in targets:
        if 1 <= t <= 45:
            v[t - 1] = 1
    return v


def _band(x, mn, mx):
    return (x >= mn) & (x <= mx)


def compute_static_gap_mask(combo_oh: np.ndarray, static_rules, gap_rules, combos: np.ndarray):
    """1차 고정형 378개 + 2차 이격수 48개 — 회차와 무관, 매번 동일한 결과."""
    n = combo_oh.shape[0]
    static_pass = np.ones(n, dtype=bool)
    batch = 30
    for start in range(0, len(static_rules), batch):
        chunk = static_rules[start : start + batch]
        mat = np.stack([_targets_to_vec(r["targets"]) for r in chunk], axis=1)
        cnt = combo_oh @ mat
        mins = np.array([r["min"] for r in chunk])
        maxs = np.array([r["max"] for r in chunk])
        static_pass &= ((cnt >= mins) & (cnt <= maxs)).all(axis=1)

    gaps = np.diff(combos, axis=1)
    gap_pass = np.ones(n, dtype=bool)
    for r in gap_rules:
        lut = np.zeros(MAXGAP + 1, dtype=np.int8)
        for t in r["targets"]:
            if 0 <= t <= MAXGAP:
                lut[t] = 1
        cnt = lut[gaps].sum(axis=1)
        gap_pass &= (cnt >= r["min"]) & (cnt <= r["max"])

    return static_pass & gap_pass


def _gap_order_for_anchor(history_asc: list[dict], anchor_round: int) -> list[int]:
    """history_asc: draw_round 오름차순 정렬된 [{'draw_round','nums':[6개],'bonus'}...].
    anchor_round까지의 데이터로 역대/최근100회 출현빈도 순위 격차를 계산."""
    rounds = [h["draw_round"] for h in history_asc]
    idx = rounds.index(anchor_round)
    freq_all = np.zeros(46, dtype=np.int64)
    for h in history_asc[: idx + 1]:
        for x in h["nums"]:
            freq_all[x] += 1
    freq_recent = np.zeros(46, dtype=np.int64)
    for h in history_asc[max(0, idx + 1 - RECENT_WINDOW) : idx + 1]:
        for x in h["nums"]:
            freq_recent[x] += 1
    alltime_rank = {
        n: i + 1
        for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-freq_all[x], x)))
    }
    recent_rank = {
        n: i + 1
        for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-freq_recent[x], x)))
    }
    return sorted(
        range(1, 46), key=lambda x: (-(recent_rank[x] - alltime_rank[x]), x)
    )


def _prep_history(history_desc: list[dict]) -> list[dict]:
    if len(history_desc) < RECENT_WINDOW + 1:
        raise ValueError("역대 데이터가 부족합니다(최소 101회차 필요).")
    history_asc = list(reversed(history_desc))
    for h in history_asc:
        h["nums"] = [h["num1"], h["num2"], h["num3"], h["num4"], h["num5"], h["num6"]]
    return history_asc


def tier_counts(combo_oh: np.ndarray, actual: list[int], bonus: int) -> dict:
    actual_v = _targets_to_vec(actual)
    match_all = combo_oh @ actual_v
    bonus_hit = combo_oh[:, bonus - 1] == 1
    return dict(
        t1=int((match_all == 6).sum()),
        t2=int(((match_all == 5) & bonus_hit).sum()),
        t3=int(((match_all == 5) & (~bonus_hit)).sum()),
        t4=int((match_all == 4).sum()),
        t5=int((match_all == 3).sum()),
    )


def _compute_pool_for_anchor(history_asc: list[dict], anchor_round: int):
    """anchor_round까지의 데이터만으로 1차+2차+4차 통과 마스크를 계산.
    반환: (combos, combo_oh, stage4_mask, static_gap_count, stage2_count)."""
    rounds = [h["draw_round"] for h in history_asc]
    idx = rounds.index(anchor_round)
    anchor = history_asc[idx]
    anchors7 = anchor["nums"] + [anchor["bonus"]]

    static_rules, auto_rules, gap_rules = _load_rules()
    combos = _all_combos()
    combo_oh = _onehot(combos)

    base_mask = compute_static_gap_mask(combo_oh, static_rules, gap_rules, combos)

    gap_order = _gap_order_for_anchor(history_asc, anchor_round)

    target_prev = set(anchors7)
    target_neighbor = set()
    for n in anchors7:
        target_neighbor.add(n)
        if n > 1:
            target_neighbor.add(n - 1)
        if n < 45:
            target_neighbor.add(n + 1)
    target_cand_neighbor = set()
    for w in anchors7:
        gi = gap_order.index(w)
        if gi > 0:
            target_cand_neighbor.add(gap_order[gi - 1])
        if gi < 44:
            target_cand_neighbor.add(gap_order[gi + 1])

    auto_pass = np.ones(combos.shape[0], dtype=bool)
    for ar in auto_rules:
        if ar["name"] == "전 출현번호":
            tv = _targets_to_vec(target_prev)
        elif ar["name"] == "이웃수":
            tv = _targets_to_vec(target_neighbor)
        elif ar["name"] == "후보패턴 이웃수":
            tv = _targets_to_vec(target_cand_neighbor)
        else:
            continue
        cnt = combo_oh @ tv
        auto_pass &= _band(cnt, ar["min"], ar["max"])

    stage2_mask = base_mask & auto_pass

    sang = _targets_to_vec(gap_order[:15])
    jung = _targets_to_vec(gap_order[15:30])
    ha = _targets_to_vec(gap_order[30:45])
    c_sang = combo_oh @ sang
    c_jung = combo_oh @ jung
    c_ha = combo_oh @ ha
    cond1 = _band(c_sang, 0, 4) & _band(c_jung, 0, 4) & _band(c_ha, 0, 4)

    top3_vec = _targets_to_vec(gap_order[:3])
    cond2 = (combo_oh @ top3_vec) >= 1

    stage4_mask = stage2_mask & cond1 & cond2

    return combos, combo_oh, stage4_mask, int(base_mask.sum()), int(stage2_mask.sum()), gap_order


def generate_next_round_combos(history_desc: list[dict]) -> tuple[int, list[tuple[int, ...]], dict]:
    """history_desc: draw_results_db.get_all_draw_results() 그대로(최신 먼저).
    반환: (예측 대상 회차번호, 통과 조합 리스트, 통계dict)."""
    history_asc = _prep_history(history_desc)
    anchor_round = history_asc[-1]["draw_round"]
    target_round = anchor_round + 1

    combos, combo_oh, stage4_mask, static_gap_count, stage2_count, gap_order = (
        _compute_pool_for_anchor(history_asc, anchor_round)
    )
    passing = combos[stage4_mask]
    stats = {
        "anchor_round": anchor_round,
        "target_round": target_round,
        "static_gap_count": static_gap_count,
        "stage2_count": stage2_count,
        "final_count": int(stage4_mask.sum()),
        # 2026-09-05: 구매조합 배포 시 "1~3위 절대수 겹침 조합" 5종 묶음 배분에
        # 쓰는 격차순위 1~3위 숫자(gap_order[:3]과 동일) — combo_gen_worker.py가
        # bulk_insert_lotto_combinations에 그대로 넘겨 조합마다 top3_mask를 매긴다.
        "top3_numbers": tuple(int(x) for x in gap_order[:3]),
    }
    return target_round, [tuple(int(x) for x in row) for row in passing], stats


def compute_reference_stats(
    history_desc: list[dict], drawn_round: int
) -> tuple[int, dict] | None:
    """drawn_round가 실제로 추첨 완료됐다는 전제 하에 — 그 전주에 생성됐을
    전체 필터 통과 풀을 그대로 재현해서(anchor=drawn_round-1), drawn_round의
    진짜 당첨번호와 대조한 실제 등수별 개수를 구하고, 참고통계 공식(1~3등
    50%, 4등 10%, 5등 5%, 올림)을 적용한다. drawn_round 자체나 그 직전 회차
    데이터가 없으면 None."""
    import math

    history_asc = _prep_history(history_desc)
    rounds = [h["draw_round"] for h in history_asc]
    if drawn_round not in rounds:
        return None
    idx = rounds.index(drawn_round)
    if idx == 0:
        return None
    anchor_round = history_asc[idx - 1]["draw_round"]

    combos, combo_oh, stage4_mask, _, _, _ = _compute_pool_for_anchor(
        history_asc, anchor_round
    )
    pool_oh = combo_oh[stage4_mask]
    drawn = history_asc[idx]
    t = tier_counts(pool_oh, drawn["nums"], drawn["bonus"])

    ref_ranks = (
        math.ceil(t["t1"] * 0.5),
        math.ceil(t["t2"] * 0.5),
        math.ceil(t["t3"] * 0.5),
        math.ceil(t["t4"] * 0.10),
        math.ceil(t["t5"] * 0.05),
    )
    return int(stage4_mask.sum()), {"raw_tiers": t, "ref_ranks": ref_ranks}
