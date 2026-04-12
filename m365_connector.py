#!/usr/bin/env python3
"""
m365_connector.py — Microsoft Graph API connector for M365 Scanner.

Handles OAuth device-code flow via MSAL and exposes iterators for:
  - Exchange/Outlook mail (body + attachments)
  - OneDrive personal files
  - SharePoint site files
  - Teams channel files (backed by SharePoint)

All file content is yielded as (metadata_dict, bytes_content) tuples so the
scanner can process them without keeping everything in memory.
"""

import json
import logging
import time
import tempfile
import threading
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# ── MSAL ──────────────────────────────────────────────────────────────────────
try:
    import msal
    MSAL_OK = True
except ImportError:
    MSAL_OK = False

# ── Requests ──────────────────────────────────────────────────────────────────
try:
    import requests as _requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Delegated scopes — used when signing in as a specific user (device code flow)
SCOPES = [
    "Mail.Read",
    "Files.Read.All",
    "Sites.Read.All",
    "Team.ReadBasic.All",
    "ChannelMessage.Read.All",
    "User.Read",
    "User.Read.All",
]

# Application scope — client credentials flow uses a single fixed scope
APP_SCOPES = ["https://graph.microsoft.com/.default"]

_DATA_DIR         = Path.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)
_TOKEN_CACHE_FILE = _DATA_DIR / "token.json"


class M365Error(Exception):
    pass


class M365PermissionError(M365Error):
    """
    Raised when the Graph API returns 403 Forbidden.

    With delegated (device-code) permissions the signed-in user can only
    access their own data via /me/...  Accessing /users/{other}/... requires
    one of:
      • The signed-in user is a Global Admin or Exchange Admin
      • The Azure app has been granted Application permissions (not Delegated)
        for Mail.Read, Files.Read.All, etc. and an admin has consented
      • The target user has explicitly shared their mailbox/OneDrive
    """
    def __init__(self, path: str, user_hint: str = ""):
        self.path = path
        self.user_hint = user_hint
        who = f" for {user_hint}" if user_hint else ""
        super().__init__(
            f"403 Forbidden{who}: the signed-in account does not have permission "
            f"to access this resource.\n"
            f"  Path: {path}\n"
            f"  Fix: the signed-in user must be a Global/Exchange Admin, OR an admin must "
            f"grant Application permissions (Mail.Read, Files.Read.All, Sites.Read.All) "
            f"in Azure → App registrations → API permissions → Grant admin consent."
        )


class M365DeltaTokenExpired(M365Error):
    """Raised when a stored delta token is no longer valid (HTTP 410 Gone).
    The caller should clear the token and fall back to a full scan."""
    pass


class M365DriveNotFound(M365Error):
    """Raised when the Graph API returns 404 for a drive/root path.

    Common causes: OneDrive licence not assigned, service plan disabled,
    drive not yet provisioned (user has never signed in), or account
    suspended/deleted.  Not a scan error — callers should skip the user
    and log at a lower severity.
    """
    pass


class M365Connector:
    def __init__(self, client_id: str, tenant_id: str, client_secret: str = ""):
        if not MSAL_OK:
            raise M365Error("msal not installed — run: pip install msal")
        if not REQUESTS_OK:
            raise M365Error("requests not installed — run: pip install requests")

        self.client_id     = client_id
        self.tenant_id     = tenant_id
        self.client_secret = client_secret.strip()
        self._token: Optional[dict] = None
        self._lock = threading.Lock()

        authority = f"https://login.microsoftonline.com/{tenant_id}"

        if self.client_secret:
            # ── Application mode (client credentials) ─────────────────────────
            self._app = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=self.client_secret,
            )
            self._mode = "application"
        else:
            # ── Delegated mode (device code flow) ─────────────────────────────
            cache = msal.SerializableTokenCache()
            if _TOKEN_CACHE_FILE.exists():
                try:
                    cache.deserialize(_TOKEN_CACHE_FILE.read_text())
                except Exception:
                    pass
            self._app = msal.PublicClientApplication(
                client_id, authority=authority, token_cache=cache
            )
            self._mode = "delegated"

    @property
    def is_app_mode(self) -> bool:
        return self._mode == "application"

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _save_cache(self):
        if self._mode == "delegated" and self._app.token_cache.has_state_changed:
            try:
                _TOKEN_CACHE_FILE.write_text(self._app.token_cache.serialize())
            except Exception:
                pass

    def get_device_code_flow(self) -> dict:
        """Start device code flow (delegated mode only)."""
        if self._mode == "application":
            raise M365Error("Device code flow is not used in application mode.")
        flow = self._app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise M365Error(f"Failed to start device flow: {flow.get('error_description', flow)}")
        return flow

    def complete_device_code_flow(self, flow: dict) -> bool:
        """Poll until user completes auth. Returns True on success."""
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self._token = result
            self._save_cache()
            return True
        raise M365Error(result.get("error_description", str(result)))

    def try_silent_auth(self) -> bool:
        """Try to get a token without user interaction."""
        if self._mode == "application":
            result = self._app.acquire_token_for_client(scopes=APP_SCOPES)
            if result and "access_token" in result:
                result["_acquired_at"] = time.time()
                self._token = result
                return True
            return False
        else:
            accounts = self._app.get_accounts()
            if not accounts:
                return False
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                result["_acquired_at"] = time.time()
                self._token = result
                self._save_cache()
                return True
            return False

    def get_access_token(self) -> str:
        with self._lock:
            if self._token and "access_token" in self._token:
                expires_in = self._token.get("expires_in", 0)
                acquired   = self._token.get("_acquired_at", time.time())
                if time.time() < acquired + expires_in - 60:
                    return self._token["access_token"]
            if self.try_silent_auth():
                return self._token["access_token"]
        raise M365Error("Not authenticated — please sign in first.")

    def authenticate_app_mode(self) -> bool:
        """Acquire token via client credentials. Call once after init with client_secret."""
        if self._mode != "application":
            raise M365Error("authenticate_app_mode() called in delegated mode.")
        result = self._app.acquire_token_for_client(scopes=APP_SCOPES)
        if "access_token" in result:
            result["_acquired_at"] = time.time()
            self._token = result
            return True
        err = result.get("error_description") or result.get("error") or str(result)
        raise M365Error(f"Client credentials auth failed: {err}")

    def get_user_info(self) -> dict:
        if self._mode == "application":
            # /me is not available with app-only tokens — return a placeholder
            return {"displayName": "App (service account)", "id": "", "mail": ""}
        return self._get("/me")

    def list_users(self, top: int = 999) -> list:
        """List licensed domain users in the tenant (requires User.Read.All).

        Tries a filtered query first; falls back to a plain /users call if the
        tenant's directory index doesn't support $count + ConsistencyLevel.
        """
        select = "id,displayName,mail,userPrincipalName,accountEnabled,userType,assignedLicenses"

        def _fetch(params: dict, extra_headers: dict = None) -> list:
            """Paginate through /users with given params, using _get() so 403s
            are raised as M365PermissionError with the Graph error body."""
            url = "/users"
            all_items = []
            first = True
            while url:
                if extra_headers:
                    # _get() doesn't support extra headers, so call requests directly
                    full_url = url if url.startswith("http") else GRAPH_BASE + url
                    r = _requests.get(full_url,
                                      headers={**self._headers(), **extra_headers},
                                      params=(params if first else None),
                                      timeout=self._TIMEOUT_API)
                    if r.status_code == 429:
                        time.sleep(int(r.headers.get("Retry-After", 5)))
                        continue
                    if r.status_code == 403:
                        try:
                            msg = r.json().get("error", {}).get("message", "")
                        except Exception:
                            msg = r.text[:200]
                        raise M365PermissionError(url, msg)
                    if not r.ok:
                        try:
                            err = r.json().get("error", {})
                            msg = err.get("message") or err.get("code") or r.text[:300]
                        except Exception:
                            msg = r.text[:300]
                        raise M365Error(f"Graph /users error {r.status_code}: {msg}")
                    data = r.json()
                else:
                    data = self._get(url, params if first else None)
                first = False
                all_items.extend(data.get("value", []))
                url = data.get("@odata.nextLink")
            return all_items

        # Attempt 1: filtered query with ConsistencyLevel (works on most tenants)
        try:
            users = _fetch(
                params={
                    "$top": str(top),
                    "$filter": "accountEnabled eq true and userType eq 'Member'",
                    "$select": select,
                    "$count": "true",
                },
                extra_headers={"ConsistencyLevel": "eventual"},
            )
        except M365PermissionError:
            raise
        except Exception:
            # Attempt 2: plain /users with no filter (works everywhere)
            users = _fetch(params={"$top": str(top), "$select": select})
            # Post-filter guests / disabled accounts
            users = [u for u in users
                     if u.get("accountEnabled")
                     and u.get("userType", "Member") == "Member"]

        # Post-filter: skip accounts with no mail, external sync objects,
        # or no assigned licenses (service accounts, shared mailboxes, sync objects)
        users = [
            u for u in users
            if (u.get("mail") or u.get("userPrincipalName", ""))
            and "#EXT#" not in (u.get("userPrincipalName") or "")
            and u.get("assignedLicenses")  # must have at least one license
        ]
        users.sort(key=lambda u: (u.get("displayName") or "").lower())
        return users

    # ── User-scoped variants (scan other users as admin) ──────────────────────

    def list_mail_folders_for(self, user_id: str) -> list:
        return list(self._paginate(f"/users/{user_id}/mailFolders", {"$top": "100"}))


    def iter_messages_for(self, user_id: str, folder_id: str = "inbox", top: int = 50) -> Iterator[dict]:
        path = f"/users/{user_id}/mailFolders/{folder_id}/messages"
        params = {
            "$top": str(top),
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,bodyPreview,body,parentFolderId",
            "$orderby": "receivedDateTime desc",
        }
        yield from self._paginate(path, params)

    def iter_message_attachments_for(self, user_id: str, message_id: str) -> Iterator[dict]:
        try:
            yield from self._paginate(
                f"/users/{user_id}/messages/{message_id}/attachments", {"$top": "100"}
            )
        except Exception:
            return

    def download_attachment_for(self, user_id: str, message_id: str, attachment_id: str) -> bytes:
        import base64 as _b64
        data = self._get(f"/users/{user_id}/messages/{message_id}/attachments/{attachment_id}")
        return _b64.b64decode(data.get("contentBytes", "") or "")

    def iter_onedrive_files_for(self, user_id: str, display_name: str = "") -> Iterator[dict]:
        label = display_name or user_id
        yield from self._iter_drive_folder_for(user_id, f"/users/{user_id}/drive/root", f"OneDrive ({label})")

    def _iter_drive_folder_for(self, user_id: str, item_path: str, source: str) -> Iterator[dict]:
        path = f"{item_path}/children"
        try:
            items = list(self._paginate(path, {"$top": "200", "$select": "id,name,file,folder,size,webUrl,lastModifiedDateTime,parentReference,shared"}))
        except Exception:
            return
        for item in items:
            if item.get("folder"):
                next_path = f"/users/{user_id}/drive/items/{item['id']}"
                yield from self._iter_drive_folder_for(user_id, next_path, source)
            elif item.get("file"):
                item["_source"] = source
                item["_user_id"] = user_id
                yield item

    def download_drive_item_for(self, user_id: str, item_id: str) -> bytes:
        url = f"{GRAPH_BASE}/users/{user_id}/drive/items/{item_id}/content"
        return self._get_bytes(url)

    def iter_teams_files_for(self, user_id: str, display_name: str = "") -> Iterator[dict]:
        """Yield Teams files for a specific user."""
        try:
            teams = list(self._paginate(f"/users/{user_id}/joinedTeams", {"$top": "50"}))
        except Exception:
            return
        for team in teams:
            yield from self.iter_teams_files(team["id"], team.get("displayName", ""))


    def is_authenticated(self) -> bool:
        try:
            self.get_access_token()
            return True
        except M365Error:
            return False

    def sign_out(self):
        accounts = self._app.get_accounts()
        for acc in accounts:
            self._app.remove_account(acc)
        self._token = None
        if _TOKEN_CACHE_FILE.exists():
            _TOKEN_CACHE_FILE.unlink()

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Accept": "application/json",
        }

    # ── Timeouts ──────────────────────────────────────────────────────────────
    # Tuple: (connect_timeout, read_timeout) — tight connect, generous read.
    # File downloads get extra read time for slow wireless connections.
    _TIMEOUT_API   = (10, 45)   # JSON API calls
    _TIMEOUT_BYTES = (10, 120)  # File / attachment downloads

    # Network errors that are safe to retry (transient dropouts, resets)
    _RETRYABLE_ERRORS = (
        _requests.exceptions.ConnectionError,
        _requests.exceptions.Timeout,
        _requests.exceptions.ChunkedEncodingError,
        _requests.exceptions.ReadTimeout,
    )
    _MAX_RETRIES = 4            # total attempts (1 original + 3 retries)
    _BACKOFF_BASE = 2           # seconds: 2, 4, 8 between retries

    def _backoff_sleep(self, attempt: int, extra: float = 0) -> None:
        """Sleep 2^attempt seconds (capped at 30) plus any server-requested delay."""
        wait = min(self._BACKOFF_BASE ** attempt, 30) + extra
        time.sleep(wait)

    def _get(self, path: str, params: dict = None, _retry: bool = True) -> dict:
        url = path if path.startswith("http") else GRAPH_BASE + path
        for attempt in range(self._MAX_RETRIES):
            try:
                r = _requests.get(url, headers=self._headers(),
                                  params=params, timeout=self._TIMEOUT_API)
            except self._RETRYABLE_ERRORS:
                if attempt == self._MAX_RETRIES - 1:
                    raise
                self._backoff_sleep(attempt)
                continue

            if r.status_code == 429:
                self._backoff_sleep(attempt, float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code == 503 or r.status_code == 504:
                # Gateway timeout / service unavailable — transient, retry
                if attempt < self._MAX_RETRIES - 1:
                    self._backoff_sleep(attempt)
                    continue
            if r.status_code == 410:
                raise M365DeltaTokenExpired(f"410 Gone — delta token expired: {path}")
            if r.status_code == 401 and _retry:
                self._token = None
                if self.try_silent_auth():
                    return self._get(path, params, _retry=False)
            if r.status_code == 403:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except Exception:
                    msg = r.text[:200]
                raise M365PermissionError(path, msg)
            if r.status_code == 404:
                raise M365DriveNotFound(f"404 Not Found: {path}")
            r.raise_for_status()
            return r.json()
        raise _requests.exceptions.RetryError(f"Gave up after {self._MAX_RETRIES} attempts: {url}")

    def _post(self, path: str, body: dict, _retry: bool = True) -> dict:
        url = path if path.startswith("http") else GRAPH_BASE + path
        headers = {**self._headers(), "Content-Type": "application/json"}
        for attempt in range(self._MAX_RETRIES):
            try:
                r = _requests.post(url, headers=headers, json=body,
                                   timeout=self._TIMEOUT_API)
            except self._RETRYABLE_ERRORS:
                if attempt == self._MAX_RETRIES - 1:
                    raise
                self._backoff_sleep(attempt)
                continue

            if r.status_code == 429:
                self._backoff_sleep(attempt, float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code == 503 or r.status_code == 504:
                if attempt < self._MAX_RETRIES - 1:
                    self._backoff_sleep(attempt)
                    continue
            if r.status_code == 401 and _retry:
                self._token = None
                if self.try_silent_auth():
                    return self._post(path, body, _retry=False)
            if r.status_code == 403:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except Exception:
                    msg = r.text[:200]
                raise M365PermissionError(path, msg)
            r.raise_for_status()
            return r.json()
        raise _requests.exceptions.RetryError(f"Gave up after {self._MAX_RETRIES} attempts: {url}")

    def _get_bytes(self, url: str, _retry: bool = True) -> bytes:
        """Download binary content (file / attachment) with streaming and retry."""
        for attempt in range(self._MAX_RETRIES):
            try:
                r = _requests.get(url, headers=self._headers(),
                                  timeout=self._TIMEOUT_BYTES, stream=True)
            except self._RETRYABLE_ERRORS:
                if attempt == self._MAX_RETRIES - 1:
                    raise
                self._backoff_sleep(attempt)
                continue

            if r.status_code == 429:
                self._backoff_sleep(attempt, float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code == 503 or r.status_code == 504:
                if attempt < self._MAX_RETRIES - 1:
                    self._backoff_sleep(attempt)
                    continue
            if r.status_code == 401 and _retry:
                self._token = None
                if self.try_silent_auth():
                    return self._get_bytes(url, _retry=False)
            if r.status_code == 403:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except Exception:
                    msg = r.text[:200]
                raise M365PermissionError(url, msg)
            r.raise_for_status()
            # Stream in chunks — avoids loading entire file into memory at once
            # and allows the read timeout to apply per-chunk rather than total
            chunks = []
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    chunks.append(chunk)
            return b"".join(chunks)
        raise _requests.exceptions.RetryError(f"Gave up after {self._MAX_RETRIES} attempts: {url}")

    def _delete(self, path: str, _retry: bool = True) -> bool:
        url = path if path.startswith("http") else GRAPH_BASE + path
        for attempt in range(self._MAX_RETRIES):
            try:
                r = _requests.delete(url, headers=self._headers(),
                                     timeout=self._TIMEOUT_API)
            except self._RETRYABLE_ERRORS:
                if attempt == self._MAX_RETRIES - 1:
                    raise
                self._backoff_sleep(attempt)
                continue

            if r.status_code == 429:
                self._backoff_sleep(attempt, float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code == 503 or r.status_code == 504:
                if attempt < self._MAX_RETRIES - 1:
                    self._backoff_sleep(attempt)
                    continue
            if r.status_code == 401 and _retry:
                self._token = None
                if self.try_silent_auth():
                    return self._delete(path, _retry=False)
            if r.status_code == 403:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except Exception:
                    msg = r.text[:200]
                raise M365PermissionError(path, msg)
            if r.status_code == 404:
                return False  # already deleted
            r.raise_for_status()
            return True  # 204 No Content = success
        raise _requests.exceptions.RetryError(f"Gave up after {self._MAX_RETRIES} attempts: {url}")
        """Move an email to Deleted Items (soft delete)."""
        base = "/me" if (not user_id or user_id == "me") else f"/users/{user_id}"
        try:
            self._post(f"{base}/messages/{message_id}/move", {"destinationId": "deleteditems"})
            return True
        except Exception:
            return self._delete(f"{base}/messages/{message_id}")

    def delete_drive_item(self, drive_id: str, item_id: str) -> bool:
        """Delete a OneDrive/SharePoint/Teams file (moves to recycle bin)."""
        return self._delete(f"/drives/{drive_id}/items/{item_id}")

    def delete_drive_item_for_user(self, user_id: str, item_id: str) -> bool:
        """Delete a drive item via user path as fallback."""
        base = "/me" if (not user_id or user_id == "me") else f"/users/{user_id}"
        return self._delete(f"{base}/drive/items/{item_id}")

    def _paginate(self, path: str, params: dict = None) -> Iterator[dict]:
        """Yield all items across paginated Graph responses."""
        url = path if path.startswith("http") else GRAPH_BASE + path
        while url:
            data = self._get(url, params=params)
            params = None  # only on first request
            yield from data.get("value", [])
            url = data.get("@odata.nextLink")

    def _paginate_delta(self, path: str, params: dict = None,
                        delta_url: str = None) -> tuple[list, str | None]:
        """Exhaust a delta query and return (items, new_delta_link).

        Pass *delta_url* to resume from a previously saved deltaLink token.
        The returned delta_link should be stored by the caller and passed back
        on the next run to receive only changed items.
        """
        url = delta_url or (path if path.startswith("http") else GRAPH_BASE + path)
        items: list = []
        delta_link: str | None = None
        while url:
            data = self._get(url, params=params)
            params = None
            items.extend(data.get("value", []))
            delta_link = data.get("@odata.deltaLink") or delta_link
            url = data.get("@odata.nextLink")
        return items, delta_link

    # ── Delta iterators ───────────────────────────────────────────────────────

    def iter_onedrive_delta_for(self, user_id: str, display_name: str = "",
                                delta_url: str = None) -> tuple[list, str | None]:
        """Return (changed_file_items, new_delta_url) for a user's OneDrive.

        Items with 'deleted' key are removed items — callers should skip them
        for CPR scanning but may use them to prune result sets.
        On first call (delta_url=None) returns ALL files plus a token.
        Subsequent calls with the saved token return only changes.
        """
        label = display_name or user_id
        path  = f"/users/{user_id}/drive/root/delta"
        params = {"$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl,deleted"}
        try:
            raw, new_token = self._paginate_delta(path, params=params, delta_url=delta_url)
        except M365Error as e:
            if "410" in str(e) or "resync" in str(e).lower() or "deltaToken" in str(e):
                # Token expired — caller should clear and retry as full scan
                raise M365DeltaTokenExpired(f"OneDrive delta token expired for {label}")
            raise
        items = []
        for item in raw:
            if item.get("folder"):
                continue  # skip folder entries
            item["_source"]    = f"OneDrive ({label})"
            item["_user_id"]   = user_id
            item["_source_type"] = "onedrive"
            items.append(item)
        return items, new_token

    def iter_onedrive_delta(self, delta_url: str = None) -> tuple[list, str | None]:
        """Delegated-mode OneDrive delta for the signed-in user."""
        path   = "/me/drive/root/delta"
        params = {"$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl,deleted"}
        try:
            raw, new_token = self._paginate_delta(path, params=params, delta_url=delta_url)
        except M365Error as e:
            if "410" in str(e) or "resync" in str(e).lower():
                raise M365DeltaTokenExpired("OneDrive delta token expired for /me")
            raise
        items = []
        for item in raw:
            if item.get("folder"):
                continue
            item["_source"]      = "OneDrive"
            item["_source_type"] = "onedrive"
            items.append(item)
        return items, new_token

    def iter_drive_delta(self, drive_id: str, source_label: str,
                         delta_url: str = None) -> tuple[list, str | None]:
        """Delta query for any drive (SharePoint document library or Teams channel).

        Returns (changed_file_items, new_delta_url).
        """
        path   = f"/drives/{drive_id}/root/delta"
        params = {"$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,webUrl,deleted"}
        try:
            raw, new_token = self._paginate_delta(path, params=params, delta_url=delta_url)
        except M365Error as e:
            if "410" in str(e) or "resync" in str(e).lower():
                raise M365DeltaTokenExpired(f"Drive delta token expired for {drive_id}")
            raise
        items = []
        for item in raw:
            if item.get("folder"):
                continue
            item["_source"]      = source_label
            item["_drive_id"]    = drive_id
            item["_source_type"] = "sharepoint"
            items.append(item)
        return items, new_token

    def iter_messages_delta_for(self, user_id: str, folder_id: str,
                                delta_url: str = None,
                                top: int = 500) -> tuple[list, str | None]:
        """Delta query for a mail folder for a specific user.

        Returns (changed_message_items, new_delta_url).
        """
        path   = f"/users/{user_id}/mailFolders/{folder_id}/messages/delta"
        params = {
            "$top":    str(top),
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,bodyPreview,body,parentFolderId",
        }
        try:
            raw, new_token = self._paginate_delta(path, params=params, delta_url=delta_url)
        except M365Error as e:
            if "410" in str(e) or "resync" in str(e).lower():
                raise M365DeltaTokenExpired(f"Email delta token expired for {user_id}/{folder_id}")
            raise
        return raw, new_token

    def iter_messages_delta(self, folder_id: str,
                            delta_url: str = None,
                            top: int = 500) -> tuple[list, str | None]:
        """Delegated-mode email delta for the signed-in user."""
        path   = f"/me/mailFolders/{folder_id}/messages/delta"
        params = {
            "$top":    str(top),
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,bodyPreview,body,parentFolderId",
        }
        try:
            raw, new_token = self._paginate_delta(path, params=params, delta_url=delta_url)
        except M365Error as e:
            if "410" in str(e) or "resync" in str(e).lower():
                raise M365DeltaTokenExpired(f"Email delta token expired for /me/{folder_id}")
            raise
        return raw, new_token

    # ── Exchange / Outlook ────────────────────────────────────────────────────

    def list_mail_folders(self) -> list:
        folders = list(self._paginate("/me/mailFolders", {"$top": "100"}))
        return folders

    def list_all_mail_folders(self, errors_out: list = None) -> list:
        """Return all mail folders recursively (including subfolders)."""
        def _recurse(folder_id: str, path: str, base: str, depth: int = 0) -> list:
            if depth > 10:
                return []
            result = []
            try:
                children = list(self._paginate(
                    f"{base}/mailFolders/{folder_id}/childFolders",
                    {"$top": "100", "$select": "id,displayName,totalItemCount,childFolderCount"}
                ))
            except Exception as e:
                if errors_out is not None:
                    errors_out.append(f"{path}: {e}")
                return result
            for child in children:
                child["_display_path"] = path + " / " + child.get("displayName", "")
                result.append(child)
                result.extend(_recurse(child["id"], child["_display_path"], base, depth + 1))
            return result

        base = "/me"
        top_folders = list(self._paginate(
            f"{base}/mailFolders",
            {"$top": "100", "$select": "id,displayName,totalItemCount,childFolderCount"}
        ))
        all_folders = []
        for f in top_folders:
            f["_display_path"] = f.get("displayName", "")
            all_folders.append(f)
            all_folders.extend(_recurse(f["id"], f["_display_path"], base))
        return all_folders

    def list_all_mail_folders_for(self, user_id: str, errors_out: list = None) -> list:
        """Return all mail folders recursively for a specific user."""
        def _recurse(folder_id: str, path: str, depth: int = 0) -> list:
            if depth > 10:
                return []
            result = []
            try:
                children = list(self._paginate(
                    f"/users/{user_id}/mailFolders/{folder_id}/childFolders",
                    {"$top": "100", "$select": "id,displayName,totalItemCount,childFolderCount"}
                ))
            except Exception as e:
                if errors_out is not None:
                    errors_out.append(f"{path}: {e}")
                return result
            for child in children:
                child["_display_path"] = path + " / " + child.get("displayName", "")
                result.append(child)
                result.extend(_recurse(child["id"], child["_display_path"], depth + 1))
            return result

        top_folders = list(self._paginate(
            f"/users/{user_id}/mailFolders",
            {"$top": "100", "$select": "id,displayName,totalItemCount,childFolderCount"}
        ))
        all_folders = []
        for f in top_folders:
            f["_display_path"] = f.get("displayName", "")
            all_folders.append(f)
            all_folders.extend(_recurse(f["id"], f["_display_path"]))
        return all_folders

    def count_messages(self, folder_id: str = "inbox") -> int:
        try:
            data = self._get(f"/me/mailFolders/{folder_id}", {"$select": "totalItemCount"})
            return data.get("totalItemCount", 0)
        except Exception:
            return 0

    def iter_messages(self, folder_id: str = "inbox", top: int = 50) -> Iterator[dict]:
        """Yield message metadata dicts."""
        path = f"/me/mailFolders/{folder_id}/messages"
        params = {
            "$top": str(top),
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,bodyPreview,body,parentFolderId",
            "$orderby": "receivedDateTime desc",
        }
        yield from self._paginate(path, params)

    def get_message_body_text(self, msg: dict) -> str:
        """Extract plain text from message body."""
        body = msg.get("body", {})
        content = body.get("content", "")
        if body.get("contentType", "").lower() == "html":
            # Strip HTML tags simply
            import re
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"&nbsp;", " ", content)
            content = re.sub(r"&[a-z]+;", "", content)
        return content

    def iter_message_attachments(self, message_id: str) -> Iterator[dict]:
        """Yield attachment metadata (with contentBytes for small files)."""
        path = f"/me/messages/{message_id}/attachments"
        params = {"$top": "100"}
        try:
            yield from self._paginate(path, params)
        except Exception:
            return

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        data = self._get(f"/me/messages/{message_id}/attachments/{attachment_id}")
        import base64 as _b64
        content = data.get("contentBytes", "")
        return _b64.b64decode(content) if content else b""

    # ── OneDrive ──────────────────────────────────────────────────────────────

    def iter_onedrive_files(self, folder_path: str = "root") -> Iterator[dict]:
        """Recursively yield all files in OneDrive."""
        yield from self._iter_drive_folder("/me/drive/root", "OneDrive")

    def _iter_drive_folder(self, item_path: str, source: str) -> Iterator[dict]:
        path = f"{item_path}/children"
        try:
            items = list(self._paginate(path, {"$top": "200", "$select": "id,name,file,folder,size,webUrl,lastModifiedDateTime,parentReference,shared"}))
        except Exception:
            return
        for item in items:
            if item.get("folder"):
                next_path = f"/me/drive/items/{item['id']}"
                yield from self._iter_drive_folder(next_path, source)
            elif item.get("file"):
                item["_source"] = source
                yield item

    def download_drive_item(self, item_id: str, drive_id: str = None) -> bytes:
        if drive_id:
            url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        else:
            url = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
        return self._get_bytes(url)

    # ── SharePoint ────────────────────────────────────────────────────────────

    def list_sharepoint_sites(self) -> list:
        try:
            data = self._get("/sites", {"search": "*", "$top": "50"})
            return data.get("value", [])
        except Exception:
            return []

    def iter_sharepoint_files(self, site_id: str, site_name: str = "") -> Iterator[dict]:
        """Recursively yield all files in a SharePoint site's default drive."""
        try:
            drives = list(self._paginate(f"/sites/{site_id}/drives", {"$top": "20"}))
        except Exception:
            return
        for drive in drives:
            drive_id = drive["id"]
            yield from self._iter_sharepoint_drive(drive_id, f"/drives/{drive_id}/root", site_name or drive.get("name", "SharePoint"))

    def _iter_sharepoint_drive(self, drive_id: str, item_path: str, source: str) -> Iterator[dict]:
        path = f"{item_path}/children"
        try:
            items = list(self._paginate(path, {"$top": "200", "$select": "id,name,file,folder,size,webUrl,lastModifiedDateTime,parentReference,shared"}))
        except Exception:
            return
        for item in items:
            if item.get("folder"):
                next_path = f"/drives/{drive_id}/items/{item['id']}"
                yield from self._iter_sharepoint_drive(drive_id, next_path, source)
            elif item.get("file"):
                item["_source"] = source
                item["_drive_id"] = drive_id
                yield item

    def download_sharepoint_item(self, drive_id: str, item_id: str) -> bytes:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        return self._get_bytes(url)

    # ── Teams ─────────────────────────────────────────────────────────────────

    def list_all_teams(self) -> list:
        """List all Teams in the tenant using /groups filter (app-only compatible).
        Falls back to /teams if the groups endpoint is unavailable."""
        try:
            return list(self._paginate(
                "/groups",
                {
                    "$filter": "resourceProvisioningOptions/Any(x:x eq 'Team')",
                    "$select": "id,displayName",
                    "$top":    "999",
                }
            ))
        except Exception:
            try:
                return list(self._paginate("/teams", {"$top": "999", "$select": "id,displayName"}))
            except Exception:
                return []

    def list_teams(self) -> list:
        """Delegated-mode: return teams the signed-in user is a member of."""
        try:
            return list(self._paginate("/me/joinedTeams", {"$top": "50"}))
        except Exception:
            return []

    def get_team_members(self, team_id: str) -> list:
        """Return member user IDs for a team (app-only compatible)."""
        try:
            members = list(self._paginate(
                f"/groups/{team_id}/members",
                {"$select": "id", "$top": "999"}
            ))
            return [m["id"] for m in members if m.get("id")]
        except Exception:
            return []

    def iter_teams_files(self, team_id: str, team_name: str = "") -> Iterator[dict]:
        """Yield files from all channels in a Team (backed by SharePoint)."""
        try:
            channels = list(self._paginate(f"/teams/{team_id}/channels", {"$top": "50"}))
        except Exception:
            return
        for ch in channels:
            ch_id   = ch["id"]
            ch_name = ch.get("displayName", ch_id)
            source  = f"Teams / {team_name} / {ch_name}"
            try:
                # Get the SharePoint folder for this channel
                data = self._get(f"/teams/{team_id}/channels/{ch_id}/filesFolder")
                drive_id    = data.get("parentReference", {}).get("driveId")
                item_id     = data.get("id")
                if drive_id and item_id:
                    yield from self._iter_sharepoint_drive(
                        drive_id, f"/drives/{drive_id}/items/{item_id}", source
                    )
            except Exception:
                continue

    # ── Convenience: download any item ───────────────────────────────────────

    def download_item(self, item: dict) -> bytes:
        """Download file bytes for any drive item dict."""
        drive_id = item.get("_drive_id") or item.get("parentReference", {}).get("driveId")
        item_id  = item["id"]
        if drive_id:
            return self.download_sharepoint_item(drive_id, item_id)
        return self.download_drive_item(item_id)

    # ── License / role classification ─────────────────────────────────────────

    # SKU IDs and part-number fragments are loaded from classification/m365_skus.json at
    # startup.  Edit that file to add new SKUs — no code change needed.
    # The two ID sets must remain disjoint (student checked first).

    @classmethod
    def _sku_file_path(cls) -> Path:
        """Resolve classification/m365_skus.json correctly both normally and in a PyInstaller bundle."""
        import sys as _sys
        if getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS"):
            return Path(_sys._MEIPASS) / "classification" / "m365_skus.json"
        return Path(__file__).parent / "classification" / "m365_skus.json"

    @classmethod
    def _load_sku_data(cls) -> None:
        """Load SKU IDs and fragments from classification/m365_skus.json.

        Falls back silently to empty sets if the file is missing or malformed —
        the skuPartNumber fragment fallback in classify_user_role() still works
        when get_subscribed_skus() succeeds, and manual role overrides are always
        available as a last resort.
        """
        try:
            import json as _j
            data = _j.loads(cls._sku_file_path().read_text(encoding="utf-8"))
            cls._STUDENT_SKU_IDS  = set(data.get("student_ids", {}).keys())
            cls._STAFF_SKU_IDS    = set(data.get("staff_ids",   {}).keys())
            cls._STUDENT_SKU_LABELS = dict(data.get("student_ids", {}))
            cls._STAFF_SKU_LABELS   = dict(data.get("staff_ids",   {}))
            cls._STUDENT_SKU_FRAGMENTS = tuple(data.get("student_fragments", []))
            cls._STAFF_SKU_FRAGMENTS   = tuple(data.get("staff_fragments",   []))
            overlap = cls._STUDENT_SKU_IDS & cls._STAFF_SKU_IDS
            if overlap:
                import warnings
                warnings.warn(
                    f"[m365_skus.json] SKU ID collision between student_ids and staff_ids "
                    f"— these will always resolve to 'student': {overlap}",
                    RuntimeWarning, stacklevel=2,
                )
            logger.info("[skus] Loaded %d student + %d staff SKUs from classification/m365_skus.json",
                        len(cls._STUDENT_SKU_IDS), len(cls._STAFF_SKU_IDS))
        except FileNotFoundError:
            logger.warning("[skus] classification/m365_skus.json not found — role classification uses fragment fallback only")
            cls._STUDENT_SKU_IDS = set()
            cls._STAFF_SKU_IDS   = set()
            cls._STUDENT_SKU_LABELS = {}
            cls._STAFF_SKU_LABELS   = {}
            cls._STUDENT_SKU_FRAGMENTS = ("STUDENT",)
            cls._STAFF_SKU_FRAGMENTS   = ("FACULTY", "TEACHER")
        except Exception as e:
            logger.error("[skus] Failed to load classification/m365_skus.json: %s", e)
            cls._STUDENT_SKU_IDS = set()
            cls._STAFF_SKU_IDS   = set()
            cls._STUDENT_SKU_LABELS = {}
            cls._STAFF_SKU_LABELS   = {}
            cls._STUDENT_SKU_FRAGMENTS = ("STUDENT",)
            cls._STAFF_SKU_FRAGMENTS   = ("FACULTY", "TEACHER")

    # Populated by _load_sku_data() below — treated as read-only after that
    _STUDENT_SKU_IDS:       set   = set()
    _STAFF_SKU_IDS:         set   = set()
    _STUDENT_SKU_LABELS:    dict  = {}
    _STAFF_SKU_LABELS:      dict  = {}
    _STUDENT_SKU_FRAGMENTS: tuple = ()
    _STAFF_SKU_FRAGMENTS:   tuple = ()

    def get_subscribed_skus(self) -> dict:
        """Return a mapping of {skuId: skuPartNumber} for the tenant.

        Tries three endpoints in order, using whichever the token permits:

        1. /subscribedSkus          — requires Directory.Read.All (admin)
                                      returns ALL tenant SKUs in one call
        2. /me/licenseDetails       — requires only User.Read (delegated)
                                      returns the signed-in user's SKUs only
        3. /users/{id}/licenseDetails for each user already fetched
                                      requires User.Read.All; covers all users

        Returns {skuId: skuPartNumber}.  An empty dict means no endpoint
        succeeded — role classification will fall back to the hardcoded
        SKU ID sets in m365_skus.json only.
        """
        # Attempt 1: tenant-wide (admin)
        try:
            data = self._get("/subscribedSkus", {"$select": "skuId,skuPartNumber"})
            result = {s["skuId"]: s["skuPartNumber"]
                      for s in data.get("value", []) if s.get("skuId")}
            if result:
                logger.info("[skus] sku_map via /subscribedSkus: %d entries", len(result))
                return result
        except Exception:
            pass

        # Attempt 2: signed-in user's own license details (delegated, User.Read only)
        result = {}
        try:
            data = self._get("/me/licenseDetails", {"$select": "skuId,skuPartNumber"})
            for item in data.get("value", []):
                if item.get("skuId") and item.get("skuPartNumber"):
                    result[item["skuId"]] = item["skuPartNumber"]
        except Exception:
            pass

        if result:
            logger.info("[skus] sku_map via /me/licenseDetails: %d entries (partial — add Directory.Read.All for full coverage)", len(result))
            return result

        logger.warning("[skus] could not fetch skuPartNumber from any endpoint — role classification uses SKU ID matching only")
        return {}

    def build_sku_map_from_users(self, users: list, max_calls: int = 30) -> dict:
        """Build a {skuId: skuPartNumber} map by calling /users/{id}/licenseDetails
        for a spread of users across the full list.  Requires User.Read.All.

        Samples evenly across the entire user list rather than taking the first N,
        so that both student and staff SKUs are discovered even when users are
        sorted alphabetically and staff appear only later in the list.
        """
        if not users:
            return {}
        result = {}
        # Pick indices spread evenly across the full list
        n = len(users)
        step = max(1, n // max_calls)
        indices = list(range(0, n, step))[:max_calls]
        # Always include the last few in case staff sort at end
        for tail_idx in range(max(0, n - 5), n):
            if tail_idx not in indices:
                indices.append(tail_idx)
        for i in indices:
            u = users[i]
            uid = u.get("id", "")
            if not uid:
                continue
            try:
                data = self._get(f"/users/{uid}/licenseDetails",
                                 {"$select": "skuId,skuPartNumber"})
                for item in data.get("value", []):
                    if item.get("skuId") and item.get("skuPartNumber"):
                        result[item["skuId"]] = item["skuPartNumber"]
            except Exception:
                pass
            # Stop early if we've seen both student and staff SKU types
            if result and len(result) >= 4:
                break
        return result

    def classify_user_role(self, assigned_licenses: list,
                           sku_map: dict) -> str:
        """Return 'student', 'staff', or 'other' based on assigned O365 licenses.

        Classification order:
        1. SKU IDs from classification/m365_skus.json (loaded at startup, no extra permissions)
        2. skuPartNumber fragment matching via sku_map (requires subscribedSkus)
        3. Falls back to 'other'

        To add new SKUs: edit classification/m365_skus.json — no code change needed.
        If auto-classification is still wrong for specific users, use the
        manual role override in the UI (role badge on each user row).
        """
        # ── Helper: resolve skuPartNumber for a licence ─────────────────────
        def _sku_name(lic: dict) -> str:
            sid = lic.get("skuId", "").lower()
            return sku_map.get(sid, sku_map.get(lic.get("skuId", ""), "")).upper()

        # ── Pass 1: skuPartNumber fragment match (preferred) ─────────────────
        # Fragment matching is done FIRST when sku_map is available because
        # Microsoft's part-number strings (e.g. STANDARDWOFFPACK_FACULTY) are
        # stable across all SKU ID generations — EA, A1/A3/A5, new commerce,
        # CSP, benefit variants — while UUIDs change with every new SKU issuance.
        # Staff fragments checked across ALL licences before student, so a
        # STUDENT_BENEFIT add-on cannot mask a FACULTY licence.
        if sku_map:
            if any(any(f in _sku_name(lic) for f in self._STAFF_SKU_FRAGMENTS)
                   for lic in assigned_licenses):
                return "staff"
            if any(any(f in _sku_name(lic) for f in self._STUDENT_SKU_FRAGMENTS)
                   for lic in assigned_licenses):
                return "student"

        # ── Pass 2: SKU ID fallback (m365_skus.json) ─────────────────────────
        # Used when sku_map is unavailable or when a licence has no recognisable
        # fragment (e.g. Power Automate Free assigned to faculty accounts).
        # Staff checked before student for the same add-on masking reason above.
        for lic in assigned_licenses:
            if lic.get("skuId", "").lower() in self._STAFF_SKU_IDS:
                return "staff"
        for lic in assigned_licenses:
            if lic.get("skuId", "").lower() in self._STUDENT_SKU_IDS:
                return "student"

        return "other"


# Load SKU classification data from classification/m365_skus.json at import time
M365Connector._load_sku_data()
