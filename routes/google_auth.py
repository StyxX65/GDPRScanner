"""
Google Workspace authentication routes.

Endpoints:
  GET  /api/google/auth/status    — is a service account loaded?
  POST /api/google/auth/connect   — save key JSON + optional admin_email
  POST /api/google/auth/disconnect — remove saved key + clear connector
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request
import json
import threading

from routes import state

bp = Blueprint("google_auth", __name__)


def __getattr__(name):
    import gdpr_scanner as _m
    if hasattr(_m, name):
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@bp.route("/api/google/auth/status")
def google_auth_status():
    """Return current Google connection state."""
    from google_connector import GOOGLE_AUTH_OK, load_saved_key
    if not GOOGLE_AUTH_OK:
        return jsonify({
            "connected": False,
            "error": "google-auth not installed — run: pip install google-auth google-auth-httplib2 google-api-python-client",
            "libs_ok": False,
        })

    key = load_saved_key()
    if not key:
        return jsonify({"connected": False, "libs_ok": True})

    sa_email   = key.get("client_email", "")
    project_id = key.get("project_id", "")
    admin_email = ""

    # Read persisted admin_email from config
    cfg = _load_google_config()
    admin_email = cfg.get("admin_email", "")

    # Rebuild connector in state if not present
    if not state.google_connector:
        try:
            from google_connector import GoogleConnector
            state.google_connector = GoogleConnector(key, admin_email=admin_email)
        except Exception as e:
            return jsonify({"connected": False, "libs_ok": True,
                            "error": str(e), "sa_email": sa_email})

    return jsonify({
        "connected":    True,
        "libs_ok":      True,
        "sa_email":     sa_email,
        "project_id":   project_id,
        "admin_email":  admin_email,
    })


@bp.route("/api/google/auth/connect", methods=["POST"])
def google_auth_connect():
    """
    Accept a service account key JSON + optional admin_email.
    Body: { "key_json": "<raw JSON string or object>", "admin_email": "admin@domain.com" }
    """
    from google_connector import GOOGLE_AUTH_OK, save_key, GoogleConnector
    if not GOOGLE_AUTH_OK:
        return jsonify({"error": "google-auth not installed"}), 503

    data = request.get_json() or {}
    raw_key  = data.get("key_json", "")
    admin_email = data.get("admin_email", "").strip()

    # Accept both a JSON string and an already-parsed object
    if isinstance(raw_key, str):
        try:
            key_dict = json.loads(raw_key)
        except json.JSONDecodeError as e:
            return jsonify({"error": f"Invalid JSON: {e}"}), 400
    elif isinstance(raw_key, dict):
        key_dict = raw_key
    else:
        return jsonify({"error": "key_json must be a JSON string or object"}), 400

    if key_dict.get("type") != "service_account":
        return jsonify({"error": "File must be a service_account JSON key (type != service_account)"}), 400

    # Validate by building a connector
    try:
        conn = GoogleConnector(key_dict, admin_email=admin_email)
        if not conn.is_authenticated():
            return jsonify({"error": "Credentials did not validate — check the key file"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    save_key(key_dict)
    _save_google_config({"admin_email": admin_email})

    state.google_connector = conn

    return jsonify({
        "ok":         True,
        "sa_email":   key_dict.get("client_email", ""),
        "project_id": key_dict.get("project_id", ""),
    })


@bp.route("/api/google/auth/disconnect", methods=["POST"])
def google_auth_disconnect():
    """Remove saved service account key and clear the connector."""
    from google_connector import delete_key
    delete_key()
    _save_google_config({})
    state.google_connector = None
    return jsonify({"ok": True})


# ── Personal Google account (device-code OAuth) ───────────────────────────────

@bp.route("/api/google/personal/status")
def google_personal_status():
    """Check whether a personal Google OAuth token is present and valid."""
    from google_connector import GOOGLE_AUTH_OK, load_personal_token, PersonalGoogleConnector
    if not GOOGLE_AUTH_OK:
        return jsonify({"connected": False, "libs_ok": False, "auth_mode": "personal"})

    token_data = load_personal_token()
    if not token_data:
        return jsonify({"connected": False, "libs_ok": True, "auth_mode": "personal"})

    if not isinstance(state.google_connector, PersonalGoogleConnector):
        try:
            conn = PersonalGoogleConnector(token_data)
            if conn.is_authenticated():
                state.google_connector = conn
            else:
                return jsonify({"connected": False, "libs_ok": True, "auth_mode": "personal"})
        except Exception as e:
            return jsonify({"connected": False, "libs_ok": True, "auth_mode": "personal",
                            "error": str(e)})

    try:
        info = state.google_connector.get_user_info()
        return jsonify({
            "connected":   True,
            "libs_ok":     True,
            "auth_mode":   "personal",
            "email":       info.get("email", ""),
            "displayName": info.get("displayName", ""),
        })
    except Exception as e:
        return jsonify({"connected": False, "libs_ok": True, "auth_mode": "personal",
                        "error": str(e)})


@bp.route("/api/google/personal/start", methods=["POST"])
def google_personal_start():
    """Initiate a Google device-code flow for a personal account."""
    from google_connector import GOOGLE_AUTH_OK, PersonalGoogleConnector
    if not GOOGLE_AUTH_OK:
        return jsonify({"error": "google-auth not installed"}), 503

    data          = request.get_json() or {}
    client_id     = data.get("client_id", "").strip()
    client_secret = data.get("client_secret", "").strip()
    if not client_id or not client_secret:
        return jsonify({"error": "client_id and client_secret required"}), 400

    try:
        flow = PersonalGoogleConnector.get_device_code_flow(client_id, client_secret)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    state.google_pending_flow = flow
    state.google_poll_result  = None

    def _do_auth():
        try:
            conn = PersonalGoogleConnector.complete_device_code_flow(flow)
            state.google_connector  = conn
            state.google_poll_result = "ok"
        except Exception as e:
            state.google_poll_result = str(e)

    threading.Thread(target=_do_auth, daemon=True).start()

    return jsonify({
        "user_code":        flow["user_code"],
        "verification_url": flow["verification_url"],
    })


@bp.route("/api/google/personal/poll", methods=["POST"])
def google_personal_poll():
    """Check whether the device-code sign-in has completed."""
    result = state.google_poll_result
    if result == "ok":
        state.google_poll_result  = None
        state.google_pending_flow = None
        return jsonify({"status": "ok"})
    if result and result != "pending":
        state.google_poll_result  = None
        state.google_pending_flow = None
        return jsonify({"status": "error", "error": result})
    return jsonify({"status": "pending"})


@bp.route("/api/google/personal/signout", methods=["POST"])
def google_personal_signout():
    """Delete the stored personal OAuth token and clear the connector."""
    from google_connector import delete_personal_token, PersonalGoogleConnector
    delete_personal_token()
    if isinstance(state.google_connector, PersonalGoogleConnector):
        state.google_connector = None
    return jsonify({"ok": True})


# ── Config helpers ────────────────────────────────────────────────────────────

from pathlib import Path as _Path
_DATA_DIR      = _Path.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)
_GOOGLE_CONFIG = _DATA_DIR / "google.json"


def _load_google_config() -> dict:
    if _GOOGLE_CONFIG.exists():
        try:
            return json.loads(_GOOGLE_CONFIG.read_text())
        except Exception:
            pass
    return {}


def _save_google_config(cfg: dict) -> None:
    try:
        _GOOGLE_CONFIG.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass
