"""
Route integration tests — security-sensitive paths and data-correctness contracts.

Covers:
  - Viewer token CRUD and scope validation
  - GET /api/db/flagged role and user scope enforcement
  - POST /api/db/disposition/bulk — only updates selected items
  - Viewer PIN set / verify / rate-limit / clear
  - Interface PIN set / gate / clear
  - Scan lock always released (even when run_scan raises)
  - GET /api/db/sessions basic shape
  - Profile routes CRUD and rename
"""
from __future__ import annotations
import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module-level app fixture (shared with test_routes.py via flask_app)
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
    from routes import state
    conn = MagicMock()
    monkeypatch.setattr(state, "connector", conn)
    return conn


@pytest.fixture(autouse=True)
def clean_state():
    from routes import state
    yield
    state.flagged_items.clear()
    if not state._scan_lock.acquire(blocking=False):
        pass
    else:
        state._scan_lock.release()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_scan(db, items: list[dict]) -> int:
    """Create a completed scan and persist items.  Returns the scan_id."""
    scan_id = db.begin_scan({"sources": ["email"], "user_ids": [], "options": {}})
    for item in items:
        db.save_item(scan_id, item)
    db.finish_scan(scan_id, total_scanned=len(items))
    return scan_id


def _item(item_id: str, role: str = "staff", account_id: str = "") -> dict:
    return {
        "id":         item_id,
        "name":       f"{item_id}.docx",
        "source":     "email",
        "source_type": "email",
        "account_id": account_id or f"{item_id}@school.dk",
        "user_role":  role,
        "cpr_count":  1,
        "face_count": 0,
        "size_kb":    10,
        "modified":   "2025-01-01T00:00:00",
    }


def _clear_viewer_pins():
    """Remove both viewer and interface PINs between tests."""
    from app_config import clear_viewer_pin, clear_interface_pin
    clear_viewer_pin()
    clear_interface_pin()


# ---------------------------------------------------------------------------
# Viewer token CRUD
# ---------------------------------------------------------------------------

class TestViewerTokenCRUD:
    def test_create_and_list(self, client):
        r = client.post("/api/viewer/tokens",
                        json={"label": "Test token", "expires_days": 7})
        assert r.status_code == 201
        data = r.get_json()
        assert "token" in data
        tok = data["token"]

        r2 = client.get("/api/viewer/tokens")
        assert r2.status_code == 200
        tokens = r2.get_json()
        assert any(t["token"] == tok for t in tokens)

    def test_delete_existing_token(self, client):
        r = client.post("/api/viewer/tokens", json={"label": "to-delete"})
        tok = r.get_json()["token"]

        r2 = client.delete(f"/api/viewer/tokens/{tok}")
        assert r2.status_code == 200
        assert r2.get_json()["ok"] is True

        r3 = client.get("/api/viewer/tokens")
        tokens = r3.get_json()
        assert not any(t["token"] == tok for t in tokens)

    def test_delete_nonexistent_token_returns_404(self, client):
        r = client.delete("/api/viewer/tokens/doesnotexist123")
        assert r.status_code == 404

    def test_validate_valid_token(self, client):
        tok = client.post("/api/viewer/tokens", json={}).get_json()["token"]
        r = client.post("/api/viewer/tokens/validate", json={"token": tok})
        assert r.status_code == 200
        assert r.get_json()["valid"] is True

    def test_validate_invalid_token(self, client):
        r = client.post("/api/viewer/tokens/validate",
                        json={"token": "notarealtoken00000000"})
        assert r.status_code == 401
        assert r.get_json()["valid"] is False


class TestViewerTokenScopeValidation:
    def test_role_and_user_mutually_exclusive(self, client):
        r = client.post("/api/viewer/tokens", json={
            "scope": {"role": "student", "user": "alice@school.dk"}
        })
        assert r.status_code == 400
        assert "mutually exclusive" in r.get_json()["error"]

    def test_invalid_role_value(self, client):
        r = client.post("/api/viewer/tokens", json={
            "scope": {"role": "teacher"}
        })
        assert r.status_code == 400
        assert "role" in r.get_json()["error"]

    def test_user_email_must_contain_at(self, client):
        r = client.post("/api/viewer/tokens", json={
            "scope": {"user": "notanemail"}
        })
        assert r.status_code == 400
        assert "email" in r.get_json()["error"].lower()

    def test_valid_role_scope_stored(self, client):
        r = client.post("/api/viewer/tokens",
                        json={"scope": {"role": "student"}})
        assert r.status_code == 201
        assert r.get_json()["scope"] == {"role": "student"}

    def test_valid_user_scope_stored(self, client):
        r = client.post("/api/viewer/tokens", json={
            "scope": {
                "user": ["alice@m365.dk", "alice@gws.dk"],
                "display_name": "Alice Smith",
            }
        })
        assert r.status_code == 201
        scope = r.get_json()["scope"]
        assert scope["user"] == ["alice@m365.dk", "alice@gws.dk"]
        assert scope["display_name"] == "Alice Smith"


# ---------------------------------------------------------------------------
# GET /api/db/flagged — scope enforcement
# ---------------------------------------------------------------------------

class TestFlaggedScopeEnforcement:
    def test_no_scope_returns_all_items(self, client, db_patch):
        _seed_scan(db_patch, [
            _item("s1", role="student"),
            _item("s2", role="staff"),
        ])
        r = client.get("/api/db/flagged")
        assert r.status_code == 200
        ids = {row["id"] for row in r.get_json()}
        assert "s1" in ids
        assert "s2" in ids

    def test_role_scope_student_excludes_staff(self, client, db_patch):
        _seed_scan(db_patch, [
            _item("r1", role="student"),
            _item("r2", role="staff"),
        ])
        with client.session_transaction() as sess:
            sess["viewer_ok"] = True
            sess["viewer_scope"] = {"role": "student"}
        r = client.get("/api/db/flagged")
        ids = {row["id"] for row in r.get_json()}
        assert "r1" in ids
        assert "r2" not in ids

    def test_role_scope_staff_excludes_students(self, client, db_patch):
        _seed_scan(db_patch, [
            _item("t1", role="student"),
            _item("t2", role="staff"),
        ])
        with client.session_transaction() as sess:
            sess["viewer_ok"] = True
            sess["viewer_scope"] = {"role": "staff"}
        r = client.get("/api/db/flagged")
        ids = {row["id"] for row in r.get_json()}
        assert "t2" in ids
        assert "t1" not in ids

    def test_user_scope_returns_only_matching_account_id(self, client, db_patch):
        _seed_scan(db_patch, [
            _item("u1", account_id="alice@m365.dk"),
            _item("u2", account_id="bob@m365.dk"),
        ])
        with client.session_transaction() as sess:
            sess["viewer_ok"] = True
            sess["viewer_scope"] = {"user": ["alice@m365.dk"]}
        r = client.get("/api/db/flagged")
        ids = {row["id"] for row in r.get_json()}
        assert "u1" in ids
        assert "u2" not in ids

    def test_user_scope_matches_both_platform_emails(self, client, db_patch):
        # Same person — M365 UPN and GWS email both in scope
        _seed_scan(db_patch, [
            _item("p1", account_id="alice@m365.dk"),
            _item("p2", account_id="alice@gws.dk"),
            _item("p3", account_id="bob@m365.dk"),
        ])
        with client.session_transaction() as sess:
            sess["viewer_ok"] = True
            sess["viewer_scope"] = {"user": ["alice@m365.dk", "alice@gws.dk"]}
        r = client.get("/api/db/flagged")
        ids = {row["id"] for row in r.get_json()}
        assert "p1" in ids
        assert "p2" in ids
        assert "p3" not in ids

    def test_user_scope_case_insensitive(self, client, db_patch):
        _seed_scan(db_patch, [_item("ci1", account_id="Alice@M365.dk")])
        with client.session_transaction() as sess:
            sess["viewer_ok"] = True
            sess["viewer_scope"] = {"user": ["alice@m365.dk"]}
        r = client.get("/api/db/flagged")
        ids = {row["id"] for row in r.get_json()}
        assert "ci1" in ids

    def test_ref_param_loads_historical_session(self, client, db_patch):
        # Push first scan >300 s into the past so it occupies its own session window.
        old_id = _seed_scan(db_patch, [_item("h1")])
        db_patch._connect().execute(
            "UPDATE scans SET started_at = started_at - 400 WHERE id = ?", (old_id,)
        )
        db_patch._connect().commit()
        _seed_scan(db_patch, [_item("h2")])

        r = client.get(f"/api/db/flagged?ref={old_id}")
        ids = {row["id"] for row in r.get_json()}
        assert "h1" in ids
        # h2 belongs to a different (newer) session window — must not appear
        assert "h2" not in ids


# ---------------------------------------------------------------------------
# POST /api/db/disposition/bulk
# ---------------------------------------------------------------------------

class TestBulkDisposition:
    def test_updates_selected_items(self, client, db_patch):
        _seed_scan(db_patch, [_item("b1"), _item("b2"), _item("b3")])
        r = client.post("/api/db/disposition/bulk", json={
            "item_ids": ["b1", "b2"],
            "status": "retain-legal",
        })
        assert r.status_code == 200
        assert r.get_json()["saved"] == 2

        assert db_patch.get_disposition("b1")["status"] == "retain-legal"
        assert db_patch.get_disposition("b2")["status"] == "retain-legal"

    def test_unselected_item_unchanged(self, client, db_patch):
        _seed_scan(db_patch, [_item("c1"), _item("c2")])
        client.post("/api/db/disposition/bulk", json={
            "item_ids": ["c1"],
            "status": "delete-scheduled",
        })
        d = db_patch.get_disposition("c2")
        # c2 was not in the bulk request — must remain unreviewed
        assert d is None or d.get("status", "unreviewed") == "unreviewed"

    def test_missing_item_ids_returns_400(self, client, db_patch):
        r = client.post("/api/db/disposition/bulk",
                        json={"status": "retain-legal"})
        assert r.status_code == 400

    def test_missing_status_returns_400(self, client, db_patch):
        r = client.post("/api/db/disposition/bulk",
                        json={"item_ids": ["x"]})
        assert r.status_code == 400

    def test_without_db_returns_503(self, client, monkeypatch):
        import routes.database
        monkeypatch.setattr(routes.database, "DB_OK", False)
        r = client.post("/api/db/disposition/bulk",
                        json={"item_ids": ["x"], "status": "retain-legal"})
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# Viewer PIN
# ---------------------------------------------------------------------------

class TestViewerPin:
    def setup_method(self):
        _clear_viewer_pins()

    def teardown_method(self):
        _clear_viewer_pins()

    def test_status_no_pin(self, client):
        r = client.get("/api/viewer/pin")
        assert r.status_code == 200
        assert r.get_json()["pin_set"] is False

    def test_set_and_status_reflects_set(self, client):
        client.post("/api/viewer/pin", json={"pin": "1234"})
        r = client.get("/api/viewer/pin")
        assert r.get_json()["pin_set"] is True

    def test_set_too_short_rejected(self, client):
        r = client.post("/api/viewer/pin", json={"pin": "123"})
        assert r.status_code == 400

    def test_set_too_long_rejected(self, client):
        r = client.post("/api/viewer/pin", json={"pin": "123456789"})
        assert r.status_code == 400

    def test_set_non_digits_rejected(self, client):
        r = client.post("/api/viewer/pin", json={"pin": "abcd"})
        assert r.status_code == 400

    def test_verify_correct_pin_sets_session(self, client):
        client.post("/api/viewer/pin", json={"pin": "4321"})
        r = client.post("/api/viewer/pin/verify", json={"pin": "4321"})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_verify_wrong_pin_returns_401(self, client):
        client.post("/api/viewer/pin", json={"pin": "4321"})
        r = client.post("/api/viewer/pin/verify", json={"pin": "9999"})
        assert r.status_code == 401

    def test_verify_rate_limit_after_5_failures(self, client):
        client.post("/api/viewer/pin", json={"pin": "5678"})
        from routes.viewer import _pin_attempts
        _pin_attempts.clear()
        for _ in range(5):
            client.post("/api/viewer/pin/verify", json={"pin": "0000"})
        r = client.post("/api/viewer/pin/verify", json={"pin": "0000"})
        assert r.status_code == 429
        _pin_attempts.clear()

    def test_change_pin_requires_current(self, client):
        client.post("/api/viewer/pin", json={"pin": "1111"})
        r = client.post("/api/viewer/pin",
                        json={"pin": "2222", "current_pin": "9999"})
        assert r.status_code == 403

    def test_change_pin_with_correct_current(self, client):
        client.post("/api/viewer/pin", json={"pin": "1111"})
        r = client.post("/api/viewer/pin",
                        json={"pin": "2222", "current_pin": "1111"})
        assert r.status_code == 200
        # Old PIN no longer valid
        r2 = client.post("/api/viewer/pin/verify", json={"pin": "1111"})
        assert r2.status_code == 401

    def test_clear_pin_requires_current(self, client):
        client.post("/api/viewer/pin", json={"pin": "3333"})
        r = client.delete("/api/viewer/pin", json={"current_pin": "0000"})
        assert r.status_code == 403

    def test_clear_pin_with_correct_current(self, client):
        client.post("/api/viewer/pin", json={"pin": "3333"})
        r = client.delete("/api/viewer/pin", json={"current_pin": "3333"})
        assert r.status_code == 200
        assert client.get("/api/viewer/pin").get_json()["pin_set"] is False


# ---------------------------------------------------------------------------
# Interface PIN
# ---------------------------------------------------------------------------

class TestInterfacePin:
    def setup_method(self):
        _clear_viewer_pins()

    def teardown_method(self):
        _clear_viewer_pins()

    def test_status_no_pin(self, client):
        r = client.get("/api/interface/pin")
        assert r.get_json()["pin_set"] is False

    def test_set_and_verify(self, client):
        r = client.post("/api/interface/pin", json={"pin": "7777"})
        assert r.status_code == 200
        # Gate is now active — authenticate before the status check
        with client.session_transaction() as sess:
            sess["interface_ok"] = True
        assert client.get("/api/interface/pin").get_json()["pin_set"] is True

    def test_non_digit_rejected(self, client):
        r = client.post("/api/interface/pin", json={"pin": "abcd"})
        assert r.status_code == 400

    def test_set_requires_current_when_set(self, client):
        client.post("/api/interface/pin", json={"pin": "7777"})
        with client.session_transaction() as sess:
            sess["interface_ok"] = True
        r = client.post("/api/interface/pin",
                        json={"pin": "8888", "current_pin": "0000"})
        assert r.status_code == 403

    def test_clear_requires_current(self, client):
        client.post("/api/interface/pin", json={"pin": "7777"})
        with client.session_transaction() as sess:
            sess["interface_ok"] = True
        r = client.delete("/api/interface/pin", json={"current_pin": "0000"})
        assert r.status_code == 403

    def test_clear_with_correct_current(self, client):
        client.post("/api/interface/pin", json={"pin": "7777"})
        with client.session_transaction() as sess:
            sess["interface_ok"] = True
        r = client.delete("/api/interface/pin", json={"current_pin": "7777"})
        assert r.status_code == 200
        assert client.get("/api/interface/pin").get_json()["pin_set"] is False


# ---------------------------------------------------------------------------
# Scan lock released on run_scan() exception
# ---------------------------------------------------------------------------

class TestScanLockReleasedOnError:
    def test_lock_released_when_run_scan_raises(self, client, mock_connector,
                                                monkeypatch):
        import scan_engine
        from routes import state

        def _boom(opts):
            raise RuntimeError("simulated scan failure")

        monkeypatch.setattr(scan_engine, "run_scan", _boom)
        r = client.post("/api/scan/start", json={"sources": ["email"]})
        assert r.status_code == 200

        # Wait for the background thread to finish and release the lock
        deadline = time.time() + 2.0
        while True:
            acquired = state._scan_lock.acquire(blocking=False)
            if acquired:
                state._scan_lock.release()
                break
            assert time.time() < deadline, "scan lock was never released after exception"
            time.sleep(0.05)


# ---------------------------------------------------------------------------
# GET /api/db/sessions
# ---------------------------------------------------------------------------

class TestDbSessions:
    def test_returns_list(self, client, db_patch):
        r = client.get("/api/db/sessions")
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_completed_scan_appears_in_sessions(self, client, db_patch):
        _seed_scan(db_patch, [_item("sess1")])
        r = client.get("/api/db/sessions")
        sessions = r.get_json()
        assert len(sessions) >= 1
        s = sessions[0]
        assert "ref_scan_id" in s
        assert "flagged_count" in s
        assert s["flagged_count"] == 1

    def test_sessions_ordered_newest_first(self, client, db_patch):
        # Create two scans >300 s apart so each forms its own session window.
        old_id = _seed_scan(db_patch, [_item("old1")])
        db_patch._connect().execute(
            "UPDATE scans SET started_at = started_at - 400 WHERE id = ?", (old_id,)
        )
        db_patch._connect().commit()
        _seed_scan(db_patch, [_item("new1")])
        sessions = client.get("/api/db/sessions").get_json()
        assert len(sessions) == 2
        # Newest session (highest ref_scan_id) must be first
        assert sessions[0]["ref_scan_id"] > sessions[1]["ref_scan_id"]


# ---------------------------------------------------------------------------
# Profile routes
# ---------------------------------------------------------------------------

class TestProfileRoutes:
    """
    Tests for GET /api/profiles, POST /api/profiles/save,
    GET /api/profiles/get, and POST /api/profiles/delete.

    Each test monkeypatches the profile storage path to a tmp directory so
    tests are fully isolated from the real ~/.gdprscanner/settings.json.
    """

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        import app_config
        monkeypatch.setattr(app_config, "_SETTINGS_PATH", tmp_path / "settings.json")

    def test_list_returns_empty_list_initially(self, client):
        r = client.get("/api/profiles")
        assert r.status_code == 200
        assert r.get_json()["profiles"] == []

    def test_save_missing_name_returns_400(self, client):
        r = client.post("/api/profiles/save", json={"sources": ["email"]})
        assert r.status_code == 400
        assert "error" in r.get_json()

    def test_save_creates_profile_and_returns_it(self, client):
        r = client.post("/api/profiles/save", json={
            "id": "", "name": "Alpha", "sources": ["email"], "options": {}
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "saved"
        assert data["profile"]["name"] == "Alpha"
        assert data["profile"]["id"]  # server assigned a non-empty id

    def test_saved_profile_appears_in_list(self, client):
        client.post("/api/profiles/save", json={"name": "Beta", "sources": [], "options": {}})
        profiles = client.get("/api/profiles").get_json()["profiles"]
        assert any(p["name"] == "Beta" for p in profiles)

    def test_rename_updates_name_in_list(self, client):
        """Regression: _pmgmtSaveFullEdit renames the copy — the API must
        persist the new name so loadProfiles() returns fresh data for the
        left-column re-render."""
        r = client.post("/api/profiles/save", json={
            "id": "", "name": "LOCAL-TEST (copy)", "sources": [], "options": {}
        })
        profile_id = r.get_json()["profile"]["id"]

        # Simulate the user renaming the copy in the editor and clicking Save
        r2 = client.post("/api/profiles/save", json={
            "id": profile_id, "name": "LOCAL-TEST-2", "sources": [], "options": {}
        })
        assert r2.status_code == 200
        assert r2.get_json()["profile"]["name"] == "LOCAL-TEST-2"

        profiles = client.get("/api/profiles").get_json()["profiles"]
        names = [p["name"] for p in profiles]
        assert "LOCAL-TEST-2" in names
        assert "LOCAL-TEST (copy)" not in names

    def test_get_by_id(self, client):
        r = client.post("/api/profiles/save", json={
            "id": "fixed-id-1", "name": "Gamma", "sources": [], "options": {}
        })
        profile_id = r.get_json()["profile"]["id"]
        r2 = client.get(f"/api/profiles/get?id={profile_id}")
        assert r2.status_code == 200
        assert r2.get_json()["profile"]["name"] == "Gamma"

    def test_get_nonexistent_returns_404(self, client):
        r = client.get("/api/profiles/get?id=does-not-exist")
        assert r.status_code == 404

    def test_delete_removes_profile(self, client):
        client.post("/api/profiles/save", json={"name": "ToDelete", "sources": [], "options": {}})
        r = client.post("/api/profiles/delete", json={"name": "ToDelete"})
        assert r.status_code == 200
        assert r.get_json()["status"] == "deleted"
        profiles = client.get("/api/profiles").get_json()["profiles"]
        assert not any(p["name"] == "ToDelete" for p in profiles)

    def test_delete_nonexistent_returns_not_found(self, client):
        r = client.post("/api/profiles/delete", json={"name": "Ghost"})
        assert r.status_code == 200
        assert r.get_json()["status"] == "not_found"

    def test_delete_missing_key_returns_400(self, client):
        r = client.post("/api/profiles/delete", json={})
        assert r.status_code == 400
