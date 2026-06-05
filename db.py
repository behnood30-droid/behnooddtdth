"""مدیریت دیتابیس SQLite برای سفارش‌ها."""
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id                INTEGER   PRIMARY KEY AUTOINCREMENT,
    order_id          TEXT      UNIQUE NOT NULL,
    telegram_user_id  INTEGER   NOT NULL,
    telegram_username TEXT,
    plan_gb           INTEGER   NOT NULL,
    price_toman       INTEGER   NOT NULL,
    price_rial        INTEGER   NOT NULL,
    days              INTEGER   NOT NULL DEFAULT 30,
    status            TEXT      NOT NULL DEFAULT 'pending',
    authority         TEXT,
    tracking_id       TEXT,
    panel_username    TEXT,
    sub_link          TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at           TIMESTAMP,
    delivered_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_id    ON orders(order_id);
CREATE INDEX IF NOT EXISTS idx_authority   ON orders(authority);
CREATE INDEX IF NOT EXISTS idx_tg_user_id  ON orders(telegram_user_id);
"""


@dataclass
class Order:
    id: int
    order_id: str
    telegram_user_id: int
    telegram_username: str | None
    plan_gb: int
    price_toman: int
    price_rial: int
    days: int
    status: str
    authority: str | None
    tracking_id: str | None
    panel_username: str | None
    sub_link: str | None
    created_at: str
    paid_at: str | None
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

    def _gen_order_id(self) -> str:
        return uuid.uuid4().hex[:16].upper()

    # ─── نوشتن ───────────────────────────────────────────────────────────────

    def create_order(
        self,
        telegram_user_id: int,
        telegram_username: str | None,
        plan_gb: int,
        price_toman: int,
        price_rial: int,
        days: int = 30,
    ) -> str:
        order_id = self._gen_order_id()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO orders "
                "(order_id, telegram_user_id, telegram_username, plan_gb, price_toman, price_rial, days) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (order_id, telegram_user_id, telegram_username, plan_gb, price_toman, price_rial, days),
            )
        return order_id

    def set_authority(self, order_id: str, authority: str, tracking_id: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET authority = ?, tracking_id = ? WHERE order_id = ?",
                (authority, tracking_id, order_id),
            )

    def mark_paid(self, order_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status = 'paid', paid_at = CURRENT_TIMESTAMP "
                "WHERE order_id = ? AND status = 'pending'",
                (order_id,),
            )

    def mark_delivered(self, order_id: str, panel_username: str, sub_link: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status = 'delivered', panel_username = ?, "
                "sub_link = ?, delivered_at = CURRENT_TIMESTAMP WHERE order_id = ?",
                (panel_username, sub_link, order_id),
            )

    def mark_failed(self, order_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status = 'failed' WHERE order_id = ?",
                (order_id,),
            )

    # ─── خواندن ──────────────────────────────────────────────────────────────

    def get_order(self, order_id: str) -> Order | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
        return _to_order(row) if row else None

    def get_order_by_authority(self, authority: str) -> Order | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE authority = ?", (authority,)
            ).fetchone()
        return _to_order(row) if row else None

    def list_user_orders(self, telegram_user_id: int, limit: int = 5) -> list[Order]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE telegram_user_id = ? ORDER BY id DESC LIMIT ?",
                (telegram_user_id, limit),
            ).fetchall()
        return [_to_order(r) for r in rows]


def _to_order(row: sqlite3.Row) -> Order:
    return Order(**dict(row))
