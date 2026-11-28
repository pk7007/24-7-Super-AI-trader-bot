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
        (d / "paper_exchange.json").write_text(json.dumps({"cash": 113.6, "positions": {}, "stops": {}, "seq": 0, "fills": []}))
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


@pytest.mark.parametrize("name", ["../escaped.txt", "C:/escaped.txt", "C:escaped.txt",
                                 "\\\\server\\share\\escaped.txt", "paper\\escaped.txt",
                                 "/escaped.txt", "unexpected.txt"])
def test_restore_rejects_unsafe_or_unmanifested_members_before_writing(root, name):
    z = backup(root)
    with zipfile.ZipFile(z, "a") as archive:
        archive.writestr(name, "bad")
    target = root / "restored"
    with pytest.raises(ValueError):
        restore(z, target)
    assert not target.exists()


def test_restore_verifies_hashes_before_writing(root):
    z = backup(root)
    bad = root / "tampered.zip"
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            dst.writestr(name, b"{}" if name.endswith("paper_exchange.json") else data)
    with pytest.raises(ValueError):
        restore(bad, root / "restored")
    assert not (root / "restored").exists()


def test_empty_backup_is_not_recovery_evidence(tmp_path):
    assert not verify(backup(tmp_path))["ok"]
    assert not drill(tmp_path)["ok"]


@pytest.mark.parametrize("keep", [0, -1])
def test_invalid_retention_does_not_create_or_delete_archives(root, keep):
    with pytest.raises(ValueError):
        backup(root, keep=keep)
    assert not (root / "backups").exists()


def test_failed_backup_cli_exits_nonzero_and_drill_honors_keep(monkeypatch):
    from bot import backup as module
    seen = []
    monkeypatch.setattr("sys.argv", ["backup", "--drill", "--keep", "3"])
    monkeypatch.setattr(module, "drill", lambda **kw: (seen.append(kw), {
        "ok": False, "backup": "failed.zip", "verify": {"problems": ["broken"]}})[1])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 1 and seen == [{"keep": 3}]


def test_backup_supports_paths_with_uri_special_characters(root):
    import shutil
    special = root / "account #1"
    shutil.copytree(root / "state", special / "state")
    assert drill(special)["ok"]


def test_invalid_new_backup_never_rotates_valid_recovery_points(root):
    first = backup(root, keep=1, stamp="20261120T000000Z")
    (root / "state" / "paper" / "paper_exchange.json").write_text("broken")
    latest = backup(root, keep=1, stamp="20261121T000000Z")
    assert first.exists() and verify(first)["ok"] and not verify(latest)["ok"]


def test_repeated_explicit_stamp_never_overwrites_an_archive(root):
    first = backup(root, stamp="20261120T000000Z")
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        backup(root, stamp="20261120T000000Z")
    assert first.read_bytes() == original


@pytest.mark.parametrize("account", [[], None, {"cash": 113.6},
    {"cash": float("nan"), "positions": {}, "stops": {}, "seq": 0, "fills": []},
    {"cash": 113.6, "positions": [], "stops": {}, "seq": 0, "fills": []},
    {"cash": 113.6, "positions": {}, "stops": {}, "seq": -1, "fills": []},
    {"cash": 113.6, "positions": {}, "stops": {}, "seq": 0, "fills": [{}]},
    {"cash": 113.6, "positions": {"BTC": {"side": 1, "contracts": -1, "entry": 100}}, "stops": {}, "seq": 0, "fills": []},
    {"cash": 113.6, "positions": {}, "stops": {"P1": {"symbol": "BTC", "side": "sell", "contracts": 1, "stop": float("inf"), "since": "2026-11-28T00:00:00+00:00"}}, "seq": 1, "fills": []},
])
def test_backup_drill_rejects_unrecoverable_account_schema(root, account):
    (root / "state/paper/paper_exchange.json").write_text(json.dumps(account))
    report = drill(root)
    assert not report["ok"]
    assert any("paper/paper_exchange.json" in problem for problem in report["verify"]["problems"])
