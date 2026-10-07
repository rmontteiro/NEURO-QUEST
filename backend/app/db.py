from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path(os.environ.get("DATA_PATH", "./data/lastro.db"))
_lock = threading.Lock()

SEED = [
    ("ETH", "Ether", "ethereum", 1.8, 3450.0),
    ("SOL", "Solana", "solana", 22.0, 158.0),
    ("WBTC", "Wrapped Bitcoin", "ethereum", 0.035, 67200.0),
    ("USDC", "USD Coin", "ethereum", 1800.0, 1.0),
    ("AAVE", "Aave", "arbitrum", 4.2, 168.0),
]


def connect() -> sqlite3.Connection:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _seed(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for symbol, name, chain, amount, price in SEED:
        conn.execute(
            """
            insert into positions (id, symbol, name, chain, amount, price_usd, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex[:12], symbol, name, chain, amount, price, now),
        )


def init_db() -> None:
    with _lock:
        conn = connect()
        try:
            conn.execute(
                """
                create table if not exists positions (
                    id text primary key,
                    symbol text not null,
                    name text not null,
                    chain text not null,
                    amount real not null,
                    price_usd real not null,
                    created_at text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists meta (
                    key text primary key,
                    value text not null
                )
                """
            )
            seeded = conn.execute("select value from meta where key = 'seeded'").fetchone()
            count = conn.execute("select count(*) as c from positions").fetchone()["c"]
            if seeded is None:
                if count == 0:
                    _seed(conn)
                conn.execute("insert into meta (key, value) values ('seeded', '1')")
            conn.commit()
        finally:
            conn.close()


def list_positions() -> list[dict]:
    with _lock:
        conn = connect()
        try:
            rows = conn.execute(
                "select id, symbol, name, chain, amount, price_usd, created_at from positions order by created_at asc"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def insert_position(symbol: str, name: str, chain: str, amount: float, price_usd: float) -> dict:
    row = {
        "id": uuid.uuid4().hex[:12],
        "symbol": symbol,
        "name": name,
        "chain": chain,
        "amount": amount,
        "price_usd": price_usd,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        conn = connect()
        try:
            conn.execute(
                """
                insert into positions (id, symbol, name, chain, amount, price_usd, created_at)
                values (:id, :symbol, :name, :chain, :amount, :price_usd, :created_at)
                """,
                row,
            )
            conn.commit()
        finally:
            conn.close()
    return row


def delete_position(position_id: str) -> bool:
    with _lock:
        conn = connect()
        try:
            cursor = conn.execute("delete from positions where id = ?", (position_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def clear_positions() -> int:
    with _lock:
        conn = connect()
        try:
            cursor = conn.execute("delete from positions")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
