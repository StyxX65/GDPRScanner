"""
Read-only viewer token + PIN management routes (#33).
"""
from __future__ import annotations
import time
from flask import Blueprint, jsonify, request, session
from app_config import (
    create_viewer_token,
    validate_viewer_token,
    revoke_viewer_token,
    cleanup_expired_viewer_tokens,
    _load_viewer_tokens,
    get_viewer_pin_hash,
    set_viewer_pin,
    verify_viewer_pin,
    clear_viewer_pin,
    get_interface_pin_hash,
    set_interface_pin,
    verify_interface_pin,
    clear_interface_pin,
)

bp = Blueprint("viewer", __name__)

# Simple brute-force guard: keyed by remote IP.
_pin_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_WINDOW_S     = 300   # 5 minutes


def _pin_rate_limit(ip: str) -> bool:
    """Return True if the IP is rate-limited (too many recent failures)."""
    now   = time.time()
    times = [t for t in _pin_attempts.get(ip, []) if now - t < _WINDOW_S]
    _pin_attempts[ip] = times
    return len(times) >= _MAX_ATTEMPTS


def _pin_record_failure(ip: str) -> None:
    now = time.time()
    _pin_attempts.setdefault(ip, []).append(now)


def _pin_clear_failures(ip: str) -> None:
    _pin_attempts.pop(ip, None)


# ── Token endpoints ───────────────────────────────────────────────────────────

@bp.route("/api/viewer/tokens", methods=["GET"])
def list_tokens():
    cleanup_expired_viewer_tokens()
    tokens = _load_viewer_tokens()
    safe = [
        {
            "token_hint":  t["token"][:8] + "…",
            "token":       t["token"],
            "label":       t.get("label", ""),
            "scope":       t.get("scope", {}),
            "created_at":  t.get("created_at"),
            "expires_at":  t.get("expires_at"),
            "last_used_at": t.get("last_used_at"),
        }
        for t in tokens
    ]
    return jsonify(safe)


@bp.route("/api/viewer/tokens", methods=["POST"])
def create_token():
    body         = request.get_json(silent=True) or {}
    label        = str(body.get("label", "")).strip()
    expires_days = body.get("expires_days")
    if expires_days is not None:
        try:
            expires_days = int(expires_days)
            if expires_days <= 0:
                return jsonify({"error": "expires_days must be a positive integer"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "expires_days must be a positive integer"}), 400
    raw_scope = body.get("scope", {})
    if not isinstance(raw_scope, dict):
        return jsonify({"error": "scope must be an object"}), 400
    role = str(raw_scope.get("role", "")).strip()
    # user may be a single email string (legacy) or a list of email strings
    raw_user = raw_scope.get("user", "")
    if isinstance(raw_user, str):
        user_emails = [raw_user.strip().lower()] if raw_user.strip() else []
    elif isinstance(raw_user, list):
        user_emails = [str(e).strip().lower() for e in raw_user if str(e).strip()]
    else:
        user_emails = []
    display_name = str(raw_scope.get("display_name", "")).strip()
    if role and user_emails:
        return jsonify({"error": "scope.role and scope.user are mutually exclusive"}), 400
    if role not in ("", "student", "staff"):
        return jsonify({"error": "scope.role must be '', 'student', or 'staff'"}), 400
    if user_emails and not all("@" in e for e in user_emails):
        return jsonify({"error": "scope.user entries must be valid email addresses"}), 400
    if user_emails:
        scope = {"user": user_emails, "display_name": display_name or user_emails[0]}
    elif role:
        scope = {"role": role}
    else:
        scope = {}
    entry = create_viewer_token(label=label, expires_days=expires_days, scope=scope)
    return jsonify(entry), 201


@bp.route("/api/viewer/tokens/<token>", methods=["DELETE"])
def delete_token(token: str):
    if not token:
        return jsonify({"error": "token required"}), 400
    removed = revoke_viewer_token(token)
    if not removed:
        return jsonify({"error": "token not found"}), 404
    return jsonify({"ok": True})


@bp.route("/api/viewer/tokens/validate", methods=["POST"])
def validate_token():
    body  = request.get_json(silent=True) or {}
    token = str(body.get("token", "")).strip()
    entry = validate_viewer_token(token)
    if entry is None:
        return jsonify({"valid": False}), 401
    return jsonify({"valid": True, "label": entry.get("label", ""), "expires_at": entry.get("expires_at")})


# ── PIN endpoints ─────────────────────────────────────────────────────────────

@bp.route("/api/viewer/pin", methods=["GET"])
def pin_status():
    """Return whether a viewer PIN is currently set."""
    return jsonify({"pin_set": bool(get_viewer_pin_hash())})


@bp.route("/api/viewer/pin", methods=["POST"])
def pin_set():
    """Set or change the viewer PIN.
    Body: {pin: "...", current_pin: "..."}
    current_pin required only when a PIN is already set.
    """
    body = request.get_json(silent=True) or {}
    new_pin = str(body.get("pin", "")).strip()
    if not new_pin:
        return jsonify({"error": "pin required"}), 400
    if not new_pin.isdigit() or not (4 <= len(new_pin) <= 8):
        return jsonify({"error": "PIN must be 4–8 digits"}), 400
    if get_viewer_pin_hash():
        if not verify_viewer_pin(str(body.get("current_pin", "")).strip()):
            return jsonify({"error": "current PIN is incorrect"}), 403
    set_viewer_pin(new_pin)
    return jsonify({"ok": True})


@bp.route("/api/viewer/pin", methods=["DELETE"])
def pin_clear():
    """Remove the viewer PIN.  Requires current PIN if one is set."""
    body = request.get_json(silent=True) or {}
    if get_viewer_pin_hash():
        if not verify_viewer_pin(str(body.get("current_pin", "")).strip()):
            return jsonify({"error": "current PIN is incorrect"}), 403
    clear_viewer_pin()
    return jsonify({"ok": True})


# ── Interface PIN management endpoints ───────────────────────────────────────

@bp.route("/api/interface/pin", methods=["GET"])
def interface_pin_status():
    """Return whether an interface PIN is currently set."""
    return jsonify({"pin_set": bool(get_interface_pin_hash())})


@bp.route("/api/interface/pin", methods=["POST"])
def interface_pin_set():
    """Set or change the interface PIN.
    Body: {pin: "...", current_pin: "..."}
    current_pin required only when a PIN is already set.
    """
    body = request.get_json(silent=True) or {}
    new_pin = str(body.get("pin", "")).strip()
    if not new_pin:
        return jsonify({"error": "pin required"}), 400
    if not new_pin.isdigit() or not (4 <= len(new_pin) <= 8):
        return jsonify({"error": "PIN must be 4–8 digits"}), 400
    if get_interface_pin_hash():
        if not verify_interface_pin(str(body.get("current_pin", "")).strip()):
            return jsonify({"error": "current PIN is incorrect"}), 403
    set_interface_pin(new_pin)
    return jsonify({"ok": True})


@bp.route("/api/interface/pin", methods=["DELETE"])
def interface_pin_clear():
    """Remove the interface PIN.  Requires current PIN if one is set."""
    body = request.get_json(silent=True) or {}
    if get_interface_pin_hash():
        if not verify_interface_pin(str(body.get("current_pin", "")).strip()):
            return jsonify({"error": "current PIN is incorrect"}), 403
    clear_interface_pin()
    return jsonify({"ok": True})


@bp.route("/api/viewer/pin/verify", methods=["POST"])
def pin_verify():
    """Verify a PIN submission and set a viewer session on success."""
    ip  = request.remote_addr or "unknown"
    if _pin_rate_limit(ip):
        return jsonify({"error": "Too many failed attempts. Try again later."}), 429
    body = request.get_json(silent=True) or {}
    pin  = str(body.get("pin", "")).strip()
    if not verify_viewer_pin(pin):
        _pin_record_failure(ip)
        remaining = _MAX_ATTEMPTS - len(_pin_attempts.get(ip, []))
        return jsonify({"error": "Incorrect PIN", "remaining": max(0, remaining)}), 401
    _pin_clear_failures(ip)
    session["viewer_ok"] = True
    return jsonify({"ok": True})
