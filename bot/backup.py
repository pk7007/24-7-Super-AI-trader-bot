"""Backups of the bots' state, safe to take while the bots run, plus a restore drill.

    python -m bot.backup              # write backups/state_<UTC stamp>.zip, keep the newest 14
    python -m bot.backup --drill      # backup, restore into a temp folder, compare, write reports/backup_drill.json

Each zip holds, per mode (paper, shadow, live): ``state.db`` copied with SQLite's online backup API (a consistent
snapshot even while the bot writes), ``paper_exchange.json`` and ``trades_ledger.csv``, plus ``manifest.json`` with
SHA-256 hashes and row counts. Never copied: ``.env``, lock files, logs. Restore only writes into an EMPTY folder;
moving a restored copy into ``state/`` is a manual step taken with the bot stopped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

FILES = ("state.db", "paper_exchange.json", "trades_ledger.csv")
ALLOWED = {f"{mode}/{name}" for mode in ("paper", "shadow", "live") for name in FILES}


def _sources(root: Path) -> dict[str, Path]:
    """archive name -> file on disk, for every mode that has state."""
    st, out = root / "state", {}
    for mode in ("paper", "shadow"):
        for f in FILES:
            if (st / mode / f).exists():
                out[f"{mode}/{f}"] = st / mode / f
    if (st / "state.db").exists():  # live keeps state.db in state/ and the ledger at the project root
        out["live/state.db"] = st / "state.db"
        if (root / "trades_ledger.csv").exists():
            out["live/trades_ledger.csv"] = root / "trades_ledger.csv"
    return out


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _db_snapshot(src: Path, dst: Path) -> None:
    s = sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _row_counts(db: Path) -> dict[str, int]:
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        return {t: con.execute('select count(*) from "' + t.replace('"', '""') + '"').fetchone()[0] for t in tables}
    finally:
        con.close()


def backup(root: Path = ROOT, dest: Path | None = None, keep: int = 14, stamp: str | None = None) -> Path:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    dest = Path(dest or root / "backups")
    dest.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not stamp or any(c not in "0123456789TZ" for c in stamp):
        raise ValueError("invalid backup timestamp")
    out, manifest = dest / f"state_{stamp}.zip", {"created_utc": stamp, "files": {}}
    if out.exists():
        raise FileExistsError(out)
    pending = out.with_suffix(".tmp")
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in _sources(Path(root)).items():
            if name.endswith(".db"):
                snap = Path(tmp) / name.replace("/", "_")
                _db_snapshot(src, snap)
                data, rows = snap.read_bytes(), _row_counts(snap)
            else:
                data, rows = src.read_bytes(), None
            z.writestr(name, data)
            manifest["files"][name] = {"sha256": _sha(data), "bytes": len(data), "rows": rows}
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    with pending.open("r+b") as fh:
        os.fsync(fh.fileno())
    os.replace(pending, out)
    # Preserve previous recovery points when the newly captured state is corrupt.
    if verify(out)["ok"]:
        for old in sorted(dest.glob("state_*.zip"))[:-keep]:
            old.unlink()
    return out


def _manifest(z: zipfile.ZipFile) -> dict:
    names = z.namelist()
    if len(names) != len(set(names)):
        raise ValueError("duplicate archive members")
    man = json.loads(z.read("manifest.json"))
    files = man["files"]
    if not isinstance(files, dict) or not files or not any(n.endswith("/state.db") for n in files):
        raise ValueError("backup contains no database")
    if not set(files) <= ALLOWED or set(names) != set(files) | {"manifest.json"}:
        raise ValueError("unsafe or unmanifested archive members")
    for meta in files.values():
        if not isinstance(meta, dict) or not isinstance(meta.get("sha256"), str):
            raise ValueError("invalid file metadata")
    if not isinstance(man["created_utc"], str):
        raise ValueError("invalid creation timestamp")
    return man


def _valid_account(account: object) -> bool:
    """Validate the fields PaperBroker needs on startup, not just JSON syntax."""
    def number(value, *, positive=False, nonnegative=False):
        return (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                and (not positive or value > 0) and (not nonnegative or value >= 0))

    def text(value):
        return isinstance(value, str) and bool(value)

    if not isinstance(account, dict) or not number(account.get("cash")):
        return False
    positions, stops, fills = account.get("positions"), account.get("stops"), account.get("fills")
    seq = account.get("seq")
    if (not isinstance(positions, dict) or not isinstance(stops, dict) or not isinstance(fills, list)
            or not isinstance(seq, int) or isinstance(seq, bool) or seq < 0):
        return False
    for symbol, pos in positions.items():
        if (not text(symbol) or not isinstance(pos, dict) or isinstance(pos.get("side"), bool)
                or pos.get("side") not in (-1, 1) or not number(pos.get("contracts"), positive=True)
                or not number(pos.get("entry"), positive=True)):
            return False
    for order_id, stop in stops.items():
        if (not text(order_id) or not isinstance(stop, dict) or not text(stop.get("symbol"))
                or stop.get("side") not in ("buy", "sell") or not number(stop.get("contracts"), positive=True)
                or not number(stop.get("stop"), positive=True) or not text(stop.get("since"))):
            return False
        try:
            datetime.fromisoformat(stop["since"])
        except ValueError:
            return False
    for fill in fills:
        if (not isinstance(fill, dict) or not all(text(fill.get(k)) for k in ("ts", "symbol", "order_id"))
                or not isinstance(fill.get("reason"), str) or fill.get("side") not in ("buy", "sell")
                or not number(fill.get("qty"), positive=True) or not number(fill.get("price"), positive=True)
                or not number(fill.get("fee"), nonnegative=True) or not number(fill.get("realized_pnl"))):
            return False
    return True


def verify(zpath: Path) -> dict:
    try:
        return _verify(zpath)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, sqlite3.DatabaseError) as exc:
        return {"ok": False, "problems": [f"invalid backup ({type(exc).__name__})"], "files": 0, "created_utc": None}


def _verify(zpath: Path) -> dict:
    problems = []
    with zipfile.ZipFile(zpath) as z:
        man = _manifest(z)
        for name, meta in man["files"].items():
            try:
                data = z.read(name)
            except KeyError:
                problems.append(f"{name}: missing")
                continue
            if _sha(data) != meta["sha256"]:
                problems.append(f"{name}: hash mismatch")
            elif name.endswith(".json"):  # a matching hash of a broken file is still a broken backup
                try:
                    account = json.loads(data)
                except ValueError:
                    problems.append(f"{name}: not valid JSON")
                else:
                    if not _valid_account(account):
                        problems.append(f"{name}: invalid paper account schema")
            elif name.endswith(".db"):
                with tempfile.TemporaryDirectory() as tmp:
                    p = Path(tmp) / "check.db"
                    p.write_bytes(data)
                    con = sqlite3.connect(p)
                    ok = con.execute("pragma integrity_check").fetchone()[0]
                    con.close()
                    if ok != "ok":
                        problems.append(f"{name}: integrity_check {ok}")
    return {"ok": not problems, "problems": problems, "files": len(man["files"]), "created_utc": man["created_utc"]}


def restore(zpath: Path, target: Path) -> Path:
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} is not empty; restore only into an empty folder")
    result = verify(zpath)
    if not result["ok"]:
        raise ValueError("backup verification failed: " + "; ".join(result["problems"]))
    with zipfile.ZipFile(zpath) as z:
        man = _manifest(z)
        # Resolve every destination before the first write, including any existing symlinks.
        base = target.resolve()
        if any(not (base / name).resolve().is_relative_to(base) for name in man["files"]):
            raise ValueError("restore path escapes target")
        target.mkdir(parents=True, exist_ok=True)
        for name in man["files"]:
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            (target / name).write_bytes(z.read(name))
    return target


def drill(root: Path = ROOT, dest: Path | None = None, report: Path | None = None, keep: int = 14) -> dict:
    """Backup -> verify -> restore into a temp folder -> compare row counts with the live databases."""
    z = backup(root, dest, keep=keep)
    v = verify(z)
    match = False
    if v["ok"]:
        match = _restore_matches(z)
    rep = {"ok": v["ok"] and match, "row_counts_match": match, "verify": v, "backup": z.name,
           "drilled_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    report = Path(report or Path(root) / "reports" / "backup_drill.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(rep, indent=2))
    return rep


def _restore_matches(z: Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        restore(z, Path(tmp) / "restored")
        with zipfile.ZipFile(z) as zf:
            man = json.loads(zf.read("manifest.json"))
        return all(_row_counts(Path(tmp) / "restored" / n) == m["rows"] for n, m in man["files"].items()
                    if n.endswith(".db"))


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bot.backup")
    ap.add_argument("--drill", action="store_true", help="also restore into a temp folder and compare")
    ap.add_argument("--keep", type=int, default=14)
    a = ap.parse_args()
    if a.drill:
        r = drill(keep=a.keep)
        print("drill", "PASSED" if r["ok"] else "FAILED", r["backup"], r["verify"]["problems"] or "")
        if not r["ok"]:
            raise SystemExit(1)
    else:
        z = backup(keep=a.keep)
        result = verify(z)
        print(z, result)
        if not result["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
