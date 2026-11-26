"""Uptime: a failed candle step is retried before the candle is lost, and the PC is kept awake while a bot runs."""

import asyncio

import pandas as pd

from bot import keepawake
from bot.main import step_with_retry

T0 = pd.Timestamp("2026-11-26 17:00", tz="UTC")


class FlakyEngine:
    def __init__(self, fail: int):
        self.fail, self.calls = fail, []

    def step(self, ts):
        self.calls.append(ts)
        if len(self.calls) <= self.fail:
            raise ConnectionError("getaddrinfo failed")


class Clock:
    """Fake time: sleeping advances the clock instead of waiting."""

    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    async def sleep(self, s):
        self.t += pd.Timedelta(seconds=s)


def run(eng, deadline, clock, sent):
    return asyncio.run(step_with_retry(eng, T0, deadline, delays=(30, 60, 120, 240),
                                       now=clock.now, sleep=clock.sleep, notify=sent.append))


def test_transient_failure_is_retried_on_the_same_candle():
    eng, clock, sent = FlakyEngine(fail=2), Clock(T0), []
    assert run(eng, T0 + pd.Timedelta(minutes=14), clock, sent) is True
    assert eng.calls == [T0, T0, T0]          # always the same candle, never a later one
    assert sent == []                         # recovered, so no alert


def test_persistent_failure_alerts_once_and_stops_before_next_candle():
    eng, clock, sent = FlakyEngine(fail=99), Clock(T0), []
    deadline = T0 + pd.Timedelta(minutes=14)
    assert run(eng, deadline, clock, sent) is False
    assert len(eng.calls) == 5                # first try + 4 retries
    assert clock.t <= deadline
    assert len(sent) == 1 and "ConnectionError" in sent[0]


def test_only_a_lost_candle_logs_step_failed(caplog):
    """bot/alerts.py and the dashboard count 'step failed' lines as lost candles; a recovered retry must not add one."""
    caplog.set_level("INFO", logger="main")
    run(FlakyEngine(fail=2), T0 + pd.Timedelta(minutes=14), Clock(T0), [])
    assert not any(r.getMessage().startswith("step failed") for r in caplog.records)
    caplog.clear()
    run(FlakyEngine(fail=99), T0 + pd.Timedelta(minutes=14), Clock(T0), [])
    lost = [r for r in caplog.records if r.getMessage().startswith("step failed")]
    assert len(lost) == 1 and lost[0].levelname == "ERROR"


def test_no_retry_that_would_run_past_the_deadline():
    eng, clock, sent = FlakyEngine(fail=99), Clock(T0), []
    deadline = T0 + pd.Timedelta(seconds=100)  # room for the 30 s and 60 s retries only
    assert run(eng, deadline, clock, sent) is False
    assert len(eng.calls) == 3
    assert clock.t <= deadline


class FakeKernel32:
    def __init__(self):
        self.flags = []

    def SetThreadExecutionState(self, flags):
        self.flags.append(flags)
        return 1


def test_keep_awake_requests_system_not_display(monkeypatch):
    k = FakeKernel32()
    monkeypatch.delenv("KEEP_AWAKE", raising=False)
    assert keepawake.prevent_sleep(kernel32=k, platform="win32") is True
    assert k.flags == [keepawake.ES_CONTINUOUS | keepawake.ES_SYSTEM_REQUIRED]
    assert not k.flags[0] & keepawake.ES_DISPLAY_REQUIRED   # the screen may still turn off


def test_keep_awake_can_be_switched_off(monkeypatch):
    k = FakeKernel32()
    monkeypatch.setenv("KEEP_AWAKE", "0")
    assert keepawake.prevent_sleep(kernel32=k, platform="win32") is False
    assert k.flags == []


def test_keep_awake_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.delenv("KEEP_AWAKE", raising=False)
    assert keepawake.prevent_sleep(kernel32=None, platform="linux") is False
