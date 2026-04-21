"""
Scan stream, start/stop, checkpoint, settings, delta
"""
from __future__ import annotations
import threading
import logging
from flask import Blueprint, jsonify, request
from routes import state
from app_config import (
    _save_settings, _load_settings,
    _load_src_toggles, _save_src_toggles,
    _load_smtp_config,
)
from checkpoint import (
    _checkpoint_key, _load_checkpoint, _clear_checkpoint,
    _load_delta_tokens, _DELTA_PATH,
)

bp = Blueprint("scan", __name__)
_log = logging.getLogger(__name__)


def _maybe_send_auto_email():
    """Send the scan report email after a manual scan if auto_email_manual is enabled."""
    try:
        smtp_cfg = _load_smtp_config()
        if not smtp_cfg.get("auto_email_manual"):
            return
        if not state.flagged_items:
            return
        recipients = smtp_cfg.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.replace(";", ",").split(",") if r.strip()]
        if not recipients:
            return

        from routes.export import _build_excel_bytes
        from routes.email import _send_report_email, _send_email_graph
        import datetime as _dt

        xl_bytes, fname = _build_excel_bytes()
        subject = f"GDPR Scanner — scan report {_dt.datetime.now().strftime('%Y-%m-%d')}"
        body_html = (
            "<html><body style='font-family:Arial,sans-serif;color:#333;padding:24px'>"
            "<h2 style='color:#1F3864'>☁️ GDPR Scanner — scan report</h2>"
            f"<p>Please find the latest scan report attached ({fname}).</p>"
            f"<p style='color:#888;font-size:12px'>Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>"
            f"Items flagged: {len(state.flagged_items)}</p>"
            "</body></html>"
        )

        if state.connector and state.connector.is_authenticated():
            try:
                _send_email_graph(subject, body_html, recipients,
                                  attachment_bytes=xl_bytes, attachment_name=fname)
                _log.info("[auto-email] report sent via Graph to %s", recipients)
                return
            except Exception as e:
                _log.warning("[auto-email] Graph failed, trying SMTP: %s", e)

        _send_report_email(xl_bytes, fname, smtp_cfg, recipients)
        _log.info("[auto-email] report sent via SMTP to %s", recipients)
    except Exception as e:
        _log.error("[auto-email] failed: %s", e)


@bp.route("/api/scan/status")
def scan_status():
    """Lightweight status check — is a scan running? What scan_id?"""
    import sse as _sse_mod
    acquired = state._scan_lock.acquire(blocking=False)
    if acquired:
        state._scan_lock.release()
    return jsonify({
        "running":  not acquired,
        "scan_id":  _sse_mod._current_scan_id or None,
    })


@bp.route("/api/src_toggles", methods=["GET", "POST"])
def src_toggles():
    """GET: return source toggle state. POST: save."""
    if request.method == "POST":
        _save_src_toggles(request.get_json() or {})
        return jsonify({"ok": True})
    return jsonify(_load_src_toggles())


@bp.route("/api/scan/start", methods=["POST"])
def scan_start():
    if not state.connector:
        return jsonify({"error": "not authenticated"}), 401
    if not state._scan_lock.acquire(blocking=False):
        return jsonify({"error": "scan already running"}), 409
    options = request.get_json() or {}
    state._scan_abort.clear()
    profile_id = options.pop("profile_id", None)
    _save_settings({
        "sources":  options.get("sources", []),
        "user_ids": options.get("user_ids", []),
        "options":  options.get("options", {}),
    }, profile_id=profile_id)
    def _run():
        from scan_engine import run_scan
        try:
            run_scan(options)
            _maybe_send_auto_email()
        finally:
            state._scan_lock.release()
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@bp.route("/api/scan/stop", methods=["POST"])
def scan_stop():
    state._scan_abort.set()
    return jsonify({"status": "stopping"})


@bp.route("/api/scan/checkpoint", methods=["POST"])
def scan_checkpoint_info():
    """Return info about any saved checkpoint for the given scan options.
    If check_only=true, just reports whether a scan is currently running."""
    options = request.get_json() or {}
    if options.get("check_only"):
        acquired = state._scan_lock.acquire(blocking=False)
        if acquired:
            state._scan_lock.release()
        return jsonify({"running": not acquired})
    key = _checkpoint_key(options)
    cp  = _load_checkpoint(key)
    if not cp:
        return jsonify({"exists": False})
    return jsonify({
        "exists":        True,
        "scanned_count": len(cp.get("scanned_ids", [])),
        "flagged_count": len(cp.get("flagged", [])),
        "started_at":    cp.get("meta", {}).get("started_at"),
    })


@bp.route("/api/scan/clear_checkpoint", methods=["POST"])
def scan_clear_checkpoint():
    """Discard any saved checkpoint so the next scan starts fresh."""
    _clear_checkpoint()
    return jsonify({"status": "cleared"})


@bp.route("/api/settings/save", methods=["POST"])
def settings_save():
    """Persist scan settings so they can be reused by --headless mode."""
    payload = request.get_json() or {}
    _save_settings(payload)
    return jsonify({"status": "saved"})


@bp.route("/api/settings/load")
def settings_load():
    """Return previously saved scan settings (for --headless setup guidance)."""
    s = _load_settings()
    if not s:
        return jsonify({"exists": False})
    return jsonify({"exists": True, "settings": s})


@bp.route("/api/delta/status")
def delta_status():
    """Return info about stored delta tokens."""
    tokens = _load_delta_tokens()
    return jsonify({
        "count":  len(tokens),
        "keys":   list(tokens.keys()),
        "exists": len(tokens) > 0,
    })


@bp.route("/api/delta/clear", methods=["POST"])
def delta_clear():
    """Discard all stored delta tokens (next scan will be a full scan)."""
    try:
        if _DELTA_PATH.exists():
            _DELTA_PATH.unlink()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "cleared"})
