"""회원 지갑 DB — OAuth 해시 식별자만 저장 (PII·결제정보 미보관)."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import db_turso

DB_PATH = "lotto.db"
SIGNUP_BONUS = 500  # 5,000원 상당 (10원=1점 환산)
ADVANCED_PRODUCT = "advanced_filter_monthly"
FREE_SUB_DAYS = 30
ADVANCED_MONTHLY_COST = 1200
ADVANCED_3MONTH_COST = 3000  # 3개월분 묶음 가격(월 1,200P 대비 할인)
ADVANCED_3MONTH_DAYS = 90

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")


def oauth_hash(provider: str, provider_user_id: str) -> str:
    raw = f"{provider.strip().lower()}:{str(provider_user_id).strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _connect():
    return db_turso.connect()


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
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        """
    )
    conn.commit()
    conn.close()
    _WALLET_TABLES_READY = True


def link_guest_to_member(guest_id: str, member_id: int) -> None:
    """로그인 성공 시 기기 식별자(guest_id, 네이티브 앱이면 재실행해도 유지됨)를
    회원과 연결해둔다 — 다음에 세션이 끊겼다가 재연결될 때(백그라운드 전환, 네트워크
    끊김 등) 이 연결로 자동 재로그인시켜서, 매번 간편인증 화면이 다시 뜨는 걸 막는다."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO guest_member_links (guest_id, member_id, linked_at) VALUES (?, ?, ?)
        ON CONFLICT(guest_id) DO UPDATE SET member_id = excluded.member_id, linked_at = excluded.linked_at
        """,
        (str(guest_id), int(member_id), _now_iso()),
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
    conn.commit()
    conn.close()
    return member_id, True


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

        row = conn.execute(
            "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
        ).fetchone()
        if not row:
            conn.close()
            return False
        balance = int(row["balance"])
        if balance < amount:
            conn.close()
            return False

        new_balance = balance - amount
        now = _now_iso()
        conn.execute(
            "UPDATE wallets SET balance = ? WHERE member_id = ?",
            (new_balance, member_id),
        )
        conn.execute(
            """
            INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (member_id, -amount, new_balance, reason, ref_id, now),
        )
        conn.commit()
        conn.close()
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


THUNDER_COST_PER_GAME = 10
HEDGE_COST_PER_COMBO = 10
AUTO_COST_PER_UNIT = 100
TAROT_EXTRA_DRAW_COST = 50  # 하루 1회 무료 이후 추가 뽑기 1회당


def calc_thunder_cost(game_count: int) -> int:
    return THUNDER_COST_PER_GAME * max(1, int(game_count))


def calc_hedge_cost(combo_count: int) -> int:
    """안티조합/액땜조합 — 생성 조합 수에 비례."""
    return HEDGE_COST_PER_COMBO * max(1, int(combo_count))


def calc_auto_cost(quantity: int) -> int:
    return AUTO_COST_PER_UNIT * max(1, int(quantity))


def pg_configured() -> bool:
    import os

    return bool(os.environ.get("PG_MERCHANT_ID", "").strip())


# 1만원 충전 시 1,000점 지급 — 10원당 1점.
WON_PER_POINT = 10
CHARGE_WON_AMOUNTS = (10000, 30000, 50000, 100000)


def won_to_points(won: int) -> int:
    return int(won) // WON_PER_POINT


def charge_points(member_id: int, amount: int, pg_ref_id: str) -> bool:
    """PG 충전 — 카드정보 미저장, ledger ref_id로 멱등."""
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

        row = conn.execute(
            "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
        ).fetchone()
        if not row:
            conn.close()
            return False

        new_balance = int(row["balance"]) + amount
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO pg_charges (member_id, amount, pg_ref_id, status, created_at)
            VALUES (?, ?, ?, 'completed', ?)
            """,
            (member_id, amount, pg_ref_id, now),
        )
        conn.execute(
            "UPDATE wallets SET balance = ? WHERE member_id = ?",
            (new_balance, member_id),
        )
        conn.execute(
            """
            INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
            VALUES (?, ?, ?, 'pg_charge', ?, ?)
            """,
            (member_id, amount, new_balance, pg_ref_id, now),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return True


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


def fail_auto_order(order_id: int) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE auto_orders SET status = 'failed', completed_at = ? WHERE id = ?",
        (_now_iso(), int(order_id)),
    )
    conn.commit()
    conn.close()
