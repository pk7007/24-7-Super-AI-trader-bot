"""India tax ledger (RULE 5): every fill -> trades_ledger.csv AND SQLite ``fills`` table."""

from __future__ import annotations

import csv
from pathlib import Path

from .broker.base import Fill
from .state import State

COLUMNS = ["timestamp", "pair", "side", "qty", "price", "fee", "realized_pnl", "reason", "order_id"]


class Ledger:
    def __init__(self, csv_path: Path | str, state: State):
        self.path = Path(csv_path)
        self.state = state
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, f: Fill) -> None:
        new = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(COLUMNS)
            w.writerow([f.ts, f.symbol, f.side, f.qty, f.price, f.fee, f.realized_pnl, f.reason, f.order_id])
            fh.flush()
        self.state.add_fill(f.ts, f.symbol, f.side, f.qty, f.price, f.fee, f.realized_pnl, f.reason, f.order_id)
