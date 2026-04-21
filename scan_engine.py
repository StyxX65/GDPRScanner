"""
scan_engine.py — M365 and file-system scan orchestration for GDPRScanner.

Provides:
  run_scan(options)        — full M365 scan (Exchange, OneDrive, SharePoint, Teams)
  run_file_scan(source)    — local / SMB file system scan

Both functions use sse.broadcast() for progress events and gdpr_db for persistence.
"""
from __future__ import annotations
import concurrent.futures
import gc
import hashlib
import logging
import json
import re
import sys
import time
import tempfile
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Runtime dependencies — resolved at startup by gdpr_scanner.py ─────────────
# Fallback stubs allow isolated import (e.g. for tests).
try:
    from sse import broadcast, _sse_buffer
except ImportError:
    def broadcast(event, data): pass  # type: ignore
    _sse_buffer = None

try:
    from gdpr_db import get_db as _get_db
    DB_OK = True
except ImportError:
    DB_OK = False
    def _get_db(*a, **kw): return None  # type: ignore

from routes import state as _state

def _get_scan_abort():
    return _state._scan_abort

def _get_flagged_items():
    return _state.flagged_items

def _get_scan_meta():
    return _state.scan_meta

# ── Connector classes — imported at module level ──────────────────────────────
try:
    from m365_connector import (
        M365Connector, M365Error, M365PermissionError, M365DeltaTokenExpired,
        M365DriveNotFound,
        MSAL_OK, REQUESTS_OK,
    )
    CONNECTOR_OK = True
except ImportError:
    M365Connector = None        # type: ignore[assignment,misc]
    M365Error = Exception
    M365PermissionError = Exception
    M365DeltaTokenExpired = Exception
    M365DriveNotFound = Exception
    MSAL_OK = False
    REQUESTS_OK = False
    CONNECTOR_OK = False

try:
    from file_scanner import FileScanner, store_smb_password, SMB_OK as _SMB_OK
    FILE_SCANNER_OK = True
except ImportError:
    FileScanner = None          # type: ignore[assignment,misc]
    FILE_SCANNER_OK = False

try:
    import document_scanner as ds
    SCANNER_OK = True
except ImportError:
    ds = None                   # type: ignore[assignment]
    SCANNER_OK = False

try:
    from PIL import Image as PILImage
    PIL_OK = True
except ImportError:
    PILImage = None             # type: ignore[assignment]
    PIL_OK = False

try:
    from gdpr_db import get_db as _get_db
    DB_OK = True
except ImportError:
    DB_OK = False
    def _get_db(*a, **kw): return None  # type: ignore[misc]

# Stubs for standalone import — overwritten by gdpr_scanner.py injections
LANG: dict = {}
PHOTO_EXTS: set = set()
VIDEO_EXTS: set = set()
AUDIO_EXTS: set = set()
SUPPORTED_EXTS: set = set()

# cpr_detector helpers — injected by gdpr_scanner.py
def _scan_bytes(content, filename, poppler_path=None): return {"cprs": [], "dates": []}  # type: ignore[misc]
def _scan_bytes_timeout(content, filename, timeout=60): return {"cprs": [], "dates": []}  # type: ignore[misc]
def _detect_photo_faces(content, filename): return 0  # type: ignore[misc]
def _extract_exif(content, filename): return {}  # type: ignore[misc]
def _extract_video_metadata(content, filename): return {}  # type: ignore[misc]
def _extract_audio_metadata(content, filename): return {}  # type: ignore[misc]
def _make_thumb(content, filename): return ""  # type: ignore[misc]
def _placeholder_svg(ext, name): return ""  # type: ignore[misc]
def _check_special_category(text, cprs): return []  # type: ignore[misc]
def _get_pii_counts(text): return {}  # type: ignore[misc]
def _html_esc(s): return str(s)  # type: ignore[misc]

# checkpoint helpers — injected by gdpr_scanner.py
def _checkpoint_key(opts): return ""  # type: ignore[misc]
def _save_checkpoint(*a, **kw): pass  # type: ignore[misc]
def _load_checkpoint(key): return None  # type: ignore[misc]
def _clear_checkpoint(): pass  # type: ignore[misc]
def _load_delta_tokens(): return {}  # type: ignore[misc]
def _save_delta_tokens(t): pass  # type: ignore[misc]

# app_config helpers — imported directly
try:
    from app_config import _load_role_overrides, _resolve_display_name
except ImportError:
    def _load_role_overrides(): return {}  # type: ignore[misc]
    def _resolve_display_name(dn, email="", upn=""): return dn or email or upn  # type: ignore[misc]

# cpr_detector helpers — imported directly
try:
    from cpr_detector import _scan_text_direct
except ImportError:
    def _scan_text_direct(text): return {"cprs": [], "dates": []}  # type: ignore[misc]

def _with_disposition(card: dict, db) -> dict:
    """Inject prior disposition into a scan card if one exists."""
    if not db:
        return card
    try:
        prior = db.get_prior_disposition(card.get("id", ""))
        if prior:
            return {**card, "disposition": prior}
    except Exception:
        pass
    return card


def run_file_scan(source: dict):
    """Scan a single local or SMB file source for CPR numbers and PII.

    Reuses _scan_bytes, _broadcast_card, _check_special_category,
    _detect_photo_faces and all other existing scan helpers.

    Args:
        source: file source dict with keys:
            path, label, smb_host, smb_user, smb_domain, keychain_key,
            scan_photos (bool), max_file_mb (int)
    """
    # state vars accessed via _state module

    path        = source.get("path", "")
    label       = source.get("label") or path
    smb_host    = source.get("smb_host") or None
    smb_user    = source.get("smb_user") or None
    smb_domain  = source.get("smb_domain") or ""
    keychain_key= source.get("keychain_key") or None
    smb_password= source.get("smb_password") or None
    scan_photos     = bool(source.get("scan_photos", False))
    skip_gps_images = bool(source.get("skip_gps_images", False))
    min_cpr_count   = max(1, int(source.get("min_cpr_count", 1)))
    max_mb          = int(source.get("max_file_mb", 50))

    if not FILE_SCANNER_OK:
        broadcast("scan_error", {"file": label, "error": "file_scanner.py not found"})
        return

    import sse as _sse; _sse._current_scan_id = f"filescan_{int(time.time()*1000)}"
    _state.scan_meta = {"started_at": time.time(), "options": source}

    _db = _get_db() if DB_OK else None
    _db_scan_id: int | None = None
    if _db:
        try:
            _db_scan_id = _db.begin_scan({
                "sources":  [source.get("source_type", "local")],
                "user_ids": [],
                "options":  source,
            })
        except Exception as e:
            logger.error("[db] start_scan failed: %s", e)

    total_scanned = 0
    total_flagged = 0

    broadcast("scan_phase", {"phase": f"Files \u2014 {label}"})

    try:
        fs = FileScanner(
            path=path,
            smb_host=smb_host,
            smb_user=smb_user,
            smb_password=smb_password,
            smb_domain=smb_domain,
            keychain_key=keychain_key,
            max_file_bytes=max_mb * 1_048_576,
        )

        def _progress(rel_path: str):
            broadcast("scan_file", {"file": rel_path})

        for rel_path, content, meta in fs.iter_files(progress_cb=_progress):
            if _state._scan_abort.is_set():
                break

            total_scanned += 1
            broadcast("scan_progress", {"scanned": total_scanned, "flagged": total_flagged, "file": rel_path, "pct": min(90, 10 + total_scanned // 10), "source": "file"})

            # Skip sentinel (too large or error)
            if content is None:
                if meta.get("skip_reason"):
                    broadcast("scan_error", {
                        "file": rel_path,
                        "error": meta["skip_reason"],
                    })
                continue

            ext = Path(rel_path).suffix.lower()

            # CPR scan — skip for images, video and audio (no text layer)
            result: dict = {"cprs": [], "dates": []}
            if ext not in PHOTO_EXTS and ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
                try:
                    result = _scan_bytes_timeout(content, rel_path)
                except Exception as e:
                    broadcast("scan_error", {"file": rel_path, "error": str(e)})
                    continue

            cprs = result.get("cprs", [])

            # Photo / biometric scan + EXIF/video/audio metadata extraction
            _face_count = 0
            _exif       = {}
            if ext in PHOTO_EXTS:
                if scan_photos:
                    _face_count = _detect_photo_faces(content, rel_path)
                _exif = _extract_exif(content, rel_path)
            elif ext in VIDEO_EXTS:
                _exif = _extract_video_metadata(content, rel_path)
            elif ext in AUDIO_EXTS:
                _exif = _extract_audio_metadata(content, rel_path)

            # Apply filters: distinct CPR threshold and GPS suppression
            _distinct_cprs = list(dict.fromkeys(c["formatted"] for c in cprs))
            _cpr_qualifies = len(_distinct_cprs) >= min_cpr_count
            _exif_has_pii  = _exif.get("has_pii") and (
                not skip_gps_images or bool(_exif.get("pii_fields") or _exif.get("author"))
            )

            if not (_cpr_qualifies and cprs) and _face_count == 0 and not _exif_has_pii:
                continue

            # Build card metadata
            try:
                _file_text = content.decode("utf-8", errors="replace")
            except Exception:
                _file_text = ""

            _pii = _get_pii_counts(_file_text)
            _sc  = _check_special_category(_file_text, cprs)
            if _face_count > 0 and "biometric" not in _sc:
                _sc = sorted(_sc + ["biometric"])
            if _exif.get("gps") and not skip_gps_images and "gps_location" not in _sc:
                _sc = sorted(_sc + ["gps_location"])
            if _exif_has_pii and "exif_pii" not in _sc:
                _sc = sorted(_sc + ["exif_pii"])

            # Thumbnail for images
            if ext in {".jpg", ".jpeg", ".png"} and PIL_OK:
                _thumb      = _make_thumb(content, rel_path)
                _thumb_mime = True
            else:
                _thumb      = _placeholder_svg(ext, rel_path)
                _thumb_mime = False
            del content  # raw bytes no longer needed — free before card build and next iteration

            source_type = meta["source_type"]  # "local" or "smb"
            source_root = meta["source_root"]

            card = {
                "id":           hashlib.sha256(meta["full_path"].encode()).hexdigest()[:24],
                "name":         rel_path,
                "source":       label,
                "source_type":  source_type,
                "cpr_count":    len(cprs),
                "url":          "",
                "size_kb":      meta["size_kb"],
                "modified":     meta["modified"],
                "thumb_b64":    _thumb,
                "thumb_mime":   "image/jpeg" if _thumb_mime else "image/svg+xml",
                "risk":         None,
                "account_id":   "",
                "account_name": source_root,
                "user_role":    "other",
                "drive_id":     "",
                "attachments":  [],
                "folder":       str(Path(rel_path).parent) if "/" in rel_path or "\\" in rel_path else "",
                "transfer_risk": "",
                "special_category": _sc,
                "face_count":   _face_count,
                "exif":         _exif,
                "full_path":    meta["full_path"],
            }

            _state.flagged_items.append(card)
            total_flagged += 1
            broadcast("scan_file_flagged", _with_disposition(card, _db))

            if _db and _db_scan_id:
                try:
                    _db.save_item(_db_scan_id, card, cprs, pii_counts=_pii)
                except Exception as e:
                    logger.error("[db] save_item failed: %s", e)

    except Exception as e:
        import traceback
        broadcast("scan_error", {"file": label, "error": str(e)})
        logger.error("[file_scan] error:\n%s", traceback.format_exc())
    finally:
        if _db and _db_scan_id:
            try:
                _db.finish_scan(_db_scan_id, total_scanned)
            except Exception:
                pass
        _state.scan_meta["finished_at"] = time.time()
        broadcast("file_scan_done", {
            "total_scanned": total_scanned,
            "flagged_count": total_flagged,
        })


def run_scan(options: dict):
    # state vars accessed via _state module
    import sse as _sse; _sse._current_scan_id = f"scan_{int(time.time()*1000)}"
    _state.scan_meta = {"started_at": time.time(), "options": options}
    _sse_buffer.clear()  # fresh buffer for each scan

    # Open DB and start a scan record (runs alongside JSON cache)
    _db = _get_db() if DB_OK else None
    _db_scan_id: int | None = None
    if _db:
        try:
            _db_scan_id = _db.begin_scan(options)
        except Exception as _e:
            logger.error("[db] begin_scan failed: %s", _e)

    conn: M365Connector = _state.connector  # type: ignore[assignment]
    if not conn:
        broadcast("scan_error", {"file": "auth", "error": "Not connected to M365"})
        broadcast("scan_done", {"flagged_count": 0, "total_scanned": 0})
        return

    # ── Checkpoint: resume from a previous interrupted scan ──────────────────
    ck_key        = _checkpoint_key(options)
    checkpoint    = _load_checkpoint(ck_key)
    scanned_ids:  set  = set(checkpoint["scanned_ids"]) if checkpoint else set()
    resumed_count = len(scanned_ids)

    if checkpoint:
        # Restore previously found cards; new finds will be appended
        _state.flagged_items = list(checkpoint.get("flagged", []))
        broadcast("scan_phase", {
            "phase": LANG.get("m365_resuming", f"Resuming — skipping {resumed_count} already-scanned items…")
        })
        # Re-emit previously found cards so the UI grid is populated
        for card in _state.flagged_items:
            broadcast("scan_file_flagged", _with_disposition(card, _db))
    else:
        _state.flagged_items = []

    # Save checkpoint every N items so progress isn't lost mid-scan
    _CHECKPOINT_SAVE_EVERY = 25
    _items_since_save = 0

    conn: M365Connector = _state.connector  # type: ignore[assignment]
    if not conn:
        broadcast("scan_error", {"file": "auth", "error": "Not connected to M365"})
        broadcast("scan_done", {"flagged_count": 0, "total_scanned": 0})
        return

    # Log which auth mode is active — helps diagnose 403 issues
    mode_label = LANG.get("m365_auth_mode_app", "Auth mode: Application (client credentials — org-wide)") if conn.is_app_mode else LANG.get("m365_auth_mode_delegated", "Auth mode: Delegated (device code — signed-in user only)")
    broadcast("scan_phase", {"phase": mode_label})
    logger.info("[run_scan] sources=%s, users=%d, app_mode=%s",
                options.get("sources", []), len(options.get("user_ids", [])), conn.is_app_mode)

    sources        = options.get("sources", [])
    scan_opts      = options.get("options", {})
    older_than_days= int(scan_opts.get("older_than_days", 0))
    scan_email_body= scan_opts.get("email_body", True)
    scan_attachments= scan_opts.get("attachments", True)
    max_attach_mb  = float(scan_opts.get("max_attach_mb", 20))
    max_emails     = int(scan_opts.get("max_emails", 2000))
    delta_enabled  = bool(scan_opts.get("delta", False))
    scan_photos    = bool(scan_opts.get("scan_photos", False))  # biometric photo scan (#9)
    skip_gps_images= bool(scan_opts.get("skip_gps_images", False))
    min_cpr_count  = max(1, int(scan_opts.get("min_cpr_count", 1)))

    # Delta token state — loaded once, updated per-source, saved on completion
    delta_tokens:     dict = _load_delta_tokens() if delta_enabled else {}
    new_delta_tokens: dict = {}  # keys written after a successful delta query

    if delta_enabled:
        broadcast("scan_phase", {"phase": LANG.get("m365_delta_mode", "Delta mode — fetching changed items only…")})

    # Compute cutoff date if requested
    from datetime import datetime, timezone, timedelta
    cutoff_dt = None
    if older_than_days > 0:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    def _after_cutoff(date_str: str) -> bool:
        """Return True if item is NEWER than cutoff (should be skipped)."""
        if not cutoff_dt or not date_str:
            return False
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt > cutoff_dt
        except Exception:
            return False

    total     = 0
    completed = 0
    t_start   = time.monotonic()

    def _eta(done, tot):
        if done < 2 or tot == 0:
            return ""
        elapsed = time.monotonic() - t_start
        rate    = done / elapsed
        rem     = (tot - done) / rate
        if rem < 60:   return f"{int(rem)}s"
        if rem < 3600: return f"{int(rem/60)}m"
        return f"{int(rem/3600)}h"

    def _check_abort():
        if _state._scan_abort.is_set():
            broadcast("scan_cancelled", {"completed": completed})
            return True
        return False

    def _broadcast_card(item_meta: dict, cprs: list, pii_counts: dict | None = None):
        card = {
            "id":           item_meta.get("id", ""),
            "name":         item_meta.get("name", ""),
            "source":       item_meta.get("_source", ""),
            "source_type":  item_meta.get("_source_type", ""),
            "cpr_count":    len(cprs),
            "url":          item_meta.get("webUrl", "") or item_meta.get("_url", ""),
            "size_kb":      round(item_meta.get("size", 0) / 1024, 1),
            "modified":     (item_meta.get("lastModifiedDateTime") or item_meta.get("receivedDateTime") or "")[:10],
            "thumb_b64":    item_meta.get("_thumb", ""),
            "thumb_mime":   "image/jpeg" if item_meta.get("_thumb_is_jpeg") else "image/svg+xml",
            "risk":         None,
            "account_id":   item_meta.get("_account_id", "") or item_meta.get("_user_id", ""),
            "account_name": item_meta.get("_account", ""),
            "user_role":    item_meta.get("_user_role", "other"),
            "drive_id":     item_meta.get("_drive_id", "") or item_meta.get("parentReference", {}).get("driveId", ""),
            "attachments":  item_meta.get("_attachments", []),
            "folder":       item_meta.get("_folder", ""),
            "transfer_risk":    item_meta.get("_transfer_risk", ""),
            "special_category": item_meta.get("_special_category", []),
            "face_count":       item_meta.get("_face_count", 0),
            "exif":             item_meta.get("_exif", {}),
        }
        _state.flagged_items.append(card)
        broadcast("scan_file_flagged", _with_disposition(card, _db))
        # Persist to SQLite alongside JSON
        if _db and _db_scan_id:
            try:
                _db.save_item(_db_scan_id, card, cprs, pii_counts=pii_counts)
            except Exception as _e:
                logger.error("[db] save_item failed: %s", _e)

    # ── External transfer detection (#5) ─────────────────────────────────────
    def _tenant_domain() -> str:
        """Best-effort: extract the primary domain from the tenant's user list."""
        try:
            me = conn.get_user_info()
            addr = me.get("mail") or me.get("userPrincipalName", "")
            return addr.split("@")[-1].lower() if "@" in addr else ""
        except Exception:
            return ""

    _tenant_dom = _tenant_domain()

    def _check_transfer_risk(meta: dict) -> str:
        """Return transfer risk tag or empty string.

        Email: external recipient detected (domain outside tenant).
        File:  external sharing link present on the drive item.
        """
        src_type = meta.get("_source_type", "")
        if src_type == "email":
            if not _tenant_dom:
                return ""
            recipients = []
            for field in ("toRecipients", "ccRecipients"):
                for r in meta.get(field, []):
                    addr = (r.get("emailAddress") or {}).get("address", "")
                    if addr:
                        recipients.append(addr.lower())
            external = [a for a in recipients
                        if "@" in a and not a.endswith("@" + _tenant_dom)]
            if external:
                return "external-recipient"
        elif src_type in ("onedrive", "sharepoint", "teams"):
            if meta.get("shared"):
                scope = ""
                try:
                    scope = meta["shared"].get("scope", "").lower()
                except Exception:
                    pass
                if scope in ("anonymous", "organization"):
                    return "external-share"
                return "shared"
        return ""

    # ── Collect work items ────────────────────────────────────────────────────
    work_items = []  # list of (type, meta, fetch_fn)

    try:
        # Determine which user accounts to scan
        # Normalise user_ids — may be list of dicts OR list of plain ID strings (legacy)
        _raw_uids = options.get("user_ids", [])
        user_ids = [
            u if isinstance(u, dict) else {"id": u, "displayName": u, "userRole": "other"}
            for u in _raw_uids
        ]

        # Resolve the signed-in user so we can use /me/... for them (avoids
        # needing admin delegation just to read your own mailbox/drive)
        try:
            me_info = conn.get_user_info()
            me_id   = me_info.get("id", "")
        except Exception:
            me_id   = ""
            me_info = {}

        if not user_ids:
            if conn.is_app_mode:
                # App mode with no users selected — scan everyone
                logger.info("[run_scan] user_ids empty — fetching all tenant users")
                all_users = conn.list_users()
                user_ids = [{"id": u["id"],
                             "displayName": _resolve_display_name(
                                 u.get("displayName", ""),
                                 u.get("mail") or u.get("userPrincipalName", ""))}
                            for u in all_users if u.get("id")]
            else:
                user_ids = [{"id": me_id or "me",
                             "displayName": _resolve_display_name(
                                 me_info.get("displayName", ""),
                                 me_info.get("mail") or me_info.get("userPrincipalName", "me"))}]
        else:
            sample = user_ids[0] if user_ids else None
            logger.info("[run_scan] user_ids: %d entries, type=%s, sample=%s",
                        len(user_ids), type(user_ids).__name__, sample)

        # Build uid → userRole map for use during scanning
        # Manual overrides (set by admin in UI) take precedence over auto-classification
        _scan_role_overrides = _load_role_overrides()
        _user_role_map: dict[str, str] = {
            u["id"]: _scan_role_overrides.get(u["id"], u.get("userRole", "other"))
            for u in user_ids if u.get("id")
        }

        def _uid_path(uid: str) -> str:
            """In delegated mode, return 'me' when uid is the signed-in user
            so /me/... endpoints are used. In app mode, always use /users/{id}
            since there is no signed-in user context."""
            if conn.is_app_mode:
                return uid  # app mode: always explicit user ID
            return "me" if (uid == me_id or uid == "me") else uid

        def _permission_msg(resource: str, uname: str) -> str:
            return (
                f"Permission denied (403) — cannot access {resource} for {uname}. "
                f"The signed-in account needs Global Admin or Exchange Admin rights, "
                f"OR an admin must grant Application permissions in Azure "
                f"(Mail.ReadWrite / Files.ReadWrite.All / Sites.ReadWrite.All for delete; "
                f"Mail.Read / Files.Read.All / Sites.Read.All for scan-only) under "
                f"App registrations → API permissions → Grant admin consent."
            )

        def _scan_user_email(uid, uname):
            effective = _uid_path(uid)
            broadcast("scan_phase", {"phase": LANG.get("m365_phase_emails", "Collecting emails") + f" — {uname}\u2026"})
            try:
                folder_errors = []
                if effective != "me":
                    all_folders = conn.list_all_mail_folders_for(effective, errors_out=folder_errors)
                else:
                    all_folders = conn.list_all_mail_folders(errors_out=folder_errors)

                for ferr in folder_errors:
                    broadcast("scan_error", {"file": f"mail folders ({uname})", "error": ferr})

                broadcast("scan_phase", {"phase": LANG.get("m365_phase_emails", "Collecting emails") + f" — {uname}: {len(all_folders)} folders…"})

                # Skip system folders. Use wellKnownName (language-independent) when
                # Graph returns it; fall back to localised display names otherwise.
                SKIP_WELL_KNOWN = {
                    "deleteditems", "junkemail", "drafts",
                    # "sentitems" and "outbox" intentionally NOT skipped — may contain CPR numbers
                    "syncissues", "recoverableitemsdeletions",
                    "recoverableitemsroot", "recoverableitemspurges",
                    "recoverableitemsversions",
                }
                SKIP_DISPLAY = {
                    # English
                    "deleted items", "junk email", "drafts",
                    # "sent items" and "outbox" intentionally NOT skipped
                    "sync issues", "recoverable items",
                    "purges", "versions", "conflicts", "local failures",
                    "server failures",
                    # Danish
                    "slettet post", "uønsket post", "kladder",
                    "synkroniseringsproblemer",
                    # German
                    "gelöschte elemente", "junk-e-mail", "entwürfe",
                }

                def _should_skip(f):
                    wkn = f.get("wellKnownName", "").lower()
                    if wkn:
                        return wkn in SKIP_WELL_KNOWN
                    return f.get("displayName", "").lower() in SKIP_DISPLAY

                scan_folders = [f for f in all_folders if not _should_skip(f)]

                # Prioritise subfolders (depth > 0) before Inbox so the cap
                # doesn't get exhausted by Inbox alone.
                def _folder_sort_key(f):
                    path = f.get("_display_path", "")
                    depth = path.count(" / ")
                    is_inbox_root = path.lower() in ("inbox", "indbakke")
                    return (is_inbox_root, -depth)  # subfolders first, then inbox last

                scan_folders.sort(key=_folder_sort_key)

                msgs_added = 0
                for folder in scan_folders:
                    if _state._scan_abort.is_set():
                        return
                    if msgs_added >= max_emails:
                        break
                    remaining    = max_emails - msgs_added
                    folder_limit = remaining   # each folder gets whatever budget is left
                    folder_id    = folder["id"]
                    folder_path  = folder.get("_display_path", folder.get("displayName", ""))
                    delta_key    = f"email:{uid}:{folder_id}"

                    if delta_enabled:
                        saved_link = delta_tokens.get(delta_key)
                        try:
                            if effective != "me":
                                folder_msgs, new_link = conn.iter_messages_delta_for(
                                    effective, folder_id, delta_url=saved_link, top=folder_limit)
                            else:
                                folder_msgs, new_link = conn.iter_messages_delta(
                                    folder_id, delta_url=saved_link, top=folder_limit)
                            if new_link:
                                new_delta_tokens[delta_key] = new_link
                        except M365DeltaTokenExpired:
                            broadcast("scan_phase", {"phase": f"📂 {folder_path}: delta token expired — full fetch"})
                            if delta_key in delta_tokens:
                                del delta_tokens[delta_key]
                            folder_msgs = list(
                                conn.iter_messages_for(effective, folder_id, top=folder_limit)
                                if effective != "me"
                                else conn.iter_messages(folder_id, top=folder_limit)
                            )
                    else:
                        folder_msgs = list(
                            conn.iter_messages_for(effective, folder_id, top=folder_limit) if effective != "me"
                            else conn.iter_messages(folder_id, top=folder_limit)
                        )

                    # Filter deleted items returned by delta (have @removed key)
                    folder_msgs = [m for m in folder_msgs if "@removed" not in m]

                    if folder_msgs:
                        delta_badge = " Δ" if delta_enabled else ""
                        broadcast("scan_phase", {"phase": f"📂 {folder_path}{delta_badge}: {len(folder_msgs)} msg(s)"})
                    for msg in folder_msgs:
                        if _after_cutoff(msg.get("receivedDateTime", "")):
                            continue
                        msg["_account"]    = uname
                        msg["_account_id"] = effective
                        msg["_user_role"]  = _user_role_map.get(uid, "other")
                        msg["_folder"]     = folder_path
                        # Pre-extract body text and discard raw HTML to avoid storing
                        # potentially hundreds of KB of HTML per message in work_items.
                        # For a large org this is the primary driver of multi-GB RAM usage.
                        if scan_email_body:
                            msg["_precomputed_body"] = conn.get_message_body_text(msg)
                        msg.pop("body", None)       # free raw HTML (can be 100 KB+)
                        msg.pop("bodyPreview", None) # 255-char preview, not needed
                        work_items.append(("email", msg, None))
                        msgs_added += 1
                        if msgs_added >= max_emails:
                            break
            except M365PermissionError:
                broadcast("scan_error", {"file": f"mail ({uname})", "error": _permission_msg("email", uname)})
            except Exception as e:
                broadcast("scan_error", {"file": f"mail ({uname})", "error": str(e)})

        def _scan_user_onedrive(uid, uname):
            effective  = _uid_path(uid)
            delta_key  = f"onedrive:{uid}"
            saved_link = delta_tokens.get(delta_key) if delta_enabled else None
            phase_sfx  = " Δ" if (delta_enabled and saved_link) else ""
            broadcast("scan_phase", {"phase": LANG.get("m365_phase_onedrive", "Collecting OneDrive") + f" — {uname}{phase_sfx}…"})
            try:
                if delta_enabled:
                    try:
                        if effective != "me":
                            items, new_link = conn.iter_onedrive_delta_for(effective, uname, delta_url=saved_link)
                        else:
                            items, new_link = conn.iter_onedrive_delta(delta_url=saved_link)
                        if new_link:
                            new_delta_tokens[delta_key] = new_link
                    except M365DeltaTokenExpired:
                        broadcast("scan_phase", {"phase": f"OneDrive ({uname}): delta token expired — falling back to full scan"})
                        if delta_key in delta_tokens:
                            del delta_tokens[delta_key]
                        if effective != "me":
                            items = list(conn.iter_onedrive_files_for(effective, uname))
                        else:
                            items = list(conn.iter_onedrive_files())
                    for item in items:
                        if _state._scan_abort.is_set():
                            return
                        if item.get("deleted"):
                            continue
                        ext = Path(item.get("name", "")).suffix.lower()
                        if ext not in SUPPORTED_EXTS:
                            continue
                        if _after_cutoff(item.get("lastModifiedDateTime", "")):
                            continue
                        item["_source_type"] = "onedrive"
                        item["_account"]     = uname
                        item["_user_id"]     = effective
                        item["_user_role"]   = _user_role_map.get(uid, "other")
                        work_items.append(("file", item, None))
                else:
                    gen = conn.iter_onedrive_files_for(effective, uname) if effective != "me" else conn.iter_onedrive_files()
                    for item in gen:
                        if _state._scan_abort.is_set():
                            return
                        ext = Path(item.get("name", "")).suffix.lower()
                        if ext not in SUPPORTED_EXTS:
                            continue
                        if _after_cutoff(item.get("lastModifiedDateTime", "")):
                            continue
                        item["_source_type"] = "onedrive"
                        item["_account"]     = uname
                        item["_user_id"]     = effective
                        item["_user_role"]   = _user_role_map.get(uid, "other")
                        work_items.append(("file", item, None))
            except M365PermissionError:
                broadcast("scan_error", {"file": f"OneDrive ({uname})", "error": _permission_msg("OneDrive", uname)})
            except M365DriveNotFound:
                # OneDrive not provisioned for this user (no licence, service plan
                # disabled, or drive never initialised). Not a scan error — skip silently.
                broadcast("scan_phase", {"phase": f"OneDrive ({uname}): not provisioned — skipped"})
            except Exception as e:
                broadcast("scan_error", {"file": f"OneDrive ({uname})", "error": str(e)})
            else:
                od_count = sum(1 for k, m, _ in work_items if m.get("_source_type") == "onedrive" and m.get("_account") == uname)
                if od_count:
                    broadcast("scan_phase", {"phase": f"📁 OneDrive — {uname}: {od_count} file(s)"})
        def _scan_user_teams(uid, uname):
            """Scan Teams files the specific user is a member of."""
            effective = _uid_path(uid)
            phase_sfx = " Δ" if delta_enabled else ""
            broadcast("scan_phase", {"phase": LANG.get("m365_phase_teams", "Collecting Teams") + f" — {uname}{phase_sfx}…"})
            try:
                if effective == "me":
                    teams = conn.list_teams()
                elif conn.is_app_mode:
                    teams = _app_user_teams.get(uid, [])
                else:
                    teams = list(conn._paginate(f"/users/{effective}/joinedTeams", {"$top": "50"}))
                for team in teams:
                    if _state._scan_abort.is_set():
                        return
                    team_id   = team["id"]
                    team_name = team.get("displayName", team_id)
                    if delta_enabled:
                        # Each Teams channel is a SharePoint drive — use per-drive delta
                        try:
                            channels = list(conn._paginate(f"/teams/{team_id}/channels", {"$top": "50"}))
                        except Exception:
                            channels = []
                        for ch in channels:
                            if _state._scan_abort.is_set():
                                return
                            ch_id   = ch["id"]
                            ch_name = ch.get("displayName", ch_id)
                            source  = f"Teams / {team_name} / {ch_name}"
                            try:
                                data = conn._get(f"/teams/{team_id}/channels/{ch_id}/filesFolder")
                                drive_id = data.get("parentReference", {}).get("driveId")
                                if not drive_id:
                                    continue
                                delta_key  = f"teams:{drive_id}"
                                saved_link = delta_tokens.get(delta_key)
                                try:
                                    items, new_link = conn.iter_drive_delta(drive_id, source, delta_url=saved_link)
                                    if new_link:
                                        new_delta_tokens[delta_key] = new_link
                                except M365DeltaTokenExpired:
                                    broadcast("scan_phase", {"phase": f"Teams {source}: token expired — full scan"})
                                    if delta_key in delta_tokens:
                                        del delta_tokens[delta_key]
                                    items, new_link = conn.iter_drive_delta(drive_id, source, delta_url=None)
                                    if new_link:
                                        new_delta_tokens[delta_key] = new_link
                                for item in items:
                                    if item.get("deleted"):
                                        continue
                                    ext = Path(item.get("name", "")).suffix.lower()
                                    if ext not in SUPPORTED_EXTS:
                                        continue
                                    if _after_cutoff(item.get("lastModifiedDateTime", "")):
                                        continue
                                    item["_source_type"] = "teams"
                                    item["_account"]     = uname
                                    item["_user_role"]   = _user_role_map.get(uid, "other")
                                    work_items.append(("file", item, None))
                            except Exception:
                                continue
                    else:
                        for item in conn.iter_teams_files(team_id, team_name):
                            ext = Path(item.get("name", "")).suffix.lower()
                            if ext not in SUPPORTED_EXTS:
                                continue
                            if _after_cutoff(item.get("lastModifiedDateTime", "")):
                                continue
                            item["_source_type"] = "teams"
                            item["_account"]     = uname
                            item["_user_role"]   = _user_role_map.get(uid, "other")
                            work_items.append(("file", item, None))
            except M365PermissionError:
                broadcast("scan_error", {"file": f"Teams ({uname})", "error": _permission_msg("Teams", uname)})
            except Exception as e:
                broadcast("scan_error", {"file": f"Teams ({uname})", "error": str(e)})
            else:
                tm_count = sum(1 for k, m, _ in work_items if m.get("_source_type") == "teams" and m.get("_account") == uname)
                if tm_count:
                    broadcast("scan_phase", {"phase": f"💬 Teams — {uname}: {tm_count} file(s)"})
        if "email" in sources:
            for u in user_ids:
                if _state._scan_abort.is_set():
                    break
                _scan_user_email(u["id"], u["displayName"])

        if "onedrive" in sources:
            for u in user_ids:
                if _state._scan_abort.is_set():
                    break
                _scan_user_onedrive(u["id"], u["displayName"])

        if "sharepoint" in sources:
            phase_sfx = " Δ" if delta_enabled else ""
            broadcast("scan_phase", {"phase": LANG.get("m365_phase_sharepoint", "Collecting SharePoint files…") + phase_sfx})
            try:
                sites = conn.list_sharepoint_sites()
                for site in sites:
                    if _state._scan_abort.is_set():
                        break
                    site_id   = site["id"]
                    site_name = site.get("displayName", site.get("name", site_id))
                    if delta_enabled:
                        # Collect per-drive delta for this site
                        try:
                            drives = list(conn._paginate(f"/sites/{site_id}/drives", {"$top": "20"}))
                        except Exception:
                            drives = []
                        for drive in drives:
                            drive_id    = drive["id"]
                            drive_label = f"{site_name} / {drive.get('name', 'Documents')}"
                            delta_key   = f"sharepoint:{drive_id}"
                            saved_link  = delta_tokens.get(delta_key)
                            try:
                                items, new_link = conn.iter_drive_delta(drive_id, drive_label, delta_url=saved_link)
                                if new_link:
                                    new_delta_tokens[delta_key] = new_link
                            except M365DeltaTokenExpired:
                                broadcast("scan_phase", {"phase": f"SharePoint {drive_label}: token expired — full scan"})
                                if delta_key in delta_tokens:
                                    del delta_tokens[delta_key]
                                items, new_link = conn.iter_drive_delta(drive_id, drive_label, delta_url=None)
                                if new_link:
                                    new_delta_tokens[delta_key] = new_link
                            for item in items:
                                if item.get("deleted"):
                                    continue
                                ext = Path(item.get("name", "")).suffix.lower()
                                if ext not in SUPPORTED_EXTS:
                                    continue
                                if _after_cutoff(item.get("lastModifiedDateTime", "")):
                                    continue
                                item["_source_type"] = "sharepoint"
                                work_items.append(("file", item, None))
                    else:
                        for item in conn.iter_sharepoint_files(site_id, site_name):
                            ext = Path(item.get("name", "")).suffix.lower()
                            if ext not in SUPPORTED_EXTS:
                                continue
                            if _after_cutoff(item.get("lastModifiedDateTime", "")):
                                continue
                            item["_source_type"] = "sharepoint"
                            work_items.append(("file", item, None))
            except Exception as e:
                broadcast("scan_error", {"file": "SharePoint", "error": str(e)})
            else:
                sp_count = sum(1 for k, m, _ in work_items if m.get("_source_type") == "sharepoint")
                if sp_count:
                    broadcast("scan_phase", {"phase": f"🌐 SharePoint: {sp_count} file(s)"})
        if "teams" in sources:
            # App mode: /users/{id}/joinedTeams is delegated-only.
            # Build a user→teams index by listing all tenant teams once,
            # then fetching each team's member list.
            _app_user_teams: dict = {}  # uid -> [team_dict, ...]
            if conn.is_app_mode:
                broadcast("scan_phase", {"phase": LANG.get("m365_phase_teams_index", "Building Teams membership index…")})
                try:
                    all_teams = conn.list_all_teams()
                    scan_uid_set = {u["id"] for u in user_ids}
                    for team in all_teams:
                        tid   = team["id"]
                        tname = team.get("displayName", tid)
                        member_ids = conn.get_team_members(tid)
                        for mid in member_ids:
                            if mid in scan_uid_set:
                                _app_user_teams.setdefault(mid, []).append(
                                    {"id": tid, "displayName": tname}
                                )
                except Exception as e:
                    broadcast("scan_error", {"file": "Teams index", "error": str(e)})

            for u in user_ids:
                if _state._scan_abort.is_set():
                    break
                _scan_user_teams(u["id"], u["displayName"])
            # Deduplicate: same file may appear in multiple users' Teams
            seen_ids: set = set()
            deduped = []
            for entry in work_items:
                fid = entry[1].get("id", "")
                if fid and fid in seen_ids:
                    continue
                if fid:
                    seen_ids.add(fid)
                deduped.append(entry)
            work_items[:] = deduped

    except Exception as e:
        broadcast("scan_error", {"file": "collection", "error": str(e)})

    # ── Filter work items already covered by checkpoint ─────────────────────
    if scanned_ids:
        work_items = [(k, m, f) for k, m, f in work_items if m.get("id", "") not in scanned_ids]

    total = len(work_items)
    broadcast("scan_start", {
        "total": total + resumed_count,
        "resumed": resumed_count,
    })
    # Clear the "Collecting…" phase text now that we're actually scanning items
    broadcast("scan_phase", {"phase": LANG.get("m365_phase_scanning", "Scanning…")})

    # ── Process items ─────────────────────────────────────────────────────────
    # Convert to a deque so each item is released from memory as soon as it's
    # processed (popleft is O(1) and drops the reference immediately).
    _work_q: deque = deque(work_items)
    work_items = None  # type: ignore[assignment]  # release the list; items live in _work_q
    gc.collect()       # run GC now to reclaim body strings freed during collection

    _items_since_save = 0
    idx = -1
    while _work_q:
        if _check_abort():
            # Save checkpoint so scan can be resumed later
            _save_checkpoint(ck_key, scanned_ids, _state.flagged_items, _state.scan_meta)
            return
        idx += 1
        kind, meta, _ = _work_q.popleft()  # releases this item from the deque immediately
        completed = idx + 1
        grand_total = total + resumed_count
        grand_done  = resumed_count + completed
        pct = int((grand_done / grand_total) * 100) if grand_total else 100
        name = meta.get("name", "") or meta.get("subject", f"email-{idx}")

        broadcast("scan_progress", {
            "index": grand_done, "total": grand_total,
            "file": name, "pct": pct, "eta": _eta(completed, total),
            "source": "m365",
        })

        try:
            if kind == "email":
                msg_id  = meta["id"]
                subject = meta.get("subject", "(no subject)")
                meta["name"] = subject
                meta["_source"] = "Exchange"
                meta["_source_type"] = "email"
                meta["_url"] = meta.get("webLink", "")

                # Scan body — use pre-extracted text (body HTML was stripped at
                # collection time to keep work_items memory footprint small)
                all_cprs = []
                body_text = ""
                if scan_email_body:
                    body_text = meta.pop("_precomputed_body", "")
                    body_result = _scan_text_direct(body_text)
                    all_cprs = list(body_result.get("cprs", []))

                # <span data-i18n="m365_opt_attachments" data-i18n="m365_opt_attachments">Scan attachments</span>
                uid = meta.get("_account_id", "me")
                att_results = []  # list of {name, cpr_count}
                if scan_attachments and meta.get("hasAttachments"):
                    att_iter = (conn.iter_message_attachments_for(uid, msg_id)
                                if uid != "me" else conn.iter_message_attachments(msg_id))
                    for att in att_iter:
                        att_name = att.get("name", "attachment")
                        att_ext  = Path(att_name).suffix.lower()
                        if att_ext not in SUPPORTED_EXTS:
                            continue
                        att_size_mb = att.get("size", 0) / 1_048_576
                        if att_size_mb > max_attach_mb:
                            broadcast("scan_error", {"file": att_name, "error": f"Skipped — {att_size_mb:.1f} MB exceeds {max_attach_mb} MB limit"})
                            continue
                        try:
                            att_bytes = (conn.download_attachment_for(uid, msg_id, att["id"])
                                         if uid != "me" else conn.download_attachment(msg_id, att["id"]))
                            att_result = _scan_bytes(att_bytes, att_name)
                            att_cprs   = att_result.get("cprs", [])
                            all_cprs.extend(att_cprs)
                            att_results.append({"name": att_name, "cpr_count": len(att_cprs)})
                        except Exception as att_err:
                            broadcast("scan_error", {"file": att_name, "error": str(att_err)})

                if all_cprs:
                    meta["_thumb"]         = _placeholder_svg(".eml", subject)
                    meta["_thumb_is_jpeg"] = False
                    meta["_attachments"]   = att_results
                    _email_pii = _get_pii_counts(body_text) if scan_email_body else {}
                    meta["_transfer_risk"]    = _check_transfer_risk(meta)
                    meta["_special_category"] = _check_special_category(
                        body_text if scan_email_body else "", all_cprs)
                    _broadcast_card(meta, all_cprs, pii_counts=_email_pii)
                del body_text  # free email text — may be large for HTML-rich emails

            else:  # file
                drive_id = meta.get("_drive_id") or meta.get("parentReference", {}).get("driveId")
                item_id  = meta["id"]
                ext      = Path(name).suffix.lower()

                # Memory guard — skip file download if available RAM is critically low
                try:
                    import psutil as _psutil
                    _avail_mb = _psutil.virtual_memory().available // 1_048_576
                    if _avail_mb < 300:
                        broadcast("scan_error", {"file": name, "error": f"Skipped — low memory ({_avail_mb} MB free)"})
                        logger.warning("[run_scan] low memory (%d MB free), skipping %s", _avail_mb, name)
                        continue
                except ImportError:
                    pass  # psutil not installed — skip guard

                uid = meta.get("_user_id") or meta.get("_account_id", "me")
                if uid and uid != "me" and not meta.get("_drive_id"):
                    content = conn.download_drive_item_for(uid, item_id)
                else:
                    content = conn.download_item(meta)

                # CPR scan — skip for video and audio (metadata-only; no text layer)
                _media_only = ext in VIDEO_EXTS or ext in AUDIO_EXTS
                result = {"cprs": [], "dates": []} if _media_only else _scan_bytes(content, name)
                cprs   = result.get("cprs", [])

                # ── Biometric photo scan (#9) + EXIF/video/audio metadata (#18) ─
                _face_count = 0
                _exif       = {}
                if ext in PHOTO_EXTS:
                    if scan_photos:
                        _face_count = _detect_photo_faces(content, name)
                    _exif = _extract_exif(content, name)
                elif ext in VIDEO_EXTS:
                    _exif = _extract_video_metadata(content, name)
                elif ext in AUDIO_EXTS:
                    _exif = _extract_audio_metadata(content, name)

                # Apply filters: distinct CPR threshold and GPS suppression
                _distinct_cprs   = list(dict.fromkeys(c["formatted"] for c in cprs))
                _cpr_qualifies   = len(_distinct_cprs) >= min_cpr_count
                _exif_has_pii    = _exif.get("has_pii") and (
                    not skip_gps_images or bool(_exif.get("pii_fields") or _exif.get("author"))
                )

                # Flag item if CPRs found (above threshold), faces detected, or EXIF PII found
                if (_cpr_qualifies and cprs) or _face_count > 0 or _exif_has_pii:
                    # Make thumbnail
                    if ext in {".jpg", ".jpeg", ".png"} and PIL_OK:
                        thumb = _make_thumb(content, name)
                        meta["_thumb"]         = thumb
                        meta["_thumb_is_jpeg"] = True
                    else:
                        meta["_thumb"]         = _placeholder_svg(ext, name)
                        meta["_thumb_is_jpeg"] = False
                    # Widen thumbnail support to HEIC/TIFF for photo items
                    if _face_count > 0 and meta.get("_thumb", "").startswith("<svg") and PIL_OK:
                        try:
                            meta["_thumb"]         = _make_thumb(content, name)
                            meta["_thumb_is_jpeg"] = True
                        except Exception:
                            pass
                    # Extract text for PII counting (lightweight -- no CPR re-scan)
                    try:
                        _file_text = content.decode("utf-8", errors="replace")
                    except Exception:
                        _file_text = ""
                    del content  # raw bytes no longer needed — free before NER/PII counting
                    _file_pii = _get_pii_counts(_file_text)
                    meta["_transfer_risk"]    = _check_transfer_risk(meta)
                    _sc = _check_special_category(_file_text, cprs)
                    # Photos with detected faces are biometric data (Art. 9) — add
                    # the category even when no CPR is present in the file.
                    if _face_count > 0 and "biometric" not in _sc:
                        _sc = sorted(_sc + ["biometric"])
                    if _exif.get("gps") and not skip_gps_images and "gps_location" not in _sc:
                        _sc = sorted(_sc + ["gps_location"])
                    if _exif_has_pii and "exif_pii" not in _sc:
                        _sc = sorted(_sc + ["exif_pii"])
                    meta["_special_category"] = _sc
                    meta["_face_count"]        = _face_count
                    meta["_exif"]              = _exif
                    _broadcast_card(meta, cprs, pii_counts=_file_pii)
                else:
                    del content  # no hits — free raw bytes immediately

        except M365PermissionError:
            uname = meta.get("_account", meta.get("_account_id", ""))
            broadcast("scan_error", {"file": name, "error": _permission_msg("file", uname or name)})
        except Exception as e:
            broadcast("scan_error", {"file": name, "error": str(e)})

        # Mark item as scanned regardless of whether it had CPR hits
        item_id = meta.get("id", "")
        if item_id:
            scanned_ids.add(item_id)

        # Periodic checkpoint save so progress survives crashes / forced quits
        _items_since_save += 1
        if _items_since_save >= _CHECKPOINT_SAVE_EVERY:
            _save_checkpoint(ck_key, scanned_ids, _state.flagged_items, _state.scan_meta)
            _items_since_save = 0
            gc.collect()  # periodic GC to reclaim memory from processed items

    grand_total = total + resumed_count
    _state.scan_meta["total_scanned"] = grand_total
    _state.scan_meta["flagged_count"] = len(_state.flagged_items)
    _clear_checkpoint()  # scan completed — checkpoint is no longer needed

    # Finalise DB scan record
    if _db and _db_scan_id:
        try:
            _db.finish_scan(_db_scan_id, grand_total)
        except Exception as _e:
            logger.error("[db] finish_scan failed: %s", _e)

    # Persist updated delta tokens so the next scan only fetches changes
    if delta_enabled and new_delta_tokens:
        merged = {**delta_tokens, **new_delta_tokens}
        _save_delta_tokens(merged)
        broadcast("scan_phase", {"phase": f"Delta tokens saved ({len(new_delta_tokens)} source(s) — next scan will be incremental)"})

    broadcast("scan_done", {"total_scanned": grand_total, "flagged_count": len(_state.flagged_items),
                             "delta": delta_enabled, "delta_sources": len(new_delta_tokens)})

