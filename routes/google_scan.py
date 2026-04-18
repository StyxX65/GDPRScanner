"""
Google Workspace scan routes.

Endpoints:
  POST /api/google/scan/start   — kick off a Gmail + Drive scan
  POST /api/google/scan/cancel  — abort running Google scan
  GET  /api/google/scan/users   — list workspace users via Admin SDK
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request
import logging
import threading

logger = logging.getLogger(__name__)

from routes import state
from routes.state import _google_scan_lock as _scan_lock, _google_scan_abort as _scan_abort

bp = Blueprint("google_scan", __name__)


def __getattr__(name):
    import gdpr_scanner as _m
    if hasattr(_m, name):
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Scan lock shared with M365 scan so both can't run simultaneously ──────────
# _scan_lock / _scan_abort live in routes/state.py; resolved via gdpr_scanner.__getattr__.


@bp.route("/api/google/scan/users")
def google_scan_users():
    """Return list of workspace users available via Admin SDK."""
    conn = state.google_connector
    if not conn:
        return jsonify({"error": "not connected"}), 401
    try:
        users = conn.list_users()
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/google/scan/start", methods=["POST"])
def google_scan_start():
    """
    Start a Google Workspace scan.

    Body (all optional):
    {
      "sources":       ["gmail", "gdrive"],   // default: both
      "user_emails":   ["a@dom.com"],         // default: all users via Admin SDK
      "options": {
        "max_messages":    2000,
        "max_files":       5000,
        "max_attach_mb":   20,
        "scan_body":       true,
        "scan_attachments":true,
        "max_file_mb":     50
      }
    }
    """
    conn = state.google_connector
    if not conn:
        return jsonify({"error": "not connected to Google Workspace"}), 401

    if not _scan_lock.acquire(blocking=False):
        return jsonify({"error": "scan already running"}), 409

    options = request.get_json() or {}
    _scan_abort.clear()

    def _run():
        try:
            _run_google_scan(options)
        finally:
            _scan_lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@bp.route("/api/google/scan/cancel", methods=["POST"])
def google_scan_cancel():
    _scan_abort.set()
    return jsonify({"status": "cancelling"})


# ── Scan engine ───────────────────────────────────────────────────────────────

def _run_google_scan(options: dict):
    """
    Core Google Workspace scan loop.

    Mirrors the M365 scan structure:
      broadcast("scan_start")
      for each user:
        for each source (gmail / gdrive):
          for each item:
            scan bytes → broadcast card
      broadcast("scan_done")
    """
    import gdpr_scanner as _m

    broadcast  = _m.broadcast
    _scan_bytes = _m._scan_bytes
    flagged_items = _m.flagged_items
    LANG = _m.LANG

    # Import DB helpers
    try:
        from gdpr_db import get_db as _get_db
        DB_OK = True
    except ImportError:
        DB_OK = False
        def _get_db(*a, **kw): return None

    from scan_engine import _with_disposition

    conn = state.google_connector
    if not conn:
        broadcast("scan_error", {"file": "auth", "error": "Not connected to Google Workspace"})
        broadcast("google_scan_done", {"flagged_count": 0, "total_scanned": 0})
        return

    import time as _time
    _sse_buffer_clear = getattr(_m, '_sse_buffer', None)
    if _sse_buffer_clear is not None:
        _sse_buffer_clear.clear()

    sources       = options.get("sources", ["gmail", "gdrive"])
    # user_emails may come at top level or inside options
    user_emails   = options.get("user_emails", [])
    scan_opts     = options.get("options", {})
    max_messages  = int(scan_opts.get("max_messages",  2000))
    max_files     = int(scan_opts.get("max_files",     5000))
    max_attach_mb = float(scan_opts.get("max_attach_mb", 20.0))
    max_file_mb   = float(scan_opts.get("max_file_mb",   50.0))
    scan_body     = bool(scan_opts.get("scan_body",        True))
    scan_att      = bool(scan_opts.get("scan_attachments", True))
    delta_enabled = bool(scan_opts.get("delta", False))

    from checkpoint import _load_delta_tokens, _save_delta_tokens
    _drive_delta_tokens: dict = _load_delta_tokens() if delta_enabled else {}
    _new_drive_tokens:   dict = {}

    # Resolve users: explicit list → Admin SDK → fall back to SA email itself
    _user_role_map:    dict = {}  # email → role
    _user_display_map: dict = {}  # email → display name
    if not user_emails:
        try:
            ws_users    = conn.list_users()
            user_emails = [u["email"] for u in ws_users if u.get("email")]
            _user_role_map        = {u["email"]: u.get("userRole",    "other") for u in ws_users}
            _user_display_map     = {u["email"]: u.get("displayName", u["email"]) for u in ws_users}
        except Exception as e:
            # Admin SDK unavailable — scan only the delegated admin account
            broadcast("scan_phase", {"phase": f"Admin SDK unavailable ({e}) — scanning service account email only"})
            user_emails = [conn.get_service_account_email()]
            # SA email itself is not a mailbox; use admin_email if set
            if conn._admin_email:
                user_emails = [conn._admin_email]

    # If user_emails came from the request, try to get display names and roles
    if user_emails and not _user_role_map:
        try:
            ws_users = conn.list_users()
            _user_role_map    = {u["email"]: u.get("userRole",    "other") for u in ws_users}
            _user_display_map = {u["email"]: u.get("displayName", u["email"]) for u in ws_users}
        except Exception:
            _user_display_map = {}

    if not user_emails:
        broadcast("scan_error", {"file": "users", "error": "No users to scan — set admin email or provide user_emails"})
        broadcast("google_scan_done", {"flagged_count": 0, "total_scanned": 0})
        return

    source_labels = []
    if "gmail" in sources: source_labels.append("Gmail")
    if "gdrive" in sources: source_labels.append("Google Drive")

    broadcast("scan_start", {"sources": source_labels})
    broadcast("scan_phase", {"phase": f"Google Workspace scan · {len(user_emails)} user(s) · " + ", ".join(source_labels)})

    # Open DB
    _db = _get_db() if DB_OK else None
    _db_scan_id = None
    if _db:
        try:
            _db_scan_id = _db.begin_scan(options)
        except Exception as e:
            logger.error("[google_scan] begin_scan failed: %s", e)

    total_flagged = 0
    total_scanned = 0
    t_start = _time.monotonic()

    def _check_abort():
        from gdpr_scanner import _scan_abort as _sa
        if _sa.is_set():
            broadcast("scan_cancelled", {"completed": total_scanned})
            return True
        return False

    def _broadcast_card(item_meta: dict, cprs: list, pii_counts=None):
        nonlocal total_flagged
        card = {
            "id":           item_meta.get("id", ""),
            "name":         item_meta.get("name", ""),
            "source":       item_meta.get("_source", ""),
            "source_type":  item_meta.get("_source_type", ""),
            "cpr_count":    len(cprs),
            "url":          item_meta.get("_url", ""),
            "size_kb":      round(item_meta.get("size", 0) / 1024, 1),
            "modified":     (item_meta.get("lastModifiedDateTime") or item_meta.get("receivedDateTime") or "")[:10],
            "thumb_b64":    "",
            "thumb_mime":   "image/svg+xml",
            "risk":         None,
            "account_id":   item_meta.get("_account_id", ""),
            "account_name": item_meta.get("_account", ""),
            "user_role":    _user_role_map.get(user_email, "other"),
            "drive_id":     "",
            "attachments":  [],
            "folder":       "",
            "transfer_risk":    "",
            "special_category": [],
            "face_count":       0,
            "exif":             {},
        }
        flagged_items.append(card)
        broadcast("scan_file_flagged", _with_disposition(card, _db))
        total_flagged += 1
        if _db and _db_scan_id:
            try:
                _db.save_item(_db_scan_id, card, cprs, pii_counts=pii_counts)
            except Exception as e:
                logger.error("[google_scan] save_item failed: %s", e)

    # ── Per-user scan loop ────────────────────────────────────────────────────
    from google_connector import GoogleError

    for user_email in user_emails:
        _display_name = _user_display_map.get(user_email, user_email)
        if _check_abort():
            return

        broadcast("scan_phase", {"phase": f"Google Workspace \u2014 {user_email}"})

        # ── Gmail ─────────────────────────────────────────────────────────────
        if "gmail" in sources:
            try:
                broadcast("scan_phase", {"phase": f"{user_email} — Gmail"})
                for meta, data in conn.iter_gmail_messages(
                    user_email,
                    max_messages=max_messages,
                    scan_body=scan_body,
                    scan_attachments=scan_att,
                    max_attach_mb=max_attach_mb,
                ):
                    if _check_abort():
                        return
                    total_scanned += 1
                    broadcast("scan_file", {"file": meta.get("name", "")})
                    broadcast("scan_progress", {
                        "scanned": total_scanned,
                        "flagged": total_flagged,
                        "file":    meta.get("name", ""),
                        "pct":     min(90, 10 + total_scanned // 10),
                        "source":  "google",
                    })
                    try:
                        meta["_account"] = _display_name
                        result = _scan_bytes(data, meta.get("name", "msg.txt"))
                    except Exception as e:
                        broadcast("scan_error", {"file": meta.get("name", ""), "error": str(e)})
                        continue
                    cprs      = result.get("cprs", [])
                    pii_counts = result.get("pii_counts")
                    if cprs or (pii_counts and any(pii_counts.values())):
                        _broadcast_card(meta, cprs, pii_counts)
            except GoogleError as e:
                broadcast("scan_error", {"file": f"Gmail/{user_email}", "error": str(e)})
            except Exception as e:
                broadcast("scan_error", {"file": f"Gmail/{user_email}", "error": str(e)})

        # ── Google Drive ──────────────────────────────────────────────────────
        if "gdrive" in sources:
            try:
                delta_key   = f"gdrive:{user_email}"
                saved_token = _drive_delta_tokens.get(delta_key) if delta_enabled else None

                if delta_enabled and saved_token:
                    broadcast("scan_phase", {"phase": f"{user_email} — Google Drive (delta)"})
                    try:
                        drive_items, new_token = conn.get_drive_changes(
                            user_email, saved_token,
                            max_files=max_files, max_file_mb=max_file_mb,
                        )
                        _new_drive_tokens[delta_key] = new_token
                    except Exception as delta_err:
                        broadcast("scan_phase", {"phase": f"{user_email} — Google Drive (delta token invalid — full scan)"})
                        logger.warning("[gdrive delta] %s: %s — falling back to full scan", user_email, delta_err)
                        drive_items = list(conn.iter_drive_files(user_email, max_files=max_files, max_file_mb=max_file_mb))
                        try:
                            _new_drive_tokens[delta_key] = conn.get_drive_start_token(user_email)
                        except Exception:
                            pass
                else:
                    broadcast("scan_phase", {"phase": f"{user_email} — Google Drive"})
                    drive_items = list(conn.iter_drive_files(user_email, max_files=max_files, max_file_mb=max_file_mb))
                    if delta_enabled:
                        try:
                            _new_drive_tokens[delta_key] = conn.get_drive_start_token(user_email)
                        except Exception:
                            pass

                for meta, data in drive_items:
                    if _check_abort():
                        return
                    total_scanned += 1
                    broadcast("scan_file", {"file": meta.get("name", "")})
                    broadcast("scan_progress", {
                        "scanned": total_scanned,
                        "flagged": total_flagged,
                        "file":    meta.get("name", ""),
                        "pct":     min(90, 10 + total_scanned // 10),
                        "source":  "google",
                    })
                    try:
                        meta["_account"] = _display_name
                        result = _scan_bytes(data, meta.get("name", "file"))
                    except Exception as e:
                        broadcast("scan_error", {"file": meta.get("name", ""), "error": str(e)})
                        continue
                    cprs       = result.get("cprs", [])
                    pii_counts = result.get("pii_counts")
                    if cprs or (pii_counts and any(pii_counts.values())):
                        _broadcast_card(meta, cprs, pii_counts)
            except GoogleError as e:
                broadcast("scan_error", {"file": f"Drive/{user_email}", "error": str(e)})
            except Exception as e:
                broadcast("scan_error", {"file": f"Drive/{user_email}", "error": str(e)})

    if delta_enabled and _new_drive_tokens:
        try:
            current_tokens = _load_delta_tokens()
            _save_delta_tokens({**current_tokens, **_new_drive_tokens})
        except Exception as e:
            logger.warning("[gdrive delta] token save failed: %s", e)

    elapsed = _time.monotonic() - t_start
    broadcast("google_scan_done", {
        "flagged_count":   total_flagged,
        "total_scanned":   total_scanned,
        "elapsed_seconds": round(elapsed, 1),
        "delta":           delta_enabled and bool(_new_drive_tokens),
        "delta_sources":   len(_new_drive_tokens),
    })
    if _db and _db_scan_id:
        try:
            _db.finish_scan(_db_scan_id, total_scanned)
        except Exception:
            pass
