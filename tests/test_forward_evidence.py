import csv
import json
from datetime import datetime, timedelta, timezone

from bot import readiness
from bot.report import round_trips
from bot.testnet_check import Checklist, EXPECTED_STEPS, passed_recently, write_report
from bot.config import Settings


def test_partial_exits_are_one_round_trip_net_of_all_fees():
    fills = [dict(ts="1", symbol="BTC", side="buy", qty=2, price=100, fee=1, realized_pnl=0, reason="entry"),
             dict(ts="2", symbol="BTC", side="sell", qty=1, price=101, fee=1, realized_pnl=1, reason="stop"),
             dict(ts="3", symbol="BTC", side="sell", qty=1, price=101, fee=1, realized_pnl=1, reason="stop")]
    assert round_trips(fills[:2]) == []
    trips = round_trips(fills)
    assert len(trips) == 1 and trips[0]["net"] == -1


def test_forward_evidence_counts_completed_net_trades_and_successful_days(tmp_path):
    ledger = tmp_path / "trades_ledger.csv"
    columns = ["timestamp", "pair", "side", "qty", "price", "fee", "realized_pnl", "reason", "order_id"]
    with ledger.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows([["1", "BTC", "buy", 1, 100, 2, 0, "entry", "1"],
                         ["2", "BTC", "sell", 1, 101, 2, 1, "stop", "2"],
                         ["3", "BTC", "buy", 1, 100, 1, 0, "entry", "3"],
                         ["4", "BTC", "sell", 1, 100, 1, 0, "stop", "4"]])
    log = tmp_path / "paper.log"
    stamp = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp},001 INFO engine: step complete candle 2026-01-01T00:00:00+00:00\n"
    log.write_text(line + line)  # duplicate log lines are not extra successful candles
    evidence = readiness._forward_evidence(tmp_path, log)
    assert evidence["completed_trades"] == 2  # includes the break-even-price trade's fees
    assert evidence["profit_factor"] == 0
    assert evidence["days_running"] <= 1 / 96 + 0.001


def test_diagnostic_candle_does_not_prove_a_successful_step(tmp_path):
    log = tmp_path / "paper.log"
    stamp = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
    log.write_text(f"{stamp},001 INFO engine: candle 08-01 00:00 | equity 100 | held none | decisions {{}}\n")
    assert readiness._forward_evidence(tmp_path, log)["successful_candles"] == 0


def test_future_testnet_and_backup_evidence_are_rejected(tmp_path, monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    cl = Checklist()
    for name in EXPECTED_STEPS:
        cl.check(name, True)
    path = write_report(cl, Settings(), True, path=tmp_path / "testnet.json")
    report = json.loads(path.read_text())
    report["ran_utc"] = future
    path.write_text(json.dumps(report))
    assert not passed_recently(path)
    monkeypatch.setattr(readiness, "ROOT", tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/backup_drill.json").write_text(json.dumps({"ok": True, "drilled_utc": future}))
    assert not readiness._recent_drill()
