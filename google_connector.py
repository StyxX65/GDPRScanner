#!/usr/bin/env python3
"""
google_connector.py — Google Workspace connector for GDPR Scanner.

Handles service-account authentication with domain-wide delegation and exposes
iterators for:
  - Gmail messages (body + attachments) via the Gmail API
  - Google Drive files (with export for native Docs/Sheets/Slides) via Drive API

All file content is yielded as (metadata_dict, bytes_content) tuples, matching
the same contract used by m365_connector so the scan engine can reuse _scan_bytes.

Authentication:
  Service account JSON key with domain-wide delegation enabled in Google Workspace
  Admin Console → Security → API Controls → Domain-wide delegation.

  Required OAuth scopes (add to the service account's delegation entry):
    https://www.googleapis.com/auth/gmail.readonly
    https://www.googleapis.com/auth/drive.readonly
    https://www.googleapis.com/auth/admin.directory.user.readonly   (user listing)
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
import threading
from pathlib import Path
from typing import Iterator, Optional

# ── google-auth / google-api-python-client ────────────────────────────────────
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_AUTH_OK = True

    # Suppress the googleapiclient.http WARNING that fires before raising
    # HttpError for exportSizeLimitExceeded — we handle it ourselves below.
    class _SuppressExportSizeWarning(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "exportSizeLimitExceeded" not in record.getMessage()

    logging.getLogger("googleapiclient.http").addFilter(_SuppressExportSizeWarning())

except ImportError:
    GOOGLE_AUTH_OK = False

_DATA_DIR    = Path.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)
_SA_KEY_FILE       = _DATA_DIR / "google_sa.json"
_GOOGLE_TOKEN_FILE = _DATA_DIR / "google_token.json"

PERSONAL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
_DEVICE_AUTH_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL       = "https://oauth2.googleapis.com/token"
_USERINFO_URL    = "https://www.googleapis.com/oauth2/v2/userinfo"
_DEVICE_GRANT    = "urn:ietf:params:oauth:grant-type:device_code"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]
ADMIN_SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
]

# Google-native MIME types and the export format we request
_EXPORT_MAP = {
    "application/vnd.google-apps.document":     ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet":  ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing":      ("application/pdf", ".pdf"),
    "application/vnd.google-apps.form":         ("application/pdf", ".pdf"),
}

# Maximum export size for native Google files (bytes) — skip larger ones
_MAX_EXPORT_BYTES = 20 * 1024 * 1024  # 20 MB

# ── OU role mapping ───────────────────────────────────────────────────────────
_OU_ROLES_PATH = Path(__file__).parent / "classification" / "google_ou_roles.json"

def _load_ou_roles() -> tuple[list, list]:
    """Load student/staff OU prefix lists from skus/google_ou_roles.json.
    Returns (student_prefixes, staff_prefixes) — both lowercased."""
    try:
        import json as _j
        data = _j.loads(_OU_ROLES_PATH.read_text(encoding="utf-8"))
        students = [p.lower() for p in data.get("student_ou_prefixes", [])]
        staff    = [p.lower() for p in data.get("staff_ou_prefixes", [])]
        return students, staff
    except Exception:
        return ["/elever", "/students"], ["/personale", "/staff", "/lærere", "/ansatte"]

def classify_ou_role(org_unit_path: str) -> str:
    """Return 'student', 'staff', or 'other' based on orgUnitPath prefix."""
    if not org_unit_path:
        return "other"
    path_lower = org_unit_path.lower()
    students, staff = _load_ou_roles()
    for prefix in students:
        if path_lower.startswith(prefix):
            return "student"
    for prefix in staff:
        if path_lower.startswith(prefix):
            return "staff"
    return "other"



class GoogleError(Exception):
    pass


class GoogleConnector:
    """
    Wraps service-account + domain-wide delegation auth for Gmail and Drive.

    Usage:
        conn = GoogleConnector(key_dict, admin_email="admin@domain.com")
        for meta, data in conn.iter_gmail_messages("user@domain.com"):
            ...
    """

    def __init__(self, key_dict: dict, admin_email: str = ""):
        if not GOOGLE_AUTH_OK:
            raise GoogleError(
                "google-auth not installed — run: "
                "pip install google-auth google-auth-httplib2 google-api-python-client"
            )
        self._key_dict    = key_dict
        self._admin_email = admin_email.strip()
        self._lock        = threading.Lock()
        # Validate the key looks sane
        if key_dict.get("type") != "service_account":
            raise GoogleError("Key file must be a service_account JSON — found type: " + str(key_dict.get("type")))

    # ── Credential factories ──────────────────────────────────────────────────

    def _creds_for(self, user_email: str, scopes: list):
        """Return delegated credentials impersonating user_email."""
        base = service_account.Credentials.from_service_account_info(
            self._key_dict, scopes=scopes
        )
        return base.with_subject(user_email)

    def _admin_creds(self):
        """Admin Directory API credentials (impersonating admin_email)."""
        if not self._admin_email:
            raise GoogleError("admin_email required to list workspace users")
        return self._creds_for(self._admin_email, ADMIN_SCOPES + GMAIL_SCOPES + DRIVE_SCOPES)

    # ── Connectivity check ────────────────────────────────────────────────────

    def is_authenticated(self) -> bool:
        """Light check — verifies credentials refresh without making API calls."""
        try:
            creds = service_account.Credentials.from_service_account_info(
                self._key_dict, scopes=GMAIL_SCOPES
            )
            return bool(creds)
        except Exception:
            return False

    def get_service_account_email(self) -> str:
        return self._key_dict.get("client_email", "")

    def get_project_id(self) -> str:
        return self._key_dict.get("project_id", "")

    # ── User listing ─────────────────────────────────────────────────────────

    def list_users(self, domain: str = "") -> list[dict]:
        """
        Return [{id, email, displayName}] for all active users in the domain.
        Requires Admin Directory API scope on the service account delegation.
        Falls back gracefully if admin_email is not set.
        """
        if not self._admin_email:
            return []
        try:
            creds   = self._admin_creds()
            service = build("admin", "directory_v1", credentials=creds, cache_discovery=False)
            results = []
            page_token = None
            params: dict = {"customer": "my_customer", "maxResults": 500, "orderBy": "email", "projection": "full"}
            if domain:
                params["domain"] = domain
            while True:
                if page_token:
                    params["pageToken"] = page_token
                resp = service.users().list(**params).execute()
                for u in resp.get("users", []):
                    if not u.get("suspended") and not u.get("archived"):
                        ou_path = u.get("orgUnitPath", "")
                        results.append({
                            "id":           u.get("id", ""),
                            "email":        u.get("primaryEmail", ""),
                            "displayName":  u.get("name", {}).get("fullName", ""),
                            "orgUnitPath":  ou_path,
                            "userRole":     classify_ou_role(ou_path),
                        })
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return results
        except HttpError as e:
            raise GoogleError(f"Admin Directory API error: {e}") from e

    # ── Gmail iterator ────────────────────────────────────────────────────────

    def iter_gmail_messages(
        self,
        user_email: str,
        max_messages: int = 2000,
        scan_body: bool = True,
        scan_attachments: bool = True,
        max_attach_mb: float = 20.0,
    ) -> Iterator[tuple[dict, bytes]]:
        """
        Yield (metadata, content_bytes) for each Gmail message / attachment.

        For messages with only inline text body: yields one item with the body text.
        For attachments: yields one item per attachment (skips if > max_attach_mb).
        """
        try:
            creds   = self._creds_for(user_email, GMAIL_SCOPES)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Gmail auth failed for {user_email}: {e}") from e
        yield from _gmail_iter(service, user_email, max_messages, scan_body, scan_attachments, max_attach_mb)

    # ── Drive iterator ────────────────────────────────────────────────────────

    def iter_drive_files(
        self,
        user_email: str,
        max_files: int = 5000,
        max_file_mb: float = 50.0,
    ) -> Iterator[tuple[dict, bytes]]:
        """
        Yield (metadata, content_bytes) for each Drive file.

        Native Google formats (Docs/Sheets/Slides) are exported to Office format.
        Binary files are downloaded directly (skipped if > max_file_mb).
        """
        try:
            creds   = self._creds_for(user_email, DRIVE_SCOPES)
            service = build("drive", "v3", credentials=creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Drive auth failed for {user_email}: {e}") from e
        yield from _drive_iter(service, user_email, max_files, max_file_mb)

    def get_drive_start_token(self, user_email: str) -> str:
        """Return the current Changes API start page token for user's Drive."""
        try:
            creds   = self._creds_for(user_email, DRIVE_SCOPES)
            service = build("drive", "v3", credentials=creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Drive auth failed for {user_email}: {e}") from e
        return _drive_get_start_page_token(service)

    def get_drive_changes(
        self,
        user_email: str,
        page_token: str,
        max_files: int = 5000,
        max_file_mb: float = 50.0,
    ) -> "tuple[list[tuple[dict, bytes]], str]":
        """Return (changed_files, new_page_token) since page_token."""
        try:
            creds   = self._creds_for(user_email, DRIVE_SCOPES)
            service = build("drive", "v3", credentials=creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Drive auth failed for {user_email}: {e}") from e
        return _drive_changes_collect(service, user_email, page_token, max_files, max_file_mb)


# ── Persistence helpers ───────────────────────────────────────────────────────

def load_saved_key() -> Optional[dict]:
    """Load service account key from disk. Returns None if not found."""
    if _SA_KEY_FILE.exists():
        try:
            return json.loads(_SA_KEY_FILE.read_text())
        except Exception:
            return None
    return None


def save_key(key_dict: dict) -> None:
    """Persist service account key to disk (chmod 600)."""
    _SA_KEY_FILE.write_text(json.dumps(key_dict, indent=2))
    try:
        _SA_KEY_FILE.chmod(0o600)
    except Exception:
        pass


def delete_key() -> None:
    """Remove persisted service account key."""
    try:
        if _SA_KEY_FILE.exists():
            _SA_KEY_FILE.unlink()
    except Exception:
        pass


# ── Internal helpers ──────────────────────────────────────────────────────────

def _epoch_to_iso(epoch_secs: int) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(epoch_secs, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def _extract_body(payload: dict) -> bytes:
    """Recursively extract plain-text (or HTML) body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data)
    if mime == "text/html" and body_data:
        # Return raw HTML bytes — _scan_bytes handles HTML stripping
        return base64.urlsafe_b64decode(body_data)

    # Recurse into multipart
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return b""


def _iter_parts(payload: dict):
    """Yield all leaf parts (for attachment scanning)."""
    parts = payload.get("parts", [])
    if not parts:
        yield payload
    else:
        for part in parts:
            yield from _iter_parts(part)


# ── Shared iteration helpers (used by both GoogleConnector and PersonalGoogleConnector) ──

def _gmail_iter(
    service,
    user_email: str,
    max_messages: int,
    scan_body: bool,
    scan_attachments: bool,
    max_attach_mb: float,
) -> Iterator[tuple[dict, bytes]]:
    """Paginate Gmail messages and yield (metadata, bytes) tuples."""
    ids: list[str] = []
    page_token = None
    while len(ids) < max_messages:
        params: dict = {"userId": "me", "maxResults": min(500, max_messages - len(ids))}
        if page_token:
            params["pageToken"] = page_token
        try:
            resp = service.users().messages().list(**params).execute()
        except HttpError as e:
            raise GoogleError(f"Gmail list error for {user_email}: {e}") from e
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    max_attach_bytes = int(max_attach_mb * 1024 * 1024)

    for msg_id in ids:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except HttpError:
            continue

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        meta = {
            "id":           f"gmail:{msg_id}",
            "name":         headers.get("subject", "(no subject)"),
            "_source":      "gmail",
            "_source_type": "gmail",
            "_account":     user_email,
            "_account_id":  user_email,
            "_url":         f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
            "receivedDateTime": _epoch_to_iso(int(msg.get("internalDate", 0)) // 1000),
            "size":         msg.get("sizeEstimate", 0),
        }

        payload = msg.get("payload", {})

        if scan_body:
            body_bytes = _extract_body(payload)
            if body_bytes:
                yield (meta, body_bytes)

        if scan_attachments:
            for part in _iter_parts(payload):
                filename = part.get("filename", "")
                body     = part.get("body", {})
                att_id   = body.get("attachmentId")
                size     = body.get("size", 0)
                if not att_id or not filename:
                    continue
                if size > max_attach_bytes:
                    continue
                try:
                    att = service.users().messages().attachments().get(
                        userId="me", messageId=msg_id, id=att_id
                    ).execute()
                    data = base64.urlsafe_b64decode(att.get("data", ""))
                except HttpError:
                    continue
                att_meta = {
                    **meta,
                    "id":   f"gmail:{msg_id}:{att_id}",
                    "name": filename,
                    "size": len(data),
                }
                yield (att_meta, data)


def _download_drive_file(
    service,
    f: dict,
    user_email: str,
    max_bytes: int,
) -> "tuple[dict, bytes] | None":
    """Download one Drive file entry. Returns (meta, data) or None if skipped."""
    mime  = f.get("mimeType", "")
    fid   = f.get("id", "")
    fname = f.get("name", "")
    size  = int(f.get("size", 0) or 0)

    meta = {
        "id":           f"gdrive:{fid}",
        "name":         fname,
        "_source":      "gdrive",
        "_source_type": "gdrive",
        "_account":     user_email,
        "_account_id":  user_email,
        "_url":         f.get("webViewLink", ""),
        "lastModifiedDateTime": f.get("modifiedTime", "")[:10],
        "size":         size,
    }

    if mime in _EXPORT_MAP:
        export_mime, ext = _EXPORT_MAP[mime]
        try:
            req   = service.files().export_media(fileId=fid, mimeType=export_mime)
            buf   = io.BytesIO()
            dl    = MediaIoBaseDownload(buf, req, chunksize=4 * 1024 * 1024)
            done  = False
            total = 0
            while not done:
                _, done = dl.next_chunk()
                total = buf.tell()
                if total > _MAX_EXPORT_BYTES:
                    break
            if total > _MAX_EXPORT_BYTES:
                return None
            meta["name"] = fname + ext
            meta["size"] = total
            data = buf.getvalue()
            del buf
            return (meta, data)
        except HttpError as e:
            if "exportSizeLimitExceeded" in str(e):
                print(
                    f"[gdrive] skip '{fname}' — file too large for Google export API"
                    f" (exportSizeLimitExceeded); fid={fid}",
                    flush=True,
                )
            return None
    else:
        if mime.startswith("application/vnd.google-apps."):
            return None
        if size == 0 or size > max_bytes:
            return None
        try:
            req  = service.files().get_media(fileId=fid)
            buf  = io.BytesIO()
            dl   = MediaIoBaseDownload(buf, req, chunksize=4 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()
            data = buf.getvalue()
            del buf
            return (meta, data)
        except HttpError:
            return None


def _drive_iter(
    service,
    user_email: str,
    max_files: int,
    max_file_mb: float,
) -> Iterator[tuple[dict, bytes]]:
    """Paginate Drive files and yield (metadata, bytes) tuples."""
    max_bytes = int(max_file_mb * 1024 * 1024)
    fields = "nextPageToken,files(id,name,mimeType,size,webViewLink,modifiedTime,owners,parents)"
    page_token = None
    fetched = 0

    while fetched < max_files:
        params: dict = {
            "pageSize": min(1000, max_files - fetched),
            "fields": fields,
            "q": "trashed = false",
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            resp = service.files().list(**params).execute()
        except HttpError as e:
            raise GoogleError(f"Drive list error for {user_email}: {e}") from e

        for f in resp.get("files", []):
            fetched += 1
            result = _download_drive_file(service, f, user_email, max_bytes)
            if result:
                yield result

        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def _drive_get_start_page_token(service) -> str:
    """Return the current Changes API start page token for this Drive."""
    resp = service.changes().getStartPageToken().execute()
    return resp["startPageToken"]


def _drive_changes_collect(
    service,
    user_email: str,
    page_token: str,
    max_files: int,
    max_file_mb: float,
) -> "tuple[list[tuple[dict, bytes]], str]":
    """
    Collect Drive changes since page_token using the Changes API.
    Returns (list_of_(meta, data)_tuples, new_start_page_token).
    Skips removed/trashed files.
    Raises GoogleError on API failure so the caller can fall back to a full scan.
    """
    max_bytes = int(max_file_mb * 1024 * 1024)
    fields = (
        "nextPageToken,newStartPageToken,"
        "changes(removed,file(id,name,mimeType,size,webViewLink,modifiedTime,owners,parents))"
    )
    results: list = []
    new_token = page_token
    fetched = 0

    while fetched < max_files:
        params: dict = {
            "pageToken":      page_token,
            "spaces":         "drive",
            "fields":         fields,
            "includeRemoved": True,
            "pageSize":       min(1000, max_files - fetched),
        }
        try:
            resp = service.changes().list(**params).execute()
        except HttpError as e:
            raise GoogleError(f"Drive changes error for {user_email}: {e}") from e

        for change in resp.get("changes", []):
            if change.get("removed"):
                continue
            f = change.get("file")
            if not f:
                continue
            fetched += 1
            result = _download_drive_file(service, f, user_email, max_bytes)
            if result:
                results.append(result)

        if "newStartPageToken" in resp:
            new_token = resp["newStartPageToken"]
            break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results, new_token


# ── Personal Google account (OAuth device-code) connector ────────────────────

class PersonalGoogleConnector:
    """
    OAuth 2.0 device-code connector for personal Google accounts.

    Provides the same public interface as GoogleConnector so the scan engine
    can use either transparently via state.google_connector.

    Authentication:
      GCP project with an OAuth 2.0 Desktop App credential.
      Required scopes: gmail.readonly, drive.readonly.
    """

    def __init__(self, token_data: dict):
        """
        Construct from a stored token dict with keys:
          access_token, refresh_token, client_id, client_secret, token_uri, scopes
        """
        if not GOOGLE_AUTH_OK:
            raise GoogleError(
                "google-auth not installed — run: "
                "pip install google-auth google-auth-httplib2 google-api-python-client"
            )
        self._token_data = token_data
        self._creds = self._build_creds()

    def _build_creds(self):
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=self._token_data.get("access_token"),
            refresh_token=self._token_data.get("refresh_token"),
            token_uri=self._token_data.get("token_uri", _TOKEN_URL),
            client_id=self._token_data.get("client_id"),
            client_secret=self._token_data.get("client_secret"),
            scopes=self._token_data.get("scopes", PERSONAL_SCOPES),
        )

    def _refresh_if_needed(self) -> None:
        from google.auth.transport.requests import Request
        if not self._creds.valid:
            if self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
                updated = dict(self._token_data)
                updated["access_token"] = self._creds.token
                save_personal_token(updated)
                self._token_data = updated

    def is_authenticated(self) -> bool:
        try:
            self._refresh_if_needed()
            return bool(self._creds.token)
        except Exception:
            return False

    def get_user_info(self) -> dict:
        """Return {id, email, displayName} for the authenticated user."""
        if not REQUESTS_OK:
            raise GoogleError("requests library required")
        self._refresh_if_needed()
        resp = _requests.get(
            _USERINFO_URL,
            headers={"Authorization": f"Bearer {self._creds.token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "id":          data.get("id", ""),
            "email":       data.get("email", ""),
            "displayName": data.get("name", ""),
        }

    def list_users(self, domain: str = "") -> list[dict]:
        """Return a single-item list for the signed-in user (no admin access needed)."""
        info = self.get_user_info()
        return [{
            "id":          info["email"],
            "email":       info["email"],
            "displayName": info["displayName"],
            "orgUnitPath": "",
            "userRole":    "other",
        }]

    def iter_gmail_messages(
        self,
        user_email: str,
        max_messages: int = 2000,
        scan_body: bool = True,
        scan_attachments: bool = True,
        max_attach_mb: float = 20.0,
    ) -> Iterator[tuple[dict, bytes]]:
        """Yield (metadata, bytes) for each Gmail message / attachment."""
        self._refresh_if_needed()
        try:
            service = build("gmail", "v1", credentials=self._creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Gmail auth failed: {e}") from e
        yield from _gmail_iter(service, user_email, max_messages, scan_body, scan_attachments, max_attach_mb)

    def iter_drive_files(
        self,
        user_email: str,
        max_files: int = 5000,
        max_file_mb: float = 50.0,
    ) -> Iterator[tuple[dict, bytes]]:
        """Yield (metadata, bytes) for each Drive file."""
        self._refresh_if_needed()
        try:
            service = build("drive", "v3", credentials=self._creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Drive auth failed: {e}") from e
        yield from _drive_iter(service, user_email, max_files, max_file_mb)

    def get_drive_start_token(self, user_email: str) -> str:
        """Return the current Changes API start page token for this Drive."""
        self._refresh_if_needed()
        try:
            service = build("drive", "v3", credentials=self._creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Drive auth failed: {e}") from e
        return _drive_get_start_page_token(service)

    def get_drive_changes(
        self,
        user_email: str,
        page_token: str,
        max_files: int = 5000,
        max_file_mb: float = 50.0,
    ) -> "tuple[list[tuple[dict, bytes]], str]":
        """Return (changed_files, new_page_token) since page_token."""
        self._refresh_if_needed()
        try:
            service = build("drive", "v3", credentials=self._creds, cache_discovery=False)
        except HttpError as e:
            raise GoogleError(f"Drive auth failed: {e}") from e
        return _drive_changes_collect(service, user_email, page_token, max_files, max_file_mb)

    @staticmethod
    def get_device_code_flow(client_id: str, client_secret: str) -> dict:
        """
        Initiate a Google device-code flow.
        Returns a flow dict containing user_code, verification_url, device_code, etc.
        """
        if not REQUESTS_OK:
            raise GoogleError("requests library required — run: pip install requests")
        resp = _requests.post(_DEVICE_AUTH_URL, data={
            "client_id": client_id,
            "scope":     " ".join(PERSONAL_SCOPES),
        }, timeout=10)
        data = resp.json()
        if "device_code" not in data:
            raise GoogleError(
                f"Failed to start device flow: {data.get('error_description', data)}"
            )
        return {
            "device_code":      data["device_code"],
            "user_code":        data["user_code"],
            "verification_url": data.get("verification_url", "https://www.google.com/device"),
            "expires_in":       data.get("expires_in", 1800),
            "interval":         data.get("interval", 5),
            "client_id":        client_id,
            "client_secret":    client_secret,
        }

    @staticmethod
    def complete_device_code_flow(flow: dict) -> "PersonalGoogleConnector":
        """
        Poll until the user completes sign-in at verification_url.
        Blocks the calling thread. Returns a ready PersonalGoogleConnector.
        """
        if not REQUESTS_OK:
            raise GoogleError("requests library required — run: pip install requests")
        client_id     = flow["client_id"]
        client_secret = flow["client_secret"]
        device_code   = flow["device_code"]
        interval      = flow.get("interval", 5)
        expires_in    = flow.get("expires_in", 1800)
        deadline      = time.time() + expires_in

        while time.time() < deadline:
            time.sleep(interval)
            resp = _requests.post(_TOKEN_URL, data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "device_code":   device_code,
                "grant_type":    _DEVICE_GRANT,
            }, timeout=10)
            data = resp.json()
            if "access_token" in data:
                token_data = {
                    "access_token":  data["access_token"],
                    "refresh_token": data.get("refresh_token", ""),
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "token_uri":     _TOKEN_URL,
                    "scopes":        PERSONAL_SCOPES,
                }
                save_personal_token(token_data)
                return PersonalGoogleConnector(token_data)
            err = data.get("error", "")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval = max(interval + 5, 5)
                continue
            raise GoogleError(
                f"Device flow error: {data.get('error_description', err)}"
            )

        raise GoogleError("Device code flow timed out")


# ── Personal token persistence ────────────────────────────────────────────────

def save_personal_token(data: dict) -> None:
    """Persist OAuth token to disk (chmod 600)."""
    _GOOGLE_TOKEN_FILE.write_text(json.dumps(data, indent=2))
    try:
        _GOOGLE_TOKEN_FILE.chmod(0o600)
    except Exception:
        pass


def load_personal_token() -> Optional[dict]:
    """Load OAuth token from disk. Returns None if not found."""
    if _GOOGLE_TOKEN_FILE.exists():
        try:
            return json.loads(_GOOGLE_TOKEN_FILE.read_text())
        except Exception:
            return None
    return None


def delete_personal_token() -> None:
    """Remove persisted OAuth token."""
    try:
        if _GOOGLE_TOKEN_FILE.exists():
            _GOOGLE_TOKEN_FILE.unlink()
    except Exception:
        pass
