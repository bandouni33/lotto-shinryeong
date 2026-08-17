"""익명 마케팅 데이터 전용 SQLite 모듈 (sms_queue ↔ lotto_combinations 완전 분리)."""

import csv
import gzip
import random
import sqlite3
import db_turso
from collections import Counter
from datetime import datetime
from pathlib import Path

DB_PATH = "lotto.db"
_APP_ROOT = Path(__file__).resolve().parent
MARKETING_POOL_SEED_DRAWS = (1234, 1235, 1236)
_MARKETING_POOL_DIR = _APP_ROOT / "data" / "marketing_pools"
# 첫 시드 회차(1234) 미만은 테스트/스트레이 데이터로 간주 — 통계 조회에서 제외한다.
MIN_DISPLAY_DRAW_ROUND = min(MARKETING_POOL_SEED_DRAWS)

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
    return db_turso.connect()


_MARKETING_TABLES_READY = False


def init_marketing_tables():
    """sms_queue, lotto_combinations 테이블 생성 (FK/회원 ID 없음).

    CREATE TABLE/INDEX IF NOT EXISTS라 멱등이지만, 한 프로세스 안에서 같은
    렌더 경로가 여러 호출부(check_next_draw_pool_ready, _load_stats_table 등)를
    거치며 중복 실행되던 걸 막기 위해 최초 1회 이후로는 스킵한다.
    """
    global _MARKETING_TABLES_READY
    if _MARKETING_TABLES_READY:
        return
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
    # 테스트 기간(AUTO_PURCHASE_SKIP_AUTH) 구매내역 — 로그인 없이도 앱을 다시 켰을 때
    # 구매내역이 남아있도록, 쿠키로 유지되는 guest_id에 주문 메타데이터를 묶어 저장한다.
    # 조합 자체는 이미 lotto_combinations.auto_order_id로 영속돼 있으니, 여기엔
    # 그 auto_order_id를 다시 찾기 위한 최소한의 메타데이터만 저장한다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guest_auto_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT NOT NULL,
            auto_order_id INTEGER NOT NULL UNIQUE,
            draw_round INTEGER,
            combo_count INTEGER,
            cost INTEGER,
            purchase_method TEXT,
            purchase_type TEXT,
            sms_days TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_guest_auto_orders_guest
        ON guest_auto_orders(guest_id, created_at)
    """)
    # 업데이트 안내 배너 — "오늘 이미 봤는지"를 예전엔 쿠키/localStorage로만 판단했는데,
    # 이 앱은 화면마다 안드로이드 웹뷰가 통째로 새로 생성되는 구조라 방금 쓴 쿠키가
    # 디스크에 저장되기 전에 다음 화면으로 넘어가버리면 "몇 번을 눌러도 또 뜨는" 문제로
    # 이어졌다. guest_id에 묶어 서버 DB에 기록하면 그 타이밍 문제 자체가 없다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guest_update_notice (
            guest_id TEXT NOT NULL,
            version TEXT NOT NULL,
            last_shown_date TEXT,
            PRIMARY KEY (guest_id, version)
        )
    """)
    # 타로 일일 뽑기 제한 — 예전엔 쿠키(document.cookie)에 오늘 뽑은 횟수를 저장했는데,
    # 안드로이드 웹뷰가 화면 전환마다 새로 생성되는 구조상 쿠키가 디스크에 저장되기
    # 전에 유실되곤 해서 "재접속하면 계속 뽑을 수 있는" 문제로 이어졌다. guest_id에
    # 묶어 DB에 저장하면 그 타이밍 문제 자체가 없다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guest_tarot_draws (
            guest_id TEXT NOT NULL,
            draw_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guest_id, draw_date)
        )
    """)
    # 번개조합/안티조합/액땜조합 등 "그 자리에서 생성"된 조합 저장 — lotto_combinations는
    # 자동구매 재고풀(allocated_at IS NULL = 미배정 재고)로 쓰이는 테이블이라, 여기에
    # 그냥 섞어 넣으면 재고 수량 집계와 자동구매 통계(get_draw_extraction_stats)가
    # 오염된다. 그래서 완전히 별도 테이블로 분리한다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guest_generated_combos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT NOT NULL,
            source TEXT NOT NULL,
            draw_round INTEGER NOT NULL,
            num1 INTEGER NOT NULL,
            num2 INTEGER NOT NULL,
            num3 INTEGER NOT NULL,
            num4 INTEGER NOT NULL,
            num5 INTEGER NOT NULL,
            num6 INTEGER NOT NULL,
            win_rank INTEGER NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_guest_generated_combos_guest
        ON guest_generated_combos(guest_id, created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_guest_generated_combos_draw
        ON guest_generated_combos(draw_round, win_rank)
    """)
    _migrate_lotto_combinations(conn)
    conn.commit()
    conn.close()
    _MARKETING_TABLES_READY = True


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


_MARKETING_POOL_SEEDS_CHECKED: set[tuple[int, ...]] = set()


def ensure_marketing_pool_seeds(
    draw_rounds: tuple[int, ...] = MARKETING_POOL_SEED_DRAWS,
) -> dict[int, int]:
    """Cloud 등 lotto.db 가 비어 있을 때 관리자 저장 회차 풀 복원.

    같은 draw_rounds 조합에 대해 한 프로세스 안에서 이미 확인했다면 다시
    회차별 COUNT 쿼리를 반복하지 않는다 (여러 호출부가 기본값으로 중복 호출하던 문제).
    """
    if draw_rounds in _MARKETING_POOL_SEEDS_CHECKED:
        return {}
    imported: dict[int, int] = {}
    for draw_round in draw_rounds:
        count = import_marketing_pool_seed(draw_round)
        if count:
            imported[draw_round] = count
    _MARKETING_POOL_SEEDS_CHECKED.add(draw_rounds)
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
    # get_combinations_by_auto_order_id()가 auto_order_id로 조회하는데 이 컬럼엔
    # 인덱스가 없었다 — lotto_combinations는 회차마다 수천 행씩 계속 쌓이는 테이블이라,
    # 인덱스 없이는 구매내역을 열 때마다(주문 하나당 한 번씩) 테이블 전체를 스캔하게
    # 되어 데이터가 쌓일수록 점점 느려지는 위험이 있었다.
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lotto_combinations_auto_order
        ON lotto_combinations(auto_order_id)
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


def create_guest_auto_order(
    guest_id: str,
    draw_round: int,
    combo_count: int,
    cost,
    purchase_method: str,
    purchase_type: str,
    sms_days,
) -> int:
    """비로그인(테스트 기간) 구매내역 메타데이터를 guest_id에 묶어 저장하고,
    전역적으로 유일한 id를 발급해 반환한다.

    예전엔 호출부가 "9_000_000 + 세션 내 순번"으로 auto_order_id를 직접
    계산했는데, 그 순번이 세션마다(=앱을 재시작할 때마다) 1부터 다시 시작돼서
    서로 다른 세션·사용자의 "이번 세션 첫 구매"끼리 값이 겹칠 수 있었다.
    session_state만 쓰던 예전엔 어차피 재시작하면 다 사라지니 무해했지만,
    이제 이 id를 구매내역 조회 키로 영속시키다 보니 겹치면 나중 저장이
    조용히 무시되는(INSERT OR IGNORE) 문제로 이어졌다. 그래서 DB의
    AUTOINCREMENT로 진짜 유일한 id를 먼저 발급받고, 그 id를 그대로
    lotto_combinations.auto_order_id로도 쓴다.
    """
    import json

    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO guest_auto_orders
            (guest_id, auto_order_id, draw_round, combo_count, cost,
             purchase_method, purchase_type, sms_days, created_at)
        VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(guest_id),
            int(draw_round),
            int(combo_count),
            int(cost) if cost is not None else None,
            purchase_method,
            purchase_type,
            json.dumps(list(sms_days or [])),
            datetime.now().isoformat(),
        ),
    )
    new_id = int(cur.lastrowid)
    conn.execute(
        "UPDATE guest_auto_orders SET auto_order_id = ? WHERE id = ?",
        (new_id, new_id),
    )
    conn.commit()
    conn.close()
    return new_id


def get_guest_tarot_draw_count(guest_id: str, draw_date: str) -> int:
    """guest_id가 오늘(draw_date) 이미 뽑은 횟수."""
    conn = _connect()
    row = conn.execute(
        "SELECT count FROM guest_tarot_draws WHERE guest_id = ? AND draw_date = ?",
        (str(guest_id), draw_date),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def register_guest_tarot_draw(guest_id: str, draw_date: str) -> int:
    """오늘 뽑기 횟수를 1 증가시키고, 증가된 이후의 횟수를 반환한다."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO guest_tarot_draws (guest_id, draw_date, count)
        VALUES (?, ?, 1)
        ON CONFLICT(guest_id, draw_date) DO UPDATE SET count = count + 1
        """,
        (str(guest_id), draw_date),
    )
    conn.commit()
    row = conn.execute(
        "SELECT count FROM guest_tarot_draws WHERE guest_id = ? AND draw_date = ?",
        (str(guest_id), draw_date),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def was_guest_update_notice_shown_today(guest_id: str, version: str, today: str) -> bool:
    """이 guest_id에게 오늘(today, KST) 이 버전의 업데이트 배너를 이미 보여줬는지."""
    conn = _connect()
    row = conn.execute(
        "SELECT last_shown_date FROM guest_update_notice WHERE guest_id = ? AND version = ?",
        (str(guest_id), version),
    ).fetchone()
    conn.close()
    return bool(row) and row[0] == today


def mark_guest_update_notice_shown(guest_id: str, version: str, today: str) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT INTO guest_update_notice (guest_id, version, last_shown_date)
        VALUES (?, ?, ?)
        ON CONFLICT(guest_id, version) DO UPDATE SET last_shown_date = excluded.last_shown_date
        """,
        (str(guest_id), version, today),
    )
    conn.commit()
    conn.close()


def save_guest_generated_combos(
    guest_id: str,
    source: str,
    draw_round: int,
    combos,
) -> str:
    """번개조합 등에서 한 번에 생성된 조합 묶음을 저장하고, 그 묶음을 묶는 batch_id를 반환한다.

    lotto_combinations의 자동구매 주문처럼 별도 "주문" 테이블 없이, 같은 저장
    시각(created_at)을 공유하는 행들을 하나의 묶음으로 취급한다 — 이 테이블은
    한 guest_id의 한 번 저장 클릭이 한 번의 INSERT로 끝나므로 충분하다.
    """
    created_at = datetime.now().isoformat()
    conn = _connect()
    conn.executemany(
        """
        INSERT INTO guest_generated_combos
            (guest_id, source, draw_round, num1, num2, num3, num4, num5, num6, win_rank, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        [
            (str(guest_id), source, int(draw_round), *[int(n) for n in combo], created_at)
            for combo in combos
        ],
    )
    conn.commit()
    conn.close()
    return created_at


def list_guest_generated_combos(guest_id: str, source: str | None = None, limit: int = 20) -> list[dict]:
    """guest_id가 저장한 생성조합을 저장 묶음(batch) 단위로 최신순 반환."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    query = """
        SELECT id, source, draw_round, num1, num2, num3, num4, num5, num6, win_rank, created_at
        FROM guest_generated_combos
        WHERE guest_id = ?
    """
    params: list = [str(guest_id)]
    if source:
        query += " AND source = ?"
        params.append(source)
    # created_at은 한 저장(batch) 안의 모든 행이 완전히 같은 값을 공유해서, DESC 정렬만
    # 걸면 같은 값끼리의 순서가 보장되지 않는다(SQLite가 동점 행을 생성 순서의 역순으로
    # 돌려줄 수 있음 — 실제로 화면에 보인 생성 순서와 저장내역 카드 순서가 뒤집혀
    # 보이던 원인). id ASC를 2차 정렬 기준으로 추가해 저장(=생성) 순서를 보장한다.
    query += " ORDER BY created_at DESC, id ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    batches: dict[tuple, dict] = {}
    order: list[tuple] = []
    for row in rows:
        key = (row["created_at"], row["draw_round"], row["source"])
        if key not in batches:
            batches[key] = {
                "batch_id": row["created_at"],
                "source": row["source"],
                "draw_round": int(row["draw_round"]),
                "created_at": row["created_at"],
                "combos": [],
            }
            order.append(key)
        batches[key]["combos"].append(
            {
                "combo": list(_combo_nums_from_row(row)),
                "win_rank": int(row["win_rank"]) if row["win_rank"] is not None else None,
            }
        )
    return [batches[k] for k in order[:limit]]


def get_generated_combo_pending_draw_rounds() -> list[int]:
    """win_rank가 아직 비어 있는 생성조합이 존재하는 회차 목록 — 당첨마킹 동기화 대상."""
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT draw_round FROM guest_generated_combos WHERE win_rank IS NULL"
    ).fetchall()
    conn.close()
    return [int(row[0]) for row in rows]


def update_win_ranks_for_generated_draw(
    draw_round: int,
    winning_numbers: list[int],
    bonus_number: int,
) -> int:
    """생성조합(guest_generated_combos) vs 당첨번호 — 1~5등 win_rank 일괄 갱신."""
    from lotto_stats import calc_lotto_win_rank

    draw_round = int(draw_round)
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, num1, num2, num3, num4, num5, num6
        FROM guest_generated_combos
        WHERE draw_round = ?
        """,
        (draw_round,),
    ).fetchall()
    payload = []
    for row in rows:
        combo = _combo_nums_from_row(row)
        rank = calc_lotto_win_rank(combo, winning_numbers, bonus_number)
        payload.append((rank, int(row["id"])))
    if payload:
        conn.executemany(
            "UPDATE guest_generated_combos SET win_rank = ? WHERE id = ?",
            payload,
        )
    conn.commit()
    conn.close()
    return len(payload)


def delete_guest_auto_order(order_id: int) -> None:
    """조합 배정 실패 등으로 주문이 성립되지 않았을 때, 발급해둔 placeholder를 되돌린다."""
    conn = _connect()
    conn.execute("DELETE FROM guest_auto_orders WHERE id = ?", (int(order_id),))
    conn.commit()
    conn.close()


def list_guest_auto_orders(guest_id: str, limit: int = 20) -> list[dict]:
    """guest_id에 묶인 구매내역 메타데이터를 최신순으로 반환 (조합 목록은 미포함)."""
    import json

    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT auto_order_id, draw_round, combo_count, cost,
               purchase_method, purchase_type, sms_days, created_at
        FROM guest_auto_orders
        WHERE guest_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (str(guest_id), int(limit)),
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        try:
            sms_days = json.loads(row["sms_days"]) if row["sms_days"] else []
        except (TypeError, ValueError):
            sms_days = []
        result.append(
            {
                "auto_order_id": int(row["auto_order_id"]),
                "draw_round": row["draw_round"],
                "combo_count": row["combo_count"],
                "cost": row["cost"],
                "purchase_method": row["purchase_method"],
                "purchase_type": row["purchase_type"],
                "sms_days": sms_days,
            }
        )
    return result


def get_combinations_by_draw(draw_round: int) -> list[dict]:
    """해당 회차 추출 조합 전체 (다운로드용) — win_rank 포함."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, num1, num2, num3, num4, num5, num6, win_rank
        FROM lotto_combinations
        WHERE draw_round = ?
        ORDER BY id
        """,
        (int(draw_round),),
    ).fetchall()
    conn.close()
    return [
        {
            "id": int(row["id"]),
            "combo": list(_combo_nums_from_row(row)),
            "win_rank": int(row["win_rank"]) if row["win_rank"] is not None else None,
        }
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
    payload = []
    for row in rows:
        combo = _combo_nums_from_row(row)
        rank = calc_lotto_win_rank(combo, winning_numbers, bonus_number)
        payload.append((rank, int(row["id"])))
    if payload:
        conn.executemany(
            "UPDATE lotto_combinations SET win_rank = ? WHERE id = ?",
            payload,
        )
    conn.commit()
    conn.close()
    return len(payload)


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
        WHERE draw_round >= ?
        GROUP BY draw_round
        ORDER BY draw_round DESC
        LIMIT ?
        """,
        (MIN_DISPLAY_DRAW_ROUND, int(limit)),
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


def get_draw_purchase_conversion_stats(limit: int = 20) -> list[dict]:
    """회차별 추출 조합 대비 실제 구매(배정)로 이어진 개수 — 관리자 대시보드용.

    lotto_combinations의 allocated_at이 채워진 행 = 자동구매로 배정된 조합.
    draw_round, allocated_at 둘 다 이미 인덱스(idx_lotto_combinations_allocate)가
    있어서 이 GROUP BY 하나로 회차별 집계를 한 번에 가져온다(회차마다 별도
    쿼리를 반복하지 않음)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            draw_round,
            COUNT(*) AS total_count,
            SUM(CASE WHEN allocated_at IS NOT NULL THEN 1 ELSE 0 END) AS purchased_count
        FROM lotto_combinations
        WHERE draw_round >= ?
        GROUP BY draw_round
        ORDER BY draw_round DESC
        LIMIT ?
        """,
        (MIN_DISPLAY_DRAW_ROUND, int(limit)),
    ).fetchall()
    conn.close()
    return [
        {
            "draw_round": int(row["draw_round"]),
            "total_count": int(row["total_count"]),
            "purchased_count": int(row["purchased_count"] or 0),
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
    "create_guest_auto_order",
    "delete_guest_auto_order",
    "list_guest_auto_orders",
    "save_guest_generated_combos",
    "list_guest_generated_combos",
    "get_generated_combo_pending_draw_rounds",
    "update_win_ranks_for_generated_draw",
    "get_combinations_by_draw",
    "delete_lotto_combinations_by_draw",
    "update_win_ranks_for_draw",
    "get_win_rank_counts_by_draw",
    "get_combination_count_by_draw",
    "get_draw_extraction_stats",
    "get_draw_purchase_conversion_stats",
    "get_mock_draw_extraction_stats",
    "ensure_marketing_pool_seeds",
    "import_marketing_pool_seed",
    "MARKETING_POOL_SEED_DRAWS",
]
