"""India tax ledger (RULE 5): every fill -> trades_ledger.csv AND SQLite ``fills`` table."""

from __future__ import annotations

import csv
import math
import os
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
        # SQLite is authoritative. A CSV failure can be retried using the same execution ID.
        self._check_existing_csv()
        self.state.add_fill(f.ts, f.symbol, f.side, f.qty, f.price, f.fee, f.realized_pnl, f.reason, f.order_id, f.fill_id)
        self._export_csv()

    @staticmethod
    def _csv_row(row: dict) -> list:
        return [row["ts"], row["symbol"], row["side"], row["qty"], row["price"], row["fee"],
                row["realized_pnl"], row["reason"], row["order_id"]]

    def _check_existing_csv(self) -> None:
        """Never erase a historical CSV-only execution from the older CSV-first writer."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return

        def normalized(values):
            out = [str(v or "") for v in values]
            for i in (3, 4, 5, 6):
                out[i] = float(values[i])
                if not math.isfinite(out[i]):
                    raise ValueError("nonfinite CSV accounting value")
            return out

        try:
            with self.path.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames != COLUMNS:
                    raise ValueError("unexpected CSV columns")
                csv_rows = [normalized([row[k] for k in COLUMNS]) for row in reader]
            db_rows = [normalized(self._csv_row(row)) for row in self.state.fills()]
            if csv_rows != db_rows[:len(csv_rows)]:
                raise ValueError("CSV is not a prefix of the authoritative history")
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("ledger reconciliation required before overwriting divergent CSV history") from exc

    def _export_csv(self) -> None:
        pending = self.path.with_suffix(self.path.suffix + ".tmp")
        with pending.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            for row in self.state.fills():
                w.writerow(self._csv_row(row))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(pending, self.path)
