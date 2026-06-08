"""مدیریت دیتابیس SQLite."""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id      INTEGER   PRIMARY KEY,
    username         TEXT,
    first_name       TEXT      NOT NULL DEFAULT '',
    total_purchases  INTEGER   NOT NULL DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id           TEXT      PRIMARY KEY,
    telegram_id          INTEGER   NOT NULL,
    plan_gb              INTEGER   NOT NULL,
    plan_days            INTEGER   NOT NULL DEFAULT 30,
    price_toman          INTEGER   NOT NULL,
    payment_method       TEXT      NOT NULL,
    amount_usdt          REAL,
    unique_amount        REAL,
    network              TEXT,
    tx_hash              TEXT,
    pirooz_order_id      TEXT,
    pirooz_tracking_code TEXT,
    status               TEXT      NOT NULL DEFAULT 'pending',
    panel_username       TEXT,
    sub_link             TEXT,
    configs              TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at           TIMESTAMP,
    confirmed_at         TIMESTAMP,
    delivered_at         TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT      PRIMARY KEY,
    value      TEXT      NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_tg     ON payments(telegram_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
"""


@dataclass
class User:
    telegram_id: int
    username: str | None
    first_name: str
    total_purchases: int
    created_at: str


@dataclass
class Payment:
    payment_id: str
    telegram_id: int
    plan_gb: int
    plan_days: int
    price_toman: int
    payment_method: str
    amount_usdt: float | None
    unique_amount: float | None
    network: str | None
    tx_hash: str | None
    pirooz_order_id: str | None
    pirooz_tracking_code: str | None
    status: str
    panel_username: str | None
    sub_link: str | None
    configs: str | None
    created_at: str
    expires_at: str | None
    confirmed_at: str | None
    delivered_at: str | None


class DB:
    def __init__(self, path: str) -> None:
        self.path = path
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ─── Users ───────────────────────────────────────────────────────────────

    def ensure_user(self, telegram_id: int, username: str | None, first_name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
                (telegram_id, username, first_name),
            )
            conn.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                (username, first_name, telegram_id),
            )

    def get_user(self, telegram_id: int) -> User | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        return User(**dict(row)) if row else None

    def find_user(self, query: str) -> User | None:
        with self._conn() as conn:
            try:
                uid = int(query)
                row = conn.execute(
                    "SELECT * FROM users WHERE telegram_id = ?", (uid,)
                ).fetchone()
                if row:
                    return User(**dict(row))
            except ValueError:
                pass
            uname = query.lstrip("@").lower()
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = ?", (uname,)
            ).fetchone()
        return User(**dict(row)) if row else None

    def increment_purchases(self, telegram_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET total_purchases = total_purchases + 1 WHERE telegram_id = ?",
                (telegram_id,),
            )

    def get_user_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_all_user_ids(self) -> list[int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT telegram_id FROM users").fetchall()
        return [r[0] for r in rows]

    def list_users_paginated(
        self, page: int = 0, page_size: int = 20
    ) -> tuple[list[dict], int]:
        offset = page * page_size
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rows = conn.execute(
                """
                SELECT u.telegram_id, u.username, u.first_name,
                       u.total_purchases, u.created_at,
                       COALESCE(SUM(CASE WHEN p.status='delivered' THEN p.price_toman ELSE 0 END), 0) AS purchase_sum
                FROM users u
                LEFT JOIN payments p ON u.telegram_id = p.telegram_id
                GROUP BY u.telegram_id
                ORDER BY u.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
        return [dict(r) for r in rows], total

    # ─── Payments ─────────────────────────────────────────────────────────────

    def create_payment(
        self,
        payment_id: str,
        telegram_id: int,
        plan_gb: int,
        plan_days: int,
        price_toman: int,
        payment_method: str,
        amount_usdt: float | None = None,
        unique_amount: float | None = None,
        network: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=plan_days)).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO payments
                (payment_id, telegram_id, plan_gb, plan_days, price_toman,
                 payment_method, amount_usdt, unique_amount, network, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (payment_id, telegram_id, plan_gb, plan_days, price_toman,
                 payment_method, amount_usdt, unique_amount, network, expires_at),
            )
        return payment_id

    def get_payment(self, payment_id: str) -> Payment | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
            ).fetchone()
        return Payment(**dict(row)) if row else None

    def confirm_payment(
        self,
        payment_id: str,
        tx_hash: str | None = None,
        tracking_code: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE payments
                SET status='confirmed', tx_hash=?, pirooz_tracking_code=?,
                    confirmed_at=CURRENT_TIMESTAMP
                WHERE payment_id=?
                """,
                (tx_hash, tracking_code, payment_id),
            )

    def deliver_payment(
        self,
        payment_id: str,
        panel_username: str,
        sub_link: str,
        configs: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE payments
                SET status='delivered', panel_username=?, sub_link=?, configs=?,
                    delivered_at=CURRENT_TIMESTAMP
                WHERE payment_id=?
                """,
                (panel_username, sub_link, configs, payment_id),
            )

    def fail_payment(self, payment_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE payments SET status='failed' WHERE payment_id=?",
                (payment_id,),
            )

    def expire_payment(self, payment_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE payments SET status='expired' WHERE payment_id=?",
                (payment_id,),
            )

    def cancel_payment(self, payment_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE payments SET status='expired' WHERE payment_id=? AND status='pending'",
                (payment_id,),
            )

    def get_pending_payments(self) -> list[Payment]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE status='pending' ORDER BY created_at ASC"
            ).fetchall()
        return [Payment(**dict(r)) for r in rows]

    def get_payments_by_status(self, status: str, limit: int = 10) -> list[Payment]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [Payment(**dict(r)) for r in rows]

    def get_user_delivered_payments(self, telegram_id: int, limit: int = 5) -> list[Payment]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE telegram_id=? AND status='delivered' "
                "ORDER BY delivered_at DESC LIMIT ?",
                (telegram_id, limit),
            ).fetchall()
        return [Payment(**dict(r)) for r in rows]

    def get_user_stats(self, telegram_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as purchase_count, "
                "COALESCE(SUM(price_toman), 0) as purchase_sum "
                "FROM payments WHERE telegram_id=? AND status='delivered'",
                (telegram_id,),
            ).fetchone()
        return {"count": row[0], "sum": int(row[1])}

    def tx_hash_used(self, tx_hash: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM payments WHERE tx_hash=?", (tx_hash,)
            ).fetchone()
        return row is not None

    def has_pending_unique(self, unique_amount: float, network: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM payments "
                "WHERE unique_amount=? AND network=? AND status='pending'",
                (unique_amount, network),
            ).fetchone()
        return row is not None

    # ─── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._conn() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            orders_today = conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status='delivered' AND DATE(delivered_at)=?",
                (today,),
            ).fetchone()[0]
            orders_total = conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status='delivered'"
            ).fetchone()[0]
            rev_today = conn.execute(
                "SELECT COALESCE(SUM(price_toman),0) FROM payments "
                "WHERE status='delivered' AND DATE(delivered_at)=?",
                (today,),
            ).fetchone()[0]
            rev_total = conn.execute(
                "SELECT COALESCE(SUM(price_toman),0) FROM payments WHERE status='delivered'"
            ).fetchone()[0]
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status='pending'"
            ).fetchone()[0]
            failed_count = conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status='failed'"
            ).fetchone()[0]
        return {
            "total_users":   total_users,
            "orders_today":  orders_today,
            "orders_total":  orders_total,
            "revenue_today": int(rev_today),
            "revenue_total": int(rev_total),
            "pending_count": pending_count,
            "failed_count":  failed_count,
        }

    # ─── Settings ─────────────────────────────────────────────────────────────

    def get_setting(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else None

    def get_setting_updated_at(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT updated_at FROM settings WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, value),
            )
