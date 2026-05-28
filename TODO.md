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

### OCR language override ✅
Tesseract language pack(s) used for scanned PDFs and images are now configurable per profile. Option `ocr_lang` (default `dan+eng`). Presets: `dan+eng`, `dan`, `eng`, `dan+eng+deu`, `dan+eng+swe`, `dan+eng+fra`. Threaded through `_scan_bytes`/`_scan_bytes_timeout` → `document_scanner.scan_pdf`/`scan_image` and the spawned PDF-OCR subprocess. OCR result cache keys include `lang` so per-language results are cached independently. Sidebar select `#optOcrLang`; profile editor `#peOptOcrLang`.

---

### CPR-only mode ✅
New scan option `cpr_only` (default `false`). When enabled, items whose only hits are email addresses, phone numbers, detected faces, or EXIF/GPS metadata are skipped — only items with at least one qualifying CPR number are flagged. Implemented as a compact short-circuit at each engine's flagging gate. Sidebar toggle `#optCprOnly`; profile editor `#peOptCprOnly`.

Also added `min_cpr_count` (default `1`) — minimum number of **distinct** CPR numbers required before a file is flagged. Files with faces or EXIF PII are still flagged regardless of this threshold.

---

### Skip GPS images ✅
Scan option `skip_gps_images` (default `false`). When enabled, images whose only PII is GPS coordinates are not flagged. GPS data is still stored in the card `exif` field if the item is flagged by another signal. Sidebar toggle `#optSkipGps`; profile editor `#peOptSkipGps`.

---

### CPR cross-referencing (related documents) ✅
The preview panel now shows a "Related documents" section listing other items in the same scan session that share ≥1 CPR number. Clicking any related item opens its preview. Implemented as a query-time self-join on the existing `cpr_index` table — no new data collection needed. `GET /api/db/related/<item_id>?ref=N` returns rows ordered by shared CPR count descending.

---

### Email preview on checkpoint resume ✅
A 500-character plain-text body excerpt (`body_excerpt`) is now stored per flagged email at broadcast time and persisted in the DB. When the preview modal opens for an email item, this excerpt is shown immediately without requiring a live Graph/Gmail connection. Enables email preview to work correctly after a server restart and checkpoint resume.

---

### Built-in file redaction ✅
Local files (`.docx`, `.xlsx`, `.csv`, `.txt`) can be redacted in-place: CPR numbers are replaced by `██████-████` / `█` blocks, the card is removed from the grid, and a `"redacted"` disposition is logged. The ✂ button appears on redactable local file cards (hidden in viewer mode and for resolved items). File is written to a temp path in the same directory before `shutil.move` to avoid cross-device rename failures.

---

### Date-range scoping for viewer tokens ✅
Viewer tokens can now carry `valid_from` and/or `valid_to` fields (YYYY-MM-DD). `GET /api/db/flagged` filters out items whose `modified` date falls outside the range. All three scope dimensions (role, user, date-range) are independent and combinable. The share modal exposes `#shareValidFrom` / `#shareValidTo` date inputs. Token list shows a green date-range badge when a range is present.

---

### Re-scan diff ✅
When viewing a history session, items present in the immediately preceding session but absent from the current one are shown below a `.resolved-divider` separator with a green ✓ Resolved badge (opacity dimmed). These resolved items are grid-only — they are not added to `S.flaggedData` and cannot be bulk-selected or exported. The history banner shows a resolved count when applicable.

---

### Tests for Google Workspace scan engine ✅
19 tests added in `tests/test_google_scan.py` covering: `GET /api/google/scan/users`, `POST /api/google/scan/start`, `POST /api/google/scan/cancel`, and `_run_google_scan` engine internals. Uses synchronous invocation with mocked `broadcast`, `_scan_bytes`, `checkpoint.*`, and `gdpr_db.get_db`. The `clean_google_state` autouse fixture releases `_google_scan_lock` and clears `_google_scan_abort` after each test.

---

### Compliance audit log ✅
Every significant admin action is written to an immutable `audit_log` table in the scanner database. Recorded events: profile save/delete, viewer token create/revoke, viewer/interface/admin PIN set/change/clear, file source add/update/delete, scheduler job save/delete, scan start/stop, SMTP config save, single and bulk disposition changes, item delete, and item redact. Each record stores a Unix timestamp, action key, human-readable detail, and client IP. `GET /api/audit_log` returns newest-first (max 1000; filterable by `?action=`). Visible in Settings → **Audit Log** tab; refreshes when the tab is opened. `log_audit_event()` helper in `gdpr_db.py` silently no-ops if the DB is unavailable.

---

### Scheduled report-only email job ✅
Scheduler jobs can now be configured as "report only" (toggle `#schedReportOnly`). The job skips the scan entirely and emails the latest results already in the database. If the in-memory result list is empty (e.g. after a server restart), results are loaded from DB via `get_session_items()`. M365 auth is not required — email is sent Graph-first if authenticated, SMTP otherwise. Jobs fail with a clear error if no scan results are available. The job list card shows a blue "Report only" badge. Enabling report-only automatically checks "Email report automatically" and dims the Profile field (unused for report-only runs).

---

### SFTP as a 4th file connector ✅
Scan SFTP servers (SSH File Transfer Protocol) alongside local, SMB, and cloud sources. A new `SFTPScanner` class in `sftp_connector.py` implements the same `iter_files()` interface as `FileScanner`, so `run_file_scan()` and everything downstream (SSE, DB, export, scheduling) is unchanged. Auth supports password and SSH private key (+ optional passphrase). Key files stored in `~/.gdprscanner/sftp_keys/`. SFTP sources appear in the file sources panel with a 🔒 icon, are profile-aware, and are included in scheduled scans automatically.

**Files changed:** `sftp_connector.py` (new), `scan_engine.py`, `routes/sources.py`, `app_config.py`, `static/js/sources.js`, `templates/index.html`, `lang/en|da|de.json`, `routes/export.py`, `requirements.txt`

---

### Checkpoint / resume for Google and File scans ✅

Extended the M365 checkpoint/resume mechanism to all three scan engines. Each engine writes its own file (`checkpoint_m365.json`, `checkpoint_google.json`, `checkpoint_file_{source_id}.json`) every 25 items. Previously found cards are re-emitted via SSE on resume so the grid repopulates before new items arrive. The Scan button now checks for a checkpoint before clearing the grid, so the resume banner appears even without a page reload. `POST /api/scan/checkpoint` returns a per-engine breakdown; `POST /api/scan/clear_checkpoint` wipes all `checkpoint_*.json` files. `checkpoint.py` functions gained a `prefix` keyword (default `"m365"`); M365 call sites are unchanged.

---

### Extended document anonymisation (redaction beyond local DOCX/XLSX/CSV/TXT)

Currently the ✂ redact button only works for local files with extensions `.docx`, `.xlsx`, `.csv`, `.txt`. Several valuable cases are not yet covered:

**1. PDF redaction for local files** ✅ — `redact_pdf_secure` (PyMuPDF physical redaction) wired to `_REDACT_EXTS` and the ✂ button. Falls back to reportlab overlay if PyMuPDF is absent.

**2. OneDrive / SharePoint / Teams file redaction** ✅ — `put_drive_item_content()` added to `m365_connector.py`; `redact_item()` in `routes/export.py` extended with a cloud branch: download via Graph, redact to a local temp file, re-upload via PUT. Supports DOCX, XLSX, PDF. ✂ button shown on cloud cards with supported extensions.

**3. Google Drive file redaction** ✅ — `get_drive_file_mime`, `download_drive_file_by_id`, `update_drive_file` added to both `GoogleWorkspaceConnector` and `PersonalGoogleConnector`. `redact_item()` extended with a `gdrive` branch: check MIME type (rejects Google Docs/Sheets), download bytes, redact locally, upload back via `files().update()`. Requires `drive` scope (not `drive.readonly`) on the service-account delegation. ✂ button shown on Drive cards with DOCX/XLSX/PDF extension.

**4. SMB / SFTP file redaction** ✅ — `write_file(remote_path, content)` added to `SFTPScanner`; `write_smb_file(path, content, user, password, domain)` added to `file_scanner.py`. `redact_item()` extended with `sftp` and `smb` branches: download via native protocol, redact locally, write back. Source config matched from `_load_file_sources()`. SFTP requires the item to still be in `state.flagged_items` (in-session only). ✂ button shown on SMB/SFTP cards with DOCX/XLSX/CSV/TXT/PDF extension.

**5. Email body redaction (Exchange / Gmail)** — overwrite the message body via Graph `PATCH /messages/{id}` or Gmail API. High effort and high risk: HTML formatting must be preserved, inline images handled, and a mistake permanently corrupts the email. **Recommendation: skip** — deleting the email is a safer and simpler GDPR response for emails containing CPR numbers.

**Priority order:** PDF (1) first since it reuses existing code. Cloud files (2–4) on demand.  
**Size:** Small (PDF) · Medium (cloud/SMB/SFTP) · **Priority:** Medium

---

### #32 — Windowed mode for Profiles, Sources, and Settings ✗ Won't do
The workflow is sequential (configure → scan → review), not parallel — there is no realistic scenario where a modal and the results grid need to be open simultaneously. The Sources panel is already visible in the sidebar. Option A (the least-work path) still loads the full 3800-line JS stack twice. Closed.

