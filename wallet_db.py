"""회원 지갑 DB — OAuth 해시 식별자만 저장 (PII·결제정보 미보관)."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import db_turso
import products

DB_PATH = "lotto.db"
SIGNUP_BONUS = 500  # 5,000원 상당 (10원=1점 환산)
ADVANCED_PRODUCT = "advanced_filter_monthly"
# 2026-09-26: 구독 기간·포인트 가격의 기준점은 products.py다(여기서 숫자를 새로 쓰지 말 것).
FREE_SUB_DAYS = products.FREE_PROMO_DAYS
ADVANCED_MONTHLY_COST = products.SUBSCRIPTION_POINTS_COST[products.BASE_PLAN_MONTHLY]
ADVANCED_3MONTH_COST = products.SUBSCRIPTION_POINTS_COST[products.BASE_PLAN_QUARTERLY]
ADVANCED_3MONTH_DAYS = products.SUBSCRIPTION_BASE_PLAN_DAYS[products.BASE_PLAN_QUARTERLY]

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")


def oauth_hash(provider: str, provider_user_id: str) -> str:
    raw = f"{provider.strip().lower()}:{str(provider_user_id).strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _connect():
    return db_turso.connect()


def _batch_execute(conn, statements):
    """conn이 db_turso 래퍼면 batch_execute()로 원자적 배치 실행(2026-09-19,
    deduct_points/charge_points/refund_points의 잔액-원장 원자성 개선 참고).
    tests/test_wallet_db.py는 격리를 위해 _connect()를 순수 sqlite3.Connection
    으로 바꿔치기하는데, 거기엔 batch_execute()가 없다 — 그 경우 그냥 순서대로
    execute()만 호출한다. sqlite3는 같은 커넥션에서 commit() 전까지 이미 하나의
    트랜잭션이므로 순차 실행만으로도 동일하게 원자적이다(호출부가 뒤이어
    commit()을 부른다 — db_turso 쪽은 no-op, sqlite3 쪽은 실제로 커밋)."""
    if hasattr(conn, "batch_execute"):
        return conn.batch_execute(statements)
    return [conn.execute(sql, params) for sql, params in statements]


_WALLET_TABLES_READY = False


def init_wallet_tables() -> None:
    """CREATE TABLE/INDEX IF NOT EXISTS라 멱등이지만, 매 렌더마다 호출되면서 원격 DB
    왕복이 반복되던 걸 막기 위해(zero_phone_db.init_zero_phone_tables와 동일한 방식)
    최초 1회 이후로는 스킵한다."""
    global _WALLET_TABLES_READY
    if _WALLET_TABLES_READY:
        return
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            oauth_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_members_oauth ON members(oauth_hash);

        CREATE TABLE IF NOT EXISTS wallets (
            member_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            ref_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(ref_id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_member ON wallet_ledger(member_id, created_at);

        CREATE TABLE IF NOT EXISTS signup_grants (
            member_id INTEGER PRIMARY KEY,
            granted_at TEXT NOT NULL,
            amount INTEGER NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_free_promo INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sub_member_product ON subscriptions(member_id, product, expires_at);

        CREATE TABLE IF NOT EXISTS consent_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            notice_version TEXT NOT NULL,
            agreed_at TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS pg_charges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            pg_ref_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS auto_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            purchase_type TEXT NOT NULL,
            phone TEXT NOT NULL,
            sms_days TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            ledger_ref_id TEXT UNIQUE,
            sms_queue_id INTEGER,
            draw_round INTEGER,
            combo_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_auto_orders_member ON auto_orders(member_id, created_at);

        CREATE TABLE IF NOT EXISTS guest_member_links (
            guest_id TEXT PRIMARY KEY,
            member_id INTEGER NOT NULL,
            linked_at TEXT NOT NULL,
            last_seen_at TEXT,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        -- 2026-09-10: 번개조합은 번호가 브라우저(JS)에서 생성돼 서버가 실패를
        -- 즉시 알 수 없다. 차감은 "조합시작 확정" 시점에 하되(번호만 보고 무한
        -- 재생성하는 악용 방지), 번호가 저장내역에 저장되면(th_save) 정산 완료로
        -- 표시하고, 끝내 저장이 안 된 미정산 건은 일정 시간 후 자동 환불한다.
        -- settled: 0=미정산, 1=정산(저장완료), 2=환불됨
        CREATE TABLE IF NOT EXISTS thunder_pending_charges (
            ref_id TEXT PRIMARY KEY,
            member_id INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            game_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            settled INTEGER NOT NULL DEFAULT 0,
            settled_at TEXT,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_thunder_pending_member
            ON thunder_pending_charges(member_id, settled);

        -- 2026-09-19(Task #13, 토스페이먼츠 연동): 결제창을 열기 전에 서버가
        -- 먼저 주문(회원·금액)을 이 표에 심어두고, successUrl 콜백에서 클라
        -- 이언트가 들고 온 orderId/amount를 이 표의 값과 대조한다 — 클라이언트가
        -- 보낸 amount를 그대로 믿고 적립금을 주면(금액 위조) 실결제된 금액보다
        -- 더 많은 포인트를 받아갈 수 있어, 반드시 서버가 미리 기록해둔 값과
        -- 비교해야 한다(토스 공식 문서 권고사항). status: pending → confirmed
        -- (적립 완료) / failed(결제 실패·취소) / mismatch(위조 의심, 승인 거부).
        CREATE TABLE IF NOT EXISTS toss_pending_orders (
            order_id TEXT PRIMARY KEY,
            member_id INTEGER NOT NULL,
            won_amount INTEGER NOT NULL,
            points INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            confirmed_at TEXT,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_toss_pending_member
            ON toss_pending_orders(member_id, created_at);

        -- 2026-09-20(운영관리 "일간 활동 유저" 표): members.last_login_at은
        -- 로그인마다 덮어써져서 한 회원의 마지막 접속 요일 1개만 남는다 — 한
        -- 주에 여러 요일 접속한 회원은 그 전 요일 기록이 사라져 "요일별 활동
        -- 유저 수" 집계가 불가능했다. last_login_at은 그대로 두고(다른 로직이
        -- 이미 이 컬럼에 의존하므로 손대지 않음), 날짜별 방문 이력만 별도로
        -- 쌓는다. PRIMARY KEY(member_id, activity_date)라 하루 여러 번
        -- 로그인해도 INSERT OR IGNORE로 자동 중복 제거된다. 이 표는 오늘부터
        -- 쌓이기 시작하며 과거 데이터는 없다.
        CREATE TABLE IF NOT EXISTS member_daily_activity (
            member_id INTEGER NOT NULL,
            activity_date TEXT NOT NULL,
            PRIMARY KEY (member_id, activity_date),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_member_daily_activity_date
            ON member_daily_activity(activity_date);
        """
    )
    # 2026-09-06: 기존 DB 호환 ALTER — marketing_db._migrate_lotto_combinations와
    # 동일한 패턴(PRAGMA table_info로 이미 있는지 확인 후에만 추가).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(guest_member_links)")}
    if "last_seen_at" not in cols:
        conn.execute("ALTER TABLE guest_member_links ADD COLUMN last_seen_at TEXT NULL")
    # 2026-09-19: guest_id 링크공유 계정탈취 취약점 대응(1단계, UA 바인딩) —
    # 이 값이 채워진 이후 연결된 세션만 restore_member_from_guest()가 UA를
    # 대조해 자동로그인시킨다. 기존(2026-09-19 이전) 연결 행은 이 컬럼이
    # NULL이라 자동으로 "대조 불가 → 재인증 필요" 취급되며, 이는 의도된
    # 동작이다(하드 컷오버 — 테스터 16명 규모라 1회 재인증 비용이 낮음).
    if "ua_hash" not in cols:
        conn.execute("ALTER TABLE guest_member_links ADD COLUMN ua_hash TEXT NULL")
    # 2026-09-19(Task #13): 토스 결제위젯의 customerKey(카드 저장 등에 쓰이는
    # 고객 식별자) — 회원의 내부 DB id를 그대로 밖으로 노출하지 않기 위해
    # 별도의 무작위 키를 한 번만 발급해 저장해둔다.
    wallet_cols = {row[1] for row in conn.execute("PRAGMA table_info(wallets)")}
    if "toss_customer_key" not in wallet_cols:
        conn.execute("ALTER TABLE wallets ADD COLUMN toss_customer_key TEXT NULL")
    conn.commit()
    conn.close()
    _WALLET_TABLES_READY = True


def link_guest_to_member(guest_id: str, member_id: int, ua_hash: str | None = None) -> None:
    """로그인 성공 시 기기 식별자(guest_id, 네이티브 앱이면 재실행해도 유지됨)를
    회원과 연결해둔다 — 다음에 세션이 끊겼다가 재연결될 때(백그라운드 전환, 네트워크
    끊김 등) 이 연결로 자동 재로그인시켜서, 매번 간편인증 화면이 다시 뜨는 걸 막는다.

    2026-09-19: ua_hash(로그인 시점의 User-Agent 해시)를 함께 저장 — guest_id가
    담긴 링크가 공유돼도, 다른 기기(=다른 UA)에서는 restore_member_from_guest()가
    이 값을 대조해 자동로그인을 막는다(guest_id 링크공유 계정탈취 대응 1단계)."""
    now = _now_iso()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO guest_member_links (guest_id, member_id, linked_at, last_seen_at, ua_hash) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guest_id) DO UPDATE SET
            member_id = excluded.member_id,
            linked_at = excluded.linked_at,
            last_seen_at = excluded.last_seen_at,
            ua_hash = excluded.ua_hash
        """,
        (str(guest_id), int(member_id), now, now, ua_hash),
    )
    conn.commit()
    conn.close()


def get_member_for_guest(guest_id: str) -> int | None:
    conn = _connect()
    row = conn.execute(
        "SELECT member_id FROM guest_member_links WHERE guest_id = ?", (str(guest_id),)
    ).fetchone()
    conn.close()
    return int(row["member_id"]) if row else None


def get_member_and_ua_for_guest(guest_id: str) -> tuple[int | None, str | None]:
    """(member_id, 로그인 시점에 저장된 ua_hash) — restore_member_from_guest()의
    UA 대조용. 2026-09-19 이전에 연결된 행은 ua_hash가 NULL이다."""
    conn = _connect()
    row = conn.execute(
        "SELECT member_id, ua_hash FROM guest_member_links WHERE guest_id = ?", (str(guest_id),)
    ).fetchone()
    conn.close()
    if not row:
        return None, None
    return int(row["member_id"]), (row["ua_hash"] if row["ua_hash"] else None)


def get_guest_ids_for_member(member_id: int) -> list[str]:
    """이 회원에 연결된 적 있는 모든 guest_id(최신 연결순).

    2026-09-10: guest_id가 Streamlit 웹소켓 재연결 등으로 세션마다 새로
    발급되는 문제가 있어서, 구매/저장 내역이 여러 guest_id에 흩어져 저장된다.
    로그인 상태면 이 회원에 묶인 guest_id를 전부 모아 내역을 합쳐 보여줘야
    "방금 샀는데 구매내역이 안 보인다"는 신고를 막을 수 있다."""
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT guest_id FROM guest_member_links WHERE member_id = ? ORDER BY linked_at DESC",
            (int(member_id),),
        ).fetchall()
        conn.close()
        return [str(r["guest_id"]) for r in rows]
    except Exception:
        return []


def _parse_kst(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=KST)


def guest_idle_seconds(guest_id: str) -> float | None:
    """이 guest_id가 마지막으로 서버에 요청을 보낸 뒤 몇 초가 지났는지.
    2026-09-06: 클라이언트(앱) 쪽에서 "백그라운드로 간 지 3분 지났는지"를
    직접 감지하려던 시도(메모리 기록 → AsyncStorage 기록 → 하트비트 →
    웹뷰 캐시버스팅)가 실기기에서 네 번 연속 실패했다 — 뒤로가기 종료 시
    AppState 이벤트 신뢰성, 안드로이드 프로세스 종료 타이밍, 웹뷰 캐싱 등
    클라이언트 쪽 변수가 너무 많았기 때문으로 보인다.
    앱이 백그라운드에 있는 동안은 이 앱(웹뷰) 쪽에서 서버로 요청 자체가
    전혀 안 간다는 사실은 변하지 않으므로, 클라이언트가 스스로 경과 시간을
    재려 하지 말고 "서버가 마지막으로 이 기기의 요청을 받은 시각"만
    기록해두면 똑같은 정보를 훨씬 안정적으로 얻을 수 있다 — 특정 이벤트가
    안정적으로 오는지, 캐시가 새 요청을 실제로 통과시키는지 같은 클라이언트
    쪽 불확실성에 전혀 의존하지 않는다."""
    conn = _connect()
    row = conn.execute(
        "SELECT last_seen_at FROM guest_member_links WHERE guest_id = ?", (str(guest_id),)
    ).fetchone()
    conn.close()
    if not row or not row["last_seen_at"]:
        return None
    try:
        last_seen = _parse_kst(row["last_seen_at"])
    except ValueError:
        return None
    return (datetime.now(KST) - last_seen).total_seconds()


def touch_guest_last_seen(guest_id: str) -> None:
    """이 guest_id가 방금 서버에 요청을 보냈다는 걸 기록 — 정상적으로 링크가
    있는 guest에 대해서만 의미가 있으므로, 링크가 없으면 조용히 넘어간다."""
    conn = _connect()
    conn.execute(
        "UPDATE guest_member_links SET last_seen_at = ? WHERE guest_id = ?",
        (_now_iso(), str(guest_id)),
    )
    conn.commit()
    conn.close()


def unlink_guest_from_member(guest_id: str) -> None:
    """로그아웃 시 호출 — 이걸 안 하면 session_state만 비워질 뿐 guest_member_links는
    그대로 남아있어서, 다음 페이지 이동 때 restore_member_from_guest()가 이 연결을
    보고 조용히 다시 로그인시켜버린다(실사용 흐름 점검 중 발견된 버그)."""
    conn = _connect()
    conn.execute("DELETE FROM guest_member_links WHERE guest_id = ?", (str(guest_id),))
    conn.commit()
    conn.close()


def get_or_create_member(provider: str, provider_user_id: str) -> tuple[int, bool]:
    """returns (member_id, is_new)."""
    ohash = oauth_hash(provider, provider_user_id)
    conn = _connect()
    now = _now_iso()
    row = conn.execute(
        "SELECT id FROM members WHERE oauth_hash = ?", (ohash,)
    ).fetchone()
    if row:
        member_id = int(row["id"])
        conn.execute(
            "UPDATE members SET last_login_at = ? WHERE id = ?", (now, member_id)
        )
        _record_daily_activity(conn, member_id)
        conn.commit()
        conn.close()
        return member_id, False

    cur = conn.execute(
        "INSERT INTO members (provider, oauth_hash, created_at, last_login_at) VALUES (?, ?, ?, ?)",
        (provider.lower(), ohash, now, now),
    )
    member_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO wallets (member_id, balance) VALUES (?, 0)", (member_id,)
    )
    _record_daily_activity(conn, member_id)
    conn.commit()
    conn.close()
    return member_id, True


def _record_daily_activity(conn, member_id: int) -> None:
    """오늘(KST) 날짜로 방문 이력 1행 기록 — member_daily_activity의
    PRIMARY KEY(member_id, activity_date) 덕분에 하루 여러 번 로그인해도
    자동으로 1건만 남는다(INSERT OR IGNORE)."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT OR IGNORE INTO member_daily_activity (member_id, activity_date) VALUES (?, ?)",
        (member_id, today),
    )


def get_total_installed_members() -> int:
    """누적 가입자 수(=설치 인원) — admin_dashboard.py 홈 화면의 기존 통계와
    동일한 정의(SELECT COUNT(*) FROM members)."""
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) AS c FROM members").fetchone()
    conn.close()
    return int(row["c"]) if row else 0


def get_weekly_active_users(reference_date: datetime | None = None) -> list[dict]:
    """이번 주(월~일, KST) 요일별 순수 활동 유저 수. member_daily_activity가
    2026-09-20부터 쌓이기 시작하므로 그 이전 날짜는 항상 0으로 나온다 —
    과거 데이터를 소급 복원할 방법은 없다(이전엔 last_login_at 1개만
    있었고 그마저 로그인마다 덮어써졌기 때문)."""
    ref = (reference_date or datetime.now(KST)).date()
    monday = ref - timedelta(days=ref.weekday())
    conn = _connect()
    rows = conn.execute(
        """
        SELECT activity_date, COUNT(DISTINCT member_id) AS cnt
        FROM member_daily_activity
        WHERE activity_date >= ? AND activity_date <= ?
        GROUP BY activity_date
        """,
        (monday.isoformat(), (monday + timedelta(days=6)).isoformat()),
    ).fetchall()
    conn.close()
    counts = {r["activity_date"]: int(r["cnt"]) for r in rows}
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    result = []
    for i, name in enumerate(weekday_names):
        d = monday + timedelta(days=i)
        result.append(
            {
                "요일": name,
                "날짜": d.isoformat(),
                "활동유저": counts.get(d.isoformat(), 0),
            }
        )
    return result


def grant_signup_bonus(member_id: int, amount: int = SIGNUP_BONUS) -> bool:
    conn = _connect()
    exists = conn.execute(
        "SELECT 1 FROM signup_grants WHERE member_id = ?", (member_id,)
    ).fetchone()
    if exists:
        conn.close()
        return False

    row = conn.execute(
        "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"wallet not found: {member_id}")

    new_balance = int(row["balance"]) + amount
    now = _now_iso()
    ref = f"signup_bonus:{member_id}"
    conn.execute(
        "INSERT INTO signup_grants (member_id, granted_at, amount) VALUES (?, ?, ?)",
        (member_id, now, amount),
    )
    conn.execute(
        "UPDATE wallets SET balance = ? WHERE member_id = ?", (new_balance, member_id)
    )
    conn.execute(
        """
        INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
        VALUES (?, ?, ?, 'signup_bonus', ?, ?)
        """,
        (member_id, amount, new_balance, ref, now),
    )
    conn.commit()
    conn.close()
    return True


def get_balance(member_id: int) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
    ).fetchone()
    conn.close()
    return int(row["balance"]) if row else 0


def deduct_points(member_id: int, amount: int, reason: str, ref_id: str) -> bool:
    """2026-09-08 수정: 예전엔 "잔액 조회 → 파이썬에서 뺄셈 → UPDATE"로 나뉘어
    있어서, 같은 회원이 동시에 두 번 구매(다른 탭·다른 기기 등)하면 둘 다
    같은 잔액을 읽어 통과한 뒤 마지막에 쓴 UPDATE만 반영되는 레이스
    컨디션이 있었다 — ledger엔 두 건 다 기록되는데 실제 balance는 한 번만
    차감돼, 사실상 한쪽 구매가 무료가 되는 결함(실측하진 않았지만 코드
    구조상 명백한 버그). UPDATE 자체에 조건을 걸어(balance >= amount) DB가
    원자적으로 처리하게 바꿔 이 레이스를 근본적으로 없앤다.

    2026-09-19 수정: 그 뒤에도 "balance UPDATE는 성공했는데 뒤이은 ledger
    INSERT가 별도 왕복이라 타임아웃 등으로 빠지면" balance만 바뀌고 ledger엔
    기록이 안 남는 틈이 있었다(db_turso.py 상단 2026-09-03 사고 주석 참고 —
    네트워크 타임아웃은 응답만 못 받을 뿐 서버 쪽 처리 자체는 이미 끝났을 수
    있음). db_turso.batch_execute()로 두 statement를 한 원자적 트랜잭션에
    묶는다 — ledger INSERT를 SELECT ... WHERE balance >= ?로 먼저 걸어
    "그 순간 잔액이 충분했는지"를 확정하고(0행이면 잔액부족·둘 다 무효),
    UPDATE는 그 ledger 행이 실제로 삽입됐을 때만(EXISTS) balance를 깎는다 —
    같은 트랜잭션 안이라 두 statement 사이에 다른 요청이 끼어들 수 없다."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    conn = _connect()
    try:
        dup = conn.execute(
            "SELECT 1 FROM wallet_ledger WHERE ref_id = ?", (ref_id,)
        ).fetchone()
        if dup:
            conn.close()
            return True

        now = _now_iso()
        results = _batch_execute(
            conn,
            [
                (
                    """
                    INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
                    SELECT ?, ?, balance - ?, ?, ?, ?
                    FROM wallets WHERE member_id = ? AND balance >= ?
                    """,
                    (member_id, -amount, amount, reason, ref_id, now, member_id, amount),
                ),
                (
                    """
                    UPDATE wallets SET balance = balance - ?
                    WHERE member_id = ? AND EXISTS (
                        SELECT 1 FROM wallet_ledger WHERE ref_id = ?
                    )
                    """,
                    (amount, member_id, ref_id),
                ),
            ],
        )
        ledger_inserted = results[0].rowcount if results else 0
        conn.commit()
        conn.close()
        if not ledger_inserted:
            # member_id가 없거나(지갑 미생성) 잔액 부족 — 트랜잭션 전체가
            # 아무 것도 바꾸지 않고 끝났다(위 batch_execute 설계 참고).
            return False
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return True


def record_consent(member_id: int, notice_version: str) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT INTO consent_log (member_id, notice_version, agreed_at)
        VALUES (?, ?, ?)
        """,
        (member_id, notice_version, _now_iso()),
    )
    conn.commit()
    conn.close()


def get_subscription_expiry(member_id: int, product: str = ADVANCED_PRODUCT) -> str | None:
    """현재 유효한 구독의 만료일시(ISO 문자열)를 반환. 없으면 None."""
    conn = _connect()
    now = _now_iso()
    row = conn.execute(
        """
        SELECT expires_at FROM subscriptions
        WHERE member_id = ? AND product = ? AND expires_at > ?
        ORDER BY expires_at DESC LIMIT 1
        """,
        (member_id, product, now),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def has_active_subscription(member_id: int, product: str = ADVANCED_PRODUCT) -> bool:
    conn = _connect()
    now = _now_iso()
    row = conn.execute(
        """
        SELECT 1 FROM subscriptions
        WHERE member_id = ? AND product = ? AND expires_at > ?
        ORDER BY expires_at DESC LIMIT 1
        """,
        (member_id, product, now),
    ).fetchone()
    conn.close()
    return row is not None


def eligible_free_advanced_sub(member_id: int) -> bool:
    conn = _connect()
    row = conn.execute(
        """
        SELECT 1 FROM subscriptions
        WHERE member_id = ? AND product = ? AND is_free_promo = 1
        LIMIT 1
        """,
        (member_id, ADVANCED_PRODUCT),
    ).fetchone()
    conn.close()
    return row is None


def activate_free_advanced_sub(member_id: int) -> bool:
    if not eligible_free_advanced_sub(member_id):
        return False
    conn = _connect()
    now = datetime.now(KST)
    starts = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    expires = (now + timedelta(days=FREE_SUB_DAYS)).strftime("%Y-%m-%d %H:%M:%S.%f")
    conn.execute(
        """
        INSERT INTO subscriptions (member_id, product, starts_at, expires_at, is_free_promo)
        VALUES (?, ?, ?, ?, 1)
        """,
        (member_id, ADVANCED_PRODUCT, starts, expires),
    )
    conn.commit()
    conn.close()
    return True


def activate_paid_advanced_sub(member_id: int, days: int) -> bool:
    """유료 구독 등록 — 이미 유효기간이 남아있으면 그 만료일부터 이어서 연장한다."""
    conn = _connect()
    now = datetime.now(KST)
    now_iso = _now_iso()
    row = conn.execute(
        """
        SELECT expires_at FROM subscriptions
        WHERE member_id = ? AND product = ? AND expires_at > ?
        ORDER BY expires_at DESC LIMIT 1
        """,
        (member_id, ADVANCED_PRODUCT, now_iso),
    ).fetchone()
    base = now
    if row and row[0]:
        try:
            current_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=KST)
            if current_expiry > base:
                base = current_expiry
        except ValueError:
            pass
    starts = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    expires = (base + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S.%f")
    conn.execute(
        """
        INSERT INTO subscriptions (member_id, product, starts_at, expires_at, is_free_promo)
        VALUES (?, ?, ?, ?, 0)
        """,
        (member_id, ADVANCED_PRODUCT, starts, expires),
    )
    conn.commit()
    conn.close()
    return True


def activate_paid_advanced_sub_once(member_id: int, days: int, ref_id: str) -> bool:
    """유료 구독을 ref_id당 정확히 한 번만 활성화한다(멱등) — Google Play
    인앱결제 구독 검증(google_play_pg._verify_and_credit_subscription) 전용.

    왜 activate_paid_advanced_sub()를 그대로 쓰면 안 되는가: 그 함수는 호출될
    때마다 "남은 만료일부터 days를 이어서 연장"만 한다(멱등성 없음). 인앱결제는
    같은 purchaseToken이 반복 도착할 수 있고(검증 실패 후 클라이언트 재전송,
    사용자가 결제 직후 화면을 새로고침·재접속, 네트워크 재시도), 그대로 쓰면
    한 번 결제로 구독이 30일씩 두 번 연장된다 — 그래서 "이 토큰으로 이미
    지급했는가"를 DB에 남기고 한 번만 반영하는 별도 함수가 필요하다.

    멱등 마커는 pg_charges.pg_ref_id(UNIQUE)를 쓴다 — 토스·Mock 결제가 이미 쓰는
    컬럼이라 스키마 변경이 필요 없다. amount는 0으로 기록한다(돈은 구글이 받았고
    이 서버는 PG 충전을 한 게 아니라 "지급 완료" 표시만 남긴다). 기존 소비처는
    전부 pg_ref_id 접두사로 걸러 읽으므로(check_real_toss_charges.py 'pg:toss:%',
    count_recent_mock_charges 'pg:mock:%') 이 행은 그들 집계에 섞이지 않는다.

    반환: True = 이번에 지급했거나 이 ref_id로 이미 지급됨(둘 다 성공 취급),
          False = 지급되지 않음(회원 없음 등 — 마커도 남지 않아 재시도 가능).

    2026-09-19(charge_points/deduct_points)와 같은 이유로 원자성이 필요하다:
    마커 INSERT와 구독 INSERT를 _batch_execute 한 트랜잭션에 묶고, 구독 INSERT는
    이번 트랜잭션에서 마커가 실제로 생겼을 때만(EXISTS) 실행한다. 같은 토큰이
    동시에 두 번 들어오면 두 번째는 마커 UNIQUE에 걸려 IntegrityError로 배치
    전체가 되돌려지므로(그래서 except에서 True), 구독이 두 번 연장되는 상태는
    만들어지지 않는다."""
    if days <= 0:
        raise ValueError("days must be positive")
    ref_id = str(ref_id).strip()
    if not ref_id:
        raise ValueError("ref_id must be non-empty")

    conn = _connect()
    try:
        dup = conn.execute(
            "SELECT 1 FROM pg_charges WHERE pg_ref_id = ?", (ref_id,)
        ).fetchone()
        if dup:
            conn.close()
            return True

        now = datetime.now(KST)
        now_iso = now.strftime("%Y-%m-%d %H:%M:%S.%f")
        row = conn.execute(
            """
            SELECT expires_at FROM subscriptions
            WHERE member_id = ? AND product = ? AND expires_at > ?
            ORDER BY expires_at DESC LIMIT 1
            """,
            (member_id, ADVANCED_PRODUCT, now_iso),
        ).fetchone()
        base = now
        if row and row[0]:
            try:
                current_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=KST)
                if current_expiry > base:
                    base = current_expiry
            except ValueError:
                pass
        expires = (base + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S.%f")

        results = _batch_execute(
            conn,
            [
                (
                    """
                    INSERT INTO pg_charges (member_id, amount, pg_ref_id, status, created_at)
                    SELECT ?, 0, ?, 'completed', ?
                    FROM members WHERE id = ?
                    """,
                    (member_id, ref_id, now_iso, member_id),
                ),
                (
                    """
                    INSERT INTO subscriptions (member_id, product, starts_at, expires_at, is_free_promo)
                    SELECT ?, ?, ?, ?, 0
                    WHERE EXISTS (SELECT 1 FROM pg_charges WHERE pg_ref_id = ?)
                    """,
                    (member_id, ADVANCED_PRODUCT, now_iso, expires, ref_id),
                ),
            ],
        )
        marker_inserted = results[0].rowcount if results else 0
        conn.commit()
        conn.close()
        if not marker_inserted:
            # 회원 행이 없음 — 마커도 구독도 안 생겼다(지급 실패).
            return False
        return True
    except sqlite3.IntegrityError:
        # 같은 ref_id가 동시·재차 들어옴 — 배치 전체가 되돌려졌으므로 이번
        # 호출은 "이미 지급됨"으로 성공 처리한다(구독은 한 번만 연장됨).
        conn.close()
        return True


THUNDER_COST_PER_GAME = 10
HEDGE_COST_PER_COMBO = 10
# 2026-09-08 정정: 100P/개는 착오였음 — 자동구매도 번개조합과 동일하게
# 10P/개(5개=50P)가 맞는 단가. legal_notices.py의 PRICING["auto_per_unit"]도
# 같이 맞출 것 — 이 둘이 어긋나면 화면에 안내되는 금액과 실제 차감액이
# 달라진다.
AUTO_COST_PER_UNIT = 10
TAROT_EXTRA_DRAW_COST = 50  # 하루 1회 무료 이후 추가 뽑기 1회당


def calc_thunder_cost(game_count: int) -> int:
    return THUNDER_COST_PER_GAME * max(1, int(game_count))


def calc_hedge_cost(combo_count: int) -> int:
    """안티조합/액땜조합 — 생성 조합 수에 비례."""
    return HEDGE_COST_PER_COMBO * max(1, int(combo_count))


def calc_auto_cost(quantity: int) -> int:
    return AUTO_COST_PER_UNIT * max(1, int(quantity))


def _toss_secret(name: str) -> str:
    """TOSS_CLIENT_KEY/TOSS_SECRET_KEY를 env → st.secrets 순으로 읽는다
    (db_turso._shared_client()의 TURSO_DATABASE_URL/TURSO_AUTH_TOKEN 읽기 방식과
    동일한 패턴). 2026-09-19(Task #13): 토스 테스트 키는 가맹점(계정)마다
    개별 발급되고 공용 테스트 키가 없다(공식 문서 확인) — 코드에 값을
    하드코딩하지 않고 항상 이 경로로만 읽는다. 계약 확정 후 라이브 키로
    교체할 때도 이 두 값만 바꾸면 된다(코드 변경 불필요)."""
    import os

    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        import streamlit as st

        val = str(st.secrets.get(name, "") or "").strip()
    except Exception:
        val = ""
    return val


def toss_client_key() -> str:
    return _toss_secret("TOSS_CLIENT_KEY")


def toss_secret_key() -> str:
    return _toss_secret("TOSS_SECRET_KEY")


def pg_configured() -> bool:
    """PG(토스페이먼츠) 연동 여부 — 클라이언트키·시크릿키가 둘 다 있어야 True.
    2026-09-19(Task #13) 이전엔 PG_MERCHANT_ID(더미 플레이스홀더) 존재 여부만
    봤는데, 실제 토스 연동을 붙이면서 진짜 연동 상태를 반영하도록 바꿨다 —
    이 값이 True가 되는 순간 wallet_ui.py의 Mock 결제 버튼이 자동으로 숨고
    실제 결제창이 뜬다(별도 스위치 불필요)."""
    return bool(toss_client_key()) and bool(toss_secret_key())


def mock_charge_enabled() -> bool:
    """PG 미연동 상태에서 "Mock 결제(테스트)" 버튼을 노출할지 — 명시적
    opt-in(env MOCK_CHARGE_ENABLED=true/1/yes)일 때만 True(fail-closed,
    2026-09-20 구름님 지시). 2026-09-05~09-08엔 "소수 테스터만 접근 가능한
    단계"라는 전제로 PG 미연동이면 로그인만 해도 이 버튼이 무조건 떠서,
    회원당 하루 최대 3,000P(=30,000원 상당, MOCK_CHARGE_MAX_PER_WINDOW 기준)
    까지 제한 없이 충전할 수 있었다(wallet_ui.py 참고) — 심사용 PG 키를
    나중에 제거하는 시점에 실키 투입 전 잠깐이라도 공백이 생기면 이 분기가
    그대로 다시 열린다. 이 값을 명시적으로 켜지 않으면(Streamlit Cloud
    secrets에 안 넣으면) 실사용자에게는 버튼 자체가 안 보이고 대신 기존
    "결제 연동 준비 중입니다" 안내만 뜬다. 테스터 기간엔 이 값 하나만
    env/secrets에 넣으면 기존과 동일하게 쓸 수 있다."""
    import os

    return os.environ.get("MOCK_CHARGE_ENABLED", "").strip().lower() in ("1", "true", "yes")


# 1만원 충전 시 1,000점 지급 — 10원당 1점.
# 2026-09-26: 환산 기준과 금액 후보의 기준점은 products.py다(여기서 다시 정의하지 않는다).
WON_PER_POINT = products.WON_PER_POINT
CHARGE_WON_AMOUNTS = products.CHARGE_WON_AMOUNTS


def won_to_points(won: int) -> int:
    return products.won_to_points(won)


# 2026-09-19(Task #13): 토스 결제창을 열기 전 서버가 주문을 선기록 → 콜백에서
# 대조(금액 위조 방지) → confirm API 승인 → 적립금 지급까지의 흐름.
def create_toss_pending_order(member_id: int, won_amount: int) -> str:
    """결제창을 열기 직전에 호출 — orderId는 서버가 생성해 클라이언트(JS)로
    넘긴다(6~64자, 영숫자+-_ 제약 충족). 이렇게 서버가 먼저 (member_id,
    금액)을 기록해둬야, 나중에 successUrl 콜백에서 클라이언트가 들고 온
    amount가 이 값과 다르면(위조 시도) 즉시 걸러낼 수 있다."""
    order_id = f"lotto{int(member_id)}{uuid.uuid4().hex[:20]}"
    points = won_to_points(won_amount)
    now = _now_iso()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO toss_pending_orders (order_id, member_id, won_amount, points, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
        """,
        (order_id, int(member_id), int(won_amount), points, now),
    )
    conn.commit()
    conn.close()
    return order_id


def get_toss_pending_order(order_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        """
        SELECT order_id, member_id, won_amount, points, status
        FROM toss_pending_orders WHERE order_id = ?
        """,
        (str(order_id),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "order_id": row["order_id"],
        "member_id": int(row["member_id"]),
        "won_amount": int(row["won_amount"]),
        "points": int(row["points"]),
        "status": row["status"],
    }


def mark_toss_order_status(order_id: str, status: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE toss_pending_orders SET status = ?, confirmed_at = ? WHERE order_id = ?",
        (status, _now_iso(), str(order_id)),
    )
    conn.commit()
    conn.close()


# 2026-09-20: 결제 분쟁 처리(관리자 대시보드) — 웹뷰 환경에서 결제 성공 직후
# successUrl 콜백 없이 화면이 닫혀버리는 경우(실제 토스 개발자 커뮤니티에
# 보고된 사례) 등으로, toss_pending_orders가 'pending'에서 멈춘 채 영원히
# 안 넘어가는 주문이 생길 수 있다. 관리자가 고객 문의 전에 먼저 찾아내거나
# (list_stuck_toss_orders), 문의받은 회원 기준으로 내역을 찾을 때
# (find_toss_orders_by_member) 쓴다. 둘 다 읽기 전용 — 잔액에 전혀 영향 없음.
def list_stuck_toss_orders(stale_minutes: int = 10) -> list:
    conn = _connect()
    cutoff = (datetime.now(KST) - timedelta(minutes=stale_minutes)).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )
    rows = conn.execute(
        """
        SELECT order_id, member_id, won_amount, points, status, created_at
        FROM toss_pending_orders
        WHERE status = 'pending' AND created_at < ?
        ORDER BY created_at
        """,
        (cutoff,),
    ).fetchall()
    conn.close()
    return rows


def find_toss_orders_by_member(member_id: int) -> list:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT order_id, member_id, won_amount, points, status, created_at, confirmed_at
        FROM toss_pending_orders
        WHERE member_id = ?
        ORDER BY created_at DESC
        """,
        (int(member_id),),
    ).fetchall()
    conn.close()
    return rows


def get_or_create_toss_customer_key(member_id: int) -> str:
    """토스 결제위젯의 customerKey — 이미 있으면 재사용, 없으면 1회 발급해
    wallets.toss_customer_key에 저장(회원 내부 DB id를 그대로 밖에 노출하지
    않기 위한 별도 식별자)."""
    conn = _connect()
    row = conn.execute(
        "SELECT toss_customer_key FROM wallets WHERE member_id = ?", (int(member_id),)
    ).fetchone()
    existing = row["toss_customer_key"] if row else None
    if existing:
        conn.close()
        return existing
    new_key = uuid.uuid4().hex
    conn.execute(
        "UPDATE wallets SET toss_customer_key = ? WHERE member_id = ?",
        (new_key, int(member_id)),
    )
    conn.commit()
    conn.close()
    return new_key


# 2026-09-19: Mock 결제(테스트용 무료 충전) 무제한 클릭 악용 대응 — ref_id가
# pg:mock:{member_id}:{uuid} 형태로 매번 랜덤이라 wallet_ledger의 ref_id UNIQUE
# 멱등성이 이 버튼에는 전혀 작동하지 않는다(클릭할 때마다 새 ref_id라 매번
# 통과됨). session_state 등 세션별 카운터는 새 브라우저 세션(새 탭·재접속)마다
# 리셋돼 우회 가능하므로 안 되고, member_id 기준으로 DB(pg_charges)에 남는
# 기록을 직접 세야 한다. PG 연동 완료(pg_configured()=True) 후에는 이 버튼 자체가
# 안 보이므로 이 제한도 자동으로 무의미해진다(별도 원복 불필요).
MOCK_CHARGE_MAX_PER_WINDOW = 3
MOCK_CHARGE_WINDOW_HOURS = 24


def count_recent_mock_charges(member_id: int, hours: int = MOCK_CHARGE_WINDOW_HOURS) -> int:
    conn = _connect()
    cutoff = (datetime.now(KST) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S.%f")
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM pg_charges
        WHERE member_id = ? AND pg_ref_id LIKE 'pg:mock:%' AND created_at >= ?
        """,
        (int(member_id), cutoff),
    ).fetchone()
    conn.close()
    return int(row["c"]) if row else 0


def charge_points(member_id: int, amount: int, pg_ref_id: str) -> bool:
    """PG 충전 — 카드정보 미저장, ledger ref_id로 멱등.

    2026-09-08 수정: deduct_points와 같은 이유(동시 충전 시 잔액 조회→가산이
    나뉘어 있으면 레이스로 한쪽 충전이 유실될 수 있음)로 원자적 UPDATE로
    교체.

    2026-09-19 수정: UPDATE·pg_charges INSERT·wallet_ledger INSERT 3개가
    각각 별도 왕복이라, 중간에 타임아웃 등으로 끊기면 잔액만 늘고 두 기록
    중 일부가 빠지는 틈이 있었다(deduct_points와 동일한 문제). 세 statement를
    db_turso.batch_execute()로 한 트랜잭션에 묶는다 — ledger INSERT를 가장
    먼저 두고(ref_id UNIQUE로 중복충전 방지는 그대로 유지), UPDATE와
    pg_charges INSERT는 둘 다 그 ledger 행이 실제로 생겼을 때만(EXISTS/SELECT)
    실행되게 해서 셋 다 되거나 셋 다 안 되게 만든다."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    conn = _connect()
    try:
        dup = conn.execute(
            "SELECT 1 FROM wallet_ledger WHERE ref_id = ?", (pg_ref_id,)
        ).fetchone()
        if dup:
            conn.close()
            return True

        now = _now_iso()
        results = _batch_execute(
            conn,
            [
                (
                    """
                    INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
                    SELECT ?, ?, balance + ?, 'pg_charge', ?, ?
                    FROM wallets WHERE member_id = ?
                    """,
                    (member_id, amount, amount, pg_ref_id, now, member_id),
                ),
                (
                    """
                    UPDATE wallets SET balance = balance + ?
                    WHERE member_id = ? AND EXISTS (
                        SELECT 1 FROM wallet_ledger WHERE ref_id = ?
                    )
                    """,
                    (amount, member_id, pg_ref_id),
                ),
                (
                    """
                    INSERT INTO pg_charges (member_id, amount, pg_ref_id, status, created_at)
                    SELECT ?, ?, ?, 'completed', ?
                    FROM wallet_ledger WHERE ref_id = ?
                    """,
                    (member_id, amount, pg_ref_id, now, pg_ref_id),
                ),
            ],
        )
        ledger_inserted = results[0].rowcount if results else 0
        conn.commit()
        conn.close()
        if not ledger_inserted:
            # member_id에 해당하는 지갑이 없음 — 셋 다 반영되지 않았다.
            return False
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return True


def refund_points(member_id: int, amount: int, reason: str, ref_id: str) -> bool:
    """차감(deduct_points) 후 상품 지급(조합 저장·구독 활성화 등)이 실패했을 때
    되돌리는 환불. charge_points와 달리 pg_charges에는 기록하지 않고(PG 충전이
    아니므로) ledger에만 +delta로 남긴다. ref_id로 멱등 — 같은 실패를 두 번
    환불하지 않는다.

    2026-09-10(사용자 지시): "조합 실패했는데 적립금은 소진돼 있으면 분쟁위험
    큼" — deduct 성공 후 후속 처리가 예외로 끊기는 좁은 구간(자동구매의
    complete_auto_order, 고급필터 구독 활성화)을 환불로 메우기 위해 추가.

    2026-09-19 수정: charge_points/deduct_points와 동일한 이유로 UPDATE와
    ledger INSERT를 db_turso.batch_execute()로 한 트랜잭션에 묶는다."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    conn = _connect()
    try:
        dup = conn.execute(
            "SELECT 1 FROM wallet_ledger WHERE ref_id = ?", (ref_id,)
        ).fetchone()
        if dup:
            conn.close()
            return True

        now = _now_iso()
        results = _batch_execute(
            conn,
            [
                (
                    """
                    INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
                    SELECT ?, ?, balance + ?, ?, ?, ?
                    FROM wallets WHERE member_id = ?
                    """,
                    (member_id, amount, amount, reason, ref_id, now, member_id),
                ),
                (
                    """
                    UPDATE wallets SET balance = balance + ?
                    WHERE member_id = ? AND EXISTS (
                        SELECT 1 FROM wallet_ledger WHERE ref_id = ?
                    )
                    """,
                    (amount, member_id, ref_id),
                ),
            ],
        )
        ledger_inserted = results[0].rowcount if results else 0
        conn.commit()
        conn.close()
        if not ledger_inserted:
            return False
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return True


# ── 번개조합 미정산 차감(조합시작 시 차감 → 저장되면 정산, 안 되면 자동 환불) ──

THUNDER_PENDING_STALE_MINUTES = 10


def record_thunder_pending(member_id: int, ref_id: str, cost: int, game_count: int) -> None:
    """번개조합 조합시작 확정 시, 차감(deduct_points)에 성공한 직후 호출 —
    '아직 번호가 저장되지 않은 차감'으로 기록해 둔다. ref_id는 차감 때 쓴
    ledger ref_id와 같은 값이라 PRIMARY KEY 충돌이 곧 멱등 처리(같은 확정을
    두 번 기록하지 않음)."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO thunder_pending_charges
                (ref_id, member_id, cost, game_count, created_at, settled)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (ref_id, member_id, int(cost), int(game_count), _now_iso()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def settle_thunder_pending(member_id: int, ref_id: str | None = None) -> None:
    """번호가 실제로 저장내역에 저장되면(th_save 처리) 호출 — 해당 미정산 건을
    '정산 완료'로 표시해 자동 환불 대상에서 뺀다. ref_id를 알면 그것으로,
    모르면(세션 유실 등) 이 회원의 가장 오래된 미정산 건을 정산한다."""
    conn = _connect()
    try:
        if ref_id:
            conn.execute(
                "UPDATE thunder_pending_charges SET settled = 1, settled_at = ? "
                "WHERE ref_id = ? AND settled = 0",
                (_now_iso(), ref_id),
            )
        else:
            row = conn.execute(
                "SELECT ref_id FROM thunder_pending_charges "
                "WHERE member_id = ? AND settled = 0 ORDER BY created_at ASC LIMIT 1",
                (member_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE thunder_pending_charges SET settled = 1, settled_at = ? WHERE ref_id = ?",
                    (_now_iso(), row["ref_id"]),
                )
        conn.commit()
    finally:
        conn.close()


def sweep_stale_thunder_pending(
    member_id: int, *, stale_minutes: int = THUNDER_PENDING_STALE_MINUTES
) -> int:
    """번개조합 화면에 들어올 때마다 호출 — 조합시작 후 stale_minutes(기본 10분)이
    지나도록 번호가 저장되지 않은 미정산 차감을 자동 환불한다. 환불한 총 P를
    반환(0이면 없음). 번호 생성·저장이 정상 완료되면 settle_thunder_pending가
    먼저 settled=1로 바꿔 여기 걸리지 않는다."""
    # created_at은 _now_iso()로 저장되므로(KST, "%Y-%m-%d %H:%M:%S.%f") 문자열
    # 비교가 성립하도록 컷오프도 같은 시계·같은 포맷으로 만든다.
    cutoff = (datetime.now(KST) - timedelta(minutes=stale_minutes)).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT ref_id, cost FROM thunder_pending_charges "
            "WHERE member_id = ? AND settled = 0 AND created_at < ?",
            (member_id, cutoff),
        ).fetchall()
    finally:
        conn.close()

    refunded_total = 0
    for row in rows:
        ok = refund_points(
            member_id, int(row["cost"]), "thunder:refund:no_save", f"{row['ref_id']}:refund"
        )
        if ok:
            _c = _connect()
            try:
                _c.execute(
                    "UPDATE thunder_pending_charges SET settled = 2, settled_at = ? WHERE ref_id = ?",
                    (_now_iso(), row["ref_id"]),
                )
                _c.commit()
            finally:
                _c.close()
            refunded_total += int(row["cost"])
    return refunded_total


def create_auto_order(
    member_id: int,
    quantity: int,
    purchase_type: str,
    phone: str,
    sms_days: str,
    ledger_ref_id: str,
) -> int:
    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO auto_orders
            (member_id, quantity, purchase_type, phone, sms_days, status, ledger_ref_id, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (member_id, int(quantity), purchase_type, phone.strip(), sms_days, ledger_ref_id, _now_iso()),
    )
    order_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return order_id


def complete_auto_order(
    order_id: int,
    sms_queue_id: int,
    draw_round: int,
    combo_count: int,
) -> None:
    conn = _connect()
    conn.execute(
        """
        UPDATE auto_orders
        SET status = 'completed', sms_queue_id = ?, draw_round = ?,
            combo_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (sms_queue_id, int(draw_round), int(combo_count), _now_iso(), int(order_id)),
    )
    conn.commit()
    conn.close()


def list_completed_auto_orders(member_id: int, limit: int = 20) -> list[dict]:
    """완료된 자동구매 주문 목록 (최신순)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, quantity, purchase_type, phone, sms_days, draw_round,
               combo_count, created_at, completed_at
        FROM auto_orders
        WHERE member_id = ? AND status = 'completed'
        ORDER BY completed_at DESC, id DESC
        LIMIT ?
        """,
        (int(member_id), int(limit)),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def cleanup_old_auto_orders(keep_rounds: int = 2) -> int:
    """auto_orders(회원 기준 자동구매 주문) — 최근 N개 회차만 남기고 그 이전은
    삭제. marketing_db.cleanup_old_guest_auto_orders와 동일한 규칙 — 실결제
    연동 전엔 이 테이블에 실제로 쓰는 경로가 없어(전부 guest_auto_orders로만
    기록됨) 지금은 대부분 비어있겠지만, 나중에 실결제가 붙어 이 테이블도
    쌓이기 시작했을 때 처음부터 규칙이 적용돼 있도록 미리 맞춰둔다."""
    conn = _connect()
    rows = conn.execute(
        "SELECT DISTINCT draw_round FROM auto_orders WHERE draw_round IS NOT NULL ORDER BY draw_round DESC"
    ).fetchall()
    old_rounds = [int(r[0]) for r in rows[keep_rounds:]]
    deleted = 0
    for old_round in old_rounds:
        cur = conn.execute(
            "DELETE FROM auto_orders WHERE draw_round = ?", (old_round,)
        )
        deleted += int(cur.rowcount or 0)
    conn.commit()
    conn.close()
    return deleted


def fail_auto_order(order_id: int) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE auto_orders SET status = 'failed', completed_at = ? WHERE id = ?",
        (_now_iso(), int(order_id)),
    )
    conn.commit()
    conn.close()
