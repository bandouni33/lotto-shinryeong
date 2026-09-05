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
    # 2026-09-05: 1241회차부터 — "이 회차 필터 통과 조합군 전체엔 이만큼의
    # 당첨가능조합이 있었다"는 참고용 통계. 실제 판매된 조합의 진짜 당첨
    # 여부(lotto_combinations.win_rank)와는 별개의 값이라 별도 테이블에 둔다
    # — 고객 개인의 실제 당첨 판정 로직은 이 테이블과 전혀 무관하게 그대로
    # 유지된다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS draw_reference_ranks (
            draw_round INTEGER PRIMARY KEY,
            ref_rank_1 INTEGER NOT NULL,
            ref_rank_2 INTEGER NOT NULL,
            ref_rank_3 INTEGER NOT NULL,
            ref_rank_4 INTEGER NOT NULL,
            ref_rank_5 INTEGER NOT NULL,
            computed_at TEXT NOT NULL
        )
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
            win_rank INTEGER NULL,
            top3_mask INTEGER NULL
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
    # 회차별 조합을 추출(저장)한 "그 순간" 관리자 3종필터에 몇 개 규칙이 켜져 있었는지
    # 기록해둔다 — 필터는 이후에도 계속 바뀌는데, 예전엔 "지금 필터 규칙 수"를 모든
    # 회차에 똑같이 보여줘서 회차가 달라도 항상 같은 숫자가 나오는 문제가 있었다.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS draw_pattern_counts (
            draw_round INTEGER PRIMARY KEY,
            pattern_count INTEGER NOT NULL,
            recorded_at TEXT NOT NULL
        )
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
    # 당첨 등수 동기화 완료 여부 — win_rank 컬럼 자체는 "낙첨"도 NULL, "아직 동기화
    # 안 됨"도 NULL이라 이 둘을 구분할 수 없다(대부분의 조합이 낙첨이라 거의 항상
    # NULL이 남아있음). 그래서 매번 "혹시 안 된 게 있나" 싶어 이미 확정된 회차까지
    # 전체를 다시 훑어 재기록하고 있었다 — 로또 추첨은 주 1회뿐이라 한 번 확정되면
    # 다시는 안 바뀌는 데이터인데도. 회차(+출처)별로 "이미 끝났다"를 별도로 기록해서,
    # 끝난 회차는 아예 건드리지 않게 한다(2026-08-25, Turso 쓰기 할당량 초과 사고
    # 원인 근본 수정).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS draw_win_rank_sync_status (
            draw_round INTEGER NOT NULL,
            source TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (draw_round, source)
        )
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
    # 2026-09-05: 격차순위(gap_order) 1~3위 숫자 포함 여부 비트마스크
    # (1위=1, 2위=2, 3위=4) — 구매 배포 시 "5개=1묶음"을 5가지 겹침
    # 조합({1,2}/{1,3}/{1,2,3}/{2,3}/{3}만)으로 정확히 채우는 데 쓴다.
    # 관리자 CSV 업로드 등 top3_numbers 없이 저장된 기존/구버전 행은 NULL로
    # 남아 묶음 배분에선 제외되고 부족분 채우기(leftover)에만 쓰인다.
    if "top3_mask" not in cols:
        conn.execute("ALTER TABLE lotto_combinations ADD COLUMN top3_mask INTEGER NULL")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lotto_combinations_allocate
        ON lotto_combinations(draw_round, allocated_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lotto_combinations_top3_mask
        ON lotto_combinations(draw_round, allocated_at, top3_mask)
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
        SELECT id, num1, num2, num3, num4, num5, num6, top3_mask
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


# ─── 동시 배포 안전장치 (2026-08-22) ───────────────────────────────────────
# 기존에는 "BEGIN IMMEDIATE ... UPDATE ... commit()"으로 잠금을 걸었다고
# 생각했는데, 실제 TURSO_DATABASE_URL이 https(HTTP) 스킴이라 libsql_client의
# HTTP 클라이언트는 애초에 트랜잭션 자체를 지원하지 않는다("The HTTP client
# does not support transactions" — 라이브러리 자체 에러 메시지, db_turso.py의
# _ConnectionWrapper.commit()도 원래부터 아무 일도 안 하는 함수였다). 즉 조회
# (미배포 조합 찾기)와 갱신(배포 표시) 사이에 아무 원자성 보장이 없어서,
# 동시에 여러 명이 자동구매를 누르면 같은 조합이 두 사람에게 중복 배포될 수
# 있는 실제 위험이 있었다.
#
# 해결: 여러 SQL문을 트랜잭션으로 묶는 대신, "이 순간에도 여전히 미배포
# 상태인 것만" 조건(allocated_at IS NULL)을 UPDATE 문 자체에 넣는다 — SQL
# 문 하나는 트랜잭션 없이도 DB 엔진이 원자적으로 처리하므로(HTTP 기반이든
# 아니든 이건 SQL 엔진의 기본 보장), 두 요청이 동시에 같은 조합을 노려도
# 먼저 도착한 것만 실제로 갱신되고 나머지는 자동으로 실패한다. 실패(경합에서
# 밀린) 후보는 다시 새로 조회해서 채우는 재시도 루프로 감당한다.
_MAX_ALLOCATION_ATTEMPTS = 8


def _claim_pending_ids(
    conn: sqlite3.Connection,
    candidate_ids: list[int],
    auto_order_id: int,
    now: str,
) -> list:
    """candidate_ids 중, 이 UPDATE가 실제로 실행되는 순간까지도 미배포
    상태였던 것만 auto_order_id로 배정하고, 성공한 행만 반환한다(원자적).
    다른 요청이 그새 먼저 가져간 id는 이 UPDATE의 WHERE 조건에 안 걸려
    조용히 스킵된다 — 그래서 호출자는 반환된 행 수가 candidate_ids보다
    적을 수 있다는 걸 감안하고 재시도해야 한다."""
    if not candidate_ids:
        return []
    placeholders = ",".join("?" * len(candidate_ids))
    conn.execute(
        f"""
        UPDATE lotto_combinations
        SET allocated_at = ?, auto_order_id = ?
        WHERE id IN ({placeholders}) AND allocated_at IS NULL
        """,
        [now, int(auto_order_id), *candidate_ids],
    )
    # 여기서 commit()이 빠지면(Turso HTTP 백엔드는 각 execute()가 이미
    # 개별 요청으로 즉시 반영되니 무해한 no-op이지만) 다른 커넥션에서 이
    # UPDATE가 아직 안 보일 수 있어 중복 확정으로 이어질 수 있다 — 실제로
    # 로컬 sqlite3로 동시성 테스트해보니 이걸 빼먹었을 때 중복이 재현됐다.
    conn.commit()
    # auto_order_id는 구매 건마다 고유하므로, 이 값으로 필터링하면 "방금 이
    # 호출로 내가 실제로 배정에 성공한 행"만 정확히 걸러진다(다른 동시
    # 요청·과거 배정과 절대 안 섞임).
    return conn.execute(
        f"""
        SELECT id, num1, num2, num3, num4, num5, num6
        FROM lotto_combinations
        WHERE id IN ({placeholders}) AND auto_order_id = ?
        """,
        [*candidate_ids, int(auto_order_id)],
    ).fetchall()


def _verify_claims_alive(conn, claimed_ids: set, auto_order_id: int) -> list:
    """이미 확정했다고 믿고 있는 claimed_ids가 지금도 실제로 이 auto_order_id로
    배정된 채인지 DB에서 다시 확인한다. 동시에 다른 요청이 재고 소진으로
    회전(전체 초기화)을 실행하면, 그 요청이 시작되기 전에 이미 확정됐던
    내 배정도 함께 지워질 수 있다 — allocated_at IS NULL WHERE draw_round=?
    는 회차 전체를 대상으로 하는 무차별 초기화라 "누구 배정인지"를 가리지
    않기 때문이다. 그래서 매 재시도마다 실제로 살아있는 것만 신뢰하고,
    사라진 게 있으면 그만큼 다시 채우도록 재시도 루프에 맡긴다."""
    if not claimed_ids:
        return []
    placeholders = ",".join("?" * len(claimed_ids))
    return conn.execute(
        f"""
        SELECT id, num1, num2, num3, num4, num5, num6, top3_mask
        FROM lotto_combinations
        WHERE id IN ({placeholders}) AND auto_order_id = ?
        """,
        [*claimed_ids, int(auto_order_id)],
    ).fetchall()


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

    동시에 여러 구매 요청이 들어와도 같은 조합이 중복 배정되지 않도록,
    후보를 고른 뒤 실제 확정은 "그 순간까지도 미배포 상태인 것만" UPDATE로
    원자적으로 처리한다(_claim_pending_ids). 경합에서 밀려 놓친 만큼만 다시
    후보를 골라 재시도한다(최대 _MAX_ALLOCATION_ATTEMPTS회).
    """
    draw_round = int(draw_round)
    count = int(count)
    if count < 1:
        return []

    conn = _connect()
    conn.row_factory = sqlite3.Row
    rotated = False
    claimed_rows: list = []
    claimed_ids: set[int] = set()
    try:
        number_freq = build_number_frequency_map(draw_round, conn)
        if not number_freq:
            raise InsufficientCombinationsError(draw_round, count, 0)

        total = _count_total_combinations(conn, draw_round)
        if total < count:
            raise InsufficientCombinationsError(draw_round, count, total)

        for _attempt in range(_MAX_ALLOCATION_ATTEMPTS):
            if claimed_ids:
                # 다른 동시 요청이 재고 소진으로 회전(회차 전체 초기화)을
                # 실행하면 내가 이미 확정한 배정까지 함께 지워질 수 있다 —
                # 그래서 매 시도마다 실제로 살아있는지 재확인하고, 사라진
                # 만큼은 아래에서 다시 채운다.
                alive_rows = _verify_claims_alive(conn, claimed_ids, auto_order_id)
                alive_ids = {int(r["id"]) for r in alive_rows}
                if alive_ids != claimed_ids:
                    claimed_ids = alive_ids
                    claimed_rows = list(alive_rows)

            need = count - len(claimed_rows)
            if need <= 0:
                break

            pending = [
                row for row in _fetch_pending_rows(conn, draw_round)
                if int(row["id"]) not in claimed_ids
            ]
            # 이미 확정한 것이 하나도 없는 첫 시도에서만 회전(초기화)한다 —
            # 확정된 뒤에 회전하면 이번 요청이 이미 배정받은 조합까지
            # allocated_at이 NULL로 지워져 다른 요청과 중복 배정될 수 있다.
            if len(pending) < need and not claimed_rows and not rotated:
                _reset_draw_allocations(conn, draw_round)
                conn.commit()
                rotated = True
                pending = _fetch_pending_rows(conn, draw_round)

            if not pending:
                continue

            candidates = _sort_combos_by_priority(pending, number_freq)[:need]
            now = datetime.now().isoformat()
            newly_claimed = _claim_pending_ids(
                conn, [int(row["id"]) for row in candidates], auto_order_id, now
            )
            for row in newly_claimed:
                rid = int(row["id"])
                if rid not in claimed_ids:
                    claimed_ids.add(rid)
                    claimed_rows.append(row)

        # 루프가 끝난 직후에도 마지막 시도 이후 찰나에 남의 회전이 끼어들
        # 수 있으니, 반환 직전 마지막으로 한 번 더 실사를 확인한다.
        if claimed_ids:
            alive_rows = _verify_claims_alive(conn, claimed_ids, auto_order_id)
            alive_ids = {int(r["id"]) for r in alive_rows}
            if alive_ids != claimed_ids:
                claimed_ids = alive_ids
                claimed_rows = list(alive_rows)

        if len(claimed_rows) < count:
            if claimed_rows:
                release_lotto_combination_allocation(list(claimed_ids))
            raise InsufficientCombinationsError(draw_round, count, len(claimed_rows))
    finally:
        conn.close()

    return [
        {
            "id": int(row["id"]),
            "combo": _combo_nums_from_row(row),
            "rotated": rotated,
        }
        for row in claimed_rows[:count]
    ]


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


# 2026-09-05 확정(사용자 지정): 구매 5개 = "1묶음". 격차순위(gap_order) 1~3위
# 숫자를 어떤 조합으로 겹쳐서 포함하는지에 따라 5가지로 나눠 정확히 1개씩
# 채운다 — 순수 1위만/2위만 포함 조합은 흔해서 묶음에서 제외하고, 겹치는(드문)
# 조합들을 고르게 배분해 다양성을 보장한다. 비트: 1위=1, 2위=2, 3위=4.
_BUNDLE_MASKS = (3, 5, 7, 6, 4)  # {1,2} / {1,3} / {1,2,3} / {2,3} / {3}만
_BUNDLE_SIZE = len(_BUNDLE_MASKS)


def _bundle_mask_quota(count: int) -> dict[int, int]:
    """count(5의 배수 기준)를 5가지 마스크에 균등 배분한 목표 수량.
    5의 배수가 아니면 나머지를 앞에서부터 1개씩 얹는다(방어적 처리 —
    현재 구매 수량 선택지는 5/10개뿐이라 실제로는 항상 딱 떨어진다)."""
    bundles, leftover = divmod(count, _BUNDLE_SIZE)
    quota = {mask: bundles for mask in _BUNDLE_MASKS}
    for mask in _BUNDLE_MASKS[:leftover]:
        quota[mask] += 1
    return quota


def _pick_bundle_candidates(pending: list, quota_remaining: dict[int, int]) -> list:
    """마스크별 부족분을 그 마스크 버킷 안에서 분산선택(_pick_spread_indices)으로
    채운다. 특정 마스크 재고가 모자라면 남은 총량만큼 나머지 pending(마스크
    무관, NULL 포함)에서 채워 최소한 need는 맞춘다."""
    by_mask: dict[int, list] = {}
    for row in pending:
        by_mask.setdefault(int(row["top3_mask"]) if row["top3_mask"] is not None else 0, []).append(row)

    picked: list = []
    picked_ids: set[int] = set()
    for mask, need in quota_remaining.items():
        if need <= 0:
            continue
        bucket = by_mask.get(mask, [])
        if not bucket:
            continue
        idxs = _pick_spread_indices(len(bucket), min(need, len(bucket)))
        for i in idxs:
            row = bucket[i]
            rid = int(row["id"])
            if rid not in picked_ids:
                picked_ids.add(rid)
                picked.append(row)

    still_need = sum(quota_remaining.values()) - len(picked)
    if still_need > 0:
        leftover = [row for row in pending if int(row["id"]) not in picked_ids]
        if leftover:
            idxs = _pick_spread_indices(len(leftover), min(still_need, len(leftover)))
            picked.extend(leftover[i] for i in idxs)

    return picked


def allocate_lotto_combinations_random_sequential(
    draw_round: int,
    count: int,
    auto_order_id: int,
) -> list[dict]:
    """
    미배포 조합 풀(관리자 저장)에서 불규칙 간격으로 count개 분산 배정.

    예) 5개 → 인덱스 1, 3, 6, 10, 14처럼 퍼져서 선택.
    재고가 부족하면 해당 회차 배포를 초기화한 뒤 다시 배정(회전).

    동시에 여러 구매 요청이 들어와도 같은 조합이 중복 배정되지 않도록,
    후보를 고른 뒤 실제 확정은 "그 순간까지도 미배포 상태인 것만" UPDATE로
    원자적으로 처리한다(_claim_pending_ids). 경합에서 밀려 놓친 만큼만 다시
    후보를 골라 재시도한다(최대 _MAX_ALLOCATION_ATTEMPTS회).
    """
    draw_round = int(draw_round)
    count = int(count)
    if count < 1:
        return []

    conn = _connect()
    conn.row_factory = sqlite3.Row
    rotated = False
    claimed_rows: list = []
    claimed_ids: set[int] = set()
    # count가 5의 배수(현재 구매 수량 선택지는 5/10개뿐)면 "1~3위 절대수
    # 겹침 조합 5종 묶음" 배분을 적용 — 그 외(예: 관리자 도구의 임의 수량
    # 호출)는 기존 순수 분산선택 그대로.
    use_bundle_quota = count % _BUNDLE_SIZE == 0
    full_quota = _bundle_mask_quota(count) if use_bundle_quota else None
    try:
        total = _count_total_combinations(conn, draw_round)
        if total < count:
            raise InsufficientCombinationsError(draw_round, count, total)

        for _attempt in range(_MAX_ALLOCATION_ATTEMPTS):
            if claimed_ids:
                # 다른 동시 요청이 재고 소진으로 회전(회차 전체 초기화)을
                # 실행하면 내가 이미 확정한 배정까지 함께 지워질 수 있다 —
                # 그래서 매 시도마다 실제로 살아있는지 재확인하고, 사라진
                # 만큼은 아래에서 다시 채운다.
                alive_rows = _verify_claims_alive(conn, claimed_ids, auto_order_id)
                alive_ids = {int(r["id"]) for r in alive_rows}
                if alive_ids != claimed_ids:
                    claimed_ids = alive_ids
                    claimed_rows = list(alive_rows)

            need = count - len(claimed_rows)
            if need <= 0:
                break

            pending = [
                row for row in _fetch_pending_rows(conn, draw_round)
                if int(row["id"]) not in claimed_ids
            ]
            # 이미 확정한 것이 하나도 없는 첫 시도에서만 회전(초기화)한다 —
            # 확정된 뒤에 회전하면 이번 요청이 이미 배정받은 조합까지
            # allocated_at이 NULL로 지워져 다른 요청과 중복 배정될 수 있다.
            if len(pending) < need and not claimed_rows and not rotated:
                _reset_draw_allocations(conn, draw_round)
                conn.commit()
                rotated = True
                pending = _fetch_pending_rows(conn, draw_round)

            if not pending:
                continue

            if use_bundle_quota:
                claimed_mask_counts = Counter(
                    int(r["top3_mask"]) if r["top3_mask"] is not None else 0
                    for r in claimed_rows
                )
                quota_remaining = {
                    mask: full_quota[mask] - claimed_mask_counts.get(mask, 0)
                    for mask in full_quota
                }
                candidates = _pick_bundle_candidates(pending, quota_remaining)[:need]
            else:
                pick_indices = _pick_spread_indices(len(pending), min(need, len(pending)))
                candidates = [pending[i] for i in pick_indices]
            now = datetime.now().isoformat()
            newly_claimed = _claim_pending_ids(
                conn, [int(row["id"]) for row in candidates], auto_order_id, now
            )
            for row in newly_claimed:
                rid = int(row["id"])
                if rid not in claimed_ids:
                    claimed_ids.add(rid)
                    claimed_rows.append(row)

        # 루프가 끝난 직후에도 마지막 시도 이후 찰나에 남의 회전이 끼어들
        # 수 있으니, 반환 직전 마지막으로 한 번 더 실사를 확인한다.
        if claimed_ids:
            alive_rows = _verify_claims_alive(conn, claimed_ids, auto_order_id)
            alive_ids = {int(r["id"]) for r in alive_rows}
            if alive_ids != claimed_ids:
                claimed_ids = alive_ids
                claimed_rows = list(alive_rows)

        if len(claimed_rows) < count:
            if claimed_rows:
                release_lotto_combination_allocation(list(claimed_ids))
            raise InsufficientCombinationsError(draw_round, count, len(claimed_rows))
    finally:
        conn.close()

    result_rows = claimed_rows[:count]
    if use_bundle_quota:
        # "묶음 랜덤방식" — 5종류를 순서대로 채웠어도 사용자에게 보여줄
        # 때는 카테고리 순서가 드러나지 않도록 섞는다.
        random.shuffle(result_rows)

    return [
        {
            "id": int(row["id"]),
            "combo": _combo_nums_from_row(row),
            "rotated": rotated,
        }
        for row in result_rows
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


def cleanup_old_guest_generated_combos(keep_rounds: int = 2) -> int:
    """guest_generated_combos(번개조합/안티조합/액땜조합 저장분) — 최근
    N개 회차만 남기고 그 이전은 삭제. 이 테이블은 여지껏 정리 로직이 없어
    무한정 쌓이고 있었다(2026-09-05 확인)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT draw_round FROM guest_generated_combos ORDER BY draw_round DESC"
    ).fetchall()
    keep = {int(r[0]) for r in rows[:keep_rounds]}
    old_rounds = [int(r[0]) for r in rows[keep_rounds:]]
    deleted = 0
    for old_round in old_rounds:
        cur = conn.execute(
            "DELETE FROM guest_generated_combos WHERE draw_round = ?", (old_round,)
        )
        deleted += int(cur.rowcount or 0)
    conn.commit()
    conn.close()
    return deleted


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


def _compute_top3_mask(
    combo: tuple[int, ...], top3_numbers: tuple[int, int, int]
) -> int:
    """격차순위 1~3위 숫자 포함 여부 비트마스크(1위=1, 2위=2, 3위=4)."""
    combo_set = set(combo)
    mask = 0
    for bit, num in zip((1, 2, 4), top3_numbers):
        if num in combo_set:
            mask |= bit
    return mask


def bulk_insert_lotto_combinations(
    draw_round: int,
    combinations: list,
    top3_numbers: tuple[int, int, int] | None = None,
) -> int:
    """익명 로또 조합 대량 등록 (win_rank는 NULL).

    top3_numbers(격차순위 1~3위 숫자)를 주면 조합마다 top3_mask를 같이
    계산해 저장한다 — combo_gen_worker.py가 매주 생성분에 대해 넘긴다.
    관리자 CSV 업로드 등 안 넘기는 경로는 그대로 top3_mask=NULL.
    """
    draw_round = int(draw_round)
    if draw_round < 1:
        raise ValueError("draw_round는 1 이상이어야 합니다.")

    payload = []
    for row in combinations:
        combo = row if isinstance(row, tuple) else _normalize_combo(row)
        if combo is None:
            continue
        mask = _compute_top3_mask(combo, top3_numbers) if top3_numbers else None
        payload.append((draw_round, *combo, mask))

    if not payload:
        return 0

    conn = _connect()
    conn.executemany(
        """
        INSERT INTO lotto_combinations
            (draw_round, num1, num2, num3, num4, num5, num6, win_rank, top3_mask)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        payload,
    )
    conn.commit()
    conn.close()
    return len(payload)


def record_draw_pattern_count(draw_round: int, pattern_count: int) -> None:
    """이 회차 조합을 방금 추출한 시점의 3종필터 규칙 수를 기록한다(bulk_insert_
    lotto_combinations 직후 호출). 같은 회차를 나중에 다시 추출(삭제후 재저장)하면
    그 시점 값으로 덮어써서, 항상 "그 회차의 현재 저장된 조합이 만들어진 시점"의
    값을 유지한다."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO draw_pattern_counts (draw_round, pattern_count, recorded_at)
        VALUES (?, ?, ?)
        ON CONFLICT(draw_round) DO UPDATE SET
            pattern_count = excluded.pattern_count,
            recorded_at = excluded.recorded_at
        """,
        (int(draw_round), int(pattern_count), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_pattern_count_for_draw(draw_round: int) -> int | None:
    conn = _connect()
    row = conn.execute(
        "SELECT pattern_count FROM draw_pattern_counts WHERE draw_round = ?",
        (int(draw_round),),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else None


def is_win_rank_synced(draw_round: int, source: str) -> bool:
    """이 회차(+출처)의 당첨 등수 동기화가 이미 끝났는지. source는
    "lotto_combinations" 또는 "guest_generated_combos" 중 하나로 호출부에서
    구분해 쓴다 — 같은 회차라도 두 테이블은 별도로 동기화되기 때문."""
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM draw_win_rank_sync_status WHERE draw_round = ? AND source = ?",
        (int(draw_round), source),
    ).fetchone()
    conn.close()
    return row is not None


def mark_win_rank_synced(draw_round: int, source: str) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT INTO draw_win_rank_sync_status (draw_round, source, synced_at)
        VALUES (?, ?, ?)
        ON CONFLICT(draw_round, source) DO UPDATE SET synced_at = excluded.synced_at
        """,
        (int(draw_round), source, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


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


def get_random_pool_combos(draw_round: int, limit: int = 3000) -> list[tuple[int, ...]]:
    """번개조합/안티조합이 "우선배정" 후보로 참고만 하는 읽기 전용 샘플 —
    allocate_lotto_combinations_random_sequential과 달리 어떤 것도
    소비(할당)하지 않는다. 회차당 조합이 1.2만개 안팎이라 매번 그중 일부만
    무작위로 가져와도 실질적으로 충분하다."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT num1, num2, num3, num4, num5, num6
        FROM lotto_combinations
        WHERE draw_round = ?
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (int(draw_round), int(limit)),
    ).fetchall()
    conn.close()
    return [tuple(int(x) for x in row) for row in rows]


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


def set_reference_ranks(
    draw_round: int, ranks: tuple[int, int, int, int, int]
) -> None:
    """1241회차부터 — 필터 통과 조합군 전체 기준 참고용 당첨가능 통계 저장
    (실제 판매 조합의 진짜 당첨 여부와는 무관, get_draw_extraction_stats의
    실제 win_rank 집계와 별개)."""
    from datetime import datetime

    r1, r2, r3, r4, r5 = (int(x) for x in ranks)
    conn = _connect()
    conn.execute(
        """
        INSERT INTO draw_reference_ranks
            (draw_round, ref_rank_1, ref_rank_2, ref_rank_3, ref_rank_4, ref_rank_5, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(draw_round) DO UPDATE SET
            ref_rank_1 = excluded.ref_rank_1,
            ref_rank_2 = excluded.ref_rank_2,
            ref_rank_3 = excluded.ref_rank_3,
            ref_rank_4 = excluded.ref_rank_4,
            ref_rank_5 = excluded.ref_rank_5,
            computed_at = excluded.computed_at
        """,
        (int(draw_round), r1, r2, r3, r4, r5, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_reference_ranks(draw_round: int) -> dict | None:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT ref_rank_1, ref_rank_2, ref_rank_3, ref_rank_4, ref_rank_5 "
        "FROM draw_reference_ranks WHERE draw_round = ?",
        (int(draw_round),),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "rank_1": int(row["ref_rank_1"]),
        "rank_2": int(row["ref_rank_2"]),
        "rank_3": int(row["ref_rank_3"]),
        "rank_4": int(row["ref_rank_4"]),
        "rank_5": int(row["ref_rank_5"]),
    }


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
    """회차별 추출 수량 및 1~5등 당첨 건수 (draw_round DESC).

    pattern_count는 그 회차 조합을 추출한 "그 순간"에 기록해둔 필터 규칙 수
    (draw_pattern_counts, record_draw_pattern_count 참고) — 이 기록이 생기기
    전에 추출된 옛 회차는 None(관리자 화면에서 "기록 없음"으로 표시)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            lc.draw_round,
            COUNT(*) AS total_count,
            SUM(CASE WHEN lc.win_rank = 1 THEN 1 ELSE 0 END) AS rank_1,
            SUM(CASE WHEN lc.win_rank = 2 THEN 1 ELSE 0 END) AS rank_2,
            SUM(CASE WHEN lc.win_rank = 3 THEN 1 ELSE 0 END) AS rank_3,
            SUM(CASE WHEN lc.win_rank = 4 THEN 1 ELSE 0 END) AS rank_4,
            SUM(CASE WHEN lc.win_rank = 5 THEN 1 ELSE 0 END) AS rank_5,
            MAX(dpc.pattern_count) AS pattern_count
        FROM lotto_combinations lc
        LEFT JOIN draw_pattern_counts dpc ON dpc.draw_round = lc.draw_round
        WHERE lc.draw_round >= ?
        GROUP BY lc.draw_round
        ORDER BY lc.draw_round DESC
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
            "pattern_count": int(row["pattern_count"]) if row["pattern_count"] is not None else None,
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
            "pattern_count": None,
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
    "record_draw_pattern_count",
    "get_pattern_count_for_draw",
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
    "is_win_rank_synced",
    "mark_win_rank_synced",
    "get_win_rank_counts_by_draw",
    "get_combination_count_by_draw",
    "get_draw_extraction_stats",
    "get_draw_purchase_conversion_stats",
    "get_mock_draw_extraction_stats",
    "ensure_marketing_pool_seeds",
    "import_marketing_pool_seed",
    "MARKETING_POOL_SEED_DRAWS",
]
