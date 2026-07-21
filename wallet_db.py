"""회원 지갑 DB — OAuth 해시 식별자만 저장 (PII·결제정보 미보관)."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "lotto.db"
SIGNUP_BONUS = 5000
ADVANCED_PRODUCT = "advanced_filter_monthly"
FREE_SUB_DAYS = 30

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")


def oauth_hash(provider: str, provider_user_id: str) -> str:
    raw = f"{provider.strip().lower()}:{str(provider_user_id).strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_wallet_tables() -> None:
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
        """
    )
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


def calc_thunder_cost(game_count: int) -> int:
    n = max(1, int(game_count))
    return ((n + 4) // 5) * 1000


def calc_auto_cost(quantity: int) -> int:
    table = {5: 1000, 10: 2000, 15: 3000, 20: 4000}
    return table.get(int(quantity), ((int(quantity) + 4) // 5) * 1000)


def pg_configured() -> bool:
    import os

    return bool(os.environ.get("PG_MERCHANT_ID", "").strip())


CHARGE_AMOUNTS = (5000, 10000, 20000, 50000)


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


def fail_auto_order(order_id: int) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE auto_orders SET status = 'failed', completed_at = ? WHERE id = ?",
        (_now_iso(), int(order_id)),
    )
    conn.commit()
    conn.close()
