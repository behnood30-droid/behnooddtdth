import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass


SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id      INTEGER NOT NULL,
    plan_id         TEXT    NOT NULL,
    price_usdt      REAL    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',  -- pending | paid | delivered | failed
    invoice_id      TEXT,                                -- شناسه فاکتور در تتراپی
    pay_url         TEXT,
    panel_username  TEXT,
    sub_url         TEXT,
    created_at      INTEGER NOT NULL,
    paid_at         INTEGER,
    delivered_at    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_orders_invoice ON orders(invoice_id);
CREATE INDEX IF NOT EXISTS idx_orders_user    ON orders(tg_user_id);
"""


@dataclass
class Order:
    id: int
    tg_user_id: int
    plan_id: str
    price_usdt: float
    status: str
    invoice_id: str | None
    pay_url: str | None
    panel_username: str | None
    sub_url: str | None
    created_at: int
    paid_at: int | None
    delivered_at: int | None


class DB:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_order(self, tg_user_id: int, plan_id: str, price_usdt: float) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO orders (tg_user_id, plan_id, price_usdt, created_at) "
                "VALUES (?, ?, ?, ?)",
                (tg_user_id, plan_id, price_usdt, int(time.time())),
            )
            return cur.lastrowid

    def set_invoice(self, order_id: int, invoice_id: str, pay_url: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE orders SET invoice_id = ?, pay_url = ? WHERE id = ?",
                (invoice_id, pay_url, order_id),
            )

    def mark_paid(self, order_id: int) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE orders SET status = 'paid', paid_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (int(time.time()), order_id),
            )

    def mark_delivered(self, order_id: int, panel_username: str, sub_url: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE orders SET status = 'delivered', panel_username = ?, "
                "sub_url = ?, delivered_at = ? WHERE id = ?",
                (panel_username, sub_url, int(time.time()), order_id),
            )

    def mark_failed(self, order_id: int) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE orders SET status = 'failed' WHERE id = ?",
                (order_id,),
            )

    def get_order(self, order_id: int) -> Order | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
        return Order(**dict(row)) if row else None

    def get_order_by_invoice(self, invoice_id: str) -> Order | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM orders WHERE invoice_id = ?", (invoice_id,)
            ).fetchone()
        return Order(**dict(row)) if row else None

    def list_user_orders(self, tg_user_id: int, limit: int = 10) -> list[Order]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM orders WHERE tg_user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (tg_user_id, limit),
            ).fetchall()
        return [Order(**dict(r)) for r in rows]
