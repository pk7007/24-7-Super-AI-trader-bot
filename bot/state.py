"""SQLite state (state.db): open positions, fills (tax ledger mirror), small key/value store."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY, side INTEGER NOT NULL, contracts REAL NOT NULL,
    entry REAL NOT NULL, stop REAL NOT NULL, stop_id TEXT, opened_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL,
    realized_pnl REAL NOT NULL, reason TEXT, order_id TEXT
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class Position:
    symbol: str
    side: int  # +1 long, -1 short
    contracts: float
    entry: float
    stop: float
    stop_id: str | None
    opened_ts: str  # ISO UTC


class State:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------- positions
    def positions(self) -> dict[str, Position]:
        rows = self.db.execute("SELECT * FROM positions").fetchall()
        return {r["symbol"]: Position(**dict(r)) for r in rows}

    def upsert_position(self, p: Position) -> None:
        self.db.execute(
            "INSERT INTO positions(symbol,side,contracts,entry,stop,stop_id,opened_ts) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET side=excluded.side,"
            "contracts=excluded.contracts,entry=excluded.entry,stop=excluded.stop,"
            "stop_id=excluded.stop_id,opened_ts=excluded.opened_ts",
            (p.symbol, p.side, p.contracts, p.entry, p.stop, p.stop_id, p.opened_ts),
        )
        self.db.commit()

    def delete_position(self, symbol: str) -> None:
        self.db.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        self.db.commit()

    # ----------------------------------------------------------------- fills
    def add_fill(self, ts, symbol, side, qty, price, fee, realized_pnl, reason, order_id) -> None:
        self.db.execute(
            "INSERT INTO fills(ts,symbol,side,qty,price,fee,realized_pnl,reason,order_id) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (ts, symbol, side, qty, price, fee, realized_pnl, reason, order_id),
        )
        self.db.commit()

    def fills(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM fills ORDER BY id")]

    # -------------------------------------------------------------------- kv
    def kv_get(self, key: str, default: str | None = None) -> str | None:
        r = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def kv_set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
