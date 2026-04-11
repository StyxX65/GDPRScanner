"""
Microsoft 365 authentication routes
"""
from __future__ import annotations
import threading
from flask import Blueprint, jsonify, request
from routes import state
from app_config import _load_config, _save_config

try:
    from m365_connector import M365Connector, M365Error, MSAL_OK
except ImportError:
    MSAL_OK = False
    M365Connector = None  # type: ignore[assignment,misc]
    class M365Error(Exception): pass  # type: ignore[no-redef]

bp = Blueprint("auth", __name__)


@bp.route("/api/auth/status")
def auth_status():
    cfg = _load_config()
    if not MSAL_OK:
        return jsonify({"authenticated": False, "error": "msal not installed",
                        "client_id": cfg.get("client_id",""), "tenant_id": cfg.get("tenant_id","")})

    saved_secret = cfg.get("client_secret", "")
    saved_cid    = cfg.get("client_id", "")
    saved_tid    = cfg.get("tenant_id", "")

    # Rebuild connector if:
    #  • none exists yet, OR
    #  • the saved secret doesn't match what the current connector was built with
    #    (user entered a secret after previously connecting without one)
    connector_secret = getattr(state.connector, "client_secret", None)
    need_rebuild = (
        not state.connector
        or connector_secret != saved_secret
        or getattr(state.connector, "client_id", None) != saved_cid
    )

    if need_rebuild and saved_cid and saved_tid:
        try:
            state.connector = M365Connector(saved_cid, saved_tid, client_secret=saved_secret)
            if state.connector.is_app_mode:
                state.connector.authenticate_app_mode()
        except Exception:
            state.connector = None

    if state.connector and state.connector.is_authenticated():
        try:
            info = state.connector.get_user_info()
            return jsonify({"authenticated": True,
                            "display_name": info.get("displayName",""),
                            "email": info.get("mail") or info.get("userPrincipalName",""),
                            "client_id":     saved_cid,
                            "tenant_id":     saved_tid,
                            "client_secret": saved_secret,
                            "app_mode":      state.connector.is_app_mode})
        except Exception:
            pass
    return jsonify({"authenticated": False,
                    "client_id":     saved_cid,
                    "tenant_id":     saved_tid,
                    "client_secret": saved_secret})


@bp.route("/api/auth/start", methods=["POST"])
def auth_start():
    if not MSAL_OK:
        return jsonify({"error": "msal not installed — run: pip install msal"})
    data          = request.get_json() or {}
    client_id     = data.get("client_id","").strip()
    tenant_id     = data.get("tenant_id","").strip()
    client_secret = data.get("client_secret","").strip()
    if not client_id or not tenant_id:
        return jsonify({"error": "client_id and tenant_id required"})
    try:
        state.connector = M365Connector(client_id, tenant_id, client_secret=client_secret)

        if state.connector.is_app_mode:
            # Application mode — acquire token immediately, no device code
            state.connector.authenticate_app_mode()
            _save_config({"client_id": client_id, "tenant_id": tenant_id,
                          "client_secret": client_secret})
            return jsonify({"mode": "application"})

        # Delegated mode — start device code flow
        state.pending_flow     = state.connector.get_device_code_flow()
        state.auth_poll_result = None
        _save_config({"client_id": client_id, "tenant_id": tenant_id, "client_secret": ""})

        flow_copy = state.pending_flow
        def _do_auth():
            try:
                ok = state.connector.complete_device_code_flow(flow_copy)
                state.auth_poll_result = "ok" if ok else "Sign-in failed"
            except M365Error as e:
                state.auth_poll_result = str(e)
            except Exception as e:
                state.auth_poll_result = str(e)
        threading.Thread(target=_do_auth, daemon=True).start()

        return jsonify({
            "mode":             "delegated",
            "user_code":        state.pending_flow["user_code"],
            "verification_uri": state.pending_flow["verification_uri"],
            "message":          state.pending_flow["message"],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@bp.route("/api/auth/poll", methods=["POST"])
def auth_poll():
    if not state.connector or not state.pending_flow:
        return jsonify({"status": "error", "error": "No pending flow"})
    # Return current poll result (set by background thread)
    result = state.auth_poll_result
    if result == "ok":
        state.auth_poll_result = None
        state.pending_flow = None
        return jsonify({"status": "ok"})
    elif result and result != "pending":
        state.auth_poll_result = None
        state.pending_flow = None
        return jsonify({"status": "error", "error": result})
    return jsonify({"status": "pending"})


@bp.route("/api/auth/userinfo")
def auth_userinfo():
    if not state.connector:
        return jsonify({"error": "not connected"}), 401
    try:
        return jsonify(state.connector.get_user_info())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/auth/signout", methods=["POST"])
def auth_signout():
    if state.connector:
        try: state.connector.sign_out()
        except Exception: pass
        state.connector = None
    # Also clear the delegated token cache so a fresh sign-in is required
    from m365_connector import _TOKEN_CACHE_FILE
    try:
        if _TOKEN_CACHE_FILE.exists():
            _TOKEN_CACHE_FILE.unlink()
    except Exception:
        pass
    return jsonify({"status": "ok"})


@bp.route("/api/auth/config", methods=["GET", "POST"])
def auth_config():
    """GET: return saved config (secret masked). POST: update config directly."""
    if request.method == "POST":
        data          = request.get_json() or {}
        client_id     = data.get("client_id", "").strip()
        tenant_id     = data.get("tenant_id", "").strip()
        client_secret = data.get("client_secret", "").strip()
        if not client_id or not tenant_id:
            return jsonify({"error": "client_id and tenant_id required"}), 400
        _save_config({"client_id": client_id, "tenant_id": tenant_id,
                      "client_secret": client_secret})
        # Force connector rebuild on next request
        state.connector = None
        return jsonify({"status": "saved", "app_mode": bool(client_secret)})
    cfg = _load_config()
    secret = cfg.get("client_secret", "")
    return jsonify({
        "client_id":     cfg.get("client_id", ""),
        "tenant_id":     cfg.get("tenant_id", ""),
        "has_secret":    bool(secret),
        "secret_preview": (secret[:4] + "…" + secret[-4:]) if len(secret) > 8 else ("***" if secret else ""),
    })
