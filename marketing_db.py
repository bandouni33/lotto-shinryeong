"""익명 마케팅 데이터 전용 SQLite 모듈 (sms_queue ↔ lotto_combinations 완전 분리)."""

import csv
import gzip
import random
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

DB_PATH = "lotto.db"
_APP_ROOT = Path(__file__).resolve().parent
MARKETING_POOL_SEED_DRAWS = (1234, 1235, 1236)
_MARKETING_POOL_DIR = _APP_ROOT / "data" / "marketing_pools"

PURCHASE_TYPES = frozenset({"정기구독", "일반구매"})
SEND_STATUSES = frozenset({"WAIT", "SENT", "TEST_SKIP", "BANNER_ONLY"})


class InsufficientCombinationsError(Exception):
    """미배포 조합 수량 부족."""

    def __init__(self, draw_round: int, requested: int, available: int):
        super().__init__(
            f"draw_round={draw_round}: requested={requested}, available={available}"
        )
        self.draw_round = draw_round
        self.requested = requested
        self.available = available


def _connect():
    return sqlite3.connect(DB_PATH)


def init_marketing_tables():
    """sms_queue, lotto_combinations 테이블 생성 (FK/회원 ID 없음)."""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            purchase_type TEXT NOT NULL,
            send_status TEXT NOT NULL DEFAULT 'WAIT',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sms_queue_status
        ON sms_queue(send_status, created_at)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lotto_combinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_round INTEGER NOT NULL,
            num1 INTEGER NOT NULL,
            num2 INTEGER NOT NULL,
            num3 INTEGER NOT NULL,
            num4 INTEGER NOT NULL,
            num5 INTEGER NOT NULL,
            num6 INTEGER NOT NULL,
            win_rank INTEGER NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lotto_combinations_draw
        ON lotto_combinations(draw_round)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lotto_combinations_win_rank
        ON lotto_combinations(draw_round, win_rank)
    """)
    _migrate_lotto_combinations(conn)
    conn.commit()
    conn.close()


def _marketing_pool_seed_path(draw_round: int) -> Path:
    return _MARKETING_POOL_DIR / f"draw_{int(draw_round)}.csv.gz"


def import_marketing_pool_seed(draw_round: int) -> int:
    """회차 DB가 비어 있으면 repo 의 data/marketing_pools/draw_N.csv.gz 를 적재."""
    draw_round = int(draw_round)
    if get_combination_count_by_draw(draw_round) > 0:
        return 0
    path = _marketing_pool_seed_path(draw_round)
    if not path.is_file():
        return 0
    rows: list[list] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) >= 6:
                rows.append(row[:6])
    if not rows:
        return 0
    return bulk_insert_lotto_combinations(draw_round, rows)


def ensure_marketing_pool_seeds(
    draw_rounds: tuple[int, ...] = MARKETING_POOL_SEED_DRAWS,
) -> dict[int, int]:
    """Cloud 등 lotto.db 가 비어 있을 때 관리자 저장 회차 풀 복원."""
    imported: dict[int, int] = {}
    for draw_round in draw_rounds:
        count = import_marketing_pool_seed(draw_round)
        if count:
            imported[draw_round] = count
    return imported


def _migrate_lotto_combinations(conn: sqlite3.Connection) -> None:
    """미배포/배포 추적 컬럼 (기존 DB 호환 ALTER)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(lotto_combinations)")}
    if "allocated_at" not in cols:
        conn.execute("ALTER TABLE lotto_combinations ADD COLUMN allocated_at TEXT NULL")
    if "auto_order_id" not in cols:
        conn.execute("ALTER TABLE lotto_combinations ADD COLUMN auto_order_id INTEGER NULL")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lotto_combinations_allocate
        ON lotto_combinations(draw_round, allocated_at)
    """)


def _combo_nums_from_row(row) -> tuple[int, int, int, int, int, int]:
    return (
        int(row["num1"]),
        int(row["num2"]),
        int(row["num3"]),
        int(row["num4"]),
        int(row["num5"]),
        int(row["num6"]),
    )


def build_number_frequency_map(draw_round: int, conn: sqlite3.Connection | None = None) -> dict[int, int]:
    """
    해당 회차 전체 추출 조합(배포 여부 무관)에서 번호 1~45 출현 횟수.
    배포 우선순위 산정의 기준 데이터.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT num1, num2, num3, num4, num5, num6
        FROM lotto_combinations
        WHERE draw_round = ?
        """,
        (int(draw_round),),
    ).fetchall()
    if own_conn:
        conn.close()

    freq: Counter[int] = Counter()
    for row in rows:
        freq.update(_combo_nums_from_row(row))
    return dict(freq)


def combo_priority_score(
    combo: tuple[int, int, int, int, int, int],
    number_freq: dict[int, int],
) -> int:
    """
    조합 우선순위 점수 = 6개 번호 각각의 출현 빈도 합.
    (추출 풀에서 많이 등장하는 번호를 더 많이 포함한 조합이 높은 점수)
    """
    return sum(number_freq.get(n, 0) for n in combo)


def _sort_combos_by_priority(
    rows: list,
    number_freq: dict[int, int],
) -> list:
    """점수 내림차순 → 동점 시 id 오름차순(선입선출)."""
    scored = []
    for row in rows:
        combo = _combo_nums_from_row(row)
        scored.append(
            (
                -combo_priority_score(combo, number_freq),
                int(row["id"]),
                row,
            )
        )
    scored.sort(key=lambda x: (x[0], x[1]))
    return [item[2] for item in scored]


def _fetch_pending_rows(conn: sqlite3.Connection, draw_round: int) -> list:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, num1, num2, num3, num4, num5, num6
        FROM lotto_combinations
        WHERE draw_round = ? AND allocated_at IS NULL
        ORDER BY id
        """,
        (int(draw_round),),
    ).fetchall()


def _count_total_combinations(conn: sqlite3.Connection, draw_round: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM lotto_combinations WHERE draw_round = ?",
        (int(draw_round),),
    ).fetchone()
    return int(row[0]) if row else 0


def _reset_draw_allocations(conn: sqlite3.Connection, draw_round: int) -> None:
    """회차 전체 배포 상태 초기화 → 회전 배포 시작점."""
    conn.execute(
        """
        UPDATE lotto_combinations
        SET allocated_at = NULL, auto_order_id = NULL
        WHERE draw_round = ?
        """,
        (int(draw_round),),
    )


def allocate_lotto_combinations(
    draw_round: int,
    count: int,
    auto_order_id: int,
) -> list[dict]:
    """
    관리자 저장 조합에서 우선순위 순으로 count개 배정.

    우선순위: 해당 회차 전체 추출 조합의 번호 빈도 →
              빈도 높은 번호를 더 많이 포함한 조합 우선 → 동점 시 id 순.

    미배포 재고가 구매 수량보다 적으면(전량 소진 포함) 해당 회차 배포를
    초기화한 뒤 처음부터 같은 우선순위로 다시 순차 배포(회전).
    """
    draw_round = int(draw_round)
    count = int(count)
    if count < 1:
        return []

    conn = _connect()
    conn.row_factory = sqlite3.Row
    rotated = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        number_freq = build_number_frequency_map(draw_round, conn)
        if not number_freq:
            raise InsufficientCombinationsError(draw_round, count, 0)

        total = _count_total_combinations(conn, draw_round)
        if total < count:
            raise InsufficientCombinationsError(draw_round, count, total)

        pending = _fetch_pending_rows(conn, draw_round)
        if len(pending) < count:
            _reset_draw_allocations(conn, draw_round)
            pending = _fetch_pending_rows(conn, draw_round)
            rotated = True

        ordered = _sort_combos_by_priority(pending, number_freq)[:count]
        now = datetime.now().isoformat()
        ids = [int(row["id"]) for row in ordered]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"""
            UPDATE lotto_combinations
            SET allocated_at = ?, auto_order_id = ?
            WHERE id IN ({placeholders})
            """,
            [now, int(auto_order_id), *ids],
        )
        conn.commit()
    except InsufficientCombinationsError:
        conn.execute("ROLLBACK")
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    result = [
        {
            "id": int(row["id"]),
            "combo": _combo_nums_from_row(row),
            "rotated": rotated,
        }
        for row in ordered
    ]
    return result


def _pick_spread_indices(pool_size: int, count: int) -> list[int]:
    """
    풀 전체에 count개를 불규칙 간격으로 분산 (1-indexed 예: 1, 3, 6, 10, 14).
    시작 위치 + 매번 랜덤 gap(최소 1)으로 앞쪽부터 퍼뜨림.
    """
    if count <= 0:
        return []
    if count == 1:
        return [random.randrange(pool_size)]
    if count >= pool_size:
        return sorted(random.sample(range(pool_size), pool_size))

    head_room = pool_size - count
    max_start = max(0, min(head_room, pool_size // 3))
    pos = random.randint(0, max_start)
    indices = [pos]
    picks_left = count - 1

    for remaining_picks in range(picks_left, 0, -1):
        slots_left = pool_size - pos - 1
        min_gap = 1
        max_gap = max(min_gap, slots_left - remaining_picks + 1)
        if max_gap > min_gap + 1 and random.random() < 0.6:
            upper = max(min_gap + 1, max_gap // 2 + random.randint(0, max(0, max_gap // 3)))
            gap = random.randint(min_gap, min(upper, max_gap))
        else:
            gap = random.randint(min_gap, max_gap)
        pos += gap
        indices.append(pos)

    return indices


def allocate_lotto_combinations_random_sequential(
    draw_round: int,
    count: int,
    auto_order_id: int,
) -> list[dict]:
    """
    미배포 조합 풀(관리자 저장)에서 불규칙 간격으로 count개 분산 배정.

    예) 5개 → 인덱스 1, 3, 6, 10, 14처럼 퍼져서 선택.
    재고가 부족하면 해당 회차 배포를 초기화한 뒤 다시 배정(회전).
    """
    draw_round = int(draw_round)
    count = int(count)
    if count < 1:
        return []

    conn = _connect()
    conn.row_factory = sqlite3.Row
    rotated = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        total = _count_total_combinations(conn, draw_round)
        if total < count:
            raise InsufficientCombinationsError(draw_round, count, total)

        pending = _fetch_pending_rows(conn, draw_round)
        if len(pending) < count:
            _reset_draw_allocations(conn, draw_round)
            pending = _fetch_pending_rows(conn, draw_round)
            rotated = True

        if len(pending) < count:
            raise InsufficientCombinationsError(draw_round, count, len(pending))

        pick_indices = _pick_spread_indices(len(pending), count)
        ordered = [pending[i] for i in pick_indices]
        now = datetime.now().isoformat()
        ids = [int(row["id"]) for row in ordered]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"""
            UPDATE lotto_combinations
            SET allocated_at = ?, auto_order_id = ?
            WHERE id IN ({placeholders})
            """,
            [now, int(auto_order_id), *ids],
        )
        conn.commit()
    except InsufficientCombinationsError:
        conn.execute("ROLLBACK")
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return [
        {
            "id": int(row["id"]),
            "combo": _combo_nums_from_row(row),
            "rotated": rotated,
        }
        for row in ordered
    ]


def release_lotto_combination_allocation(combo_ids: list[int]) -> int:
    """배포 롤백 (결제 실패 등)."""
    if not combo_ids:
        return 0
    conn = _connect()
    placeholders = ",".join("?" * len(combo_ids))
    cur = conn.execute(
        f"""
        UPDATE lotto_combinations
        SET allocated_at = NULL, auto_order_id = NULL
        WHERE id IN ({placeholders})
        """,
        combo_ids,
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def count_available_combinations(draw_round: int) -> int:
    """미배포 조합 수."""
    conn = _connect()
    row = conn.execute(
        """
        SELECT COUNT(*) FROM lotto_combinations
        WHERE draw_round = ? AND allocated_at IS NULL
        """,
        (int(draw_round),),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_combinations_by_auto_order_id(auto_order_id: int) -> list[dict]:
    """자동구매 주문에 배정된 조합 목록."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, num1, num2, num3, num4, num5, num6
        FROM lotto_combinations
        WHERE auto_order_id = ?
        ORDER BY id
        """,
        (int(auto_order_id),),
    ).fetchall()
    conn.close()
    return [
        {"id": int(row["id"]), "combo": list(_combo_nums_from_row(row))}
        for row in rows
    ]


def enqueue_sms(phone: str, purchase_type: str, send_status: str = "WAIT") -> int:
    """구매확정 시 문자 발송 대기열 등록 (로또 번호 저장 없음)."""
    phone = str(phone).strip()
    purchase_type = str(purchase_type).strip()
    send_status = str(send_status).strip().upper()

    if not phone:
        raise ValueError("전화번호가 비어 있습니다.")
    if purchase_type not in PURCHASE_TYPES:
        raise ValueError("purchase_type은 '정기구독' 또는 '일반구매'만 허용됩니다.")
    if send_status not in SEND_STATUSES:
        raise ValueError(
            "send_status는 'WAIT', 'SENT', 'TEST_SKIP', 'BANNER_ONLY'만 허용됩니다."
        )

    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO sms_queue (phone, purchase_type, send_status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (phone, purchase_type, send_status, datetime.now().isoformat()),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def _normalize_combo(row) -> tuple[int, int, int, int, int, int] | None:
    """6개 번호(1~45, 중복 없음) 튜플로 정규화. 실패 시 None."""
    try:
        nums = [int(float(x)) for x in row]
    except (TypeError, ValueError):
        return None
    if len(nums) != 6:
        return None
    nums = sorted(nums)
    if len(set(nums)) != 6:
        return None
    if any(n < 1 or n > 45 for n in nums):
        return None
    return tuple(nums)


def parse_combination_rows_from_text(text: str) -> list[tuple[int, int, int, int, int, int]]:
    """텍스트(줄 단위, 쉼표/공백 구분)에서 조합 목록 파싱."""
    rows = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p for p in line.replace(",", " ").split() if p.strip()]
        combo = _normalize_combo(parts)
        if combo:
            rows.append(combo)
    return rows


def parse_combination_rows_from_dataframe(df) -> list[tuple[int, int, int, int, int, int]]:
    """DataFrame(번호1~6 또는 num1~6)에서 조합 목록 파싱."""
    cols_num = [f"num{i}" for i in range(1, 7)]
    cols_ko = [f"번호{i}" for i in range(1, 7)]
    if all(c in df.columns for c in cols_ko):
        use_cols = cols_ko
    elif all(c in df.columns for c in cols_num):
        use_cols = cols_num
    else:
        raise ValueError("CSV 컬럼은 '번호1~번호6' 또는 'num1~num6' 형식이어야 합니다.")

    rows = []
    for _, row in df.iterrows():
        combo = _normalize_combo([row[c] for c in use_cols])
        if combo:
            rows.append(combo)
    return rows


def bulk_insert_lotto_combinations(
    draw_round: int,
    combinations: list,
) -> int:
    """익명 로또 조합 대량 등록 (win_rank는 NULL)."""
    draw_round = int(draw_round)
    if draw_round < 1:
        raise ValueError("draw_round는 1 이상이어야 합니다.")

    payload = []
    for row in combinations:
        combo = row if isinstance(row, tuple) else _normalize_combo(row)
        if combo is None:
            continue
        payload.append((draw_round, *combo))

    if not payload:
        return 0

    conn = _connect()
    conn.executemany(
        """
        INSERT INTO lotto_combinations
            (draw_round, num1, num2, num3, num4, num5, num6, win_rank)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        payload,
    )
    conn.commit()
    conn.close()
    return len(payload)


def update_win_ranks_for_draw(
    draw_round: int,
    winning_numbers: list[int],
    bonus_number: int,
) -> int:
    """운영자 추출 조합 vs 당첨번호 — 1~5등 win_rank 일괄 갱신."""
    from lotto_stats import calc_lotto_win_rank

    draw_round = int(draw_round)
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, num1, num2, num3, num4, num5, num6
        FROM lotto_combinations
        WHERE draw_round = ?
        """,
        (draw_round,),
    ).fetchall()
    updated = 0
    for row in rows:
        combo = _combo_nums_from_row(row)
        rank = calc_lotto_win_rank(combo, winning_numbers, bonus_number)
        conn.execute(
            "UPDATE lotto_combinations SET win_rank = ? WHERE id = ?",
            (rank, int(row["id"])),
        )
        updated += 1
    conn.commit()
    conn.close()
    return updated


def delete_lotto_combinations_by_draw(draw_round: int) -> int:
    """해당 회차 추출 조합 전체 삭제."""
    draw_round = int(draw_round)
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM lotto_combinations WHERE draw_round = ?",
        (draw_round,),
    )
    deleted = int(cur.rowcount or 0)
    conn.commit()
    conn.close()
    return deleted


def get_win_rank_counts_by_draw(draw_round: int) -> dict[int, int]:
    """특정 회차 1~5등 당첨 수량 GROUP BY 집계 (마케팅용)."""
    draw_round = int(draw_round)
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT win_rank, COUNT(*) AS cnt
        FROM lotto_combinations
        WHERE draw_round = ? AND win_rank IS NOT NULL
        GROUP BY win_rank
        ORDER BY win_rank
        """,
        (draw_round,),
    ).fetchall()
    conn.close()
    return {int(row["win_rank"]): int(row["cnt"]) for row in rows if row["win_rank"] is not None}


def get_combination_count_by_draw(draw_round: int) -> int:
    """특정 회차 등록 조합 총 개수."""
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) FROM lotto_combinations WHERE draw_round = ?",
        (int(draw_round),),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_draw_extraction_stats(limit: int = 20) -> list[dict]:
    """회차별 추출 수량 및 1~5등 당첨 건수 (draw_round DESC)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            draw_round,
            COUNT(*) AS total_count,
            SUM(CASE WHEN win_rank = 1 THEN 1 ELSE 0 END) AS rank_1,
            SUM(CASE WHEN win_rank = 2 THEN 1 ELSE 0 END) AS rank_2,
            SUM(CASE WHEN win_rank = 3 THEN 1 ELSE 0 END) AS rank_3,
            SUM(CASE WHEN win_rank = 4 THEN 1 ELSE 0 END) AS rank_4,
            SUM(CASE WHEN win_rank = 5 THEN 1 ELSE 0 END) AS rank_5
        FROM lotto_combinations
        GROUP BY draw_round
        ORDER BY draw_round DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    conn.close()
    return [
        {
            "draw_round": int(row["draw_round"]),
            "total_count": int(row["total_count"]),
            "rank_1": int(row["rank_1"] or 0),
            "rank_2": int(row["rank_2"] or 0),
            "rank_3": int(row["rank_3"] or 0),
            "rank_4": int(row["rank_4"] or 0),
            "rank_5": int(row["rank_5"] or 0),
        }
        for row in rows
    ]


def get_mock_draw_extraction_stats() -> list[dict]:
    """DB 비어 있을 때 — 관리자 저장 회차(1236~1234) 요약 fallback."""
    seed = [
        (1236, 1715, 0, 0, 0, 0, 0),
        (1235, 2008, 1, 0, 7, 70, 597),
        (1234, 7507, 1, 0, 5, 43, 311),
    ]
    return [
        {
            "draw_round": r,
            "total_count": total,
            "rank_1": r1,
            "rank_2": r2,
            "rank_3": r3,
            "rank_4": r4,
            "rank_5": r5,
        }
        for r, total, r1, r2, r3, r4, r5 in seed
    ]


__all__ = [
    "InsufficientCombinationsError",
    "init_marketing_tables",
    "enqueue_sms",
    "parse_combination_rows_from_text",
    "parse_combination_rows_from_dataframe",
    "bulk_insert_lotto_combinations",
    "build_number_frequency_map",
    "combo_priority_score",
    "allocate_lotto_combinations",
    "allocate_lotto_combinations_random_sequential",
    "release_lotto_combination_allocation",
    "count_available_combinations",
    "get_combinations_by_auto_order_id",
    "delete_lotto_combinations_by_draw",
    "update_win_ranks_for_draw",
    "get_win_rank_counts_by_draw",
    "get_combination_count_by_draw",
    "get_draw_extraction_stats",
    "get_mock_draw_extraction_stats",
    "ensure_marketing_pool_seeds",
    "import_marketing_pool_seed",
    "MARKETING_POOL_SEED_DRAWS",
]
