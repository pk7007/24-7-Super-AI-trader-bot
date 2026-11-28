"""State backups: consistent SQLite copy while the bot runs, checksummed, restorable, rotated, never .env."""

import json
import sqlite3
import zipfile

import pytest

from bot.backup import backup, drill, restore, verify


@pytest.fixture
def root(tmp_path):
    for mode in ("paper", "shadow"):
        d = tmp_path / "state" / mode
        d.mkdir(parents=True)
        con = sqlite3.connect(d / "state.db")
        con.execute("create table fills (id integer primary key, symbol text)")
        con.executemany("insert into fills (symbol) values (?)", [("BTC",), ("ETH",)])
        con.commit()
        con.close()
        (d / "paper_exchange.json").write_text(json.dumps({"cash": 113.6}))
        (d / "trades_ledger.csv").write_text("ts,pair\n1,BTC\n")
        (d / "bot.lock").write_text("lock")
    (tmp_path / ".env").write_text("DELTA_API_SECRET=do-not-copy")
    return tmp_path


def test_backup_holds_every_state_file_with_hashes_and_no_secrets(root):
    z = backup(root, root / "backups")
    names = zipfile.ZipFile(z).namelist()
    assert {"paper/state.db", "paper/paper_exchange.json", "paper/trades_ledger.csv", "shadow/state.db", "manifest.json"} <= set(names)
    assert not any(n.endswith((".env", ".lock")) for n in names)
    assert b"do-not-copy" not in z.read_bytes()


def test_backup_reads_a_database_that_is_open_for_writing(root):
    con = sqlite3.connect(root / "state" / "paper" / "state.db")
    con.execute("begin immediate")              # a running bot holds a write transaction
    con.execute("insert into fills (symbol) values ('SOL')")
    z = backup(root, root / "backups")          # must not block or copy a torn file
    con.rollback()
    con.close()
    assert verify(z)["ok"]


def test_verify_detects_a_corrupted_file(root):
    z = backup(root, root / "backups")
    bad = root / "bad.zip"
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            data = src.read(n)
            dst.writestr(n, data + b"x" if n == "paper/paper_exchange.json" else data)
    r = verify(bad)
    assert not r["ok"] and any("paper_exchange.json" in p for p in r["problems"])


def test_unreadable_json_fails_verify_and_drill(root):
    """2026-11-27: a zeroed paper_exchange.json was backed up and the drill still passed."""
    (root / "state" / "paper" / "paper_exchange.json").write_bytes(b"\0" * 68)
    r = verify(backup(root, root / "backups"))
    assert not r["ok"] and any("paper/paper_exchange.json" in p and "JSON" in p for p in r["problems"])
    assert not drill(root, root / "backups", report=root / "reports" / "d.json")["ok"]


def test_restore_refuses_a_non_empty_target(root):
    z = backup(root, root / "backups")
    with pytest.raises(FileExistsError):
        restore(z, root / "state")              # never over live state


def test_drill_restores_and_matches_row_counts(root):
    rep = drill(root, root / "backups", report=root / "reports" / "backup_drill.json")
    assert rep["ok"] and rep["row_counts_match"]
    assert json.loads((root / "reports" / "backup_drill.json").read_text())["ok"] is True


def test_rotation_keeps_the_newest(root):
    for i in range(5):
        backup(root, root / "backups", keep=3, stamp=f"2026112{i}T000000Z")
    assert sorted(p.name for p in (root / "backups").glob("*.zip")) == [
        f"state_2026112{i}T000000Z.zip" for i in (2, 3, 4)]
