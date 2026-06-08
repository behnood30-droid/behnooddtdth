"""مدیریت دیتابیس SQLite."""
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id      INTEGER   PRIMARY KEY,
    username         TEXT,
    first_name       TEXT      NOT NULL DEFAULT '',
    balance_toman    REAL      NOT NULL DEFAULT 0,
    total_purchases  INTEGER   NOT NULL DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT      PRIMARY KEY,
    telegram_id      INTEGER   NOT NULL,
    plan_gb          INTEGER   NOT NULL,
    price_toman      INTEGER   NOT NULL,
    days             INTEGER   NOT NULL DEFAULT 30,
    status           TEXT      NOT NULL DEFAULT 'pending',
    panel_username   TEXT,
    sub_link         TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallet_charges (
    charge_id        TEXT      PRIMARY KEY,
    telegram_id      INTEGER   NOT NULL,
    amount_usdt      REAL      NOT NULL,
    amount_toman     INTEGER   NOT NULL,
    unique_amount    REAL      NOT NULL,
    network          TEXT      NOT NULL,
    status           TEXT      NOT NULL DEFAULT 'pending',
    tx_hash          TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_tg       ON orders(telegram_id);
CREATE INDEX IF NOT EXISTS idx_charges_tg      ON wallet_charges(telegram_id);
CREATE INDEX IF NOT EXISTS idx_charges_status  ON wallet_charges(status);
"""


@dataclass
class User:
    telegram_id: int
    username: str | None
    first_name: str
    balance_toman: float
    total_purchases: int
    created_at: str


@dataclass
class Order:
    order_id: str
    telegram_id: int
    plan_gb: int
    price_toman: int
    days: int
    status: str
    panel_username: str | None
    sub_link: str | None
    created_at: str
    delivered_at: str | None


@dataclass
class WalletCharge:
    charge_id: str
    telegram_id: int
    amount_usdt: float
    amount_toman: int
    unique_amount: float
    network: str
    status: str
    tx_hash: str | None
    created_at: str
    confirmed_at: str | None


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

    def get_balance(self, telegram_id: int) -> float:
        user = self.get_user(telegram_id)
        return user.balance_toman if user else 0.0

    def add_balance(self, telegram_id: int, amount_toman: int) -> float:
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET balance_toman = balance_toman + ? WHERE telegram_id = ?",
                (amount_toman, telegram_id),
            )
        return self.get_balance(telegram_id)

    def deduct_balance(self, telegram_id: int, amount_toman: int) -> bool:
        """موجودی کسر می‌کنه. True = موفق، False = موجودی کافی نیست."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE users SET balance_toman = balance_toman - ? "
                "WHERE telegram_id = ? AND balance_toman >= ?",
                (amount_toman, telegram_id, amount_toman),
            )
            return cur.rowcount == 1

    def increment_purchases(self, telegram_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET total_purchases = total_purchases + 1 WHERE telegram_id = ?",
                (telegram_id,),
            )

    # ─── Orders ──────────────────────────────────────────────────────────────

    def create_order(
        self, telegram_id: int, plan_gb: int, price_toman: int, days: int = 30
    ) -> str:
        order_id = uuid.uuid4().hex[:16].upper()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO orders (order_id, telegram_id, plan_gb, price_toman, days) "
                "VALUES (?, ?, ?, ?, ?)",
                (order_id, telegram_id, plan_gb, price_toman, days),
            )
        return order_id

    def deliver_order(self, order_id: str, panel_username: str, sub_link: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status='delivered', panel_username=?, sub_link=?, "
                "delivered_at=CURRENT_TIMESTAMP WHERE order_id=?",
                (panel_username, sub_link, order_id),
            )

    def fail_order(self, order_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET status='failed' WHERE order_id=?", (order_id,)
            )

    def get_order(self, order_id: str) -> Order | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id=?", (order_id,)
            ).fetchone()
        return Order(**dict(row)) if row else None

    def list_user_orders(self, telegram_id: int, limit: int = 5) -> list[Order]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE telegram_id=? AND status='delivered' "
                "ORDER BY created_at DESC LIMIT ?",
                (telegram_id, limit),
            ).fetchall()
        return [Order(**dict(r)) for r in rows]

    # ─── Wallet Charges ──────────────────────────────────────────────────────

    def create_charge(
        self,
        telegram_id: int,
        amount_usdt: float,
        amount_toman: int,
        unique_amount: float,
        network: str,
    ) -> str:
        charge_id = uuid.uuid4().hex[:16].upper()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO wallet_charges "
                "(charge_id, telegram_id, amount_usdt, amount_toman, unique_amount, network) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (charge_id, telegram_id, amount_usdt, amount_toman, unique_amount, network),
            )
        return charge_id

    def get_pending_charges(self) -> list[WalletCharge]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM wallet_charges WHERE status='pending'"
            ).fetchall()
        return [WalletCharge(**dict(r)) for r in rows]

    def get_user_pending_charge(self, telegram_id: int) -> WalletCharge | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM wallet_charges WHERE telegram_id=? AND status='pending' "
                "ORDER BY created_at DESC LIMIT 1",
                (telegram_id,),
            ).fetchone()
        return WalletCharge(**dict(row)) if row else None

    def confirm_charge(self, charge_id: str, tx_hash: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE wallet_charges SET status='confirmed', tx_hash=?, "
                "confirmed_at=CURRENT_TIMESTAMP WHERE charge_id=?",
                (tx_hash, charge_id),
            )

    def expire_charge(self, charge_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE wallet_charges SET status='expired' WHERE charge_id=?", (charge_id,)
            )

    def cancel_user_pending_charge(self, telegram_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE wallet_charges SET status='cancelled' "
                "WHERE telegram_id=? AND status='pending'",
                (telegram_id,),
            )

    def tx_hash_used(self, tx_hash: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM wallet_charges WHERE tx_hash=?", (tx_hash,)
            ).fetchone()
        return row is not None

    def has_pending_unique(self, unique_amount: float, network: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM wallet_charges "
                "WHERE unique_amount=? AND network=? AND status='pending'",
                (unique_amount, network),
            ).fetchone()
        return row is not None
