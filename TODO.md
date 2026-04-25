# TODO — Pending features and sustainability

Quick overview of what's still to be done.

---

## Recently completed

### Bulk disposition tagging + disposition stats ✅
Select mode (filter bar "Vælg" button) reveals per-card checkboxes. Bulk tag bar appears at bottom of grid when items are selected; a single disposition dropdown + Apply sends `POST /api/db/disposition/bulk`. Stats bar shows total · unreviewed · retain · delete · % reviewed and updates after every save.

---

### Google Drive delta scan ✅
Drive scanning now uses the Google Drive Changes API when `delta` is enabled in scan options. First run records a start page token per user (`gdrive:{email}` in `delta.json`). Subsequent runs fetch only changed/new files. Invalid tokens fall back to a full scan automatically. Token save is load-then-merge to avoid overwriting concurrent M365 delta token writes.

---

### Auto-email after scheduled scan ✅ (already existed)
The scheduler already has an "Email report automatically" checkbox (`auto_email` flag in job config). `_send_email_report()` in `scan_scheduler.py` handles it after each scheduled scan completes — tries Microsoft Graph first, falls back to SMTP. Enable it in the scheduler settings panel.

---

### PDF OCR OOM kills on large documents ✅
`document_scanner` called `convert_from_path()` for the whole PDF before the processing loop, allocating all page images at once. A 50-page A4 at 300 DPI required ~1.3 GB in a single shot — enough to trigger the OS OOM killer.

Fixed in `scan_pdf`, `redact_fitz_pdf`, and `redact_pdf`:
- Replaced bulk pre-render with `convert_from_path(first_page=N, last_page=N)` inside the loop — one page in memory at a time
- Added `_ocr_mem_ok()` guard (checks `psutil.virtual_memory().available >= 500 MB`) before each render; pages that fail the check are skipped and recorded as `"skipped"` in `page_methods` with a printed warning

---

### Memory exhaustion during large M365 scans ✅
Six root causes fixed in `scan_engine.py` and `document_scanner.py`:
- Email body HTML stripped at collection time (`body` key deleted from each message dict before it enters `work_items`; plain text stored as `_precomputed_body` instead)
- `work_items` list converted to a `deque` before processing so each item is released immediately after `popleft()`
- `del content` added in file-processing branch as soon as raw bytes are no longer needed (before NER/PII counting)
- `del body_text` added after email body is fully consumed
- PDF OCR page images (`PIL.Image`) nulled out one by one after OCR instead of holding all pages in RAM
- Memory guard using `psutil` skips file downloads when < 300 MB RAM is available

**Still open:** The collection phase itself is still a "gather all, then process" loop. For very large tenants (>500k emails) the pre-extracted plain text in `work_items` could still be significant. The complete fix is to process each user's emails/files inline as they are fetched (generator/streaming pattern) rather than accumulating them into `work_items` first — estimated 1–2 days of refactor.

---

## Pending

### #15 — Scan profiles ✅
Named, reusable scan configurations. Full spec in SUGGESTIONS.md §15.  
**Size:** Large · **Priority:** High

### #23 — Google Workspace role classification + cross-platform identity mapping ✅
Full spec in SUGGESTIONS.md §23.  
**Size:** Large · **Priority:** Medium

### #27 — Migrate i18n format from `.lang` to JSON ✅
Full spec in SUGGESTIONS.md §27.  
**Size:** Medium · **Priority:** Low

### #29 — Rename `skus/` → `classification/` ✅
Full spec in SUGGESTIONS.md §29.  
**Size:** Small · **Priority:** Low

### #33 — Read-only viewer mode with PIN/token URL ✅
A shareable URL (token-protected) or numeric PIN that gives a DPO, school principal, or compliance coordinator read-only access to the results grid — with disposition tagging but without scan controls, credentials, or delete access. Full spec in SUGGESTIONS.md §33.  
**Size:** Medium · **Priority:** Medium

### OneDrive 404 errors — investigate and handle appropriately ✅
404 on `drive/root/delta` during delta scans was being broadcast as a red `scan_error`. Root cause: `_get()` hit `raise_for_status()` for 404s, which fell through to the generic `except Exception` handler in `_scan_user_onedrive`. The full-scan path silently swallowed the same 404 via `except Exception: return` in `_iter_drive_folder_for`.

Fixed by adding `M365DriveNotFound(M365Error)` exception, raising it from `_get()` on 404, and catching it explicitly in `_scan_user_onedrive` with a lower-severity `scan_phase` broadcast ("OneDrive (user): not provisioned — skipped") instead of a red error card.

---

### #34 — User-scoped viewer tokens ✅
Viewer token scope extended to `{"user": ["m365@…", "gws@…"], "display_name": "Alice Smith"}`, filtering `flagged_items` by `account_id IN (list)`. Lets a single employee see only their own flagged files across both M365 and Google Workspace.

**Implemented:**
1. Scope format — `user` is a list of email strings (one per platform); `display_name` stored for UI display. Legacy single-string format coerced to list automatically.
2. Token creation UI — scope-type selector (`All` / `Role` / `User`) reveals either the role select or a searchable name autocomplete. Autocomplete filters `S._allUsers` by display name or email; rows show name + both emails for dual-platform users. Selected user's full name fills the input; both emails stored in the scope.
3. `GET /api/db/flagged` — filters `WHERE account_id IN (scope.user set)`, covering items from both platforms.
4. Viewer header — `#viewerIdentityBadge` shows `scope.display_name` (full name); `#filterRole` hidden.
5. `POST /api/viewer/tokens` — validates all entries in `scope.user` contain `@`; rejects combined `role`+`user` scope.
6. Token list — shows display name badge; falls back to emails joined with `, `.

**Size:** Small · **Priority:** Medium

---

### Scan history browser ✅
Review results from any past scan session without running a new scan.

**Implemented:**
1. `gdpr_db.py` — `get_sessions(limit=50, window_seconds=300)`: groups `scans` rows into 300 s windows (same logic as `get_session_items`), returns newest-first list with `ref_scan_id` (highest scan_id in group), timestamps, sources set, flagged count, total scanned, and a delta flag.
2. `gdpr_db.py` — `get_session_items(ref_scan_id=N)`: when `ref_scan_id` given, anchors the 300 s window to that scan's `started_at` instead of the latest scan.
3. `GET /api/db/sessions` (new endpoint in `routes/database.py`) — returns the sessions list; viewer-mode sessions share the same `GET /api/db/flagged?ref=N` endpoint with scope enforcement intact.
4. `static/js/history.js` (new module) — `loadHistorySession(refScanId)`, `openHistoryPicker()`, `closeHistoryPicker()`, `exitHistoryMode()`, `invalidateHistoryCache()` all exposed on `window.*`. Session cache (`_sessions`) invalidated by all `*_done` SSE handlers so the picker stays fresh after a new scan.
5. History banner (`#historyBanner`) — shows session date/time, sources, item count; "Sessions" button opens picker dropdown; "Latest scan" button appears only when not already viewing the latest.
6. Auto-load on page load — `results.js` calls `window.loadHistorySession?.(null)` when the SSE watchdog detects `!status.running`; `null` resolves to the latest completed session.
7. Live→history transition: clicking a session in the picker sets `S._historyRefScanId` and shows the banner. History→live transition: `startScan()` calls `window.exitHistoryMode?.()`.

---

### Gmail SMTP error message when App Password already in use ✅
The `535` auth error from Gmail fires for wrong app password, revoked app password, spaces in the 16-char code, and wrong username — all indistinguishable at the SMTP level. The old message unconditionally told users to "create an App Password", which is unhelpful when they already have one. Both the `smtp_test` and `send_report` error handlers now emit a Gmail-specific message that lists the three common causes and links to the App Password page for regeneration.

---

### Interface PIN ✅
Optional session-level authentication gate for the main scanner interface. Set in **Settings → Security → Interface PIN**. When set, any request to the main UI or API redirects to `/login` until the correct PIN is entered. `/view` and all viewer auth routes are exempt. Salted SHA-256 hash stored in `config.json`. Rate-limited: 5 failures per IP per 5 minutes.

---

### SFTP as a 4th file connector 🔄 In progress
Scan SFTP servers (SSH File Transfer Protocol) alongside local, SMB, and cloud sources. A new `SFTPScanner` class in `sftp_connector.py` implements the same `iter_files()` interface as `FileScanner`, so `run_file_scan()` and everything downstream (SSE, DB, export, scheduling) is unchanged. Auth supports password and SSH private key (+ optional passphrase). Key files stored in `~/.gdprscanner/sftp_keys/`. SFTP sources appear in the file sources panel with a 🔒 icon, are profile-aware, and are included in scheduled scans automatically.

**Files changed:** `sftp_connector.py` (new), `scan_engine.py`, `routes/sources.py`, `app_config.py`, `static/js/sources.js`, `templates/index.html`, `lang/en|da|de.json`, `routes/export.py`, `requirements.txt`  
**Size:** Medium · **Priority:** Medium

---

### #32 — Windowed mode for Profiles, Sources, and Settings ✗ Won't do
The workflow is sequential (configure → scan → review), not parallel — there is no realistic scenario where a modal and the results grid need to be open simultaneously. The Sources panel is already visible in the sidebar. Option A (the least-work path) still loads the full 3800-line JS stack twice. Closed.

