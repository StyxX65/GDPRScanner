"""
Integration tests for Flask routes — uses the real Flask test client.

Strategy
--------
- ``flask_app``  (module-scope) — imports gdpr_scanner once, enables TESTING mode.
- ``client``     (function-scope) — fresh test_client() per test.
- ``db_patch``   (function-scope) — replaces routes.database._get_db with a ScanDB
                  backed by a tmp_path so tests never touch ~/.gdprscanner.
                  Also sets routes.database.DB_OK = True.
- ``mock_connector`` — sets routes.state.connector to a MagicMock so routes
                  that require authentication pass the ``if not state.connector``
                  guard.
- ``clean_state`` — autouse, resets routes.state.flagged_items and ensures the
                  scan lock is released between tests.
"""
import io
import threading
import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def db_patch(tmp_path, monkeypatch):
    """Point routes.database and routes.export _get_db at a fresh ScanDB in a temp dir."""
    from gdpr_db import ScanDB
    import routes.database, routes.export
    db = ScanDB(str(tmp_path / "test.db"))
    monkeypatch.setattr(routes.database, "_get_db", lambda: db)
    monkeypatch.setattr(routes.database, "DB_OK", True)
    monkeypatch.setattr(routes.export, "_get_db", lambda: db)
    monkeypatch.setattr(routes.export, "DB_OK", True)
    return db


@pytest.fixture()
def mock_connector(monkeypatch):
    """Satisfy the connector guard in scan routes.

    /api/scan/start is now handled exclusively by the blueprint (routes/scan.py),
    which checks ``state.connector``.  Patching state.connector is sufficient.
    """
    from routes import state
    conn = MagicMock()
    monkeypatch.setattr(state, "connector", conn)
    return conn


@pytest.fixture(autouse=True)
def clean_state():
    """Wipe in-memory scan state and ensure the scan lock is free after each test."""
    from routes import state
    yield
    # Clear in-memory results so export tests don't bleed into each other
    state.flagged_items.clear()
    # Release the lock if a test left it held (e.g. a failed scan-start test)
    if not state._scan_lock.acquire(blocking=False):
        pass  # still held — leave it; the test that set it is responsible
    else:
        state._scan_lock.release()


# ---------------------------------------------------------------------------
# /api/scan/status
# ---------------------------------------------------------------------------

class TestScanStatus:
    def test_idle_returns_not_running(self, client):
        r = client.get("/api/scan/status")
        assert r.status_code == 200
        data = r.get_json()
        assert data["running"] is False

    def test_scan_id_is_none_when_idle(self, client):
        r = client.get("/api/scan/status")
        data = r.get_json()
        assert "scan_id" in data
        assert data["scan_id"] is None


# ---------------------------------------------------------------------------
# /api/scan/start
# ---------------------------------------------------------------------------

class TestScanStart:
    def test_unauthenticated_returns_401(self, client, monkeypatch):
        from routes import state
        monkeypatch.setattr(state, "connector", None)
        r = client.post("/api/scan/start", json={})
        assert r.status_code == 401
        assert "not authenticated" in r.get_json()["error"]

    def test_lock_held_returns_409(self, client, mock_connector):
        from routes import state
        # Hold the lock as if a scan were already running
        acquired = state._scan_lock.acquire(blocking=False)
        assert acquired, "Lock should be free at test start"
        try:
            r = client.post("/api/scan/start", json={})
            assert r.status_code == 409
            assert "already running" in r.get_json()["error"]
        finally:
            state._scan_lock.release()

    def test_authenticated_returns_started(self, client, mock_connector, monkeypatch):
        import scan_engine
        from routes import state
        # Stub run_scan so the background thread finishes instantly
        monkeypatch.setattr(scan_engine, "run_scan", lambda opts: None)
        r = client.post("/api/scan/start", json={"sources": ["email"]})
        assert r.status_code == 200
        assert r.get_json()["status"] == "started"
        # Give the background thread time to release the lock
        deadline = time.time() + 2.0
        while not state._scan_lock.acquire(blocking=False):
            assert time.time() < deadline, "scan lock was never released"
            time.sleep(0.05)
        state._scan_lock.release()


# ---------------------------------------------------------------------------
# /api/scan/stop
# ---------------------------------------------------------------------------

class TestScanStop:
    def test_stop_always_returns_200(self, client):
        r = client.post("/api/scan/stop")
        assert r.status_code == 200
        assert r.get_json()["status"] == "stopping"


# ---------------------------------------------------------------------------
# /api/db/stats
# ---------------------------------------------------------------------------

class TestDbStats:
    def test_without_db_returns_503(self, client, monkeypatch):
        import routes.database
        monkeypatch.setattr(routes.database, "DB_OK", False)
        r = client.get("/api/db/stats")
        assert r.status_code == 503

    def test_with_db_returns_200(self, client, db_patch):
        # The direct route in gdpr_scanner.py (which takes precedence over the
        # blueprint) returns get_stats() directly — an empty dict for a fresh DB.
        r = client.get("/api/db/stats")
        assert r.status_code == 200
        assert isinstance(r.get_json(), dict)


# ---------------------------------------------------------------------------
# /api/db/disposition
# ---------------------------------------------------------------------------

class TestDisposition:
    def test_set_disposition_missing_item_id_returns_400(self, client, db_patch):
        r = client.post("/api/db/disposition", json={"status": "retain-legal"})
        assert r.status_code == 400
        assert "item_id" in r.get_json()["error"]

    def test_set_disposition_saves_and_get_returns_it(self, client, db_patch):
        item_id = "test-item-abc123"

        # Set
        r = client.post("/api/db/disposition", json={
            "item_id":    item_id,
            "status":     "retain-legal",
            "legal_basis": "GDPR Art. 6(1)(c)",
            "notes":      "Required by law",
        })
        assert r.status_code == 200
        assert r.get_json()["status"] == "saved"

        # Get
        r2 = client.get(f"/api/db/disposition/{item_id}")
        assert r2.status_code == 200
        data = r2.get_json()
        assert data["status"] == "retain-legal"

    def test_get_disposition_unknown_id_returns_unreviewed(self, client, db_patch):
        r = client.get("/api/db/disposition/no-such-item")
        assert r.status_code == 200
        assert r.get_json()["status"] == "unreviewed"

    def test_without_db_returns_503(self, client, monkeypatch):
        import routes.database
        monkeypatch.setattr(routes.database, "DB_OK", False)
        r = client.post("/api/db/disposition",
                        json={"item_id": "x", "status": "retain-legal"})
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# /api/export_excel
# ---------------------------------------------------------------------------

class TestExportExcel:
    XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_empty_db_returns_workbook(self, client, db_patch):
        r = client.get("/api/export_excel")
        assert r.status_code == 200
        assert self.XLSX_MIME in r.content_type
        # Must be a valid zip/xlsx (PK magic bytes)
        assert r.data[:2] == b"PK"

    def test_with_items_in_memory_includes_data(self, client, db_patch):
        from routes import state
        state.flagged_items.append({
            "id":         "item-001",
            "name":       "test_file.docx",
            "source":     "onedrive",
            "cpr_count":  2,
            "face_count": 0,
            "account_name": "Anna Hansen",
            "user_role":  "staff",
            "modified":   "2025-01-15T10:00:00",
            "size_kb":    42,
            "url":        "https://example.com/file",
        })
        r = client.get("/api/export_excel")
        assert r.status_code == 200
        assert r.data[:2] == b"PK"
        # Workbook with data is larger than a skeleton workbook
        assert len(r.data) > 4096


# ---------------------------------------------------------------------------
# /api/export_article30
# ---------------------------------------------------------------------------

class TestExportArticle30:
    DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_no_items_returns_400(self, client, db_patch):
        """Article 30 export requires at least one flagged item."""
        r = client.get("/api/export_article30")
        assert r.status_code == 400
        assert "scan first" in r.get_json()["error"].lower()

    def test_with_items_returns_docx(self, client, db_patch):
        from routes import state
        state.flagged_items.append({
            "id":           "item-002",
            "name":         "payroll.xlsx",
            "source":       "email",
            "cpr_count":    1,
            "account_name": "Test User",
            "user_role":    "staff",
            "modified":     "2025-03-01T09:00:00",
            "size_kb":      10,
        })
        r = client.get("/api/export_article30")
        assert r.status_code == 200
        assert self.DOCX_MIME in r.content_type
        # DOCX is a zip — check PK magic bytes
        assert r.data[:2] == b"PK"
