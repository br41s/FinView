"""Tests for the startup process-age probe (Cloud Run cold-start breakdown).

/proc/self/stat starts with "pid (comm) state ..." and comm may itself contain
spaces and parentheses, so the helper reads the fields after the *last* ")".
starttime is field 22 of the stat line → index 19 of that remainder.
"""

import io

import backend.app as app_module
from backend.app import _process_age_seconds

# "S" + 18 filler fields → index 19 is starttime (500 ticks since boot).
STAT_LINE = "123 (python3 (x)) S " + " ".join(["0"] * 18) + " 500 0 0 0\n"
UPTIME_LINE = "20.0 0.0\n"


def _fake_open(stat_line: str, uptime_line: str = UPTIME_LINE):
    def fake_open(path, *_args, **_kwargs):
        if path == "/proc/self/stat":
            return io.StringIO(stat_line)
        if path == "/proc/uptime":
            return io.StringIO(uptime_line)
        raise AssertionError(f"unexpected path: {path}")

    return fake_open


def test_process_age_seconds_reads_proc(monkeypatch):
    monkeypatch.setattr("builtins.open", _fake_open(STAT_LINE))
    monkeypatch.setattr(app_module.os, "sysconf", lambda _name: 100)

    # 20.0 s of uptime − 500 ticks / 100 ticks-per-second = 15.0 s.
    assert _process_age_seconds() == 15.0


def test_process_age_seconds_none_without_proc(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("/proc not available")

    monkeypatch.setattr("builtins.open", boom)

    assert _process_age_seconds() is None


def test_process_age_seconds_none_on_malformed_stat(monkeypatch):
    # Too few fields after the last ")" → IndexError, never an exception.
    monkeypatch.setattr("builtins.open", _fake_open("123 (python3) S 0 0\n"))
    monkeypatch.setattr(app_module.os, "sysconf", lambda _name: 100)

    assert _process_age_seconds() is None
