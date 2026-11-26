"""Optional external heartbeat ("dead man's switch").

Alerts on this PC cannot fire when the PC itself is off or asleep. Set ``HEARTBEAT_URL`` in ``.env`` to the ping URL
of an outside monitor (for example a free healthchecks.io check set to a 15-minute period with a grace time); the
bot sends one HTTPS GET after every processed candle, and the monitor emails or messages you when pings stop.
Nothing is sent when it is not set. Only https URLs are used. The URL is treated as a secret: it is never logged
or written to disk. Status goes to ``state/<mode>/heartbeat.json``.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("heartbeat")


def _open(url: str, timeout: float) -> None:
    urllib.request.urlopen(url, timeout=timeout).close()


def ping(status: Path, opener=_open, timeout: float = 10.0) -> bool | None:
    """True = delivered, False = configured but failed, None = not configured. Never raises."""
    url = os.environ.get("HEARTBEAT_URL", "").strip()
    if not url:
        return None
    status = Path(status)
    try:
        prev = json.loads(status.read_text()) if status.exists() else {}
    except (OSError, ValueError):
        prev = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        if not url.lower().startswith("https://"):
            raise ValueError("HEARTBEAT_URL must start with https://")
        opener(url, timeout)
        rec, ok = {"last_ok_utc": now, "last_error": None, "fails": 0}, True
    except Exception as exc:  # noqa: BLE001 - monitoring must never stop trading
        rec = {"last_ok_utc": prev.get("last_ok_utc"), "last_error": f"{now} {type(exc).__name__}",
               "fails": int(prev.get("fails", 0)) + 1}
        ok = False
        log.warning("heartbeat ping failed (%s); the outside monitor will alert if this continues", type(exc).__name__)
    try:
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(json.dumps(rec))
    except OSError:
        pass
    return ok


def recent_ok(status: Path, minutes: int = 60) -> bool:
    try:
        last = json.loads(Path(status).read_text()).get("last_ok_utc")
        return bool(last) and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(minutes=minutes)
    except (OSError, ValueError, TypeError):
        return False
