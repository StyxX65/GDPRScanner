"""
Route and engine tests for the Google Workspace scan module.

Covers:
  - GET  /api/google/scan/users  — auth guard, user list, error propagation
  - POST /api/google/scan/start  — auth guard, concurrency lock, successful start, lock release
  - POST /api/google/scan/cancel — abort signal
  - _run_google_scan             — no-connector broadcast, CPR hit flagging, source_type tagging
"""
from __future__ import annotations
import threading
import time
from unittest.mock import MagicMock

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def flask_app():
    import gdpr_scanner
    gdpr_scanner.app.config["TESTING"] = True
    gdpr_scanner.app.config["WTF_CSRF_ENABLED"] = False
    return gdpr_scanner.app


@pytest.fixture()
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


@pytest.fixture()
def mock_google_connector(monkeypatch):
    from routes import state
    conn = MagicMock()
    conn.list_users.return_value = []
    monkeypatch.setattr(state, "google_connector", conn)
    return conn


@pytest.fixture(autouse=True)
def clean_google_state():
    yield
    from routes import state
    # Release the Google scan lock if a test left it acquired
    acquired = state._google_scan_lock.acquire(blocking=False)
    if acquired:
        state._google_scan_lock.release()
    state._google_scan_abort.clear()


# ── GET /api/google/scan/users ────────────────────────────────────────────────

class TestGoogleScanUsers:
    def test_not_connected_returns_401(self, client, monkeypatch):
        from routes import state
        monkeypatch.setattr(state, "google_connector", None)
        r = client.get("/api/google/scan/users")
        assert r.status_code == 401
        assert r.json["error"] == "not connected"

    def test_returns_user_list(self, client, mock_google_connector):
        mock_google_connector.list_users.return_value = [
            {"id": "1", "email": "alice@test.dk", "displayName": "Alice", "userRole": "student"},
        ]
        r = client.get("/api/google/scan/users")
        assert r.status_code == 200
        assert len(r.json["users"]) == 1
        assert r.json["users"][0]["email"] == "alice@test.dk"

    def test_returns_empty_list_when_no_users(self, client, mock_google_connector):
        mock_google_connector.list_users.return_value = []
        r = client.get("/api/google/scan/users")
        assert r.status_code == 200
        assert r.json["users"] == []

    def test_connector_error_returns_500(self, client, mock_google_connector):
        mock_google_connector.list_users.side_effect = Exception("Admin SDK unavailable")
        r = client.get("/api/google/scan/users")
        assert r.status_code == 500
        assert "error" in r.json


# ── POST /api/google/scan/start ───────────────────────────────────────────────

class TestGoogleScanStart:
    def test_not_connected_returns_401(self, client, monkeypatch):
        from routes import state
        monkeypatch.setattr(state, "google_connector", None)
        r = client.post("/api/google/scan/start", json={})
        assert r.status_code == 401
        assert "not connected" in r.json["error"]

    def test_already_running_returns_409(self, client, mock_google_connector):
        from routes import state
        state._google_scan_lock.acquire()
        try:
            r = client.post("/api/google/scan/start", json={})
            assert r.status_code == 409
            assert "already running" in r.json["error"]
        finally:
            state._google_scan_lock.release()

    def test_starts_successfully(self, client, mock_google_connector, monkeypatch):
        import routes.google_scan
        monkeypatch.setattr(routes.google_scan, "_run_google_scan", lambda opts: None)
        r = client.post("/api/google/scan/start", json={})
        assert r.status_code == 200
        assert r.json["status"] == "started"

    def test_abort_event_cleared_on_start(self, client, mock_google_connector, monkeypatch):
        import routes.google_scan
        from routes import state
        state._google_scan_abort.set()
        monkeypatch.setattr(routes.google_scan, "_run_google_scan", lambda opts: None)
        client.post("/api/google/scan/start", json={})
        assert not state._google_scan_abort.is_set()

    def test_lock_released_after_scan_completes(self, client, mock_google_connector, monkeypatch):
        import routes.google_scan
        from routes import state
        done = threading.Event()

        def _fake_scan(opts):
            time.sleep(0.02)
            done.set()

        monkeypatch.setattr(routes.google_scan, "_run_google_scan", _fake_scan)
        r = client.post("/api/google/scan/start", json={})
        assert r.status_code == 200
        assert done.wait(timeout=3), "Scan thread did not complete in time"
        time.sleep(0.05)  # allow finally block to run
        acquired = state._google_scan_lock.acquire(blocking=False)
        assert acquired, "Lock was not released after scan completed"
        state._google_scan_lock.release()

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_lock_released_on_scan_exception(self, client, mock_google_connector, monkeypatch):
        import routes.google_scan
        from routes import state
        done = threading.Event()

        def _failing_scan(opts):
            done.set()
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(routes.google_scan, "_run_google_scan", _failing_scan)
        r = client.post("/api/google/scan/start", json={})
        assert r.status_code == 200
        assert done.wait(timeout=3), "Scan thread did not complete in time"
        time.sleep(0.05)
        acquired = state._google_scan_lock.acquire(blocking=False)
        assert acquired, "Lock was not released after scan raised an exception"
        state._google_scan_lock.release()


# ── POST /api/google/scan/cancel ─────────────────────────────────────────────

class TestGoogleScanCancel:
    def test_sets_abort_event(self, client):
        from routes import state
        state._google_scan_abort.clear()
        r = client.post("/api/google/scan/cancel")
        assert r.status_code == 200
        assert r.json["status"] == "cancelling"
        assert state._google_scan_abort.is_set()

    def test_idempotent_when_not_running(self, client):
        r = client.post("/api/google/scan/cancel")
        assert r.status_code == 200
        assert r.json["status"] == "cancelling"


# ── _run_google_scan engine ───────────────────────────────────────────────────

class TestRunGoogleScan:
    """
    Unit-tests for _run_google_scan() called synchronously with all heavy
    dependencies mocked: broadcast, _scan_bytes, DB, checkpoint I/O.
    """

    def _setup_mocks(self, monkeypatch, conn, scan_bytes_result=None):
        import gdpr_scanner
        import checkpoint
        import scan_engine
        import gdpr_db
        from routes import state

        events = []
        monkeypatch.setattr(state, "google_connector", conn)
        monkeypatch.setattr(gdpr_scanner, "broadcast",
                            lambda evt, data=None: events.append((evt, data or {})))
        monkeypatch.setattr(gdpr_scanner, "_scan_bytes",
                            lambda data, name: scan_bytes_result or {
                                "cprs": [], "pii_counts": None, "emails": [], "phones": []
                            })
        monkeypatch.setattr(checkpoint, "_load_checkpoint", lambda *a, **kw: None)
        monkeypatch.setattr(checkpoint, "_save_checkpoint", lambda *a, **kw: None)
        monkeypatch.setattr(checkpoint, "_clear_checkpoint", lambda *a, **kw: None)
        monkeypatch.setattr(checkpoint, "_load_delta_tokens", lambda: {})
        monkeypatch.setattr(checkpoint, "_save_delta_tokens", lambda *a: None)
        monkeypatch.setattr(scan_engine, "_with_disposition", lambda card, db: card)
        monkeypatch.setattr(gdpr_db, "get_db", lambda *a, **kw: None)

        gdpr_scanner.flagged_items.clear()
        return events

    def _run(self, monkeypatch, conn, options, scan_bytes_result=None):
        import gdpr_scanner
        import routes.google_scan as gs
        events = self._setup_mocks(monkeypatch, conn, scan_bytes_result)
        gs._run_google_scan(options)
        gdpr_scanner.flagged_items.clear()
        return events

    def test_no_connector_broadcasts_error_and_done(self, monkeypatch):
        import gdpr_scanner
        import routes.google_scan as gs
        from routes import state
        events = []
        monkeypatch.setattr(state, "google_connector", None)
        monkeypatch.setattr(gdpr_scanner, "broadcast",
                            lambda evt, data=None: events.append((evt, data or {})))
        gs._run_google_scan({"sources": ["gmail"], "user_emails": ["a@b.dk"], "options": {}})

        assert any(evt == "scan_error" for evt, _ in events)
        assert any(evt == "google_scan_done" for evt, _ in events)

    def test_gmail_item_with_cpr_is_flagged(self, monkeypatch):
        conn = MagicMock()
        conn.list_users.return_value = []
        conn.iter_gmail_messages.return_value = [
            ({"id": "msg1", "name": "report.txt", "size": 1024, "lastModifiedDateTime": "2026-01-01"}, b"content"),
        ]
        cpr_result = {"cprs": [{"formatted": "010101-1234"}], "pii_counts": None, "emails": [], "phones": []}
        events = self._run(monkeypatch, conn,
                           {"sources": ["gmail"], "user_emails": ["a@test.dk"], "options": {}},
                           scan_bytes_result=cpr_result)

        flagged = [d for evt, d in events if evt == "scan_file_flagged"]
        assert len(flagged) == 1

    def test_gmail_item_source_type_is_gmail(self, monkeypatch):
        conn = MagicMock()
        conn.list_users.return_value = []
        conn.iter_gmail_messages.return_value = [
            ({"id": "msg2", "name": "invoice.txt", "size": 512, "lastModifiedDateTime": "2026-01-01"}, b"data"),
        ]
        cpr_result = {"cprs": [{"formatted": "020202-2345"}], "pii_counts": None, "emails": [], "phones": []}
        events = self._run(monkeypatch, conn,
                           {"sources": ["gmail"], "user_emails": ["a@test.dk"], "options": {}},
                           scan_bytes_result=cpr_result)

        flagged = [d for evt, d in events if evt == "scan_file_flagged"]
        assert flagged[0]["source_type"] == "gmail"

    def test_gmail_item_without_pii_not_flagged(self, monkeypatch):
        conn = MagicMock()
        conn.list_users.return_value = []
        conn.iter_gmail_messages.return_value = [
            ({"id": "msg3", "name": "memo.txt", "size": 100}, b"hello world"),
        ]
        events = self._run(monkeypatch, conn,
                           {"sources": ["gmail"], "user_emails": ["a@test.dk"], "options": {}})

        assert not any(evt == "scan_file_flagged" for evt, _ in events)

    def test_gdrive_item_source_type_is_gdrive(self, monkeypatch):
        conn = MagicMock()
        conn.list_users.return_value = []
        conn.iter_gmail_messages.return_value = []
        conn.iter_drive_files.return_value = [
            ({"id": "file1", "name": "doc.docx", "size": 2048, "lastModifiedDateTime": "2026-01-01"}, b"data"),
        ]
        cpr_result = {"cprs": [{"formatted": "030303-3456"}], "pii_counts": None, "emails": [], "phones": []}
        events = self._run(monkeypatch, conn,
                           {"sources": ["gmail", "gdrive"], "user_emails": ["a@test.dk"], "options": {}},
                           scan_bytes_result=cpr_result)

        gdrive = [d for evt, d in events if evt == "scan_file_flagged" and d.get("source_type") == "gdrive"]
        assert len(gdrive) == 1

    def test_scan_done_always_broadcast(self, monkeypatch):
        conn = MagicMock()
        conn.list_users.return_value = []
        conn.iter_gmail_messages.return_value = []
        events = self._run(monkeypatch, conn,
                           {"sources": ["gmail"], "user_emails": ["a@test.dk"], "options": {}})

        done = [d for evt, d in events if evt == "google_scan_done"]
        assert len(done) == 1
        assert "flagged_count" in done[0]
        assert "total_scanned" in done[0]

    def test_scan_done_counts_are_correct(self, monkeypatch):
        conn = MagicMock()
        conn.list_users.return_value = []
        conn.iter_gmail_messages.return_value = [
            ({"id": "m1", "name": "a.txt", "size": 100}, b"x"),
            ({"id": "m2", "name": "b.txt", "size": 100}, b"y"),
        ]
        cpr_result = {"cprs": [{"formatted": "040404-4567"}], "pii_counts": None, "emails": [], "phones": []}
        events = self._run(monkeypatch, conn,
                           {"sources": ["gmail"], "user_emails": ["a@test.dk"], "options": {}},
                           scan_bytes_result=cpr_result)

        done = next(d for evt, d in events if evt == "google_scan_done")
        assert done["total_scanned"] == 2
        assert done["flagged_count"] == 2
