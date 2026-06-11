"""
Tests for the software-update routes (routes/updates.py).

All git interaction is mocked — no test touches the real repository,
the network, or restarts the process.
"""
from __future__ import annotations
import subprocess

import pytest


@pytest.fixture(scope="module")
def flask_app():
    import gdpr_scanner
    gdpr_scanner.app.config["TESTING"] = True
    return gdpr_scanner.app


@pytest.fixture()
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


def _cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def _fake_git(*, local="aaaaaaa1", remote="aaaaaaa1", branch="main",
              fetch_rc=0, dirty=False, reqs_changed=False, merge_rc=0,
              commits=""):
    """Build a _git() replacement dispatching on the git subcommand."""
    calls = []

    def fake(*args, timeout=None):
        calls.append(args)
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return _cp(stdout=branch + "\n")
        if args == ("rev-parse", "HEAD"):
            return _cp(stdout=local + "\n")
        if args[0] == "rev-parse":
            return _cp(stdout=remote + "\n")
        if args[0] == "fetch":
            return _cp(returncode=fetch_rc, stderr="fetch failed" if fetch_rc else "")
        if args[0] == "log":
            return _cp(stdout=commits)
        if args[0] == "diff-index":
            return _cp(returncode=1 if dirty else 0)
        if args[0] == "diff":
            return _cp(returncode=1 if reqs_changed else 0)
        if args[0] == "merge":
            return _cp(returncode=merge_rc, stderr="not a fast-forward" if merge_rc else "")
        if args[0] == "stash":
            return _cp()
        raise AssertionError(f"unexpected git call: {args}")

    fake.calls = calls
    return fake


@pytest.fixture(autouse=True)
def supported(monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_supported", lambda: True)


@pytest.fixture(autouse=True)
def no_audit(monkeypatch):
    import gdpr_db
    monkeypatch.setattr(gdpr_db, "log_audit_event", lambda *a, **k: None)


# ── /api/update/check ─────────────────────────────────────────────────────────

def test_check_unsupported(client, monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_supported", lambda: False)
    r = client.get("/api/update/check")
    assert r.status_code == 200
    assert r.get_json() == {"supported": False}


def test_check_up_to_date(client, monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_git", _fake_git())
    d = client.get("/api/update/check").get_json()
    assert d["supported"] and d["up_to_date"]
    assert d["commits"] == []


def test_check_update_available(client, monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_git", _fake_git(
        local="aaaaaaa1", remote="bbbbbbb2",
        commits="bbbbbbb2 Fix thing\nccccccc3 Add thing\n"))
    d = client.get("/api/update/check").get_json()
    assert d["up_to_date"] is False
    assert d["current"] == "aaaaaaa"
    assert d["latest"] == "bbbbbbb"
    assert len(d["commits"]) == 2


def test_check_fetch_failure(client, monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_git", _fake_git(fetch_rc=1))
    d = client.get("/api/update/check").get_json()
    assert d["supported"] is True
    assert "fetch failed" in d["error"]


# ── /api/update/apply ─────────────────────────────────────────────────────────

def test_apply_up_to_date_is_noop(client, monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_git", _fake_git())
    monkeypatch.setattr(upd, "_schedule_restart", lambda *a, **k: pytest.fail("must not restart"))
    r = client.post("/api/update/apply")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["updated"] is False


def test_apply_refused_while_scan_running(client, monkeypatch):
    import routes.updates as upd
    from routes import state
    monkeypatch.setattr(upd, "_git", _fake_git(remote="bbbbbbb2"))
    monkeypatch.setattr(upd, "_schedule_restart", lambda *a, **k: pytest.fail("must not restart"))
    assert state._scan_lock.acquire(blocking=False)
    try:
        r = client.post("/api/update/apply")
    finally:
        state._scan_lock.release()
    assert r.status_code == 409
    assert r.get_json()["code"] == "scan_running"


def test_apply_happy_path(client, monkeypatch):
    import routes.updates as upd
    fake = _fake_git(remote="bbbbbbb2", commits="bbbbbbb2 Fix\n")
    monkeypatch.setattr(upd, "_git", fake)
    restarts = []
    monkeypatch.setattr(upd, "_schedule_restart", lambda *a, **k: restarts.append(1))
    r = client.post("/api/update/apply")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] and d["updated"] and d["restarting"]
    assert d["from"] == "aaaaaaa" and d["to"] == "bbbbbbb"
    assert restarts == [1]
    assert ("merge", "--ff-only", "origin/main") in fake.calls
    # tree was clean — no stash
    assert not any(c[0] == "stash" for c in fake.calls)


def test_apply_stashes_dirty_tree(client, monkeypatch):
    import routes.updates as upd
    fake = _fake_git(remote="bbbbbbb2", dirty=True)
    monkeypatch.setattr(upd, "_git", fake)
    monkeypatch.setattr(upd, "_schedule_restart", lambda *a, **k: None)
    r = client.post("/api/update/apply")
    assert r.status_code == 200
    assert any(c[0] == "stash" for c in fake.calls)


def test_apply_merge_failure(client, monkeypatch):
    import routes.updates as upd
    monkeypatch.setattr(upd, "_git", _fake_git(remote="bbbbbbb2", merge_rc=1))
    monkeypatch.setattr(upd, "_schedule_restart", lambda *a, **k: pytest.fail("must not restart"))
    r = client.post("/api/update/apply")
    assert r.status_code == 409
    d = r.get_json()
    assert d["code"] == "merge_failed"
    assert "fast-forward" in d["error"]


def test_apply_installs_requirements_when_changed(client, monkeypatch):
    import routes.updates as upd
    fake = _fake_git(remote="bbbbbbb2", reqs_changed=True)
    monkeypatch.setattr(upd, "_git", fake)
    monkeypatch.setattr(upd, "_schedule_restart", lambda *a, **k: None)
    pip_calls = []
    monkeypatch.setattr(upd.subprocess, "run",
                        lambda cmd, **kw: pip_calls.append(cmd) or _cp())
    r = client.post("/api/update/apply")
    assert r.status_code == 200
    assert len(pip_calls) == 1
    assert "pip" in pip_calls[0] and "-r" in pip_calls[0]


# ── Restart fd hygiene ────────────────────────────────────────────────────────

def test_mark_fds_cloexec_unmarks_inheritable_socket():
    """Werkzeug sets the listening socket inheritable; the restart must undo
    that or the socket leaks through execv and squats on the port."""
    import socket
    import routes.updates as upd
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.set_inheritable(True)
        assert s.get_inheritable() is True
        upd._mark_fds_cloexec()
        assert s.get_inheritable() is False
    finally:
        s.close()


# ── /api/update/settings ──────────────────────────────────────────────────────

def test_settings_roundtrip(client, monkeypatch):
    import routes.updates as upd
    store = {"auto_update": False}
    monkeypatch.setattr(upd, "get_update_config", lambda: dict(store))
    monkeypatch.setattr(upd, "save_update_config",
                        lambda v: store.__setitem__("auto_update", bool(v)))
    d = client.get("/api/update/settings").get_json()
    assert d == {"supported": True, "auto_update": False}
    r = client.post("/api/update/settings", json={"auto_update": True})
    assert r.get_json() == {"ok": True}
    assert store["auto_update"] is True
    d = client.get("/api/update/settings").get_json()
    assert d["auto_update"] is True
