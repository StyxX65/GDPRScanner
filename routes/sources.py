"""
File sources and file scan
"""
from __future__ import annotations
import threading
import uuid as _uuid
from pathlib import Path
from flask import Blueprint, jsonify, request
from routes import state
from app_config import _load_file_sources, _save_file_sources, _SFTP_KEYS_DIR

try:
    from file_scanner import store_smb_password, SMB_OK as _SMB_OK
    _FILE_SCANNER_OK = True
except ImportError:
    _FILE_SCANNER_OK = False
    _SMB_OK = False
    def store_smb_password(*a, **kw): return False  # type: ignore[misc]

try:
    from sftp_connector import store_sftp_password, SFTP_OK as _SFTP_OK
except ImportError:
    _SFTP_OK = False
    def store_sftp_password(*a, **kw): return False  # type: ignore[misc]

bp = Blueprint("sources", __name__)


@bp.route("/api/file_sources", methods=["GET"])
def file_sources_list():
    """Return all saved file source definitions."""
    sources = _load_file_sources()
    return jsonify({
        "sources":        sources,
        "smb_available":  _SMB_OK,
        "sftp_available": _SFTP_OK,
        "scanner_ok":     _FILE_SCANNER_OK,
    })


@bp.route("/api/file_sources/save", methods=["POST"])
def file_sources_save():
    """Add or update a file source.  Assigns a UUID if id is missing."""
    data = request.get_json() or {}
    source_type = data.get("source_type", "")

    # Validate required fields per source type
    if source_type == "sftp":
        if not data.get("sftp_host", "").strip():
            return jsonify({"error": "sftp_host required"}), 400
        if not data.get("sftp_user", "").strip():
            return jsonify({"error": "sftp_user required"}), 400
        if not data.get("path", "").strip():
            data["path"] = "/"
    else:
        if not data.get("path", "").strip():
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
    """Remove a file source by id.  Also deletes any associated SFTP key file."""
    uid = (request.get_json() or {}).get("id", "")
    if not uid:
        return jsonify({"error": "id required"}), 400
    sources = _load_file_sources()
    deleted = next((s for s in sources if s.get("id") == uid), None)
    sources = [s for s in sources if s.get("id") != uid]
    _save_file_sources(sources)

    # Clean up key file if this was an SFTP key-auth source
    if deleted and deleted.get("sftp_key_path"):
        key_file = Path(deleted["sftp_key_path"])
        if key_file.parent == _SFTP_KEYS_DIR and key_file.exists():
            try:
                key_file.unlink()
            except OSError:
                pass

    return jsonify({"ok": True})


@bp.route("/api/file_sources/store_creds", methods=["POST"])
def file_sources_store_creds():
    """Store SMB or SFTP password/passphrase in the OS keychain."""
    data        = request.get_json() or {}
    source_type = data.get("source_type", "smb")
    password    = data.get("password", "")

    if source_type == "sftp":
        if not _SFTP_OK:
            return jsonify({"error": "paramiko not installed — run: pip install paramiko"}), 503
        host = data.get("sftp_host", "")
        user = data.get("sftp_user", "")
        if not user or not password:
            return jsonify({"error": "sftp_user and password required"}), 400
        key = data.get("keychain_key") or f"sftp:{user}@{host}"
        ok = store_sftp_password(host, user, password, key)
        if ok:
            return jsonify({"ok": True, "keychain_key": key})
        return jsonify({"error": "keyring not available — install: pip install keyring"}), 500
    else:
        if not _FILE_SCANNER_OK:
            return jsonify({"error": "file_scanner not available"}), 503
        smb_host = data.get("smb_host", "")
        smb_user = data.get("smb_user", "")
        if not smb_user or not password:
            return jsonify({"error": "smb_user and password required"}), 400
        key = data.get("keychain_key") or smb_user
        ok = store_smb_password(smb_host, smb_user, password, key)
        if ok:
            return jsonify({"ok": True, "keychain_key": key})
        return jsonify({"error": "keyring not available — install: pip install keyring"}), 500


@bp.route("/api/file_sources/upload_key", methods=["POST"])
def file_sources_upload_key():
    """Accept an SSH private key file upload and store it in the SFTP keys directory.

    Validates the file is a recognised private key format before saving.
    Returns {"key_id": uuid, "key_path": absolute_path}.
    """
    if not _SFTP_OK:
        return jsonify({"error": "paramiko not installed — run: pip install paramiko"}), 503

    if "key_file" not in request.files:
        return jsonify({"error": "key_file required"}), 400

    file = request.files["key_file"]
    raw  = file.read(65536)  # 64 KB is more than enough for any private key

    # Validate before saving — try loading the key material with paramiko
    import io
    import paramiko
    loaded = False
    for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey):
        try:
            cls.from_private_key(io.BytesIO(raw))
            loaded = True
            break
        except (paramiko.ssh_exception.SSHException, Exception):
            continue

    if not loaded:
        # Might be passphrase-protected — still accept it; validation will happen at connect time
        if b"-----BEGIN" not in raw and b"OPENSSH PRIVATE KEY" not in raw:
            return jsonify({"error": "File does not appear to be a private key"}), 400

    key_id   = str(_uuid.uuid4())
    key_path = _SFTP_KEYS_DIR / key_id
    key_path.write_bytes(raw)
    key_path.chmod(0o600)

    return jsonify({"ok": True, "key_id": key_id, "key_path": str(key_path)})


@bp.route("/api/file_scan/start", methods=["POST"])
def file_scan_start():
    """Start a file system scan for a single file source (local, SMB, or SFTP)."""
    source      = request.get_json() or {}
    source_type = source.get("source_type", "")

    if source_type == "sftp":
        if not _SFTP_OK:
            return jsonify({"error": "paramiko not installed — run: pip install paramiko"}), 503
    elif not _FILE_SCANNER_OK:
        return jsonify({"error": "file_scanner not available"}), 503

    if not state._scan_lock.acquire(blocking=False):
        return jsonify({"error": "scan already running"}), 409

    state._scan_abort.clear()

    def _run():
        from scan_engine import run_file_scan
        try:
            run_file_scan(source)
        finally:
            state._scan_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})
