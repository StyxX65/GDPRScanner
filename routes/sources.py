"""
File sources and file scan
"""
from __future__ import annotations
import threading
from flask import Blueprint, jsonify, request
from routes import state
from app_config import _load_file_sources, _save_file_sources

try:
    from file_scanner import store_smb_password, SMB_OK as _SMB_OK
    _FILE_SCANNER_OK = True
except ImportError:
    _FILE_SCANNER_OK = False
    _SMB_OK = False
    def store_smb_password(*a, **kw): return False  # type: ignore[misc]

bp = Blueprint("sources", __name__)


@bp.route("/api/file_sources", methods=["GET"])
def file_sources_list():
    """Return all saved file source definitions."""
    sources = _load_file_sources()
    return jsonify({
        "sources":       sources,
        "smb_available": _SMB_OK,
        "scanner_ok":    _FILE_SCANNER_OK,
    })


@bp.route("/api/file_sources/save", methods=["POST"])
def file_sources_save():
    """Add or update a file source.  Assigns a UUID if id is missing."""
    import uuid as _uuid
    data = request.get_json() or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    sources = _load_file_sources()
    uid = data.get("id") or ""
    for i, s in enumerate(sources):
        if s.get("id") == uid:
            sources[i] = {**s, **data}
            _save_file_sources(sources)
            return jsonify({"ok": True, "source": sources[i]})
    data["id"] = data.get("id") or str(_uuid.uuid4())
    sources.append(data)
    _save_file_sources(sources)
    return jsonify({"ok": True, "source": data})


@bp.route("/api/file_sources/delete", methods=["POST"])
def file_sources_delete():
    """Remove a file source by id."""
    uid = (request.get_json() or {}).get("id", "")
    if not uid:
        return jsonify({"error": "id required"}), 400
    sources = [s for s in _load_file_sources() if s.get("id") != uid]
    _save_file_sources(sources)
    return jsonify({"ok": True})


@bp.route("/api/file_sources/store_creds", methods=["POST"])
def file_sources_store_creds():
    """Store SMB password in the OS keychain."""
    if not _FILE_SCANNER_OK:
        return jsonify({"error": "file_scanner not available"}), 503
    data     = request.get_json() or {}
    smb_host = data.get("smb_host", "")
    smb_user = data.get("smb_user", "")
    password = data.get("password", "")
    key      = data.get("keychain_key") or smb_user
    if not smb_user or not password:
        return jsonify({"error": "smb_user and password required"}), 400
    ok = store_smb_password(smb_host, smb_user, password, key)
    if ok:
        return jsonify({"ok": True, "keychain_key": key})
    return jsonify({"error": "keyring not available — install: pip install keyring"}), 500


@bp.route("/api/file_scan/start", methods=["POST"])
def file_scan_start():
    """Start a file system scan for a single file source."""
    if not _FILE_SCANNER_OK:
        return jsonify({"error": "file_scanner not available"}), 503
    if not state._scan_lock.acquire(blocking=False):
        return jsonify({"error": "scan already running"}), 409
    source = request.get_json() or {}
    state._scan_abort.clear()

    def _run():
        from scan_engine import run_file_scan
        try:
            run_file_scan(source)
        finally:
            state._scan_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})
