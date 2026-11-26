"""External heartbeat: one GET to the user's monitor after each processed candle; never crashes, never logs the URL."""

import json
import logging

from bot.heartbeat import ping, recent_ok

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
