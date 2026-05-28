"""
Scan profiles
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request
from app_config import _profiles_load, _profile_save, _profile_delete, _profile_get
try:
    from gdpr_db import log_audit_event as _audit
except ImportError:
    def _audit(*a, **kw): pass  # type: ignore[misc]

bp = Blueprint("profiles", __name__)


@bp.route("/api/profiles", methods=["GET"])
def profiles_list():
    """Return all saved profiles."""
    return jsonify({"profiles": _profiles_load()})


@bp.route("/api/profiles/save", methods=["POST"])
def profiles_save():
    """Create or update a profile."""
    profile = request.get_json() or {}
    if not profile.get("name"):
        return jsonify({"error": "name required"}), 400
    saved = _profile_save(profile)
    _audit("profile_save", f"name={profile.get('name')!r}",
           ip=request.remote_addr or "")
    return jsonify({"status": "saved", "profile": saved})


@bp.route("/api/profiles/delete", methods=["POST"])
def profiles_delete():
    """Delete a profile by name or id."""
    data = request.get_json() or {}
    key  = data.get("name") or data.get("id", "")
    if not key:
        return jsonify({"error": "name or id required"}), 400
    ok = _profile_delete(key)
    if ok:
        _audit("profile_delete", f"key={key!r}", ip=request.remote_addr or "")
    return jsonify({"status": "deleted" if ok else "not_found"})


@bp.route("/api/profiles/get")
def profiles_get():
    """Return a single profile by name or id."""
    key = request.args.get("name") or request.args.get("id", "")
    p   = _profile_get(key)
    if not p:
        return jsonify({"error": "not found"}), 404
    return jsonify({"profile": p})
