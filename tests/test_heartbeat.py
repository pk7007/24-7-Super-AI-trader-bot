"""External heartbeat: GETs to the user's monitor every 5 minutes while candles succeed; never crashes, never logs the URL."""

import json
import logging

from bot.heartbeat import Pacer, ping, recent_ok


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def pacer(every_s=300):
    clock, sent = FakeClock(), []
    return Pacer("hb.json", every_s=every_s, send=lambda status: sent.append(clock.t), now=clock), clock, sent


def test_pacer_pings_every_five_minutes_while_healthy():
    p, clock, sent = pacer()
    for _ in range(180):              # one hour of 20-second wait slices, one 15-min candle each quarter hour
        p.tick()
        clock.t += 20
        if clock.t % 900 == 0:
            p.candle(True)
    gaps = [b - a for a, b in zip(sent, sent[1:])]
    assert sent[0] == 0                         # pings as soon as the bot starts
    assert max(gaps) <= 300 + 20                # never more than 5 min (+ one slice) apart
    assert min(gaps) > 0 and len(sent) >= 12    # no duplicate pings at the same moment


def test_skipped_candle_stops_pings_until_a_candle_succeeds():
    p, clock, sent = pacer()
    p.tick()
    p.candle(False)                   # every retry failed: candle skipped
    n = len(sent)
    for _ in range(60):               # 20 minutes of waiting
        clock.t += 20
        p.tick()
    assert len(sent) == n             # silent, so the outside monitor alerts
    p.candle(True)
    assert len(sent) == n + 1 and sent[-1] == clock.t   # recovery pings at once
    clock.t += 300
    p.tick()
    assert len(sent) == n + 2         # and the 5-minute rhythm resumes


def test_successful_candle_restarts_the_five_minute_timer():
    p, clock, sent = pacer()
    p.tick()                          # t=0
    clock.t = 200
    p.candle(True)                    # t=200
    clock.t = 400
    p.tick()
    assert sent == [0, 200]           # 400 is only 200 s after the candle ping
    clock.t = 500
    p.tick()
    assert sent == [0, 200, 500]

URL = "https://hc-ping.example/secret-uuid"


class Opener:
    def __init__(self, fail=False):
        self.urls, self.fail = [], fail

    def __call__(self, url, timeout):
        self.urls.append(url)
        if self.fail:
            raise OSError("no route")


def test_not_configured_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("HEARTBEAT_URL", raising=False)
    op = Opener()
    assert ping(tmp_path / "hb.json", opener=op) is None
    assert op.urls == [] and not (tmp_path / "hb.json").exists()


def test_ping_records_success_without_the_url(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_URL", URL)
    op = Opener()
    assert ping(tmp_path / "hb.json", opener=op) is True
    assert op.urls == [URL]
    text = (tmp_path / "hb.json").read_text()
    assert "secret-uuid" not in text and json.loads(text)["last_ok_utc"]
    assert recent_ok(tmp_path / "hb.json", minutes=60)


def test_failure_is_logged_never_raised_and_url_never_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("HEARTBEAT_URL", URL)
    caplog.set_level(logging.WARNING, logger="heartbeat")
    assert ping(tmp_path / "hb.json", opener=Opener(fail=True)) is False
    assert json.loads((tmp_path / "hb.json").read_text())["fails"] == 1
    assert "secret-uuid" not in caplog.text and "OSError" in caplog.text
    assert not recent_ok(tmp_path / "hb.json", minutes=60)


def test_only_https_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_URL", "http://insecure.example/x")
    op = Opener()
    assert ping(tmp_path / "hb.json", opener=op) is False and op.urls == []
