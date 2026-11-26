"""Keep a Windows PC from idle sleep while a bot process runs.

Most missed candles on the development PC happened while Windows was asleep (silent log gaps of 7-10 hours).
``SetThreadExecutionState`` with ES_CONTINUOUS | ES_SYSTEM_REQUIRED asks Windows not to idle-sleep for as long as
the calling thread lives. It is a runtime request, not a settings change: it ends when the bot stops, the screen
may still turn off, and closing a laptop lid or pressing the power button still sleeps the PC.
Set KEEP_AWAKE=0 to turn it off. On Linux (the VPS) it does nothing.
"""

from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger("keepawake")

ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_CONTINUOUS = 0x80000000


def prevent_sleep(kernel32=None, platform: str | None = None) -> bool:
    """Ask Windows not to idle-sleep while this thread runs. Returns True if the request was accepted."""
    if os.getenv("KEEP_AWAKE", "1").strip().lower() in ("0", "false", "no", "off"):
        log.info("keep-awake off (KEEP_AWAKE=0)")
        return False
    if not (platform or sys.platform).startswith("win"):
        return False
    if kernel32 is None:
        import ctypes
        kernel32 = ctypes.windll.kernel32
    ok = bool(kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
    if ok:
        log.info("keep-awake on: Windows will not idle-sleep while this bot runs (lid close still sleeps)")
    else:
        log.warning("keep-awake request refused by Windows; the PC may sleep and miss candles")
    return ok
