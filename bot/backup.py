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
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

FILES = ("state.db", "paper_exchange.json", "trades_ledger.csv")


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
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _row_counts(db: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        return {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
    finally:
        con.close()


def backup(root: Path = ROOT, dest: Path | None = None, keep: int = 14, stamp: str | None = None) -> Path:
    dest = Path(dest or root / "backups")
    dest.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out, manifest = dest / f"state_{stamp}.zip", {"created_utc": stamp, "files": {}}
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
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
    for old in sorted(dest.glob("state_*.zip"))[:-keep]:
        old.unlink()
    return out


def verify(zpath: Path) -> dict:
    problems = []
    with zipfile.ZipFile(zpath) as z:
        man = json.loads(z.read("manifest.json"))
        for name, meta in man["files"].items():
            try:
                data = z.read(name)
            except KeyError:
                problems.append(f"{name}: missing")
                continue
            if _sha(data) != meta["sha256"]:
                problems.append(f"{name}: hash mismatch")
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
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if name == "manifest.json" or ".." in name or name.startswith("/"):
                continue
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            (target / name).write_bytes(z.read(name))
    return target


def drill(root: Path = ROOT, dest: Path | None = None, report: Path | None = None) -> dict:
    """Backup -> verify -> restore into a temp folder -> compare row counts with the live databases."""
    z = backup(root, dest)
    v = verify(z)
    with tempfile.TemporaryDirectory() as tmp:
        restore(z, Path(tmp) / "restored")
        with zipfile.ZipFile(z) as zf:
            man = json.loads(zf.read("manifest.json"))
        match = all(_row_counts(Path(tmp) / "restored" / n) == m["rows"] for n, m in man["files"].items()
                    if n.endswith(".db"))
    rep = {"ok": v["ok"] and match, "row_counts_match": match, "verify": v, "backup": z.name,
           "drilled_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    report = Path(report or Path(root) / "reports" / "backup_drill.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(rep, indent=2))
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bot.backup")
    ap.add_argument("--drill", action="store_true", help="also restore into a temp folder and compare")
    ap.add_argument("--keep", type=int, default=14)
    a = ap.parse_args()
    if a.drill:
        r = drill()
        print("drill", "PASSED" if r["ok"] else "FAILED", r["backup"], r["verify"]["problems"] or "")
    else:
        z = backup(keep=a.keep)
        print(z, verify(z))


if __name__ == "__main__":
    main()
