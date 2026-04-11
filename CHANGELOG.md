# Changelog

All notable changes to GDPR Scanner are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **GitHub Actions CI/CD** — automated build workflow (`.github/workflows/build.yml`) builds Windows `.exe` and Linux binary on every push to `main`. Creates a GitHub Release with artifacts when a `v*` tag is pushed.
- **`EFFORT_ESTIMATE.md`** — build effort estimate document covering component-by-component hour breakdowns and complexity drivers for the project.
- **Settings → Security tab** — new dedicated pane in the Settings modal. Admin PIN and Viewer PIN groups moved here from the General tab, which now contains only Appearance and About. The Share modal's **Configure** button navigates directly to the Security tab.
- **Viewer mode layout** — the sidebar, log panel, and progress bar are now hidden in viewer mode so results fill the full window width. The `🔍 GDPRScanner` brand is shown in the top-left of the topbar (replacing the sidebar header) at the same size and weight as the normal sidebar title.

### Fixed

- **Share modal — Revoke / Copy buttons broken** — `JSON.stringify(token)` produced a double-quoted string that terminated the surrounding `onclick="…"` HTML attribute early, so neither button fired its handler. Both now pass the token as a single-quoted JS string literal, which is safe for the hex token format.
- **Viewer PIN — Clear PIN rejected with "current PIN is incorrect"** — clicking **Clear PIN** without first typing in the Current PIN field sent an empty string to the server, which correctly rejected it. A client-side guard now validates the field is non-empty before sending the request, and focuses the input with an inline error message if it is empty.
- **Share modal — all UI strings now translated** — the Share results modal and Viewer PIN settings group were fully hardcoded in English. All visible strings are now backed by i18n keys (`share_*`, `viewer_pin_*`) in `en.json`, `da.json`, and `de.json`.

---

## [1.6.14] — 2026-04-10

### Added — read-only viewer mode (#33)

A DPO, school principal, or compliance coordinator can now review scan results and tag dispositions without access to scan controls, credentials, or settings.

**Token links**

- New `🔗` **Share** button in the topbar opens a token management modal.
- **Create** generates a 64-char hex token (`secrets.token_hex(32)`) with an optional label and expiry (7 d / 30 d / 90 d / 1 yr / never).
- **Copy** copies the full `http://host:5100/view?token=…` URL to the clipboard.
- **Revoke** deletes the token immediately; any browser using it is locked out on next navigation.
- Tokens are stored in `~/.gdprscanner/viewer_tokens.json` with `created_at`, `expires_at`, and `last_used_at` metadata. Expired tokens are cleaned up on each list fetch.

**PIN alternative**

- A 4–8 digit numeric PIN can be set in **Settings → General → Viewer PIN**.
- Opening `/view` without a token shows a PIN entry form (`templates/viewer_pin.html`).
- Correct PIN sets a Flask session cookie (`session["viewer_ok"]`) valid for the browser session — no token needed after that.
- Brute-force guard: 5 failed attempts per 5 minutes per IP returns 429.
- PIN stored as salted SHA-256 inside `viewer_tokens.json` (no extra dependencies).

**`/view` route**

- Checks `?token=` first (validates + binds session), then existing session cookie, then PIN form (if a PIN is configured), then 403.
- Serves the same `index.html` with `window.VIEWER_MODE = true` injected.
- Invalid/expired tokens show `templates/viewer_denied.html`.

**Viewer mode (JS)**

- `auth.js` — bypasses M365 auth check entirely; adds `viewer-mode` class to `<body>`; shows scanner screen immediately.
- `results.js` — on `DOMContentLoaded` calls `_loadViewerResults()` which fetches `GET /api/db/flagged` (all items from the last completed scan session, joined with dispositions) and renders the grid directly — no SSE required.
- CSS (`body.viewer-mode`) hides: Sources/Options/Accounts sidebar panels; Scan/Stop buttons; profile bar; config-group buttons; resume banner; bulk-delete button; per-card delete button; data-subject delete button; Share button.
- Disposition tagging (select + Save) remains fully functional — `/api/db/disposition` has no auth guard.
- Filter bar, Excel export, Art.30 export, preview panel, and log remain accessible.

**New files:** `routes/viewer.py`, `static/js/viewer.js`, `templates/viewer_pin.html`, `templates/viewer_denied.html`

**Files changed:** `app_config.py`, `gdpr_scanner.py`, `templates/index.html`, `static/style.css`, `static/js/auth.js`, `static/js/results.js`, `static/js/scheduler.js`, `routes/database.py`

---

### Fixed — memory exhaustion during large M365 scans

Addressed root causes of runaway memory growth (reported: up to 90 GB RSS) that could crash the host machine during scans of large Microsoft 365 tenants.

**`scan_engine.py`**

- **Email body HTML stripped at collection time** — Graph API returns the full `body` field (raw HTML, up to ~1 MB per message) for every email fetched. Previously, all message dicts — including the raw HTML — were accumulated in `work_items` before any scanning began. For 1 000 users × 2 000 emails this could mean >100 GB in `work_items` alone. The body is now converted to plain text immediately on collection (`_precomputed_body`), and the raw `body` and `bodyPreview` keys are deleted from the dict before it is queued. The processing loop reads `_precomputed_body` via `pop()` and `del`s it after use.
- **`work_items` converted to `deque` before processing** — items are now released from memory one by one via `popleft()` as they are processed, rather than keeping the entire list alive for the duration of the scan. `gc.collect()` is called immediately after conversion and after each checkpoint save.
- **`content` bytes freed as early as possible in the file processing branch** — raw download bytes are now `del`'d immediately after `content.decode()` (before the expensive NER/PII pass), and also in the no-hits `else` branch where they were previously kept alive until the next loop iteration.
- **`body_text` freed after use in the email branch** — `del body_text` added after `_broadcast_card` so large plain-text bodies do not linger until the next iteration.
- **Memory guard before file downloads** — uses `psutil.virtual_memory().available` to skip a file download and log a warning if fewer than 300 MB of RAM are available, preventing a single large file from pushing an already-pressured machine into OOM.

**`document_scanner.py`**

- **PDF OCR page images freed page by page** — `convert_from_path()` renders all pages at 300 DPI before scanning begins (~26 MB per A4 page; a 100-page PDF ≈ 2.6 GB). Each rendered `PIL.Image` is now nulled out (`images[page_num-1] = None`) immediately after OCR, so only one page image is live at a time instead of the entire document.

### Changed — Sources panel is now resizable and collapsible

The **KILDER** sidebar panel now behaves consistently with the other sidebar sections.

- **Collapsible** — the `▾` / `▸` toggle was already wired up; collapse state is already persisted in `localStorage`. No change needed here.
- **Resizable** — a drag handle (`sources-resize-handle`) added at the bottom of the panel body. Dragging up shrinks the panel (scroll appears); dragging down is capped at the panel's natural content height — you cannot expand it beyond what is needed to show all sources. Height preference persisted in `localStorage` under `gdpr_sources_h`.
- **Auto-fit on render** — `_fitSourcesPanel()` is called at the end of every `renderSourcesPanel()` invocation. On first load and whenever sources are added or removed (e.g. connecting Google), the panel height snaps to exactly fit all visible sources. A previously saved smaller height is honoured only if it is still smaller than the new content height; dragging back to full height clears the saved preference.
- The old `max-height: calc(5 * 26px)` fixed cap is removed.

**Files changed:** `templates/index.html`, `static/style.css`, `static/js/log.js` (`_fitSourcesPanel`, `_initSourcesResize`), `static/js/sources.js`, `static/js/results.js`.

---

## [1.6.13] — 2026-04-10

### Added — developer tooling

- **`run_tests.sh`** — shell script to activate the venv and run the full test suite. Accepts any `pytest` arguments: `./run_tests.sh`, `./run_tests.sh -q`, `./run_tests.sh tests/test_app_config.py`.
- **Directory-scoped `CLAUDE.md` rules** — `routes/CLAUDE.md`, `static/js/CLAUDE.md`, `templates/CLAUDE.md`, `lang/CLAUDE.md` replace the previous single-file context document. Each file is loaded automatically by Claude Code only when working in the relevant directory.

### Fixed — documentation

- **`README.md` project files table** — removed four phantom entries (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `scanner_audit.jsonl`); corrected `static/app.js` description to "archived monolith — no longer loaded"; fixed manual paths (`MANUAL-EN.md` → `docs/manuals/MANUAL-EN.md`); added missing files: `scan_engine.py`, `sse.py`, `checkpoint.py`, `app_config.py`, `cpr_detector.py`, `google_connector.py`, `static/style.css`, `static/js/*.js`, `routes/google_auth.py`, `routes/google_scan.py`, `run_tests.sh`, `docs/setup/` guides.
- **`docs/manuals/MANUAL-EN.md`**, **`docs/manuals/MANUAL-DA.md`** — version header updated from 1.6.11 → 1.6.13; footer updated from v1.6.8 → v1.6.13.

### Changed — blueprint migration batch 3, 4, 5 (auth, database, export — migration complete)

All remaining direct `@app.route` registrations removed from `gdpr_scanner.py`. Flask now routes every API endpoint exclusively through its blueprint. Only `GET /` and `GET /api/scan/stream` (SSE) remain in `gdpr_scanner.py`.

**`routes/auth.py`** — rewritten with direct imports (batch 3, 6 routes):
- `MSAL_OK`, `M365Connector`, `M365Error` imported from `m365_connector`
- `_load_config`, `_save_config` imported from `app_config`
- Dead module-level globals `_pending_flow` and `_auth_poll_result` removed from `gdpr_scanner.py`
- Routes removed: `/api/auth/status`, `/api/auth/start`, `/api/auth/poll`, `/api/auth/userinfo`, `/api/auth/signout`, `/api/auth/config`

**`routes/database.py`** — rewritten with direct imports (batch 4, 15 routes):
- `_get_db`, `DB_OK` from `gdpr_db`; `_set_admin_pin`, `_verify_admin_pin`, `_admin_pin_is_set` from `app_config`; `_clear_checkpoint`, `_DELTA_PATH` from `checkpoint`; `_extract_exif`, `_html_esc`, `_placeholder_svg` from `cpr_detector`
- `SCANNER_OK` determined by local `import document_scanner` try/except
- `db_export` improved: uses `NamedTemporaryFile` instead of `mktemp` (safer for frozen apps)
- Email preview HTML: full CSS ruleset (`*, *::before, *::after`, `img`, `table`, scrollbar) from gdpr_scanner.py version restored
- Routes removed: `/api/db/stats`, `/api/db/trend`, `/api/db/scans`, `/api/db/subject`, `/api/db/overdue`, `/api/db/disposition` (×2), `/api/db/deletion_log`, `/api/db/reset`, `/api/admin/pin` (×2), `/api/db/export`, `/api/db/import`, `/api/preview/<item_id>`, `/api/thumb`

**`routes/export.py`** — rewritten with direct imports (batch 5, 3 routes):
- `_get_db`, `DB_OK` from `gdpr_db`; `_GUID_RE`, `_resolve_display_name` from `app_config`; `M365PermissionError` from `m365_connector`
- `app.logger` replaced with `logging.getLogger(__name__)`
- Dead `delete_item()` helper removed from `gdpr_scanner.py` (was unreachable; blueprint has its own copy)
- Routes removed: `/api/export_excel`, `/api/export_article30`, `/api/delete_bulk`

**`tests/test_routes.py`** — `db_patch` fixture updated: now patches `routes.database._get_db` / `routes.database.DB_OK` and `routes.export._get_db` / `routes.export.DB_OK` (was patching `gdpr_scanner._get_db`/`gdpr_scanner.DB_OK` which no longer have any effect). Two `test_without_db_returns_503` tests updated to monkeypatch `routes.database.DB_OK` instead of `gdpr_scanner.DB_OK`.

---

## [1.6.12] — 2026-04-10

### Fixed — profile editor save drops users from non-active role groups

In `_pmgmtSaveFullEdit` (profile management editor), the save function applied the active role filter (`_pmgmtRoleActive`) to the list of checked checkboxes before saving. Since `_pmgmtFilterAccounts` hides rows via `display:none` but does not uncheck them, users from other role groups that remained checked (but hidden) were silently discarded on save. The role filter at save time is removed — all checked checkboxes are now captured regardless of which role tab is visible.

---

## [1.6.11] — 2026-04-10

### Changed — blueprint migration batch 1 (scan + app_routes)

15 direct `@app.route` registrations removed from `gdpr_scanner.py`. Flask now routes all of these exclusively through their blueprint counterparts, which previously existed as dead code shadowed by the direct routes.

**`routes/scan.py`** — rewritten with direct imports (was entirely non-functional as dead code due to bare-name `NameError`s behind the shadow):
- Added `GET /api/scan/status` (new — was only in gdpr_scanner.py)
- Added `GET /api/src_toggles`, `POST /api/src_toggles` (new — was only in gdpr_scanner.py)
- `scan_checkpoint_info` — added missing `check_only` handling present in the gdpr_scanner.py version
- All state references converted from bare names to `state._scan_lock` / `state._scan_abort`; `run_scan` imported lazily from `scan_engine` inside `_run` to avoid circular imports
- `_save_settings`, `_load_settings`, `_load_src_toggles`, `_save_src_toggles` imported from `app_config`
- `_checkpoint_key`, `_load_checkpoint`, `_clear_checkpoint`, `_load_delta_tokens`, `_DELTA_PATH` imported from `checkpoint`

**`routes/app_routes.py`** — cleaned up:
- `APP_VERSION` now computed locally from `VERSION` file (was a bare-name reference to gdpr_scanner.py global)
- `_LANG_DIR` computed at module level; fixed `sys` / `_sys` alias mismatch in `get_langs` (bug in blueprint that never manifested while shadowed)
- `_set_lang_override`, `_load_lang_forced` imported directly from `app_config`
- `get_langs` — added missing `langs.sort()` present in the gdpr_scanner.py version

**`tests/test_routes.py`** — `mock_connector` fixture simplified: no longer needs to patch `gdpr_scanner._connector` since the direct `scan/start` route is gone; `state.connector` alone is sufficient. `run_scan` stub in `test_authenticated_returns_started` updated to target `scan_engine` directly.

**Routes removed from `gdpr_scanner.py`:** `/api/about`, `/api/langs`, `/api/set_lang`, `/api/lang`, `/api/scan/status`, `/api/scan/start`, `/api/scan/stop`, `/api/scan/checkpoint`, `/api/scan/clear_checkpoint`, `/api/settings/save`, `/api/settings/load`, `/api/src_toggles`, `/api/delta/status`, `/api/delta/clear`

**Still in `gdpr_scanner.py`:** `GET /` (root), `GET /api/scan/stream` (SSE — cannot be in a blueprint), and the `auth`, `users`, `sources`, `database`, `export` route groups (31 routes — next batches).

---

## [1.6.10] — 2026-04-10

### Fixed — Google Drive `exportSizeLimitExceeded` warning

Native Google Workspace files too large for Drive's export API (Google's server-side limit, distinct from the 20 MB local cap) now produce a clean skip message instead of a stray `WARNING googleapiclient.http — Encountered 403 Forbidden with reason "exportSizeLimitExceeded"` in the log. A `logging.Filter` subclass is installed on the `googleapiclient.http` logger at import time to suppress the duplicate external warning; the `except HttpError` block in `_drive_iter` detects the reason and logs `[gdrive] skip '<name>' — file too large for Google export API (exportSizeLimitExceeded)` with the file ID.

### Fixed — peak memory during large file/SMB scans (OOM risk reduction)

Three targeted buffer-lifetime fixes reduce peak RSS during large scans:

- **`cpr_detector.py`** — `del content` after writing the PDF bytes to a temp file in `_scan_bytes_timeout`. The 20 MB buffer was previously held in the main process for the entire duration of `p.join(timeout)` (up to 60 s), overlapping with the spawned subprocess's ~150–300 MB heap. It is now freed before the subprocess starts.
- **`scan_engine.py`** — `del content` after the thumbnail block in `run_file_scan`. The raw file buffer was kept alive through card dict construction and the start of the next loop iteration; it is now freed as soon as the thumbnail (or placeholder SVG) has been generated.
- **`file_scanner.py`** — `PREFETCH_WINDOW` reduced from 2 to 1. Halves the maximum number of concurrently-held SMB read buffers (from 2 × 20 MB to 1 × 20 MB).

---

## [1.6.9] — 2026-04-10

### Changed — frontend migrated to ES modules

**Phase 2 complete:** All 10 split JS files converted from `<script defer>` to `<script type="module">`.

- `static/js/state.js` introduced as the shared state module — exports a single `S` object holding all previously-global mutable state (`flaggedData`, `_allUsers`, `_profiles`, `_fileSources`, `_srcPct`, scan-running flags, etc.). All 10 modules import `{ S }` from `state.js` and mutate its properties in place.
- Every function called from an inline HTML `onclick=` handler is explicitly exported via `window.fnName = fnName` at the bottom of each module (~80 exports across 10 files).
- `var LANG` retained in the inline `<script>` block (not a module) so it remains a true global accessible from all modules as a bare name.
- `app.js` retained as archive; no longer loaded by `index.html`.

### Fixed — connector.js SyntaxError caused by duplicate function declarations

`openFileSourcesModal` and `closeFileSourcesModal` were declared **twice** at module top level in `connector.js` — once as redirect stubs pointing to the new unified Sources modal, and once as the old `#fsrcBackdrop` implementations left over from the pre-unification code. In ES module strict mode, duplicate `function` declarations in the same scope are a **SyntaxError**. The engine rejected the entire module at parse time, meaning none of its ~35 `window.*` exports were ever set. Symptoms:

- **"Kilder" (Sources) button did nothing** — `window.openSourcesMgmt` was never set
- Google status dot, file source loading, and sources panel re-render all silently failed — `window.smGoogleRefreshStatus`, `window._loadFileSources` etc. were undefined
- Sources panel showed only M365 sources even when Google Workspace was configured

**Fix:** removed the stale `async function openFileSourcesModal` / `function closeFileSourcesModal` bodies (lines 511–518). The redirect stubs at lines 505–506 (`openSourcesMgmt('files')`) are the correct new behaviour. Also removed the duplicate `window.openFileSourcesModal` and `window.closeFileSourcesModal` assignments that appeared twice in the exports block.

### Fixed — Profiler modal did not open when `_renderProfileMgmt` threw

If `_renderProfileMgmt()` threw a runtime error (e.g. due to downstream failures from the connector.js parse error), `openProfileMgmtModal` would abort before reaching `classList.add('open')`, leaving the modal invisibly closed. The function now wraps both `_renderProfileMgmt()` and `_pmgmtOpenEditor()` in individual try-catch blocks. Any error is logged to the console; the modal opens regardless.

### Fixed — blocking alert on every unhandled async error

`ui.js` contained a duplicate `unhandledrejection` listener that called `alert()` for every unhandled Promise rejection. Background API calls (Google status, file sources, src_toggles) could fire these alerts at page load, and browsers that had already suppressed one alert silently blocked all subsequent ones. Removed the `alert()` handler; the `console.error` handler is retained.

---

## [1.6.8] — 2026-04-09

### Fixed — memory pressure during large scans

**SMB prefetch window reduced**
- `PREFETCH_WINDOW` reduced from 5 to 2 in `file_scanner.py`. Peak in-flight SMB memory drops from ~250 MB to ~40 MB during large network share scans.
- `MAX_FILE_BYTES` reduced from 50 MB to 20 MB — files larger than 20 MB are skipped rather than buffered in full.

**PDF subprocess concurrency limited**
- A module-level `threading.Semaphore(1)` in `cpr_detector.py` ensures at most one PDF OCR subprocess runs at a time. Previously, multiple threads could each spawn a ~200 MB subprocess simultaneously, causing OOM under load.

**Google Workspace export buffer reduced**
- `_MAX_EXPORT_BYTES` in `google_connector.py` reduced from 50 MB to 20 MB.
- `_drive_iter` now explicitly deletes the `BytesIO` buffer (`del buf`) before yielding each file's bytes, releasing the double-buffer peak immediately rather than waiting for GC.

### Fixed — Excel and Article 30 exports missing sources

**Gmail and Google Drive tabs added to Excel export**
- `SOURCE_MAP` in `routes/export.py` was missing `gmail`, `gdrive`, `local`, and `smb` entries. Items from these sources were silently dropped — they were grouped internally but never written to a sheet.
- All eight source types now have dedicated tabs: Outlook, OneDrive, SharePoint, Teams, Gmail, Google Drive, Local, Network.
- The same fix applies to the inline Excel builder in `gdpr_scanner.py`.

**Concurrent scan results captured in exports**
- M365, Google Workspace, and file scans each create their own `scan_id`. The previous DB fallback used `get_flagged_items()`, which only returned results for the single most-recently-completed scan — silently dropping the other sources after page reload.
- New `get_session_items(window_seconds=300)` in `gdpr_db.py` returns items from all scans whose `started_at` falls within a 5-minute session window of the latest completed scan.
- Both `export_excel()` and `export_article30()` now use `get_session_items()` as their DB fallback. `_build_article30_docx()` also uses it directly.

### Changed — "Email" source renamed to "Outlook"

The `email` source type (Microsoft Exchange mailboxes) is now consistently labelled **Outlook** everywhere:
- Source badges on result cards (`SOURCE_BADGES.email`)
- Filter bar dropdown
- `_sourceLabel()` in JS
- Excel tab label
- `m365_src_email`, `m365_filter_email`, `m365_phase_emails` in all three lang files (`en.json`, `da.json`, `de.json`)
- Article 30 report uses **Exchange (Outlook)** for the formal legal context

Rationale: with Gmail also present, "Email" was ambiguous. "Outlook" ties the source unambiguously to Microsoft 365.

### Changed — progress bar moved above log panel

- `#progressBar` moved from below the topbar to just above `#logWrap` (above the activity log).
- The bar is now a permanent placeholder — always visible, never hidden. `display: flex` is the permanent state; `display: none` is no longer used.
- Background changed from `var(--surface)` to `var(--bg)` to match the log area. Border changed from `border-bottom` to `border-top`.
- New `_clearProgressBar()` helper resets phase, stats, ETA, and file fields on scan end, leaving the bar visually empty at idle. All previous `style.display` assignments removed.

### Fixed — profile manager Cancel closes entire modal

- Clicking **Cancel** in the profile editor previously closed the editor panel but left the profile list modal open behind it. `_pmgmtCloseEditor()` now calls `closeProfileMgmt()` to dismiss the full modal.
- Dead stub `function _pmgmtCancelEdit(id) {}` removed.

### Changed — exports available without running a new scan

- The filter bar (including Excel and Art.30 export buttons) is always visible on page load.
- Exports now use `get_session_items()` as the DB fallback, so the buttons produce a complete report from the previous session immediately after page reload — no new scan required.

### Fixed — profile loading clobbered by scan start

- `_save_settings()` is called on every M365 scan start with a payload containing only M365 `sources`, `user_ids`, and `options`. It was writing this back via `_profile_from_settings()`, which has no `google_sources` field — permanently stripping Google and file source selections from the active profile after each scan.
- `_save_settings()` now preserves `google_sources` and `file_sources` from the existing profile when the payload does not include them, and rebuilds the combined `sources` array as M365 + google + file.
- `_profile_from_settings()` updated to pass through `google_sources` when present in the payload.

### Fixed — "no results" shown during live scan after hard refresh

- Hard-refreshing the browser mid-scan caused the "Ingen CPR-numre fundet" card to appear immediately, before the SSE watchdog had detected the running scan.
- `loadLastScanSummary()` is no longer called directly on `DOMContentLoaded`. It is now called inside `_sseWatchdog` on the first status poll, only if no scan is currently running (`_initialStatusChecked` flag).

### Fixed — progress bar source pill showing "Email" instead of "Outlook"

- `_PHASE_SOURCE_MAP` entry for Exchange mail phases still had `label: 'Email'`. Updated to `'Outlook'` to match the rename applied elsewhere.

### Changed — profile manager UI simplified

- Removed the redundant **×** close button from the list panel header — the editor panel's **×** already closes the entire modal.
- Removed the **Luk** (Close) button from the list panel footer — the footer now contains only **+ Ny profil**.
- The editor footer **Cancel/Annuller** button replaced with a single **Luk** button that closes the entire modal (consistent with `_pmgmtCloseEditor()` behaviour).

### Changed — log panel collapsible

- A **▾/▸** toggle button added to the left of the log header. Clicking it collapses or expands the log panel (resize handle + log body together, wrapped in `#logSectionBody`).
- State persists in `localStorage` via the existing `toggleSection` / `restoreSectionStates` mechanism (`sc_logSection` key).

### Changed — log header buttons translated

- **All**, **Errors**, and **Copy** buttons in the log header now use `data-i18n` attributes and are fully translated in all three lang files.
- Translation keys added: `btn_errors` (da: Fejl, de: Fehler), `log_copy` (da: Kopier, de: Kopieren).
- Symbol prefix `⎘` removed from the Copy button label.

### Changed — project documentation structure

- User manuals moved from project root to `docs/manuals/` (`MANUAL-DA.md`, `MANUAL-EN.md`).
- Setup guides moved from project root to `docs/setup/` (`M365_SETUP.md`, `GOOGLE_SETUP.md`).
- `routes/app_routes.py` and `build_gdpr.py` updated to reference the new manual paths.
- `README.md` links updated accordingly.

### Fixed — disposition carry-forward across scans

When a previously reviewed file reappears in a new scan it now shows its prior disposition immediately on the result card — no need to open the preview panel first.

- `get_prior_disposition(item_id)` added to `ScanDB` in `gdpr_db.py`. Returns the stored disposition status if it differs from `'unreviewed'`, otherwise `None`.
- `get_flagged_items()` and `get_session_items()` in `gdpr_db.py` now `LEFT JOIN dispositions` and return `COALESCE(d.status, 'unreviewed')` as `disposition` on every row. Exports and the results grid therefore reflect the latest review decision without an extra round-trip.
- `_with_disposition(card, db)` helper added to `scan_engine.py`. Injects the prior disposition into a card dict before it is broadcast as `scan_file_flagged`. Used at all four broadcast points:
  - `scan_engine.py` — file scan (line ~297)
  - `scan_engine.py` — checkpoint resume re-emit loop (line ~357)
  - `scan_engine.py` — M365 scan (line ~456)
  - `routes/google_scan.py` — Google Workspace scan (line ~225)
- The frontend already reads `f.disposition || 'unreviewed'` for filter matching — no JS changes required.

---

## [1.6.7] — 2026-04-06

### Fixed — emoji/symbol removal from all buttons and indicators

**All UI buttons stripped of emoji and symbol prefixes**
- Every interactive element in the topbar, filter bar, modals, and settings panels now uses plain text only. Removed: `▶`, `■`, `💾`, `✕`, `⚙`, `🕐`, `⬇`, `⬆`, `🗑`, `📋`, `☰`, `⊞`.
- Affected buttons: Scan, Stop, Save (profile), Clear (profile), Profiler/Profiles, Kilder/Sources, Indstillinger/Settings, Excel, Art.30, Slet/Delete (bulk), Liste/List, Gitter/Grid, Export (DB), Import (DB), Reset DB, scheduled scan title.
- Labels updated in `templates/index.html` and all three lang files (`da.json`, `en.json`, `de.json`).

**Filter bar — Clear button standardised**
- The `×` clear-filter button was an oversized bare symbol (`font-size: 16px`, no border). Replaced with a proper text button (`Ryd`/`Clear`/`Löschen`) matching the 26 px filter bar standard: bordered, `border-radius: 5px`, turns red on hover.
- Translation key `m365_filter_clear` added to all three lang files.

**Scheduler indicator — "Next:" label translated**
- The hardcoded `'Next: '` prefix in `schedUpdateSidebarIndicator()` is now `t('m365_sched_next', 'Next')`. Key added to all three lang files (da: `Næste`, de: `Nächste`).
- Clock emoji `🕐` removed from the indicator and from `m365_sched_title` in all lang files.

### Fixed — result card badges, progress bar on browser refresh

**Result card badges — standardised to 9 px pill style**
- All result card badges now follow the app-wide badge standard: `font-size: 9px; padding: 1px 5px; border-radius: 10px`.
- `.source-badge` (OneDrive, Exchange, Gmail, etc.) had no CSS definition at all — it now has the correct size, padding, and border-radius.
- `.cpr-badge` reduced from `10px / 2px 6px` to `9px / 1px 5px`.
- `.photo-face-badge`, `.special-cat-badge`, `.overdue-badge`, `.role-pill` reduced from `10px` / `border-radius: 4px` to `9px / 1px 5px / border-radius: 10px`.
- Removed camera emoji (📷) from the Faces badge.
- `.card-source` gains `flex-wrap: wrap` so badges wrap on narrow cards instead of overflowing.

**Progress bar — survives browser refresh**
- Refreshing the browser mid-scan no longer causes the progress bar to appear without coloured segment pills.
- Three code paths now defensively set the correct running flag and call `_renderProgressSegments()` before the track is needed:
  - `scan_start` SSE handler (sets `_m365ScanRunning`).
  - `scan_progress` SSE handler (sets the flag matching the event's `source` field — covers mid-scan reconnects where `scan_start` has scrolled out of the 500-event replay buffer).
  - `scan_phase` SSE handler (infers source from phase text; fires before `scan_progress` in the replay sequence).
  - `_sseWatchdog` (sets `_m365ScanRunning` immediately on detecting a running scan via `/api/scan/status`, which checks the M365 lock).

### Improved — scan responsiveness, UI layout, preview panel

**Scan abort responsiveness**
- Stop now takes effect within one Graph API round-trip across all collection phases. Previously, pressing Stop only checked the abort flag in the *processing* loop — the entire collection phase (email folder enumeration, OneDrive file listing, Teams channel fetching, SharePoint site iteration) ran to completion first, which could take 10+ minutes on large tenants.
- Abort checks added to: email folder loop (inside `_scan_user_email`), OneDrive items loop (delta and full modes in `_scan_user_onedrive`), Teams team loop and channel loop (inside `_scan_user_teams`), SharePoint site loop, and all outer per-user loops.
- Side effect: the scheduler no longer fails with "Manual scan already running" when a job fires shortly after the user pressed Stop — the lock is now released promptly.

**Scheduler — graceful skip on lock contention**
- When a scheduled job fires while a manual (or other scheduled) scan holds the lock, the job now logs `Skipped — a scan is already running` and returns cleanly. Previously it raised `RuntimeError("Manual scan already running")`, which was logged as a hard failure with a full traceback in the UI.

**Filter bar — always visible, full-width, 26 px**
- Filter bar was hidden until the first result arrived. It is now always visible.
- Moved from inside the left column to a direct child of `.main`, above `.content-area`. The preview panel's top edge now aligns with the grid's top edge rather than overlapping the filter bar.
- All filter bar controls standardised to `height: 26 px` (`input`, `select`, `button`) to match the topbar control standard. Redundant inline `padding`/`font-size`/`border-radius` stripped from button inline styles.

**Preview panel**
- Resizable: a 5 px drag handle on the left edge lets the user adjust the panel width. Handle uses pointer capture (`setPointerCapture`) so dragging over the iframe or releasing outside the browser window always terminates the drag cleanly. Width is persisted in `sessionStorage` and restored when the panel is next opened.
- Min width: 280 px; max width: 70% of window width.
- Fixed: clicking the close (×) button had no effect. Root cause: `panel.style.width` set by the resize logic is an inline style and overrides the CSS class `.hidden { width: 0 }`. Fix: `closePreview()` now clears `panel.style.width = ''` before adding `.hidden`; `openPreview()` restores the saved width when showing the panel.
- Email preview iframe: added `* { max-width: 100% }`, `overflow-x: hidden`, `table { table-layout: fixed }`, and `img { height: auto }` to prevent wide HTML emails from creating a horizontal scrollbar inside the 420 px panel.
- Email preview iframe scrollbar: matches the app's 4 px thin scrollbar style.

**Thin scrollbars everywhere**
- `.grid-area` (results grid) and `.log-panel` now use the same 4 px thin scrollbar style (`scrollbar-width: thin; width: 4px`) as `#accountsList` and `#sourcesPanel`. Previously they used the system-default wide scrollbar.

**Scheduler next scan indicator**
- `#schedNextIndicator` was a plain `display: block` div with no height constraint, causing it to sit taller than adjacent topbar controls. Fixed to `height: 26 px; display: inline-flex; align-items: center` with a border and border-radius matching the surrounding pill buttons.

**Log and preview resize — pointer capture fix**
- Both resize handles (`logResizeHandle`, `previewResizeHandle`) switched from `mousedown` + `document.addEventListener('mousemove'/'mouseup')` to `pointerdown` + `setPointerCapture`. The old approach lost the drag when the cursor moved over the iframe (which has its own input context) or left the browser window. Pointer capture routes all pointer events to the handle until `pointerup`/`pointercancel` regardless of cursor position.

**Manuals updated (MANUAL-DA.md, MANUAL-EN.md)**
- Version 1.6.4 → 1.6.6.
- Section 2: activity log description now mentions copy button, error filter, and resize handle.
- Section 4.4: progress bar description updated — source pill labels listed, old "current phase" wording removed.
- Section 8: profiles section updated for loader model, ✕ clear button, and explicit mention that Google/file sources are saved.

---

## [1.6.6] — 2026-04-06

### Improved — UX polish II (clusters, badges, log panel, progress bar)

**Pill clusters**
- KONTI section header: Alle / Ingen / ↻ converted from bare text links to a pill cluster (`height: 22px`), matching the pattern used in the Profile editor.
- Profile list rows (Profiler modal): Brug + Kopier grouped into a pill cluster; Slet kept as a separate standalone danger button.

**Badge sizing**
- Platform badges (M365, GWS, M365+GWS) and role badges (Ansat, Elev, Anden) standardised to `font-size: 9px; padding: 1px 5px; border-radius: 10px` across the main sidebar account list and the profile modal. Previously the sidebar used larger inline styles (`font-size: 10px; padding: 2px 7px`) that made badges visually heavier than in the modal.

**Account rows**
- Main sidebar account row padding reduced from `4px 0` to `2px 0`, matching the compact density of the profile modal account list.
- SKU debug search icon button standardised to `height: 26px` to match the adjacent role filter cluster.

**Log panel — full rebuild**
- Color-coded log levels: `.log-err` (red `var(--danger)`), `.log-ok` (green `var(--success)`), `.log-warn` (orange `#e0922a)`). Level classes were already passed to `log()` but had no CSS — all entries appeared in the same muted colour.
- Live scanning indicator: a single italic `▶ filename` line at the bottom of the log updates in place via `scan_file` SSE events. Never scrolls; clears automatically when the scan finishes. Avoids flooding the log with per-file entries.
- Copy button (`⎘ Copy`) in the log header copies all log text to clipboard; flashes `✓ Copied` for 1.5 s.
- Log level filter (`All` / `Errors`) in log header — hides info lines when Errors mode is active.
- Resizable: drag handle at the top edge of the panel resizes vertically and **snaps to the nearest full line** (row = 18 px: 16 px line-height + 2 px margin; 2–30 lines range).
- Default height set to **8 lines exactly** (`height: 154px` = 8 × 18 + 10 px padding).
- Persistent across page refresh: up to 300 lines saved to `sessionStorage`; restored on `DOMContentLoaded`; cleared on new scan start.
- Smart scroll: auto-scroll only triggers when already within 24 px of the bottom — scrolling up to read earlier entries stops the follow behaviour.

**Progress bar — segmented multi-source**
- Replaced the single `progressFill` bar with a dynamically segmented track (`#progressTrack`). One segment per active scan type (M365 / Google / Files), equal width, separated by a 1 px gap. Segments are added at scan start and removed as each source finishes.
- Color-coded: M365 = blue (`var(--accent)`), Google = dark green (`#3a7d44`), Files = purple-gray (`#7a6a9e`).
- Each segment fills independently — M365 at 80% and Google at 20% are shown simultaneously with no interference. Eliminates the `_maxPct` hack (bar stuck at 100% after first source finishes).
- Backend (`scan_engine.py`, `routes/google_scan.py`): all `scan_progress` SSE events now include `"source": "m365"` / `"google"` / `"file"`. Frontend routes each event to the correct segment by `d.source`.
- Stats (`X / Y`) and ETA only update from M365 events — the only source with meaningful totals and time estimates.

**Progress bar — phase display**
- `#progressWho` replaces the plain-text phase span. Renders a colour-coded source pill (`[Email]`, `[OneDrive]`, `[Gmail]`, `[GDrive]`, `[Local]`, etc.) followed by the user's full display name.
- Source pill uses the universal badge standard: `font-size: 9px; padding: 1px 5px; border-radius: 10px; font-weight: 500`.
- `_setProgressPhase()` identifies the source from the full phase string via `_PHASE_SOURCE_MAP`, then splits on ` — ` to extract the username. Phases without a dash (e.g. `📂 folder: 3 msg(s)`) fall back to the last known user (`_progressCurrentUser`).
- `_resolveDisplayName()` resolves email addresses in Google phase strings to the user's display name via `_allUsers`. Also strips trailing count suffixes (`: 3 file(s)`).
- Pill labels standardised: `Email`, `OneDrive`, `SharePoint`, `Teams`, `Gmail`, `GDrive`, `Local` — matching the source names used elsewhere in the UI.
- All 25 `scan_phase` strings now produce a pill: `📂` emoji maps to `Email`; `Google Workspace — email` phases resolve to display name; file scan startup uses `Files — {label}`; Google per-user phase uses `Google Workspace — {email}`.
- Source map ordering: `Google Workspace` matched before `Gmail` so the GWS startup phase shows `[Gmail]` only when no broader match applies.
- Fixed: email regex was missing the `i` flag (`/E-?mail.../u` → `/E-?mail.../iu`), causing Danish `"Indsamler e-mails"` to fall through to plain text.

**Scheduler — Google and file sources**
- Scheduled scans now run Google Workspace sources. `_build_options` extracts `google_sources` from the profile (with legacy fallback for profiles that stored gmail/gdrive inside `sources`). A separate Google scan block runs after the file scan loop using `_google_scan_lock`.

**Profile dropdown — loader model**
- Removed the selectable "Standard (sidebar)" / "Default (sidebar)" empty option. Profiles are now **loaders**, not persistent modes — selecting one pushes its settings into the sidebar; the sidebar is always the live state.
- Replaced with a `disabled` placeholder `"— Vælg profil —"` shown when no profile has been loaded.
- Added a `✕` clear button (`#profileClearBtn`) that appears next to the dropdown when a profile is active. Clicking it clears `_activeProfileId` and resets the dropdown to the placeholder **without touching the sidebar** — the loaded settings remain.
- `clearActiveProfile()` function added.
- Lang keys: `m365_profile_default` removed, `m365_profile_placeholder` added (da/en/de).

**Bug fixes**
- Profile role filter respected at scan time: `getSelectedUsers()` now filters the returned list by `_activeRoleFilter`, preventing hidden-role users from being silently included in M365 scans and profile saves via the topbar quick-save.
- Profile editor role filter respected at save time: `_pmgmtSaveFullEdit` now excludes IDs whose role doesn't match `_pmgmtRoleActive`. Prevents "select all → filter by staff → save" from silently saving student accounts that were checked but hidden.
- Profile editor role filter state reset on open: `_openEditorForProfile` resets `_pmgmtRoleActive = ''` so a stale filter from a previous session doesn't silently hide accounts when the editor is reopened.
- Google and file sources not saved in profiles: `_pmgmtSaveFullEdit` now checks whether the checkboxes are actually present in `#peSourcesPanel` (DOM query) rather than using `!!window._googleConnected` and `_fileSources.length > 0` as proxies. The async status fetches could complete after the editor opened, leaving the panel without checkboxes while the proxy read `true`, silently discarding the user's selection.
- Profile editor now re-renders `#peSourcesPanel` when `smGoogleRefreshStatus()` resolves or `_loadFileSources()` completes if the editor is open and the panel has no Google/file checkboxes yet.

---

## [1.6.5] — 2026-04-04

### Improved — UX polish pass (topbar, sidebar, clusters)

**Topbar**
- All topbar elements normalised to `height: 26px`: Scan/Stop buttons, profile dropdown, save button, config cluster, stats pill, icon buttons (🔍, ?, 🌙). Previously each had independent padding, making the topbar uneven.
- Config buttons (Profiler, Kilder, Indstillinger) extracted from `#profileBar` into a dedicated `.config-group` pill cluster separated by a `.topbar-sep` divider — visually distinct from the profile selector group.
- Data subject lookup moved from the sidebar footer into the topbar as a 🔍 icon button (left of `?`). Sidebar strip removed.

**Sidebar**
- KILDER, INDSTILLINGER, and KONTI sections are now collapsible. Each header gets a `▾`/`▸` chevron (`section-collapse-btn`). Collapse state persists in `localStorage` per section. KONTI releases its `flex:1` when collapsed.
- Role filter buttons (Alle / Ansat / Elev) converted to a pill cluster (`.role-filter-btn`) matching the topbar cluster pattern. SKU debug button stays separate.
- Date preset buttons (1 år / 2 år / 5 år / 10 år / Alle) converted to a pill cluster.
- All pill cluster buttons, input fields, and date picker set to `height: 26px` — the universal control height across the UI.
- Toggle size reduced from `36×20px` to `32×18px` with knob gap tightened from 3px to 2px. Knob-to-track ratio improved for a sleeker look.
- Role filter buttons display live counts: "Alle (277)", "Ansat (62)", "Elev (254)". Updated by `updateRoleFilterCounts()`, called from `renderAccountList()`.

**Empty state**
- On load, fetches `/api/db/stats`. If a previous scan exists, shows a summary card (hits, unique CPR subjects, items scanned, date, sources) instead of the bare placeholder. The placeholder is shown below as a "start new scan" prompt. Summary hidden when a scan starts.

### Added — Single-instance lock

- **`~/.gdprscanner/app.lock`** — an exclusive process lock is acquired at startup to prevent two instances from running simultaneously against the same database and settings files.
- **Desktop (`build_gdpr.py` launcher)**: lock is checked before Flask starts. If another instance holds the lock the app prints `"GDPRScanner is already running."` to stderr and exits immediately.
- **Server (`gdpr_scanner.py`)**: same guard in interactive web-UI mode (not headless — batch runs may legitimately coexist with a live server).
- Uses `fcntl.flock(LOCK_EX | LOCK_NB)` on macOS/Linux and `msvcrt.locking` on Windows. The OS releases the lock automatically on crash or clean exit — no stale lockfiles.

### Added — Port auto-increment + stdout port signal

- **`gdpr_scanner.py`** (server mode): if the requested port (default 5100, or `--port N`) is already in use, the server auto-increments up to 100 ports and logs a warning: `[!] Port 5100 in use — using 5101 instead`.
- **`build_gdpr.py` launcher** (desktop mode): `find_free_port()` was already present; auto-increment was already the desktop behaviour.
- Both modes emit `GDPR_PORT=<n>` (flush=True) to stdout before Flask starts — a machine-readable signal parseable by any parent process or wrapper script that needs to know the actual bound port.

### Added — Built-in user manual (#31 ✅)

- **`MANUAL-EN.md`** / **`MANUAL-DA.md`** — standalone end-user manuals in English and Danish. 14 sections covering all major features: Getting started, Sources panel, Running a scan, Understanding results, Reviewing results, Bulk actions, Profiles, Scheduler, Export & email, Article 30 report, Data subject lookup, Settings, Retention policy, and FAQ. Written for school administrators and municipal compliance officers — no technical knowledge assumed.
- **`GET /manual`** — new Flask route in `routes/app_routes.py`. Reads `?lang=da|en` (falls back to the current UI language). Finds the appropriate `.md` file relative to the project root, converts it to a fully self-contained styled HTML page, and returns it without any external dependencies.
- **`_md_to_html(md)`** — zero-dependency Markdown-to-HTML converter using only Python's `re` and `html` stdlib modules. Handles headings with anchor IDs, fenced code blocks, tables, ordered/unordered lists, blockquotes, bold, italic, inline code, links, and horizontal rules.
- **`?` button** in the topbar (right of the theme toggle) — opens the manual in a dedicated window (960×800, resizable) using the current `langSelect` value. In the packaged desktop app the window is a native pywebview window (`pywebview.api.open_manual()`); in the browser it opens via `window.open()`. Repeated clicks reuse the same window rather than spawning new ones. Does not interrupt any in-progress scan.
- Manual page: 860 px max-width layout, language switcher (DA ↔ EN), 🖨 print button, `@media print` CSS (toolbar hidden, `h2` page breaks, external link URLs appended for paper printing).

### Fixed — Manual not found in packaged app

- `MANUAL-DA.md` and `MANUAL-EN.md` were missing from the PyInstaller bundle — `build_gdpr.py` now includes all `MANUAL-*.md` files as root-level data files (`--add-data MANUAL-*.md:.`). The route already used `sys._MEIPASS` for the frozen path; the files simply weren't being copied in.
- `build_gdpr.py` `LAUNCHER_CODE` — added `open_manual(lang)` method to the `Api` class. Creates a new pywebview window for the manual URL; reuses the existing window if already open.

### Fixed — Email routing, profile source persistence, SMTP error messages

**`routes/email.py`** — structural rewrite
- Removed `__getattr__` module-level hook. Bare-name lookups inside function bodies do not go through `__getattr__` (Python resolves them via `LOAD_GLOBAL` directly from `__dict__`), so `_load_smtp_config`, `_save_smtp_config`, `_build_excel_bytes`, and `_send_report_email` all raised `NameError` at runtime when the blueprint route won instead of the app-level duplicate.
- `_load_smtp_config`, `_save_smtp_config` now imported directly from `app_config`. `_build_excel_bytes` imported from `routes.export`.
- `_send_report_email(xl_bytes, fname, smtp_cfg, recipients)` was called in three places but never defined anywhere. Now defined as a module-level helper: builds a `MIMEMultipart("mixed")` message with the Excel as a `MIMEBase` attachment and sends via the configured SMTP server.
- `_send_email_graph` moved into the blueprint (was only used by the duplicate app-level routes).

**`gdpr_scanner.py`**
- Removed four duplicate app-level routes that were masking the broken blueprint: `GET /api/smtp/config`, `POST /api/smtp/config`, `POST /api/smtp/test`, `POST /api/send_report`.
- `from routes.email import _send_report_email` added after blueprint imports so `scan_scheduler.py` (`_m._send_report_email`) and the CLI headless path both resolve the function correctly.

**SMTP error messages** (`routes/email.py`)
- All three auth/connection error handlers (smtp_test, send_report, _send_report_email) now classify errors by host type before choosing a message:
  - DNS / connection failure (`nodename nor servname`, `getaddrinfo`, `Connection refused`, timeout) → "Could not connect to SMTP server — check hostname and port."
  - Corporate M365 host (`office365`, `microsoft`) + auth error → M365 admin centre / enable Authenticated SMTP guidance.
  - Personal Microsoft host (`outlook`, `live`, `hotmail`) + auth error → App Password guidance at `account.microsoft.com/security`.
  - Gmail host + auth error → App Password guidance at Google Account Security.
  - Anything else → raw SMTP error, unmodified.
- Previously `530` (generic "authentication required") unconditionally triggered the M365 admin centre message even when the configured host was Gmail or a personal Outlook account.

**`static/app.js`** — profile source persistence
- `_pmgmtSaveFullEdit` was overwriting `google_sources` and `file_sources` with `[]` whenever the editor was opened and those checkboxes weren't rendered (Google not connected / file sources not loaded). Now preserves the profile's existing `google_sources` when `_googleConnected` is false, and `file_sources` when `_fileSources` is empty.
- `_applyProfile` built `_pendingProfileSources` by filtering against `_fileSources` — which is empty at profile-apply time (async load not yet complete), so the pending list was always empty and file source checkboxes defaulted to `checked=true` regardless of the profile. Now stores `profile.file_sources` directly (falling back to non-M365/Google IDs from `profile.sources`).
- Added `_pendingGoogleSources` (mirrors `_pendingProfileSources` for Google). Set in `_applyProfile` from `profile.google_sources`; consumed in `renderSourcesPanel()` the first time Gmail/Drive checkboxes appear (when Google connects after the profile was applied). Previously they defaulted to `checked=true`.

### Fixed — Progress bar and profile sources

**`static/app.js`**
- Progress bar fluctuated and ETA flickered when M365, Google, and file scans ran concurrently. Root cause: all three scan types broadcast `scan_progress` on the same SSE stream and their events interleave. Fixed with two changes: (1) `_maxPct` tracks the highest `pct` seen across all concurrent scans — the bar only ever moves forward; (2) ETA and stats counter are only written when the incoming event actually carries those fields (`d.eta !== undefined`, `d.total` present) — a Google/file event without ETA no longer wipes the ETA set by the M365 event a millisecond earlier.
- `progressPhase` was being overwritten with the current filename by `scan_progress` events, causing it to alternate between phase text ("Google Workspace scan…") and individual filenames. Current filename now correctly updates `progressFile` instead.
- Profile editor (`_openEditorForProfile`) only passed `profile.sources` (M365 IDs) to `_renderEditorSources` — Google and Local/SMB source checkboxes were always unchecked when reopening a saved profile. Now passes the union of `sources`, `google_sources`, and `file_sources`.

### Added — SMB pre-fetch cache (#22 ✅)

- SMB file scans now decouple directory traversal from file reads. A 5-slot sliding-window `ThreadPoolExecutor` keeps up to 5 reads in flight simultaneously, with a 60-second hard timeout per file. A stalled NAS read produces an error card in the UI and the scan continues — the scan thread is never blocked.
- **`file_scanner.py`** — `_smb_collect()` new method walks the SMB tree (directory listing only, no reads), yielding file descriptors plus `_COLLECT_SKIP` / `_COLLECT_ERROR` sentinels for over-size files and listing failures. `_iter_smb()` rewritten: phase 1 collects all candidates; phase 2 resolves sentinels immediately then feeds real files through the executor window. `PREFETCH_WINDOW = 5` and `SMB_READ_TIMEOUT = 60` constants added. Local scanner (`_iter_local`) untouched.

### Added — PDF OCR via multiprocessing (#20 ✅)

- PDF files are now scanned in local/SMB file scans. Previously excluded because Tesseract/Poppler subprocesses could hang indefinitely.
- **`cpr_detector.py`** — new `_worker_scan_pdf()` (module-level, required for `spawn` context) runs `document_scanner.scan_pdf()` in a fresh subprocess and returns results via a `multiprocessing.Queue`. New `_scan_bytes_timeout()` wraps PDF scanning: writes content to a temp file, spawns the worker via `multiprocessing.get_context("spawn")`, joins with a 60-second hard timeout, and terminates the process tree if it exceeds the limit. Non-PDF files delegate straight to `_scan_bytes()`.
- **`scan_engine.py`** — `run_file_scan()` now calls `_scan_bytes_timeout()` instead of `_scan_bytes()` for all files. Stub added to module-level injected globals.
- **`gdpr_scanner.py`** — `_scan_bytes_timeout` imported from `cpr_detector` and injected into `scan_engine`.
- **`file_scanner.py`** — `.pdf` removed from `FILE_SCAN_EXTENSIONS` exclusion; all default extensions now included.

### Fixed — Post-v1.6.4 release bugs (continued)

**`routes/google_scan.py`**
- `_run_google_scan()` crashed with `UnboundLocalError: cannot access local variable 'data'` when `user_emails` was not passed in the request. The fallback `data.get("user_emails", [])` referenced the request-handler local `data` which is not in scope inside the scan function — `data` and `options` are the same object. Removed the redundant fallback.

**`routes/export.py`** — Article 30 report
- `SOURCE_LABELS` was missing `gmail`, `gdrive`, `local`, and `smb` — all four source types rendered as raw keys in every table (inventory, Art. 9, photo, deletion audit log). Now map to "Gmail", "Google Drive", "Local files", "Network / SMB".
- Per-source breakdown table only iterated M365 sources (`email`, `onedrive`, `sharepoint`, `teams`) — Google and local/SMB findings were completely absent from the summary even when present. Loop now covers all eight source types.
- Methodology bullet (`a30_method_4`) only mentioned Microsoft Graph sources. Updated in `en.json`, `da.json`, `de.json`, and the hardcoded fallback to also mention Google Workspace (service account + domain-wide delegation) and local/SMB file shares.

**`scheduler.py`**
- Removed stale file. `scan_scheduler.py` fully supersedes it; `routes/scheduler.py` and `gdpr_scanner.py` both import from `scan_scheduler`. The old file had diverged significantly (missing UUID migration, connector auto-reconnect, file source resolution, debug SSE events).

**`templates/index.html`**
- Removed 9 unused CSS classes: `.sidebar-sub`, `.btn-secondary`, `.log-ok`, `.log-err`, `.log-warn`, `.user-bar`, `.sign-out-btn`, `.source-badge`, `.srcmgmt-coming-soon`.

### Added — Personal Google account OAuth (#30 ✅)

- Personal Google accounts can now be scanned without a service account or Workspace admin. A device-code OAuth flow (mirrors M365 delegated mode) lets a user sign in interactively with their own Google account.
- **`google_connector.py`** — new `PersonalGoogleConnector` class: `get_device_code_flow()` / `complete_device_code_flow()` static methods hit Google's device-auth endpoint; `_refresh_if_needed()` handles transparent token refresh via `google.oauth2.credentials.Credentials`; `list_users()` returns a single-item list (the signed-in user) so the scan engine needs no changes. `iter_gmail_messages()` / `iter_drive_files()` share the same iteration logic as `GoogleConnector` via extracted `_gmail_iter()` / `_drive_iter()` module-level helpers.
- Token persisted to `~/.gdprscanner/google_token.json` (chmod 600). New helpers: `save_personal_token`, `load_personal_token`, `delete_personal_token`.
- **`routes/google_auth.py`** — four new endpoints: `GET /api/google/personal/status`, `POST /api/google/personal/start`, `POST /api/google/personal/poll`, `POST /api/google/personal/signout`. Background thread blocks on `complete_device_code_flow`; frontend polls — identical pattern to M365 delegated auth.
- **`routes/state.py`** — `google_pending_flow` and `google_poll_result` added.
- **`templates/index.html`** — auth-mode toggle (Workspace / Personal account) in the Google pane; personal section with client ID/secret fields and inline device-code box (reuses `.device-code-box` CSS); workspace setup guide hidden in personal mode.
- **`static/app.js`** — `smGoogleSetMode()` switches visible sections; `smGoogleRefreshStatus()` now checks both `/api/google/auth/status` and `/api/google/personal/status` in parallel; `smGooglePersonalStart()`, `smGooglePersonalPoll()`, `smGooglePersonalSignOut()` added.
- **`lang/en.json`, `da.json`, `de.json`** — 14 new keys each.

### Fixed — Post-v1.6.4 release bugs

**`checkpoint.py`**
- Scheduled scans crashed with `string indices must be integers, not 'str'` when `user_ids` in the profile contained plain ID strings rather than dicts. `_checkpoint_key()` now handles both formats: `u["id"] if isinstance(u, dict) else u`.

**`scan_engine.py`**
- Same root cause as above: `run_scan()` now normalises `user_ids` entries to dicts at the top of the function before any access, so both plain strings and `{id, displayName, userRole}` objects work correctly.

**`scan_scheduler.py`**
- `file_sources` in profiles are stored as source ID strings by the JS frontend. The scheduler now resolves each ID to its full source dict via `_load_file_sources()` before calling `run_file_scan()`. Plain path strings are also handled as a fallback.
- Full traceback is now included in the `scheduler_error` SSE event so failures are diagnosable from the UI status panel without needing the CLI.

**`routes/app_routes.py`**
- `/api/langs` (language selector endpoint) only globbed `*.lang` files — after the v1.6.3 JSON migration the language dropdown was silently empty. Now globs both `*.json` and `*.lang` with deduplication, matching the existing logic in `gdpr_scanner.py`.

**`static/app.js`**
- Profile editor (`_pmgmtSaveFullEdit`) did not update `file_sources` or `google_sources` when the user changed source checkboxes — both fields were carried forward unchanged via `...profile`. Now splits `#peSourcesPanel` checkboxes by `data-source-type` and writes `file_sources`, `google_sources`, and `sources` explicitly on every save.

**`gdpr_scanner.py`**
- `/api/langs` only globbed `*.lang` files — after migrating to JSON, the language selector showed nothing. Now globs both `*.json` and `*.lang`, deduplicates by language code, and sorts alphabetically.
- `SOURCE_LABELS` was missing `gmail`, `gdrive`, `local`, and `smb` entries — these sources now get correct tab names in Excel export and correct labels in the Article 30 report.
- Excel export filename changed from `m365_scan_*.xlsx` to `gdpr_scan_*.xlsx`.
- Article 30 methodology paragraph now mentions Google Workspace scanning via service account with domain-wide delegation. DA and DE lang files updated to match.

**`routes/google_scan.py`**
- Gmail and Google Drive result cards showed the email address as account name instead of the user's display name. Fixed: `_user_display_map` is now built from `list_users()` and applied to each scanned item.
- Role badge (Elev/Ansat/Anden) was missing on Google results when `user_emails` came from the request rather than `list_users()`. Fixed: role map is now populated in both cases.
- Google scan now emits `google_scan_done` instead of `scan_done` so the progress bar stays open until both M365 and Google scans finish.

**`scan_engine.py`**
- File scan now emits `file_scan_done` instead of `scan_done` so the progress bar stays open until all active scan types finish.
- `pct` in both Google and file scan progress events was hardcoded at 50 — now increments from 10 to a max of 90.

**`static/app.js`**
- Progress bar now tracks three independent flags (`_m365ScanRunning`, `_googleScanRunning`, `_fileScanRunning`) and only hides when all active scans have completed.
- `google_scan_done` and `file_scan_done` SSE event handlers added.
- Source filter dropdown (search results) and bulk delete source dropdown were missing Gmail, Google Drive, Lokal, and Netværk (SMB) options.
- Profile preset buttons (1 år / 2 år / etc.) were never highlighted when applying a profile — matching used `years × 365.25` but profiles store `years × 365`. Fixed.
- `_fileScanRunning` flag set correctly at scan start from `fileSources.length`.

**`routes/state.py` / `routes/google_scan.py`**
- M365 and Google scans shared `_scan_lock` — Google now uses `_google_scan_lock` and `_google_scan_abort` so both platforms scan in parallel.

**`templates/index.html`**
- Sources, Settings and Schedule indicator moved from sidebar section header / footer into the topbar, to the right of the Profiles button.
- Source filter dropdown and bulk delete dropdown updated with Google and file source options.

**`README.md`**
- All emoji removed (role badges, action icons, status indicators). Plain text equivalents used throughout.
- `lang/da.json` and `lang/de.json` updated with Google Workspace methodology text for the Article 30 report.

---

## [1.6.4] — 2026-04-03

### Added — Full profile editor (#15e ✅)

- Two-panel modal (profile list left, full editor right). Click a profile row to edit it; the active row is highlighted.
- **+ Ny profil** button in the left panel footer — creates a blank profile and opens the editor immediately, works when no profiles exist.
- Editor sections match the sidebar exactly:
  - **Navn** — name + description fields
  - **Kilder** — same rendering as the main KILDER panel, including M365, Google Workspace, and file/SMB sources
  - **Konti** — role filter (Alle / Ansat / Elev), text search, Alle / Ingen select buttons, + Tilføj konto manual entry, platform badges (M365 / GWS / M365+GWS), role badges
  - **Indstillinger** — date picker with year presets (1/2/5/10/Alle), Scan e-mailindhold, Scan vedhæftede filer, Maks. vedhæftet filstørrelse (MB), Maks. e-mails pr. bruger, Delta-scanning, Søg efter ansigter i billeder — all as toggle sliders
  - **Opbevaringspolitik** — always visible; Opbevaringsår + Regnskabsår slut dropdown
- Annuller, ×, and Gem all close the full modal. Auto-opens first profile on modal open.
- Profile editor defaults match the main window: accounts are unchecked by default; only explicitly saved `user_ids` are shown as checked.

### Fixed — Parallel M365 + Google scanning

- M365 and Google scans shared `_scan_lock` — starting both simultaneously caused "Google scan already running" immediately after scan start. Fixed: `routes/state.py` now defines `_google_scan_lock` and `_google_scan_abort` as separate threading primitives; `routes/google_scan.py` uses these instead of the M365 lock. Both platforms now scan in parallel.

### Fixed — User selection defaults

- All users now default to `selected: false` on page load (previously `true`). The profile editor follows the same rule.
- "Vælg alle" button renamed to "Alle" to match the main sidebar.

---

## [1.6.3] — 2026-04-03

### Fixed — Post-v1.6.3 release bugs

**`static/app.js`**
- Source toggle state (Email, OneDrive, SharePoint, Teams, Gmail, Google Drev) not persisted across restarts. Fixed: all toggles now save to `~/.gdprscanner/src_toggles.json` via a new `/api/src_toggles` endpoint and are restored on page load.
- Deselecting M365 sources in Source Management did not update account badges — `M365 + GWS` still shown. Fixed: badge now uses `hasM365Src` and `effectiveGws` computed inside `renderAccountList()`, and M365 source toggles now call `renderAccountList()` on change.
- Google-only scans reported wrong account count in live log (e.g. "26 konto(er)" when 1 was selected). Root cause: `getSelectedUsers()` returned all selected users including Google-only accounts. Fixed: `getSelectedUsers()` now returns only M365 users; Google users are counted separately for the log message. The "select at least one account" guard no longer blocks Google-only scans.
- Cross-platform identity matching used email prefix (`anne.hansen` before `@`) — changed to `displayName` matching since both M365 and GWS are maintained from the same AD source.
- `_onGoogleSourceToggle()` and M365 source toggles did not call `renderAccountList()` — account badges not updated when toggling sources in Source Management.

**`routes/google_auth.py`**
- Removed `/api/google/auth/sources` endpoint and `src_gmail`/`src_drive` keys from the status response — replaced by unified `/api/src_toggles` endpoint in `gdpr_scanner.py`.

**`app_config.py` / `gdpr_db.py` / `checkpoint.py` / `google_connector.py` / `m365_connector.py` / `scan_scheduler.py` / `scheduler.py` / `gdpr_scanner.py`**
- All data files moved from `~/` root into `~/.gdprscanner/` subdirectory with cleaner short names (`scanner.db`, `config.json`, `token.json`, etc.). A migration shim runs on first startup and moves existing `~/.gdpr_scanner_*` files automatically. `MAINTAINER.md` updated with new file locations.

**`scan_scheduler.py`**
- Scheduled scans ignored `file_sources` from the profile — `_build_options()` dropped them. Fixed: `file_sources` now included in opts, and `run_file_scan()` is called for each file source in the profile during a scheduled run (#15f ✅).

**`static/app.js` — profile save**
- `file_sources` in profile was hardcoded to `[]` — now saves the actual checked file sources from `buildScanPayload()` (#15f).

### Fixed — Post-release (continued)

**`routes/state.py` / `routes/google_scan.py`**
- M365 and Google scans shared `_scan_lock` — starting both simultaneously caused "Google scan already running" immediately. Fixed: Google scan now uses its own `_google_scan_lock` and `_google_scan_abort` so both platforms can run in parallel.

**`static/app.js`** — profile editor (#15e ✅)
- Profile editor drawer implemented: two-panel modal (profile list left, full editor right). Click any profile to open its editor.
- Editor sections: Navn + beskrivelse, Kilder (same rendering as main KILDER panel, including Google and file sources), Konti (with Alle / Ansat / Elev role filter, text search, Alle / Ingen select buttons, + Tilføj konto manual add), Indstillinger (full mirror of sidebar — date picker with year presets, Scan e-mailindhold, Scan vedhæftede filer, Maks. vedhæftet filstørrelse, Maks. e-mails pr. bruger, Delta-scanning, Søg efter ansigter i billeder, all as toggle sliders), Opbevaringspolitik (always visible — Opbevaringsår + Regnskabsår slut).
- + Ny profil button in left panel footer — creates a blank profile and opens the editor immediately, works even when no profiles exist.
- Annuller, ×, and Gem all close the full modal (not just the editor panel).
- Auto-opens first profile's editor when modal opens.

**`static/app.js`** — defaults
- All users now default to `selected: false` on load (were `true`). Profile editor follows the same rule — only explicitly saved user_ids are shown as checked.
- "Vælg alle" button renamed to "Alle" to match the main sidebar.

**`routes/state.py`**
- Added `_google_scan_lock` and `_google_scan_abort` as separate threading primitives for Google scans.

---

### Added — Google Workspace full integration

**Accounts panel**
- Google Workspace users now appear in the Accounts panel alongside M365 users. Each row shows a platform badge: `M365` (blue) or `GWS` (green).
- Account list filters by checked sources: check only Google sources → only GWS accounts shown; check only M365 → only M365 accounts; check both → all; check none → empty.
- Role filter (All / Ansat / Elev) works across both platforms.
- `_mergeGoogleUsers()` — dedicated async function fetches `/api/google/scan/users` and merges results into `_allUsers` independently of M365 auth timing. Called on page load, on Google connect/disconnect, and after M365 `loadUsers()`.

**Scanning**
- Selected Google user emails are now passed as `user_emails` to `/api/google/scan/start` — only selected accounts are scanned, not all users in the domain.
- `routes/google_scan.py` — `_scan_lock` and `_scan_abort` now imported directly from `routes.state` (previously relied on `__getattr__`, which does not resolve bare names inside function bodies — caused `NameError` on scan start).
- `user_emails` now read from the top-level request body in addition to the nested `options` dict.
- Gmail scan result cards now correctly labelled "Gmail" (source_type was `email` → mapped to "Exchange"). Fixed in `google_connector.py`.
- Gmail and Google Drive cards now show styled source badges (`badge-gmail` red tint, `badge-gdrive` blue tint). Previously fell back to unstyled.

**Profiles**
- Google sources (`gmail`, `gdrive`) and selected Google user emails are now saved to scan profiles and correctly restored on load.
- Fixed `googleSources` `const` temporal dead zone — declaration moved before use in `buildScanPayload()`.

### Added — OU-based role classification for Google Workspace (#23 Phase 1 ✅)

- **`classification/google_ou_roles.json`** — maps Google Workspace Organisational Unit paths to roles. Edit to match your school's OU structure; no code change required. Default: `/Elever` → student, `/Personale` → staff.
- **`google_connector.py`** — `list_users()` fetches `orgUnitPath` via `projection=full` and classifies each user via `classify_ou_role()`.
- **`routes/google_scan.py`** — role map built from `list_users()` result; each scan card now carries the correct `user_role`.

### Added — Documentation split

- **`M365_SETUP.md`** — step-by-step Microsoft 365 setup (app registration, permissions, auth modes, headless config, troubleshooting).
- **`GOOGLE_SETUP.md`** — step-by-step Google Workspace setup (service account, domain-wide delegation, scopes, OU role mapping, troubleshooting).
- **`README.md`** — trimmed from 774 to 611 lines; setup detail moved to the two new files.

### Changed — i18n migrated from `.lang` to JSON (#27 ✅)

- `lang/en.json`, `da.json`, `de.json` — 709 keys each, standard flat JSON.
- `app_config.py` — loader now prefers `.json`, falls back to `.lang` for backward compatibility.
- Old `.lang` files retained as fallback; can be deleted once JSON files are confirmed working.

### Changed — `skus/` renamed to `classification/` (#29 ✅)

- `skus/education.json` → `classification/m365_skus.json`
- `skus/google_ou_roles.json` → `classification/google_ou_roles.json`
- All path references updated in `m365_connector.py`, `google_connector.py`, `routes/users.py`, `gdpr_scanner.py`, `build_gdpr.py`, all lang files, and `static/app.js`.

### Changed — UI polish (icons removed, badges added)

- Role filter buttons (Staff / Student), scan option labels (Delta scan, Scan photos, Retention policy), and account list role badges — all emoji removed, plain text only.
- Role badge on account rows changed from emoji icon button to plain outline pill (`Ansat` / `Elev` / `Anden`).
- Scan result cards — role icon prefix replaced with small inline badge.
- All six lang files cleaned of emoji in role, mode, option, and Art.30 inventory keys.
- Progress bar fixed at 32px height — emoji in filenames no longer push the bar taller.
- Scrollbars in Sources and Accounts panels thinned to 4px.

### Fixed — Account list / source interaction

- Deselecting all sources now empties the account list.
- Deselecting M365 sources no longer disables Accounts when Google sources are still checked.
- `_updateAccountsVisibility()` now checks all source types, not just M365.

### Fixed — Role override cycling

- Role override never cleared for users loaded with a pre-existing override (`roleOverride: true` from a previous session) because `_autoRole` was never populated from the server. Fixed: replaced `_autoRole` comparison with a step counter — after 3 clicks the override clears regardless of the original auto role.
- Role badge changed from `<span>` to `<button type="button">` inside label rows — prevents label click-forwarding to the checkbox (which caused the first user to receive the override instead of the clicked user).

---

## [1.6.2] — 2026-03-28

### Added — Google Workspace account list and source integration

- **`static/app.js`** — Google Workspace users (292 users in testing) now appear in the Accounts panel with `GWS` badge (blue = M365, green = GWS). M365 users carry `M365` badge.
- Account list filters by checked sources: check only Google sources → only GWS accounts shown; check only M365 → only M365 accounts; check both → all accounts; check none → empty list.
- Role filter buttons (All / Ansat / Elev) work across both platforms.
- `_mergeGoogleUsers()` — dedicated function fetches `/api/google/scan/users` and merges results into `_allUsers` independently of M365 auth timing. Called on page load, on Google connect/disconnect, and after M365 `loadUsers()`.
- `startScan()` — selected Google user emails now passed as `user_emails` to `/api/google/scan/start`, so only the chosen accounts are scanned (previously ignored selection and scanned all users).
- **`routes/google_scan.py`** — `_scan_lock` and `_scan_abort` now imported directly from `routes.state` (previously relied on `__getattr__` which doesn't resolve bare names inside function bodies — caused `NameError` on scan start).
- `user_emails` now read from the top-level request body in addition to the nested `options` dict.

### Added — OU-based role classification for Google Workspace (#23 Phase 1)

- **`classification/google_ou_roles.json`** — new file mapping Google Workspace Organisational Unit paths to roles. Edit to match your school's OU structure; no code change required. Default: `/Elever` → student, `/Personale` → staff.
- **`google_connector.py`** — `list_users()` now fetches `orgUnitPath` via `projection=full` and classifies each user via `classify_ou_role()`. Each user dict now includes `userRole` and `orgUnitPath`.

### Added — Documentation split

- **`M365_SETUP.md`** — step-by-step Microsoft 365 setup guide (app registration, permissions, auth modes, headless config, role classification, troubleshooting).
- **`GOOGLE_SETUP.md`** — step-by-step Google Workspace setup guide (service account, domain-wide delegation, OAuth scopes, OU role mapping, troubleshooting).
- **`README.md`** — trimmed from 774 to 611 lines. Auth/permissions/headless detail moved to setup guides. Two new "Microsoft 365" and "Google Workspace" sections link to the respective files.

### Changed — UI polish (icons removed)

- Role filter buttons (Staff / Student) — emoji removed, plain text only.
- Scan option labels (Delta scan, Scan photos for faces, Retention policy) — emoji removed.
- Account list role badge — replaced clickable emoji button (`👔`/`🎓`/`👤`) with plain outline pill badge (`Ansat` / `Elev`), matching the platform badge style.
- Scan result cards — role icon prefix removed from account name; replaced with small inline outline badge.
- All three lang files (`en.lang`, `da.lang`, `de.lang`) cleaned of emoji in `m365_role_staff`, `m365_role_student`, `m365_opt_delta`, `m365_opt_scan_photos`, `m365_opt_retention`, `m365_mode_delegated`, `m365_bulk_overdue_btn`, `a30_inv_staff`, `a30_inv_students`.

### Fixed — Profile save/load with Google sources

- Google sources (`gmail`, `gdrive`) and selected Google user emails now saved in scan profiles and correctly restored on load.
- `googleSources` `const` declaration moved before use in `buildScanPayload()` — fixed temporal dead zone `ReferenceError`.

### Fixed — Account list / source interaction

- Deselecting all sources now empties the account list (previously kept showing all users).
- Selecting only Google sources no longer disables the Accounts section (previously greyed out when no M365 sources were checked).
- `_updateAccountsVisibility()` now checks all source types, not just M365.

### Added — Google Workspace role classification via OU mapping (#23 Phase 1)

- **`classification/google_ou_roles.json`** — new file mapping Google Workspace Organizational
  Unit paths to roles (`student` / `staff`). Edit to match your school's OU structure;
  no code change required. Default prefixes: `/Elever` → student, `/Personale` → staff.
- **`google_connector.py`** — `list_users()` now requests `orgUnitPath` from the Admin
  Directory API and classifies each user via `classify_ou_role()`. Each user dict now
  includes `userRole` and `orgUnitPath`.
- **`routes/google_scan.py`** — role map built from `list_users()` result; scan cards
  now carry the correct `user_role` instead of always `"other"`.

### Fixed — Post-split and app runtime bugs (additional)

**`routes/database.py`**
- Settings panel showed "Scanned: 0, Flagged: 0, Scans: 0" because `get_stats()`
  returns `{}` when no scan has a `finished_at` timestamp (interrupted or first-run).
  Fixed: stats endpoint now queries `flagged_items` and `scans` tables directly so
  counts are always correct regardless of scan completion state. Stats populate on
  app start from existing DB data — no re-scan required.
- DB export produced a ZIP but nothing was downloaded in the native app because
  `URL.createObjectURL()` does not work in pywebview. Fixed: `exportDB()`,
  `exportExcel()`, and `exportArticle30()` in `static/app.js` now detect pywebview
  and call `window.pywebview.api.save_db_export()` / `save_excel()` / `save_article30()`
  which use the native macOS/Windows save dialog. Browser fallback preserved.
- Added `save_db_export()` and `save_article30()` methods to the pywebview `Api`
  class in `build_gdpr.py`. Fixed `save_excel` filename from `m365_scan_` to `gdpr_scan_`.

**`scan_engine.py`**
- `run_file_scan()` called `_db.start_scan()` which does not exist — the correct
  method is `begin_scan()`. Silent exception meant `_db_scan_id` was always `None`
  and no file scan results were ever written to the database. Fixed.

### Added — Personal use disposition value (#28)

Staff members using work equipment for private purposes will now appear in scan
results. Added `personal-use` as a disposition value so reviewers can explicitly
mark items as outside the organisation's compliance scope.

- New disposition: **Personal use — out of scope** in both UI dropdowns
- Art. 30 report labels it "Personal use — out of GDPR scope (Art. 2(2)(c))"
- Translated in EN / DA / DE

**Legal basis:** GDPR Article 2(2)(c) — processing by a natural person in the
course of a purely personal activity is outside GDPR scope.

### Added — pytest test suite (#26)

112 tests across 4 modules — all passing.

| Test module | Tests | What it covers |
|---|---|---|
| `tests/test_document_scanner.py` | 36 | `is_valid_cpr`, `extract_matches`, `scan_docx`, `scan_xlsx`, `_scan_bytes` — CPR detection, false-positive suppression, binary edge cases |
| `tests/test_app_config.py` | 34 | i18n loading, Article 9 keyword detection, config round-trip, admin PIN, profiles CRUD, Fernet encryption |
| `tests/test_checkpoint.py` | 18 | `_checkpoint_key` stability, save/load/clear, wrong-key isolation, delta token round-trip |
| `tests/test_db.py` | 24 | Scan lifecycle, `save_item`, CPR hash-only storage, `lookup_data_subject`, dispositions, export/import cycle |

**Support files:**
- `tests/conftest.py` — shared fixtures: `docx_with_cpr`, `docx_no_cpr`, `xlsx_with_cpr`, `xlsx_no_cpr`, `txt_with_art9`, `binary_garbage`, `tmp_db`
- `pytest.ini` — test discovery config

**Run with:** `pytest tests/` from the project root.

### Fixed — Six post-split runtime bugs

All bugs introduced by the #25 module split — the pre-split code had none of these.

**`gdpr_scanner.py`**
- `_current_scan_id` imported as a string binding (`from sse import _current_scan_id`), so `scan_stream()` always saw `""` — SSE replay filter excluded all events and the progress bar showed nothing. Fixed: reads `sse._current_scan_id` at call time via module reference.
- `_connector` assignment only updated the local module global, not `_state.connector`. `scan_engine.py` reads `_state.connector`, which stayed `None` after sign-in — every scan reported "Not connected to M365". Fixed: all five `_connector = ...` assignments now dual-assign `_connector = _state.connector = ...`.

**`scan_engine.py`**
- `_load_role_overrides`, `_resolve_display_name`, `_scan_text_direct` were undefined bare names inside `run_scan()` — raised `NameError` at runtime. Fixed: proper imports from `app_config` and `cpr_detector`.
- `PHOTO_EXTS` and `SUPPORTED_EXTS` were stub empty sets at import time; injection via `_se.PHOTO_EXTS = ...` replaced the module attribute but function bodies still saw the empty stubs. Fixed: `scan_engine.py` now imports these directly from `cpr_detector` at module level.
- `scan_progress` SSE event broadcasts `index` and `pct`; the UI handler read `d.completed` — progress bar was always 0%. Fixed in `static/app.js`: handler now reads `d.pct` (pre-calculated server-side) and populates `progressStats` (n / total) and `progressEta` elements that were wired in HTML but never written.
- Source collection (OneDrive, SharePoint, Teams) completed silently with no count in the live log. Fixed: broadcasts `📁 OneDrive — user: N file(s)`, `🌐 SharePoint: N file(s)`, `💬 Teams — user: N file(s)` after each successful collection.

**`cpr_detector.py`**
- `_scan_text_direct()` called `ds.scan_text()` which internally calls `extract_cpr_and_dates()` — a function that does not exist in `document_scanner.py` (pre-existing bug in that module). Result: every email body scan returned zero CPRs. Same bug affected `.txt` files and the unknown-extension fallback in `_scan_bytes()`. Fixed: all three replaced with `ds.extract_matches(text, 1, "text")` which works correctly.

**`static/app.js`**
- `scan_file_flagged` handler called `renderCards()` which is not defined anywhere — silent `ReferenceError` in the browser, cards pushed to `flaggedData` but never displayed. Fixed: replaced with `applyFilters()` which calls `renderGrid()` and shows the filter bar.
- `scan_done` handler never showed the filter bar (containing Excel and Art.30 export buttons) when results existed — only the stats numbers updated. Fixed: `scan_done` now explicitly shows the filter bar and calls `applyFilters()` when `flaggedData.length > 0`.

---

## [1.6.1] — 2026-03-28

### Changed — Split `gdpr_scanner.py` into focused modules (#25)

`gdpr_scanner.py` was 5554 lines. It is now 3591 lines and delegates to five
focused modules. No behaviour changes — all existing routes, blueprints, and
imports continue to work unchanged.

**New files:**

| Module | Lines | Contents |
|---|---|---|
| `sse.py` | 52 | `broadcast()`, `_sse_queues`, `_sse_buffer`, `_current_scan_id` |
| `checkpoint.py` | 79 | `_save_checkpoint()`, `_load_checkpoint()`, `_checkpoint_key()`, delta token load/save |
| `app_config.py` | 553 | i18n, Article 9 keywords, config, admin PIN, profiles, settings, SMTP, file sources, Fernet encryption |
| `cpr_detector.py` | 381 | `_scan_bytes()`, `_extract_exif()`, `_detect_photo_faces()`, `_make_thumb()`, `_get_pii_counts()` |
| `scan_engine.py` | 1006 | `run_scan()`, `run_file_scan()` — M365 and file-system scan orchestration |

**Changed files:**

- `gdpr_scanner.py` — imports and re-exports from all five modules; keeps Flask
  app init, `@app.route` definitions, blueprint registration, and `__main__` entry point
- `routes/state.py` — `_scan_lock` and `_scan_abort` moved here from `gdpr_scanner.py`
  so `scan_engine.py` can reference them without a circular import

**Isolation:** each new module is importable in isolation with fallback stubs,
enabling unit tests (#26) to import `cpr_detector` or `checkpoint` without
pulling in Flask, MSAL, or the full application.

---

## [1.6.0] — 2026-03-28

### Changed — Rename: M365 Scanner → GDPRScanner (#24)

The tool now scans M365, Google Workspace, local file systems, and SMB network
shares. The name "M365 Scanner" was misleading. This release renames everything
with no behaviour changes.

**Files renamed:**

| Old | New |
|---|---|
| `m365_scanner.py` | `gdpr_scanner.py` |
| `m365_db.py` | `gdpr_db.py` |
| `build_m365.py` | `build_gdpr.py` |
| `build_m365.sh` | `build_gdpr.sh` |
| `start_m365.sh` *(created by install_macos.sh)* | `start_gdpr.sh` |
| `start_m365.bat` *(created by install_windows.ps1)* | `start_gdpr.bat` |

**Config files renamed on first startup (migration shim):**

| Old `~/` path | New `~/` path |
|---|---|
| `.m365_scanner_config.json` | `.gdpr_scanner_config.json` |
| `.m365_scanner.db` | `.gdpr_scanner.db` |
| `.m365_scanner_token.json` | `.gdpr_scanner_token.json` |
| `.m365_scanner_delta.json` | `.gdpr_scanner_delta.json` |
| `.m365_scanner_settings.json` | `.gdpr_scanner_settings.json` |
| `.m365_scanner_smtp.json` | `.gdpr_scanner_smtp.json` |
| `.m365_scanner_role_overrides.json` | `.gdpr_scanner_role_overrides.json` |
| `.m365_scanner_file_sources.json` | `.gdpr_scanner_file_sources.json` |
| `.m365_scanner_machine_id` | `.gdpr_scanner_machine_id` |
| `.m365_scanner_checkpoint.json` | `.gdpr_scanner_checkpoint.json` |
| `.m365_scanner_schedule.json` | `.gdpr_scanner_schedule.json` |
| `.m365_scanner_msal_cache.bin` | `.gdpr_scanner_msal_cache.bin` |
| `.m365_scanner_lang` | `.gdpr_scanner_lang` |

The migration runs silently at startup — existing scan history, credentials,
settings, and role overrides are preserved automatically.

**Intentionally unchanged:**
- `m365_connector.py` — kept as-is; it is the Microsoft Graph connector and
  the `m365_` prefix accurately describes what it connects to
- i18n keys with the `m365_` prefix that describe M365-specific UI elements
  (Azure credential fields, device code flow screens) — the prefix is correct

**Run with:**
```
python gdpr_scanner.py [--port 5100]
```

---

## [1.5.9] — 2026-03-28

### Added — Google Workspace scanning (#10)

Organisations running mixed Microsoft/Google environments can now scan Gmail
and Google Drive alongside M365 in a single tool. The Google Workspace tab in
Source Management is now fully active (was "Coming soon" stub).

**New files:**
- `google_connector.py` — service account OAuth with domain-wide delegation;
  Gmail message + attachment iterator; Drive file iterator with automatic export
  of native Docs/Sheets/Slides → DOCX/XLSX/PPTX before scanning
- `routes/google_auth.py` — `/api/google/auth/status`, `/connect`, `/disconnect`
- `routes/google_scan.py` — `/api/google/scan/start`, `/cancel`, `/users`

**Changed files:**
- `routes/state.py` — `google_connector` slot added
- `m365_scanner.py` — Google blueprints registered; `GOOGLE_CONNECTOR_OK` /
  `GOOGLE_AUTH_OK` flags; connector auto-restored from saved key on startup
- `templates/index.html` — Google tab activated; full credentials pane with key
  file upload, admin email field, Gmail + Drive source toggles, and setup guide
- `static/app.js` — `smGoogleRefreshStatus()`, `smGoogleConnect()`,
  `smGoogleDisconnect()`, `getGoogleScanOptions()`, key file reader
- `requirements.txt`, `install_windows.ps1`, `install_macos.sh` — three new
  optional Google API dependencies
- `lang/en.lang`, `da.lang`, `de.lang` — 14 new i18n keys each

**Dependencies (optional — scanner starts without them):**
```
pip install google-auth google-auth-httplib2 google-api-python-client
```

**Setup required in Google Workspace Admin Console:**
1. Create a Google Cloud project; enable Gmail API, Drive API, Admin SDK
2. Create a service account; download the JSON key; enable domain-wide delegation
3. In Workspace Admin → Security → API Controls → Domain-wide delegation add the
   service account client ID with scopes:
   `gmail.readonly`, `drive.readonly`, `admin.directory.user.readonly`

**Scan results** write to the same SQLite database with `source_type = "gmail"`
or `"gdrive"` — Article 30 reports and data subject lookups cover both platforms
automatically.

---

## [1.5.8] — 2026-03-28

### Fixed — Scheduled scans invisible in the browser (#21)

Scheduled scans now show full live progress in the browser — progress bar,
phase text, flagged cards, and log entries — exactly like manual scans.

**Root cause (critical):** When run as `python m365_scanner.py`, the module
loads as `__main__`. The scheduler's `import m365_scanner as _m` loaded a
**second copy** of the module with its own empty `_sse_queues`. Events from
`_m.broadcast()` went nowhere — the browser's SSE connection was reading from
`__main__`'s queues.

**Fix:** `sys.modules["m365_scanner"] = sys.modules[__name__]` at the top of
the module ensures all imports share the single running instance.

### Fixed — SSE event replay for late-connecting browsers (#21)

Opening the browser mid-scan (manual or scheduled) now replays all buffered
progress events so the live log and card grid are fully populated.

**Additional root causes and fixes:**

- `_autoConnectSSEIfRunning()` only attached `scheduler_*` listeners on page
  load — replayed `scan_phase`, `scan_file_flagged`, and `scan_done` events
  were silently ignored
- Idle SSE connections died silently (Flask/Werkzeug threading); the browser
  had no live connection when a scheduled scan fired minutes/hours later

**Changes — Python (`m365_scanner.py`):**
- Module identity fix: `sys.modules["m365_scanner"] = sys.modules[__name__]`
- Added `_current_scan_id` global — unique timestamp-based ID set at the start
  of every scan (M365 and file scans) and cleared after `scan_done`
- `broadcast()` injects `scan_id` into every SSE event payload
- `scan_stream()` filters the replay buffer to only include events matching the
  current `scan_id`, preventing stale replay from previous scans
- New `sse_replay` / `sse_replay_done` marker events bracket the replayed block
  so the browser can distinguish replay from live events
- New `GET /api/scan/status` lightweight endpoint returning `{running, scan_id}`

**Changes — JavaScript (`static/app.js`):**
- Extracted `_attachScanListeners(es)` and `_attachSchedulerListeners(es)` —
  shared by both `startScan()` and `_autoConnectSSEIfRunning()`
- `_attachSchedulerListeners` now shows the progress bar on `scheduler_started`
  and hides it on `scheduler_done` / `scheduler_error`
- SSE polling watchdog (`_sseWatchdog`) checks `/api/scan/status` every 4s;
  reopens the SSE connection via `_ensureSSE()` if it has died
- `_userStartedScan` flag — `scan_done` only closes the SSE connection for
  user-initiated scans; scheduled scans keep it alive
- Fixed `es.onerror` handler — no longer silently nulls `es`

### Fixed — File scan `scan_complete` → `scan_done` event name

`run_file_scan()` was broadcasting `scan_complete` on finish, but the JS only
listens for `scan_done`. Renamed to `scan_done` with the same `total_scanned` /
`flagged_count` payload shape as M365 scans.

### Fixed — Resume scan used wrong profile

`startScan()` never told the server which profile was active. Settings were
always saved to the Default profile. Now `profile_id` is sent in the scan start
payload and `_save_settings()` accepts a `profile_id` parameter (takes
precedence over `profile_name`).

### Fixed — `install_macos.sh` launcher scripts

- `start_gdpr.sh` and `build_m365.sh` templates now use `exec python3` instead
  of `exec python` — fixes "not found" after removing python.org interpreter
- spaCy model install: creates a `pip` shim in `venv/bin/` (spaCy's
  `shutil.which("pip")` couldn't find the venv's pip3), falls back to direct
  `pip install` if `spacy download` still fails, and prepends `venv/bin` to
  PATH explicitly

### Added — Diagnostic logging

- `[run_scan]` prints sources, user count, app_mode, and a sample user entry
  at scan start — helps verify scheduled scans use the correct profile
- `[SSE]` console.log messages in the browser for `scan_phase`, `scan_done`,
  `scan_file_flagged`, `scheduler_started`, `scheduler_done`, `scheduler_error`
  — aids debugging SSE delivery issues

### Added — i18n keys (EN / DA / DE)

- `m365_sse_reconnecting` — shown when page load detects a running scan
- `m365_sse_replay_note` — logged after replayed events finish

---

## [1.5.7] — 2026-03-28

### Fixed — Missing translations in Settings modal

Several strings in the Settings → General and Settings → Scheduler tabs were
displaying in English regardless of the active language.

**Missing lang keys added** (EN / DA / DE):
- `btn_save` — Save / Gem / Speichern (used by scheduler editor Save button and others)
- `m365_settings_about` — About / Om / Über
- `m365_settings_save_pin` — Save PIN / Gem PIN / PIN speichern
- `m365_sched_freq_daily/weekly/monthly` — frequency labels in job list and editor
- `m365_sched_dow_mon` through `_sun` — day-of-week labels

**Template fixes:**
- "About" group heading now has `data-i18n="m365_settings_about"`
- "Save PIN" button uses dedicated key `m365_settings_save_pin` instead of generic `btn_save`
- Frequency and day-of-week `<option>` elements now have `data-i18n` attributes
- Scheduler job list (`schedRenderJobs`) and status update now use `t()` for frequency labels

### Changed — Theme toggle replaced with slider

The "Toggle dark / light" text button in Settings → General is replaced with a
standard toggle slider (consistent with all other toggles in the UI). The slider
reflects the current theme state when the tab opens and toggles the theme on click.

---

## [1.5.6] — 2026-03-28

### Feature — SSE event replay (#21)

Opening the browser mid-scan (e.g. while a scheduled scan is running) now
replays all buffered events so the live log and result cards populate
immediately, rather than showing nothing until the next event fires.

**`m365_scanner.py`:**
- Added `_sse_buffer: deque = deque(maxlen=500)` — a ring buffer that stores
  every `broadcast()` event
- `broadcast()` appends to the buffer before sending to SSE clients
- `run_scan()` clears the buffer at the start of each scan so stale events
  from the previous scan are not replayed
- Removed duplicate `@app.route("/api/scan/stream")` — route is now handled
  exclusively by the `routes/scan.py` blueprint

**`routes/scan.py`:**
- `scan_stream()` replays `_m._sse_buffer` immediately when a new client
  connects, then switches to live events
- All globals accessed directly via `import m365_scanner as _m` to avoid
  `__getattr__` resolution failures that caused 500 errors
- A `: connected` comment line is sent first to confirm the stream is flowing

**`static/app.js`:**
- `_autoConnectSSEIfRunning()` — new function called on `DOMContentLoaded`
  that always opens the SSE connection on page load. If a scan is already
  running, buffered events replay immediately. If the buffer is empty, no
  events fire and the log stays quiet.
- Handles `scan_phase`, `scan_progress`, `scan_start`, `scan_file_flagged`,
  `scan_done`, `scheduler_started`, `scheduler_done`, `scheduler_error` events
- `startScan()` closes and reopens the SSE connection to get a clean stream
  for each manual scan

**`m365_scanner.py` — CLI output when no browser connected:**
- `broadcast()` now prints key events to the terminal when `_sse_queues` is
  empty (i.e. no browser tab is watching), so scheduled scans are visible in
  the CLI: scan phases, file progress, errors, and completion summary

---

## [1.5.5] — 2026-03-28

### Fixed — Scheduler: multiple bugs after multi-job implementation

**`scheduler.py` renamed to `scan_scheduler.py`**

Python's stdlib includes a `sched`/`scheduler` module that was being resolved
instead of the project's own `scheduler.py`, causing `module 'scheduler' has no
attribute 'load_jobs'`. Renaming the project file to `scan_scheduler.py` eliminates
the collision entirely. All imports updated in `routes/scheduler.py` and
`m365_scanner.py`.

**Jobs with missing UUID assigned on load**

Jobs saved before the multi-job refactor had `"id": ""`. `load_jobs()` now detects
any job with a missing or empty id and assigns a fresh UUID, then rewrites the file.
This fixed "Delete failed: id required" and silent edit failures.

**Enabled toggle added to each scheduler row**

Each job row now has an inline toggle switch instead of a static ✓/— indicator.
Toggling saves the change immediately via `/api/scheduler/jobs/save`. The job
description also shows "Next: [date]" after the status fetch resolves.

**Edit no longer duplicates the job**

`_sched().reload()` inside the save route was not wrapped in its own try/except.
If APScheduler threw (e.g. not yet started), the exception propagated and caused
the save to fall through to the "create new" path. Both `reload()` calls (save and
delete) are now wrapped in `try/except: pass`.

**Delete button now works**

The delete button was passing the HTML-escaped job name through the onclick
attribute — names with apostrophes or special characters broke the JS string.
Fixed by passing only `id` and looking up the name from `_schedJobs` inside
`schedDeleteJob()`. The route and JS both have proper error handling now.

**"Not authenticated" on scheduled run**

`state.connector` is assigned once at startup (`_state.connector = _connector`)
and never updated when the user authenticates later. The scheduler now reads
`_m._connector` directly from the live `m365_scanner` module at run time,
guaranteeing it sees the current authenticated connector.
`flagged_items` and `scan_meta` reads also updated to use `_m.flagged_items`
and `_m.scan_meta` directly.

---

## [1.5.4] — 2026-03-28

### Feature — Multiple scheduled scans

The Settings → Scheduler tab now supports multiple independent named scan jobs,
replacing the previous single-job form.

**`scheduler.py`**
- Config format changed from a single dict to `{"jobs": [...]}`. Each job has
  its own `id` (UUID), `name`, and all existing fields (frequency, time, profile,
  auto-email, auto-retention).
- Old single-job `~/.m365_scanner_schedule.json` files are automatically migrated
  to the new format on first load — no manual changes needed.
- `ScanScheduler` registers one APScheduler job per enabled scan and tracks
  running state and last-run info per job independently.
- Backward-compat shims (`load_schedule_config`, `save_schedule_config`) kept
  for any existing integrations.

**`routes/scheduler.py`** — new CRUD endpoints:
- `GET  /api/scheduler/jobs` — list all jobs
- `POST /api/scheduler/jobs/save` — create or update a job (by id)
- `POST /api/scheduler/jobs/delete` — delete a job by id
- `POST /api/scheduler/jobs/run_now` — run a specific job immediately by id
- Old `/api/scheduler/config` and `/api/scheduler/run_now` kept as backward-compat shims

**`templates/index.html`** — scheduler pane replaced with a job list (styled like
File sources) and an inline editor that slides open when adding or editing. Each
row shows the job name, frequency summary, enabled/running status pill, and
▶ Run / ✏ Edit / ✕ Delete buttons. Schedule configuration lives exclusively in
the editor — nothing schedule-related appears in the sidebar except the existing
"Next: …" indicator.

**`static/app.js`** — all `sched*` functions rewritten for multi-job:
`schedLoad`, `schedRenderJobs`, `schedAddJob`, `schedEditJob`, `schedSaveJob`,
`schedDeleteJob`, `schedRunJob`, `schedCancelEdit`, `schedLoadHistory`,
`schedUpdateSidebarIndicator`.

**Lang keys added:** `m365_sched_add`, `m365_sched_name`, `m365_sched_editor_new`,
`m365_sched_editor_edit`, `m365_sched_name_required`, `m365_sched_no_runs`,
`btn_cancel` (da/en/de).

---

## [1.5.3] — 2026-03-27

### Added — Suggestion #19: Scheduled / automatic scans

In-process scheduler using APScheduler so GDPR scans run automatically on a
configurable cadence — no cron or Task Scheduler setup required.

**Backend:**
- New `scheduler.py` module wrapping APScheduler `BackgroundScheduler` with a
  single coalescing job; misfire grace time 1 hour.
- Config stored in `~/.m365_scanner_schedule.json` (daily/weekly/monthly,
  time-of-day, profile selector, auto-email, auto-retention).
- Run history persisted in new `schedule_runs` DB table (migration #7).
- `routes/scheduler.py` blueprint — `GET/POST /api/scheduler/config`,
  `GET /api/scheduler/status`, `POST /api/scheduler/run_now`,
  `GET /api/scheduler/history`.
- Scheduler starts automatically on `app.run`; status printed at boot.
- Scheduled scans reuse the full `run_scan()` pipeline (checkpoints, delta,
  broadcast, DB) — identical to interactive scans.
- Auto-email sends the Excel report via Graph or SMTP after each scheduled scan.
- Auto-retention optionally enforces the retention policy on overdue items.

**UI:**
- **Settings → Scheduler** tab — enable/disable toggle, frequency picker
  (daily/weekly/monthly), time-of-day, profile selector, auto-email and
  auto-retention toggles, status display, run history, "Run now" button.
- **Sidebar** — 🕐 next-scan indicator near the settings button; click to
  open scheduler config. Polls every 60 s.
- **Scan log** — scheduled scans appear with 🕐 prefix via SSE events
  (`scheduler_started`, `scheduler_done`, `scheduler_error`).

**Build / deps:**
- `APScheduler>=3.10` added to `requirements.txt`.
- `scheduler.py` and APScheduler hidden imports added to `build_m365.py`.
- Schedule config added to `--purge` cleanup list.
- Lang keys added for DA / EN / DE.

---

## [1.5.2] — 2026-03-27

### Fixed — File/SMB scan: image-only PDFs no longer hang the scanner

`scan_pdf()` in `document_scanner` launches Tesseract OCR and Poppler subprocesses
when a PDF has no text layer. These subprocesses cannot be killed from a Python thread,
causing the scanner to hang indefinitely on scanned documents (e.g. ESTA applications,
invoice scans).

**Fix:** Before calling `scan_pdf()`, `_scan_bytes()` now opens the PDF with `pdfplumber`
(pure Python, no subprocesses) and checks whether any page has a text layer using the
existing `is_text_page()` helper. If all pages are image-only, the file is skipped
immediately with no CPR hits — which is correct, since machine-readable CPR numbers
cannot exist in an image-only PDF.

Text-layer PDFs (the majority) pass the check and are scanned normally. Only image-only
PDFs (scanned documents) are skipped.

This replaces multiple failed approaches (`ThreadPoolExecutor` timeouts,
`shutdown(wait=False)`, extension-based skipping) that either blocked on context manager
exit or removed legitimate file types from scanning.

### Fixed — SMB scanning: multiple smbprotocol 1.14+ API changes

See v1.5.1 for details. Additional fix in this release:

- `smb_host` is now auto-derived from the path (`//host/share` → `host`) when not
  explicitly stored in the source JSON, so SMB sources saved without an explicit host
  field still connect correctly.

### Fixed — Routes blueprint: globals resolved lazily to prevent circular imports

Each route blueprint (`routes/*.py`) now uses Python's module `__getattr__` hook to
lazily resolve globals from `m365_scanner` at call time, not at import time. This
prevents the circular import that caused double blueprint registration on startup.

### Added — File source Edit button

See v1.5.1.

---

## [1.5.1] — 2026-03-27

### Fixed — SMB scanning: multiple smbprotocol 1.14+ API incompatibilities

Several functions in `file_scanner.py` used deprecated or renamed smbprotocol APIs:

- **`uuid4_str()` removed** — `Connection()` now requires a `uuid.UUID` object, not a string. Changed to `uuid.uuid4()` directly; added `import uuid` at module level.
- **`RequestedOpcodes` removed from `smbprotocol.open`** — was imported but never used; removed.
- **`FilePipePrinterAccessMask.FILE_LIST_DIRECTORY` → `DirectoryAccessMask.FILE_LIST_DIRECTORY`** — directory listing requires `DirectoryAccessMask`, not the file/pipe mask.
- **`FileDirectoryInformation` moved** — from `smbprotocol.query_info` to `smbprotocol.file_info`; import updated.
- **`FileInformationClass` enum** — `query_directory()` expects `FileInformationClass.FILE_DIRECTORY_INFORMATION` (int enum), not a class instance.
- **`query_directory()` kwargs renamed** — `file_name=` → `pattern=`, `output_buffer_length=` → `max_output=`.
- **Filename bytes** — `file_name` field now returns UTF-16-LE bytes; decoded to str with error handling.
- **`smb_host` auto-derivation** — if `smb_host` is not explicitly stored in the source JSON, it is now extracted from the path (`//host/share` → `host`). `is_smb` no longer requires `smb_host` to be pre-set.

### Fixed — SMB scanning: junk directories skipped

Added `SKIP_DIRS` constant — a set of folder names silently skipped in both local and SMB walks:

```
.recycle  .recycler  $recycle.bin  .trash  .trashes
.sync  .btsync  .syncthing
.git  .svn  .hg
__pycache__  node_modules
.spotlight-v100  .fseventsd  .temporaryitems
system volume information  lost+found
```

Local walker prunes these from `_dirs[:]` before `os.walk` descends. SMB walker checks before recursing. Hidden directories (`.` prefix) are also skipped in both.

`STATUS_END_OF_FILE` errors (zero-byte placeholder files from Bittorrent Sync, `.sync/stream_test.txt` etc.) are now silently skipped instead of logged as warnings.

### Fixed — SMB/local file scans: OCR disabled, per-file timeout added

PDF scanning via `document_scanner.scan_pdf()` would trigger Tesseract OCR on image-based PDFs (scanned forms, photos) causing single files to hang for minutes.

**`_scan_bytes_timeout()`** — new wrapper around `_scan_bytes` using `ThreadPoolExecutor` with a 30-second deadline per file. Timed-out files are logged as errors and scanning continues.

**`skip_ocr=True`** — file scan loop now passes `skip_ocr=True` to `_scan_bytes`, disabling OCR and reducing DPI to 150. Only the text layer is extracted from PDFs. This is appropriate for bulk compliance scanning where image-only PDFs rarely contain machine-readable CPR numbers.

### Added — File source Edit button

Each file source row in **⚙ Sources → File sources** now has an **✏ Edit** button between Scan and Delete. Clicking it pre-fills the add form with the existing name, path, SMB host, and username (password shown as placeholder dots). Saving with an existing ID updates the source in-place. The Add button label changes to **Save changes** while editing and reverts on save.

---

## [1.5.0] — 2026-03-27

### Refactor — HTML template and JavaScript extracted from m365_scanner.py

`m365_scanner.py` was a ~9600-line monolith containing HTML, CSS, JavaScript,
and Python all in one string. This made frontend edits unsafe (no linting,
no syntax highlighting, string escaping hazards) and diffs unreadable.

**What changed:**

- `templates/index.html` — the full HTML/CSS template (1418 lines), served via
  Flask's `render_template()` with two Jinja2 variables: `app_version` and
  `lang_json`
- `static/app.js` — all JavaScript (2832 lines), served by Flask's built-in
  static file handler at `/static/app.js`
- `m365_scanner.py` — reduced from 9586 to 5334 lines (44% smaller);
  now contains only Python: business logic, API routes, and configuration

**Flask configuration updated:**

```python
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
```

`BASE_DIR` resolves to `sys._MEIPASS` when running as a PyInstaller bundle,
or to the directory containing `m365_scanner.py` otherwise — the same pattern
already used for `lang/`, `keywords/`, and `classification/`.

**Build script updated:**

`build_m365.py` now bundles `templates/` and `static/` alongside the existing
`lang/`, `keywords/`, and `classification/` directories.

**Zero behaviour change** — the app works identically. Only the file organisation changed.

---

## [1.5.0] — 2026-03-27

### Refactor — HTML template and JavaScript extracted from m365_scanner.py

`m365_scanner.py` was a ~9600-line monolith containing HTML, CSS, JavaScript,
and Python all in one string. This makes frontend edits unsafe (no linting,
no syntax highlighting, string-escaping hazards) and diffs unreadable.

**New files:**

- `templates/index.html` — full HTML/CSS template (1452 lines) served via
  Flask `render_template()`. Two Jinja2 variables: `{{ app_version }}` and
  `{{ lang_json | safe }}`.
- `static/app.js` — all JavaScript (2832 lines) served by Flask's built-in
  static file handler at `/static/app.js`.

**Flask app updated:**

```python
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
```

`BASE_DIR` resolves to `sys._MEIPASS` when running as a PyInstaller bundle,
or the directory of `m365_scanner.py` otherwise — the same pattern already
used for `lang/`, `keywords/`, and `classification/`. `build_m365.py` updated to bundle
both new directories.

**Result:** `m365_scanner.py` reduced from 9586 to ~2100 lines of pure Python.
Zero behaviour change.

### Refactor — Routes split into Flask Blueprints

All 55 API routes extracted from `m365_scanner.py` into a `routes/` package.
Shared mutable state lives in `routes/state.py`; blueprints import from there
to avoid circular imports.

```
routes/
  __init__.py       package marker
  state.py          shared globals: connector, flagged_items, LANG, …
  auth.py           /api/auth/*                           174 lines
  users.py          /api/users/* + role overrides         222 lines
  scan.py           /api/scan/* + /api/settings/*         123 lines
  sources.py        /api/file_sources/* + /api/file_scan   93 lines
  profiles.py       /api/profiles/*                        48 lines
  email.py          /api/smtp/* + /api/send_report        210 lines
  database.py       /api/db/* + /api/admin/* + preview    536 lines
  export.py         Excel + Art.30 export + bulk delete  1177 lines
  app_routes.py     /api/about + /api/langs + /api/lang    67 lines
```

### Housekeeping — Document Scanner files removed

The following files belonged to the standalone Document Scanner product and
have been removed from this repository:

- `server.py` — Document Scanner web app
- `scanner_worker.py` — Document Scanner process-pool worker
- `build.py` — Document Scanner build script
- `build_app.sh` — Document Scanner shell build script
- `Dockerfile` — Document Scanner Docker image
- `docker-compose.yml` — Document Scanner Docker Compose file
- `doc_scanner_icon.png` — Document Scanner app icon

`requirements.txt` rewritten for the M365 Scanner only. Removed
`pdf2image`, `pytesseract`, `pypdf`, `reportlab`, `img2pdf`, and `py7zr`
(Document Scanner dependencies). Added `cryptography>=42.0` (SMTP password
encryption, already in use since v1.4.7).

---

## [1.4.8] — 2026-03-27

### Changed — Email: Microsoft Graph API preferred over SMTP

Both **Test** and **Send now** now try the Microsoft Graph API first when the
scanner is authenticated to Microsoft 365. This avoids SMTP AUTH entirely —
no port 587, no app password, no admin centre changes needed.

**New `_send_email_graph()` helper** — sends via `/me/sendMail` (delegated mode)
or `/users/{sender}/sendMail` (app mode). Supports optional Excel attachment for
the full report. Requires the `Mail.Send` Graph permission on the Azure app
registration (Application or Delegated, depending on auth mode).

**Priority order:**
1. **Microsoft Graph API** — used when connected to M365
2. **SMTP** — fallback if not connected or Graph fails

**Error surfacing** — Graph permission errors (403 / Forbidden / Mail.Send /
insufficient privileges) are now returned directly with a clear actionable
message: add `Mail.Send` permission to the Azure app registration and grant
admin consent. Previously the error was silently swallowed and the scanner
fell through to SMTP, masking the real problem.

**SMTP AUTH error** — if SMTP is used and Microsoft 365 returns error 530 5.7.57
("Client not authenticated"), the error message now includes a plain-English tip
explaining how to enable SMTP AUTH in the M365 admin centre, or how to use Graph
instead.

### Changed — Test button sends a real email to configured recipients

The SMTP **Test** button previously only verified connectivity (EHLO/STARTTLS
handshake). It now sends an actual HTML test email to the configured recipients,
making it easy to verify end-to-end delivery including spam filtering.

---

## [1.4.7] — 2026-03-27

### Security — SMTP password encrypted at rest

Previously the SMTP password was stored as plaintext in `~/.m365_scanner_smtp.json`.
It is now encrypted using **Fernet symmetric encryption** (`cryptography` library,
already a dependency).

**Implementation:**
- A random Fernet key is generated on first use and saved to
  `~/.m365_scanner_machine_id` (chmod 0o600 — owner-readable only)
- Passwords are stored as `enc:<ciphertext>` in the JSON file
- `_encrypt_password()` / `_decrypt_password()` handle the encode/decode cycle
- `_load_smtp_config()` transparently decrypts on load; `_save_smtp_config()`
  encrypts on save
- **Legacy plaintext passwords** (no `enc:` prefix) are read as-is and
  re-encrypted next time settings are saved — no migration step required
- Encrypted blobs are **machine-specific** — the ciphertext cannot be decrypted
  on another machine without the key file
- Graceful fallback to plaintext if `cryptography` is unavailable (rare)
- The GET `/api/smtp/config` endpoint never returns the password to the browser;
  it returns only `has_password: true/false`

### Fixed — EXIF `has_pii` false positives on screenshots

`_EXIF_PII_TAGS` previously included `HostComputer`, `DocumentName`, and `PageName`.
These are set automatically by macOS/Windows on every screenshot (machine name, app
name) and contain no personal data about an individual. Removed from the tag set.

Minimum content length of 3 characters added — a field must contain at least 3
non-whitespace characters to trigger a `has_pii` flag. Prevents empty or
single-character values from causing false positives.

**Affected fields retained:** `Artist`, `Copyright`, `ImageDescription`,
`UserComment`, `XPAuthor`, `XPSubject`, `XPComment`, `XPKeywords` — all fields
a human would deliberately fill with personal information.

### Fixed — Accounts section not greyed out when switching to a file-only profile

`_applyProfile()` restores source checkboxes but did not call
`_updateAccountsVisibility()` afterwards. Switching to a profile with no M365
sources selected left the accounts section fully interactive. Fixed by calling
`_updateAccountsVisibility()` immediately after the checkbox restore loop.

---

## [1.4.6] — 2026-03-27

### Changed — Excel export updated for EXIF, GPS, and file sources

**New columns in all source sheets:**
- **GPS** — ✔ tick when GPS coordinates are present in the item's EXIF data
- **EXIF author** — author/artist name extracted from EXIF metadata
- Special category column now filters out `gps_location` and `exif_pii` (represented by the dedicated GPS column instead)

**New source types in `SOURCE_MAP`:**
- `local` — 📁 Local (green tab), for files from local folder scans
- `smb` — 🌐 Network (blue tab), for files from SMB/CIFS network shares
- Both get their own sheet when results exist; skipped silently if empty

**Summary sheet:**
- Row 4: "Items with GPS data" count (shown only when non-zero)
- Summary table shifted to row 7 to accommodate (was row 6)
- Source rows now skipped when a source has zero items

**New GPS locations sheet:**
- Teal tab — created only when GPS items exist
- Columns: Name, Latitude, Longitude, Maps link (blue hyperlink), Account, Date Modified
- Auto-filter enabled; alternating row colours

**Bug fix:** dead old function body (164 lines after the `return`) removed — the previous `str_replace` only replaced the docstring, leaving unreachable code in the file.

---

## [1.4.5] — 2026-03-26

### Fixed — `_detect_photo_faces` missing after EXIF insertion

The `str_replace` that added `_extract_exif()` accidentally consumed the
`def _detect_photo_faces` function definition (it was part of the replaced
string). All image scans raised `NameError: name '_detect_photo_faces' is not
defined`. Function restored at its original position before `_scan_bytes()`.

### Fixed — Progress bar shows "undefined / undefined" during file scans

The M365 `scan_progress` SSE event sends `{index, total, pct, file, eta}`.
The file scanner sent only `{scanned, flagged}`. The JS handler blindly read
`d.index` and `d.total`, producing `undefined / undefined`.

**Fixes:**
- `run_file_scan()` now broadcasts `{scanned, flagged, file, pct}` so the
  current filename and a progress indicator are shown while scanning.
- The `scan_progress` JS handler now checks which fields are present and
  renders accordingly: `index / total` for M365 scans, `N · M flagged` for
  file scans.

### Fixed — Local file preview: PDF, XLSX, DOCX now render content

`/api/preview/<id>` for `source_type=local` previously showed only a metadata
placeholder for PDF and Office files. Now:

| Type | Preview |
|---|---|
| PDF | First 5 pages extracted via `pdfplumber`, CPR numbers highlighted in red |
| XLSX / XLSM | First 50 rows of up to 3 sheets as a styled table |
| CSV | First 50 rows as a table |
| DOCX / DOC | First 80 paragraphs as text, CPR numbers highlighted |

All fall back to a metadata card if the library is unavailable or the file
cannot be parsed. `document_scanner` (already imported) provides access to
`pdfplumber` and `openpyxl`.

---

## [1.4.4] — 2026-03-26

### Added — #18 EXIF metadata extraction from images

**New function `_extract_exif(content, filename)`** — extracts structured EXIF data from JPEG, PNG, TIFF, WEBP, and HEIC images using Pillow (already a dependency). No new packages required.

**Extracted fields:**
- **GPS coordinates** — converted from DMS rational values to decimal degrees; Google Maps link generated
- **Author / Artist / Copyright / Description / UserComment / Keywords** — checked for PII content
- **Device** — camera make and model
- **Datetime** — DateTimeOriginal or DateTime

**Behaviour changes:**
- EXIF extraction runs on all scanned images regardless of the "Scan photos" toggle — it is lightweight (no CV processing) and always relevant
- Images with GPS or PII-bearing EXIF fields are flagged even without CPR hits
- `special_category` gains `"gps_location"` and/or `"exif_pii"` entries as appropriate
- Face detection (`_detect_photo_faces`) still requires the "🖼 Scan photos for faces" opt-in

**UI:**
- **🌍 GPS badge** — teal pill on result cards (grid and list view) when GPS coordinates are present
- **Preview panel** — local image previews now show a collapsible "EXIF data" section beneath the image with GPS (clickable Google Maps link), author, date, device, and any other PII-bearing fields

**Applies to both M365 and file system scans** — OneDrive/SharePoint images and local/SMB files go through the same extraction path.

---

## [1.4.3] — 2026-03-26

### Added — General Settings modal

Three sidebar sections (✉ Email report, 🗄 Database, and the language selector + About link) have been removed from the sidebar and consolidated into a single **⚙ Settings** modal, opened via a button in the sidebar footer.

**General tab** — language selector (mirrors the hidden `langSelect`), theme toggle, and About info (version, Python, MSAL, Requests, openpyxl versions).

**Email report tab** — full SMTP configuration (host, port, username, password, from address, STARTTLS, recipients), Save, and Send now. Pre-fills from saved config. `openSmtpModal()` now redirects to this tab for backward compatibility.

**Database tab** — DB stats (total items, flagged items, scan count), ⬇ Export, ⬆ Import, and 🗑 Reset DB. `exportDB()` and `openImportDBModal()` work unchanged.

**🔍 Data subject lookup** remains as a sidebar shortcut since it is part of the active compliance workflow.

---

## [1.4.2] — 2026-03-26

### Added — Dynamic sources panel in sidebar

The sidebar sources panel is now fully dynamic. Previously the four M365 sources (Email, OneDrive, SharePoint, Teams) were hardcoded checkboxes. Now:

- **`renderSourcesPanel()`** builds the list at runtime from `_M365_SOURCES` (the four fixed M365 entries) and `_fileSources` (saved local/SMB sources). A "File sources" group header appears automatically when any file sources are configured.
- Per-source visibility toggles in the ⚙ Sources modal (Microsoft 365 tab) control which M365 sources appear in the panel. Toggling one off removes it from the panel immediately.
- File sources added in the Sources modal appear as checkboxes in the panel alongside the M365 sources, with 📁 (local) or 🌐 (SMB) icons.
- The panel shows up to 5 rows before scrolling (`max-height: calc(5 * 26px)`).
- **Profile save/restore** — file source selections are now included when saving a profile. `buildScanPayload()` merges M365 and file source IDs into `allSources`; `_applyProfile()` restores all of them. A `_pendingProfileSources` mechanism handles the async case where file sources load after the profile is applied.

### Added — Hint tooltips on Delta scan, Scan photos, Retention policy toggles

Each of the three advanced option toggles now has a circled **?** icon to the right of the label. Clicking it shows a speech bubble (fixed-positioned, `z-index: 9999`) with the hint text, positioned to the right of the icon and visible above the main content area. Only one bubble can be open at a time; clicking anywhere outside closes it.

### Changed — ⚙ Profiles button moved to topbar

The accent-coloured **⚙ Profiles** button was removed from the Database section in the sidebar. A plain **⚙ Profiles** button (matching the style of **⚙ Sources**) now appears to the right of the 💾 save button in the topbar profile bar.

### Changed — App mode badge (modeBadge) removed

The `modeBadge` button and `userBar` div have been removed from the sidebar. Connection status and mode (App / Delegated) are now shown exclusively in the Sources modal (Microsoft 365 tab) — connection info row with green/grey status dot, display name, email, and mode label.

### Fixed — Sources modal: credentials pre-filled from saved config

`smRefreshStatus()` now calls `/api/auth/status` (correct endpoint) and pre-fills Client ID, Tenant ID, and Client Secret fields from the saved config. Connects via `/api/auth/config` + `/api/auth/start`; disconnects via `/api/auth/signout` + `signOut()`.

### Fixed — File source naming: Name field required; auto-suggest from path

The "Label" field renamed to "Name" and marked required (red asterisk). `fsrcAutoName()` suggests a name as the user types the path — last path segment for local paths, `host / share` for SMB paths. The user's own name is never overwritten once typed.

### Fixed — Sources panel fixed height with scroll

`#sourcesPanel` in the sidebar now has `max-height: calc(5 * 26px); overflow-y: auto` so it shows exactly 5 rows before scrolling, regardless of how many sources are configured.

### Fixed — Fiscal year end dropdown alignment

The "Fiscal year end" label and select were previously side-by-side, causing the label to wrap on long translations (e.g. "Regnskabsårs afslutning"). Now stacked vertically (`flex-direction: column`) with `width: 100%` on the select.

### Fixed — ⚙ cog size inconsistency between Sources and Profiles buttons

Both buttons previously used `⚙️` (U+2699 + variation selector U+FE0F), which can render at emoji size rather than text size. Replaced with plain `⚙` (U+2699) in both so they render at identical size.

### Fixed — MB label removed from max attachment size picker

The "MB" text span to the right of the attachment size number input has been removed.

### Fixed — File source selections included in profiles

`buildScanPayload()` now collects both M365 and file source IDs and merges them into `allSources`, which is saved as `profile.sources`. Previously only M365 source IDs were saved.

---

## [1.4.1] — 2026-03-26

### Added — #17 Unified source management modal

Replaced the fragmented sidebar source configuration with a single **⚙️ Sources** button above the sources panel. This opens a tabbed modal:

**Microsoft 365 tab:** Azure credentials (Client ID, Tenant ID, Client Secret) moved from the auth screen into the modal — can be updated or cleared post-connect. Per-source toggles (Email, OneDrive, SharePoint, Teams) control which sources appear in the sidebar panel. Disconnect button signs out without leaving the page.

**Google Workspace tab:** Stub with "Coming soon" — placeholder for Gmail and Google Drive when implemented.

**File sources tab:** Full file source management (list, add, delete, scan) moved from the standalone "📁 File sources" sidebar row into this tab. The separate sidebar row is removed.

**Sidebar change:** The "📁 File sources" sidebar section is removed. The sources panel now has a compact **⚙️ Sources** button in its header row. The panel itself respects the per-source visibility toggles set in the modal — if a user disables OneDrive, it disappears from the panel immediately.

**Backward compatibility:** `openFileSourcesModal()` redirects to `openSourcesMgmt('files')` so any existing call sites continue to work.

---

## [1.4.0] — 2026-03-26

### Added — #8 File system scanning (local folders and SMB/CIFS network shares)

**New file: `file_scanner.py`** — unified local + network file iterator.

`FileScanner.iter_files()` yields `(relative_path, bytes, metadata)` regardless
of whether the source is a local path or a network share. All CPR scanning, card
streaming, and DB persistence stay in `m365_scanner.py` — `file_scanner.py` only
handles how files are accessed.

**Local scanning** uses `os.walk()` on any path (workstation, USB drive, or
already-mounted network share). **SMB/CIFS scanning** uses `smbprotocol` directly
without requiring a mount — supports SMB2/3 with NTLM or domain credentials.
`smbprotocol` is optional: if not installed, the scanner falls back to local-only
mode with a logged warning.

**Credential storage priority (SMB):**
1. OS keychain via `keyring` (recommended — password never touches the filesystem)
2. `NAS_PASSWORD` environment variable
3. `.env` file (chmod 600) via `python-dotenv`

Both optional dependencies (`smbprotocol`, `keyring`, `python-dotenv`) are added
to `requirements.txt` as opt-in extras.

**Results** write to the same SQLite DB as M365 items with
`source_type = "local"` or `"smb"`, so the Article 30 report and data subject
lookup cover all sources in a single view. File/network cards use 📁 and 🌐
source badges respectively.

**UI — 📁 File sources sidebar section:**

- **Manage button** → opens the File Sources modal
- **Add source form** — label, path; SMB fields (host, user, password) appear
  automatically when the path starts with `//` or `\`; host is auto-filled from
  the path
- **Per-source ▶ Scan button** — starts a scan immediately; results stream into
  the main grid via SSE exactly like an M365 scan
- **Delete** — removes a source definition (does not affect scan results already
  in the DB)
- Sources persist in `~/.m365_scanner_file_sources.json`

**New API routes:**

| Route | Method | Description |
|---|---|---|
| `/api/file_sources` | GET | List all file source definitions |
| `/api/file_sources/save` | POST | Add or update a source |
| `/api/file_sources/delete` | POST | Remove a source by id |
| `/api/file_sources/store_creds` | POST | Store SMB password in OS keychain |
| `/api/file_scan/start` | POST | Start a file scan (non-blocking) |

**New CLI flags:**

```bash
# Scan a local folder
python m365_scanner.py --scan-path ~/Documents

# Scan an SMB share (password from OS keychain)
python m365_scanner.py --scan-path //nas.school.dk/shares \
  --smb-user "DOMAIN\\henrik" --smb-keychain-key gdpr-scanner-nas

# One-time credential storage
python m365_scanner.py --smb-store-creds --smb-host nas.school.dk \
  --smb-user "DOMAIN\\henrik"

# With photo scanning and file size limit
python m365_scanner.py --scan-path //nas/staff --scan-photos --max-file-mb 100
```

**`build_m365.py`** — `file_scanner.py` added to PyInstaller datas bundle.

---

## [1.3.11] — 2026-03-26

### Fixed — Face detection: excessive false positives on background elements

Haar cascade detection with `minNeighbors=5` and `min_size=40px` was triggering
on background textures, bottle labels, artwork, and out-of-focus persons,
reporting up to 16 faces for a photo containing 1–2 actual subjects.

**Changes in `_detect_photo_faces()` (`m365_scanner.py`):**

- `min_size` raised **40 → 80 px** — eliminates detections on small background
  features; out-of-focus background persons and objects are too small in pixels
  to exceed this threshold
- `minNeighbors` raised **5 → 8** — each candidate region must be confirmed by
  8 overlapping scale-pyramid detections instead of 5; random texture patterns
  rarely survive this many confirmations

If over-detection persists on a specific image, `minNeighbors=10` and
`min_size=100` are reasonable next steps before genuine faces are missed.

### Fixed — Result cards: replaced 👤 + separate role-pill with unified role icon

The account-pill (showing the owner's display name) previously prepended a
static `👤` via CSS `::before` and rendered a separate `role-pill` span
(🎓/👔) alongside it. Both elements have been merged: the account-pill now
prefixes the display name directly with the role icon — **🎓 name** for
students, **👔 name** for staff, **👤 name** for unclassified — removing the
redundant separate badge and saving horizontal space in both grid and list view.

---

## [1.3.10] — 2026-03-26

### Changed — Role classification: fragment-first, ID-second

**Motivation:** Microsoft has reissued new UUIDs for the same licence multiple
times over the past 5–6 years (EA → A1/A3/A5 → new commerce/CSP → benefit
variants). `skuPartNumber` strings like `STANDARDWOFFPACK_FACULTY` have been
stable across all those generations while UUIDs change with every new issuance.

**New `classify_user_role()` order:**

1. **Fragment match on `skuPartNumber`** (runs first when `sku_map` available) — staff fragments checked before student across all licences, so a `STUDENT_BENEFIT` add-on cannot mask a `FACULTY` licence.
2. **SKU ID lookup from `m365_skus.json`** — fallback when `sku_map` is empty or when a licence has no recognisable fragment (e.g. Power Automate Free assigned to faculty).

Any future Microsoft SKU re-issuance is classified correctly without updating `m365_skus.json`, as long as the part number still contains `FACULTY` or `STUDENT`.

### Fixed — `m365_skus.json`: added two missing faculty SKUs

- `c2273bd0-dff7-4215-9ef5-2c7bcfb06425` — Microsoft 365 Apps for Faculty (primary licence at Gudenåskolen, absent from all previous versions)
- `f30db892-07e9-47e9-837c-80727f46fd3d` — relabelled Microsoft Power Automate Free (assigned to faculty)

---

## [1.3.9] — 2026-03-26

### Fixed — `m365_skus.json` not deployed; `build_sku_map_from_users` sampled wrong users

**File missing:** `m365_skus.json` was never copied into `classification/` on disk. `_load_sku_data()` fell back to empty sets (`staff_ids_count: 0`). Students still classified via `STUDENT` fragment; staff always `"other"`. Fix: file now shipped. Place in `GDPRScanner/classification/m365_skus.json`.

**Wrong sample:** `build_sku_map_from_users` took the first 20 alphabetical users — all students at Gudenåskolen — so it never fetched a staff part number. Fixed to sample evenly across the full list and always include the last 5 users.

---

## [1.3.8] — 2026-03-26

### Fixed — `m365_skus.json` not found in PyInstaller bundle; `🔍` SKU debug modal

`_SKU_FILE = Path(__file__).parent / ...` evaluated at class-definition time, before `sys._MEIPASS` is set in a frozen build. Replaced with `_sku_file_path()` classmethod that checks `_MEIPASS` at call time.

Added 🔍 SKU debug button to the accounts panel role-filter row. Opens a modal showing every tenant SKU ID colour-coded as 🎓 student / 👔 staff / ❓ unknown, with selectable text for pasting unknowns into `m365_skus.json`.

`/api/users/license_debug` extended: now returns `student_ids`, `staff_ids`, `runtime` block (set sizes, fragment lists, file path, sku_map entry count), and per-licence `in_staff`/`in_student`/`frag_staff`/`frag_student` trace for every user — sufficient to diagnose any classification failure without reading server logs.

---

## [1.3.7] — 2026-03-26

### Fixed — `license_debug` extended for full runtime diagnostics

`/api/users/license_debug` rewritten to expose all runtime state: `staff_ids_count`, `student_ids_count`, fragment lists, `sku_file_path`, `sku_map_entries`, and a step-by-step per-licence classification trace for every user (`in_staff`, `in_student`, `frag_staff`, `frag_student`, `skuName`).

---

## [1.3.6] — 2026-03-26

### Fixed — Staff misclassified as student: two-pass classify_user_role

**Root cause:** `f30db892-07e9-47e9-837c-80727f46fd3d` is a Microsoft *Student
Use Benefit* add-on that Microsoft automatically assigns alongside faculty
licences in Education tenants. Its `skuPartNumber` contains `"STUDENT"`. Because
the old single-pass loop checked student and staff in per-licence order, the
fragment match on this add-on fired before the authoritative faculty ID
(`94763226`) was ever reached, returning `"student"` instead of `"staff"`.

**Fix — `classify_user_role()` now uses a strict two-pass approach:**

**Pass 1 — authoritative ID match (m365_skus.json), staff before student:**
All licences are scanned for staff IDs first, then student IDs. A single faculty
SKU ID anywhere in the licence list wins regardless of what other add-on licences
appear before it.

**Pass 2 — skuPartNumber fragment match, staff before student:**
Only reached if no ID match was found. Staff fragments are checked across every
licence before student fragments — preventing a `STUDENT_BENEFIT` add-on from
masking a `FACULTY` licence later in the list.

**Result:** A staff member holding `[STUDENT_BENEFIT_ADDON, FACULTY_A1, STUDENT_DEVICE]`
is now correctly classified as `"staff"` in all cases, whether `sku_map` is
populated or not.

---

## [1.3.5] — 2026-03-26

### Fixed — Staff not recognised: always merge per-user SKU map

**Root cause:** `build_sku_map_from_users()` (which calls `/users/{id}/licenseDetails`
for up to 20 sampled users) was only called when `sku_map` was completely empty.
In practice `get_subscribed_skus()` tier 2 (`/me/licenseDetails`) always succeeds
in delegated mode, returning the signed-in admin's own license — making `sku_map`
non-empty and silently skipping the per-user sampling.

If the admin's license happened to be a faculty A1 and other staff held A3 or an
unlisted variant, those A3 users were never added to `sku_map` and fragment
matching could not fire for them, leaving them as `"other"`.

**Fix:** `build_sku_map_from_users()` is now **always called** and its results
**merged** into `sku_map`, regardless of whether `get_subscribed_skus()` already
returned entries. This guarantees that every distinct SKU ID actually in use by
any of the first 20 users gets a `skuPartNumber` entry, enabling fragment matching
for all staff variants — including those not yet listed in `m365_skus.json`.

Same merge applied in `license_debug` so the 🔍 modal also sees complete data.

---

## [1.3.4] — 2026-03-26

### Fixed — Role classification: three-tier SKU map fallback

**Root cause:** `get_subscribed_skus()` requires `Directory.Read.All` or
`Organization.Read.All`. If the Azure app registration does not have that
permission (typical delegated/device-code setups), it silently returned `{}`
and the fragment fallback never ran, leaving every user as `"other"`.

**Fix — `get_subscribed_skus()` now tries three endpoints in order:**

| Tier | Endpoint | Permission needed |
|---|---|---|
| 1 | `/subscribedSkus` | Directory.Read.All (admin) |
| 2 | `/me/licenseDetails` | User.Read only |
| 3 | `build_sku_map_from_users()` via `/users/{id}/licenseDetails` (up to 20 users) | User.Read.All |

Each tier logs how many SKU entries it found. Tier 2 always works in delegated
mode and covers the signed-in user's licenses. Tier 3 covers all distinct SKUs
used in the tenant by sampling up to 20 users. If any tier returns results, the
others are skipped.

**UI warning banner** — when every fetched user resolves to `"other"`, a red
banner appears above the accounts list: *"No users classified — click 🔍 to
diagnose."*  It disappears automatically once classification succeeds.

---

## [1.3.3] — 2026-03-26

### Fixed — Role classification: SKU debug modal + path resolution

**Problem:** Even with `classification/m365_skus.json` loading correctly, users showed as
unclassified because the tenant's actual SKU IDs were not in the file. There was
no easy way to discover which IDs to add.

**Changes:**

- **🔍 SKU debug button** — a small magnifying-glass button added to the role
  filter row (next to 🎓 Elev). Clicking it opens a modal that calls
  `GET /api/users/license_debug` and lists every unique SKU ID in the tenant,
  colour-coded: `🎓 student` / `👔 staff` / `❓ unknown`. Unknown IDs can be
  selected and copied directly into `classification/m365_skus.json`.

- **`/api/users/license_debug`** extended — now also returns `student_ids` and
  `staff_ids` arrays from the loaded SKU file so the frontend can mark each
  tenant SKU as known or unknown without a second round-trip.

- **`_sku_file_path()` classmethod** — replaced the static `_SKU_FILE` class
  attribute with a method that checks `sys._MEIPASS` first (PyInstaller bundle)
  then falls back to `Path(__file__).parent / "skus" / "m365_skus.json"`.
  The static attribute evaluated at class-definition time before `_MEIPASS` was
  set, causing the frozen app to look in the wrong directory.

- **Server-side warning** — `GET /api/users` now logs a `WARNING` to stdout
  when 0 out of N users are classified, including a sample of the unrecognised
  SKU IDs seen in the first 20 users.

- **Translated** — EN / DA / DE (3 new keys)

---

## [1.3.2] — 2026-03-26

### Fixed — Student/Staff misclassification: incomplete SKU lists + no override (#1.3.2)

**Root cause:** The hardcoded SKU lists introduced in v1.0.0 covered only ~8 student
and 6 staff SKUs. Microsoft publishes 100+ Education SKU IDs; any tenant using a SKU
not in those lists silently fell through to `"other"`, leaving users unclassified
or relying solely on the `skuPartNumber` fragment fallback — which itself was too
specific (`STANDARDWOFFPACK_STUDENT` instead of just `STUDENT`).

#### `m365_connector.py` — Expanded SKU lists and broader fragment matching

**Student set** expanded from 8 → 12 SKUs:
- Added `46c119d4` (M365 A1 for Students — student use benefit)
- Added `8fc2205d` (O365 A5 for Students)
- Added `160d616a` (O365 A3 for Students device)
- Added `a4e376bd` (M365 A1 for Students new commerce)

**Staff set** expanded from 6 → 9 SKUs:
- Added `2d61d025` (M365 A1 for Faculty — faculty use benefit)
- Added `15b1d32e` (O365 A3 for Faculty device)
- Added `ba04c29e` (M365 A1 for Faculty new commerce)

**Fragment patterns** broadened — `"STUDENT"` and `"FACULTY"` now catch all
part-number variants (`_STUDENT`, `STUDENT_`, `STUDENT_BENEFIT`, `_FAC`, etc.)
without needing to enumerate every Microsoft naming permutation.

#### `m365_scanner.py` — Manual role overrides

Because no SKU list can ever be complete, admins can now correct individual users
directly from the accounts panel:

- **🎓/👔/❓ role badge** on every user row — click to cycle:
  `auto → student → staff → other → (clear, back to auto)`
- Overridden rows show the badge in accent colour with a **✎** indicator
- Overrides persisted to `~/.m365_scanner_role_overrides.json` — survive
  restarts and re-authentication
- Applied at both display time (`/api/users`) and scan time (`_user_role_map`)
  so card badges, filter buttons, Excel Role column, and Article 30 inventory
  split all reflect the corrected role
- `GET /api/users/role_override` — returns all current overrides
- `POST /api/users/role_override` — sets or clears one override
- Override file added to `--purge` file list
- Translated — EN / DA / DE (3 new keys)

---

## [1.3.1] — 2026-03-26

### Fixed — Student/Staff role misclassification (`m365_connector.py`)

Two SKU ID collisions in `_STUDENT_SKU_IDS` / `_STAFF_SKU_IDS` caused Faculty
users to be shown as Students (and vice versa) for any tenant using A5 or A3
Education licenses:

| SKU ID | Correct role | Bug |
|---|---|---|
| `e578b273-6db4-4691-bba0-8d691f4da603` | Staff (M365 Education A5 for Faculty) | Was also in `_STUDENT_SKU_IDS` as "O365 A5 for Students" — Faculty A5 users always showed as 🎓 Student |
| `78e66a63-337a-4a9a-8959-41c6654dfb56` | Student (Office 365 A3 for Students) | Was also in `_STAFF_SKU_IDS` as "M365 A1 for Faculty (device)" — this had no effect because student is checked first, but the comment was wrong and the duplicate entry was confusing |

`classify_user_role()` checks student first, so any overlap resolves to student,
silently misclassifying all affected Faculty accounts.

**Fix:** removed `e578b273` from `_STUDENT_SKU_IDS` and `78e66a63` from
`_STAFF_SKU_IDS`. Also removed a stale duplicate of `e578b273` that appeared
twice in `_STAFF_SKU_IDS`. Added a `RuntimeWarning` guard inside
`classify_user_role()` that logs any future collision between the two sets.

**Impact:** Article 30 staff/student inventory split, role filter buttons (👔 / 🎓),
role badges on cards, and Excel Role column are all now correct for A5 and A3
Education tenants.

**Workaround until update:** use `GET /api/users/license_debug` to see the raw
SKU IDs and current classification for each user.

---

## [1.3.0] — 2026-03-26

### Added — Biometric photo scanning (#9)

**GDPR reference:** Article 9 (special categories — biometric data), Article 5(1)(b)(e), Recital 38, Databeskyttelsesloven §6

- **`PHOTO_EXTS`** — new constant covering `.jpg .jpeg .png .bmp .tiff .tif .webp .heic .heif`
- **`_detect_photo_faces(content, filename)`** — calls `ds._get_cv2()` + `ds.detect_faces_cv2()` (already in `document_scanner.py`); PIL fallback for HEIC/HEIF; `minNeighbors=5` for conservative detection; returns face count or 0 on any failure; entirely safe — exceptions swallowed silently
- **`scan_photos` option** — new boolean scan option (default `False` — opt-in); extracted from `scan_opts` alongside `delta` and `email_body`
- **`🖼 Scan photos for faces` toggle** in the Options panel, with hint: "Slower — opt in"
- **Photo items flagged even without CPRs** — a file is added to results if `face_count > 0`, even if no CPR number is found; photographs of identifiable people are Art. 9 data regardless of CPR content
- **`"biometric"` auto-injected** into `special_category` when faces are detected and `"biometric"` is not already present
- **`face_count`** field added to card payload, DB, Excel, and Article 30 report

**DB (migration #4):**
- `face_count INTEGER NOT NULL DEFAULT 0` added to `flagged_items` via auto-migration
- `save_item()` updated to persist `face_count`

**UI:**
- **`📷 N faces` badge** — teal `photo-face-badge` pill shown on cards in both grid and list view when `face_count > 0`
- **`📷 Photos / biometric` filter** added to the Special dropdown in the filter bar; `applyFilters()` handles `specialVal === 'photo'`
- `buildScanPayload()` includes `scan_photos`; `_applyProfile()` restores it when loading a profile

**Excel export:**
- `Face count` column added as column 3 (between CPR Hits and Special category); URL column index updated from 10 → 11 for hyperlink styling

**Article 30 report:**
- Summary section: `Photos with detected faces (Art. 9 biometric)` row with item + face count; explanatory note on legal basis and parental consent (Databeskyttelsesloven §6)
- New dedicated section: *Photographs and Biometric Data (Article 9)* — intro paragraph, 4-bullet retention guidance (purpose limitation, pupil consent, website removal, archiving), item table (name, account, source, faces, modified date), capped at 50 rows
- Methodology section: bullet added describing OpenCV Haar cascade detection

**Translated** — EN / DA / DE (16 new keys per language)

---

## [1.2.3] — 2026-03-26

### Added — Profile management modal (#15d)

- **⚙ Profiles button** in the sidebar Database row opens a modal listing all saved profiles
- **Each profile row** shows name (with ● active indicator), sources summary, description, and last run timestamp
- **Use** — loads the profile into the sidebar and updates the topbar dropdown; closes the modal
- **Edit** — expands an inline edit form directly in the row; saves name and description via `POST /api/profiles/save`
- **Duplicate** — creates a copy with a unique `(copy)` / `(copy 2)` suffix; reloads the list
- **Delete** — confirms, removes via `POST /api/profiles/delete`, clears `_activeProfileId` if the deleted profile was active
- Empty state shown when no profiles have been saved yet
- Translated — EN / DA / DE (14 new keys per language)

### Added — Database export/import UI (#11)

- **🗄 Database** sidebar section with **Export** and **Import** buttons (always visible; sits between Email report and User info)
- **Export button** — calls `GET /api/db/export`; triggers a browser download of a timestamped ZIP (`gdpr_export_YYYYMMDD_HHmmss.zip`) containing 8 JSON files; CPR hashes only, thumbnails stripped
- **Import modal** — file picker (`.zip` only), mode selector (Merge / Replace), replace warning panel, status line, and Import button; calls `POST /api/db/import` with multipart form data
- **`GET /api/db/export`** Flask route — generates ZIP in a temp file, streams bytes as `application/zip` attachment
- **`POST /api/db/import`** Flask route — accepts multipart `file`, `mode`, `confirm`; validates replace confirmation server-side; returns `{ok, mode, imported: {table: count}}`
- Translated — EN / DA / DE (17 new keys per language)

### Changed — Article 9 keyword matching compiled to regex (#13)

- `_load_keywords()` now compiles one `re.Pattern` per Article 9 category at startup using a longest-first alternation: `(?:keyword_a|keyword_b|…)` with `re.IGNORECASE`
- Short keywords (≤ 4 chars) retain `(?<!\w)…(?!\w)` word-boundary anchors to prevent substring false positives
- `_check_special_category()` uses the compiled patterns via `pattern.finditer()` instead of a sequential `str.find()` loop over up to 459 entries
- Startup log now reports compiled category count: `Loaded 459 keywords (9 categories compiled)`
- **Performance:** ~10–50× faster for large tenants; negligible difference for typical school tenants (~100 flagged items); meaningful saving at 1 000+ items

---

## [1.2.2] — 2026-03-21

### Added — Profile selector in topbar (15c)

- **Profile dropdown** in the topbar, between the Scan button and the spacer — shows "Default (sidebar)" plus all saved profiles with their last run date
- **💾 Save button** next to the dropdown — prompts for a name and saves the current sidebar state (sources, options, user selection, retention settings) as a named profile via `POST /api/profiles/save`
- **`onProfileChange()`** — fires when the dropdown changes; calls `_applyProfile()` to populate the sidebar controls from the selected profile
- **`_applyProfile(profile)`** — sets all source checkboxes, scan options, retention fields, and queues user selection for when the accounts list is loaded
- **`_applyPendingProfileUsers()`** — applies a profile's `user_ids` to the accounts list after `loadUsers()` completes; safe to call multiple times
- **`loadProfiles()`** — fetches `/api/profiles` and populates the dropdown; called on `onAuthenticated()`
- **`saveCurrentAsProfile()`** — collects the full `buildScanPayload()` state and posts it as a new or updated profile
- Profiles with a description show it as a tooltip on the dropdown option
- Selecting "Default (sidebar)" clears `_activeProfileId` so the sidebar is used directly with no profile applied
- **Translated** — EN / DA / DE (6 new keys)

---

## [1.2.1] — 2026-03-21

### Added — Scan profiles 15a + 15b

**15a — Backend profile storage**

- `_profiles_load()` — reads all profiles from `~/.m365_scanner_settings.json`
- `_profiles_write()` — atomic write of the full settings dict
- `_profile_from_settings()` — wraps a flat settings dict as a profile object
- `_profile_get(name_or_id)` — case-insensitive lookup by name or UUID
- `_profile_save(profile)` — insert or update a profile
- `_profile_delete(name_or_id)` — delete by name or UUID
- `_profile_touch(id, scan_id)` — updates `last_run` and `last_scan_id` after a successful scan
- **Automatic migration** — on first run, existing flat `~/.m365_scanner_settings.json` is silently wrapped into a profile named "Default"; no user action required
- **Legacy shim** — `_save_settings()` and `_load_settings()` continue to work unchanged; all existing headless setups are unaffected
- **Profile API routes** — `GET /api/profiles`, `POST /api/profiles/save`, `POST /api/profiles/delete`, `GET /api/profiles/get` for future UI use (15c/15d)

**15b — CLI profile support**

- `--list-profiles` — tabular listing of all profiles with name, sources, last run, and scan ID
- `--save-profile NAME` — saves current CLI options as a named profile; updates existing if name matches
- `--delete-profile NAME` — removes a profile by name
- `--profile NAME` — loads a named profile for `--headless` runs; populates sources, retention, fiscal year end, and email recipients from the profile; prints profile name, description, and last run before scanning
- After a successful headless scan, the active profile's `last_run` and `last_scan_id` are updated automatically

---

## [1.2.0] — 2026-03-20

### Added — Article 9 sensitive category detection (#3)

- **`keywords/da.json`** — 459 Danish keywords across 9 Article 9 categories: health, mental health, criminal (Art. 10), trade union, religion, ethnicity, political, biometric, and sexual orientation. Includes `_false_positive_guidance` for ambiguous terms and `_proximity_note` explaining the matching strategy
- **`keywords/` subfolder** — mirrors the `lang/` pattern; `keywords/en.json` and `keywords/de.json` can be added without code changes
- **`_load_keywords()`** — loads the keyword file at startup matching the active UI language; falls back to `da.json`
- **`_check_special_category(text, cprs)`** — returns a sorted list of matched Article 9 category keys; a keyword only triggers when within 150 characters of a CPR number (proximity filter); if no CPRs are present in the text, any keyword occurrence triggers
- **Card badge** — purple `⚠ Art.9 — health, criminal` pill on flagged cards showing all detected categories
- **Filter bar dropdown** — "All risk levels / Art. 9 special category" quick filter in the results grid
- **DB migration #3** — `special_category TEXT NOT NULL DEFAULT '[]'` added to `flagged_items` via auto-migration; stored as JSON array
- **`finish_scan()`** — counts special category items per scan and writes to `scan_history.special_category` for trend tracking
- **Excel export** — "Special category" column added as column 3 on all per-source sheets
- **Article 30 report** — special category item count and DPIA warning added to the summary section; "Art. 9" column added to the per-source breakdown table with purple highlighting on non-zero values
- **Translated** — EN / DA / DE (6 new keys per language)
- **Build scripts** — `keywords/` folder bundled into PyInstaller app alongside `lang/`
- **`.gitignore`** — `!keywords/*.json` added to prevent keyword files being excluded by the `*.json` catch-all

---

## [1.1.3] — 2026-03-20

### Fixed

- **Stray duplicate `_get_bytes` body** — dead code block left after `delete_drive_item_for_user` from a previous edit has been removed

### Changed — `m365_connector.py`

- **Split timeouts** — replaced all hardcoded `timeout=30` / `timeout=60` with two tuned constants:
  - `_TIMEOUT_API = (10, 45)` — 10s connect, 45s read for JSON API calls
  - `_TIMEOUT_BYTES = (10, 120)` — 10s connect, 120s read for file/attachment downloads
  - The 10s connect timeout makes hung connections fail fast; the read timeout allows slow wireless links to complete a transfer without aborting

- **Exponential backoff with retry** — all four core request methods (`_get`, `_post`, `_get_bytes`, `_delete`) now retry up to 4 times on transient network errors:
  - Retried: `ConnectionError`, `Timeout`, `ChunkedEncodingError`, `ReadTimeout`, HTTP 429, HTTP 503, HTTP 504
  - Not retried: HTTP 403 (permission), HTTP 410 (delta token expired) — raised immediately
  - Backoff: 2s → 4s → 8s between attempts (capped at 30s); 429 responses use the `Retry-After` header value
  - Intermittent wireless dropouts and brief gateway errors are now absorbed transparently without interrupting a scan

- **Streaming file downloads** — `_get_bytes` now uses `stream=True` and `iter_content(65536)` so large attachments are received in 64 KB chunks rather than one blocking read; prevents read timeouts on slow connections for large files

- **`list_users` inline timeout** — the `_fetch` helper inside `list_users` was using its own hardcoded `timeout=30`; updated to use `_TIMEOUT_API`

---

## [1.1.2] — 2026-03-20

### Fixed

- **App does not start after build** — `m365_db.py`, `scanner_worker.py`, and `VERSION` were missing from PyInstaller `datas` in `build_m365.py`; the app crashed immediately on launch because these files could not be found inside the bundle
- **`_read_app_version()` broken in both build scripts** — still searched for `APP_VERSION = "..."` as a string literal in the scanner source, but both scanners now read from the `VERSION` file; build scripts updated to read `VERSION` directly
- **`VERSION` not bundled** — `build.py` (Document Scanner) also missing the `VERSION` file in `datas`

### Added

- **`--purge` CLI flag** — permanently deletes all data files created by the scanner (SQLite database, Azure credentials, SMTP credentials, settings, checkpoint, delta tokens, language preference, OCR cache, MSAL token cache); prompts for `yes` confirmation; `--yes` skips prompt for scripted use
- **`--export-db FILE`** — exports the database to a structured ZIP archive containing 8 JSON files; thumbnails excluded; CPR stored as hashes only
- **`--import-db FILE`** — imports a previously exported ZIP; `--import-mode merge` (default) adds dispositions and deletion log only; `--import-mode replace` wipes and restores all tables; `--yes` skips confirmation on replace

---

## [1.1.1] — 2026-03-19

### Fixed

- **Layout collapse in light mode** — `.topbar` CSS rule was broken by an earlier edit; `border-bottom` and `background` properties were orphaned onto a dangling line, causing the topbar to render with no background and the Scan button to be nearly invisible
- **Sidebar missing** — `.layout` used `height: 100vh` which ignored `body` padding, causing the flex layout to overflow and the sidebar to disappear
- **macOS pywebview titlebar overlap** — content rendered behind the traffic-light buttons; fixed with `padding-top: 30px` on `body` when running inside pywebview on macOS, combined with `box-sizing: border-box` and `height: 100%` on `.layout`
- **`<option>` elements not translated** — `applyI18n()` used `el.innerHTML` on `<option>` elements; some browsers do not re-render the select's visible text when `innerHTML` is set on an already-mounted option; switched to `el.textContent` for option elements
- **Disposition filter dropdown not translated on load** — filter bar is hidden until first scan result arrives so `applyI18n()` on `DOMContentLoaded` missed it; `applyI18n()` is now called when the filter bar is first shown
- **Card delete button z-index** — added `z-index: 1` to `.card-delete-btn` so it stacks correctly within its card context

### Added

- **`--reset-db` CLI flag** — permanently drops and recreates all database tables; shows a summary of what will be deleted and requires typing `yes` to confirm
- **`--yes` flag** — skips confirmation prompts; use with `--reset-db` for scripted/automated resets
- **`ScanDB.reset()`** — new method in `m365_db.py` that drops all tables in correct foreign-key order, resets `user_version` to 0, and reopens the connection with a fresh schema

---

## [1.1.0] — 2026-03-19

### Added — M365 Scanner

- **Student / staff role classification** — O365 license SKU IDs used to classify users as 🎓 Student or 👔 Staff with no extra Azure permissions required. Hardcoded known Microsoft Education SKU IDs cover M365/Office 365 A1/A3/A5 for Students and Faculty. Fragment fallback for future SKUs.
- **Role filter in accounts panel** — All / 👔 Ansat / 🎓 Elev buttons filter the user list before selecting accounts to scan
- **Role badge on result cards** — 🎓/👔 pill shown on every card in grid and list view
- **`user_role` in SQLite DB** — stored in `flagged_items` table; DB migration applied automatically on first run
- **Licensed users only** — accounts without an assigned O365 license are excluded from the user list
- **Disposition filter in filter bar** — filter results grid by compliance disposition status
- **Headless auto-delete of `delete-scheduled` items** — items tagged for deletion are removed automatically after each headless scan
- **Deletion audit log** — every deletion logged to `deletion_log` table with timestamp, actor, reason, and legal basis
- **`GET /api/db/deletion_log`** — API endpoint for the deletion log
- **Deletion log in Article 30 report** — dedicated section with summary-by-reason table and full 7-column log
- **Article 30 — student/staff split** — Section 3 (Data Inventory) now shows Staff and Student tables separately; parental consent note added for student items (Databeskyttelsesloven §6)
- **`GET /api/users/license_debug`** — diagnostic endpoint showing raw SKU IDs and classified roles for each user
- **`_resolve_display_name()`** — resolves GUIDs and "Microsoft Konto" guest account placeholders to email address throughout UI and Article 30 report
- **Account name in Article 30** — resolved via `user_ids` stored in scan options; GUID no longer shown in any column
- **All Article 30 strings translated** — deletion log section now uses `L()` throughout; 19 new keys in EN/DA/DE
- **`VERSION` file** — single source of truth; both scanners read version at startup via `Path(__file__).parent / "VERSION"`
- **`CHANGELOG.md`** — release history and versioning policy
- **`SECURITY.md`** — responsible disclosure process
- **`CONTRIBUTING.md`** — development setup, code style, PR process
- **`LICENSE`** — AGPL-3.0 with commercial licensing note and GDPR disclaimer
- **`.gitignore`** — covers credentials, databases, audit logs, venv, build artefacts

### Fixed — M365 Scanner

- Language switching no longer reloads the page — translations applied in-place, scan results preserved
- Connect screen freeze — duplicate `renderAccountList` function definition caused a JavaScript syntax error that prevented `onAuthenticated()` from firing
- Account column in Article 30 report showing GUIDs — resolved via `_acct_map` built from stored `user_ids`
- "Microsoft Konto" / GUID display names on cards and in reports — resolved to email address

### Changed — M365 Scanner

- **Excel export** — 9 columns (was 7): added Account (display name), Role, and Disposition; URL hyperlink column index updated accordingly
- **Accounts list** — licensed users only; `assignedLicenses` post-filter applied

---

## [1.0.0] — 2026-03-19 — Initial public release

### Document Scanner (`server.py`)

- Scan PDFs, Word, Excel, CSV, and image files for Danish CPR numbers
- OCR support via Tesseract for scanned/image-based PDFs
- NER-based detection of names, addresses, phone numbers, emails, IBANs, and bank accounts via spaCy
- CPR validation: strict Modulus 11 check + century-digit verification
- Redaction modes: mask CPR only, or full anonymisation of all personal data
- Face detection and blurring in image files via OpenCV
- Risk scoring per file based on CPR count, age, and PII density
- Dry-run mode — scan without writing any output files
- JSON audit log (`scanner_audit.jsonl`) — append-only, records every action
- SQLite OCR cache (`~/.document_scanner_ocr_cache.db`) — avoids re-OCR of unchanged pages
- Web UI on port 5000 with grid and list view, live progress, drag-and-drop upload
- Standalone macOS `.app` and Windows `.exe` via PyInstaller + pywebview

### M365 Scanner (`m365_scanner.py`)

#### Scanning
- Exchange mailboxes: all folders and subfolders, recursive, language-independent using `wellKnownName` identifiers
- OneDrive, SharePoint, Teams file scanning via Microsoft Graph API
- Attachment scanning: PDF, Word, Excel inside emails
- CPR detection with the same strict validator as the Document Scanner
- NER-based PII detection (phone, IBAN, bank account, name, address, org)
- Progressive streaming — results appear card-by-card via Server-Sent Events
- Incremental / resumable scans — checkpoint saved on interruption, resume on next run
- Delta scan — Graph `/delta` endpoints fetch only changed items since last scan
- Per-item thumbnail generation — image previews and placeholder SVGs

#### Results
- Results grid with grid and list view, search, source filter, and disposition filter
- Account name and role (🎓 Student / 👔 Staff) badge on every card
- 🗓 Overdue badge on items exceeding the retention cutoff
- Preview panel with iframe preview, metadata strip, and disposition dropdown

#### Compliance features
- **Retention policy enforcement** (GDPR Art. 5(1)(e)): rolling or fiscal-year cutoff (e.g. Bogføringsloven Dec 31), 🗓 Overdue badge, bulk-delete quick filter, headless auto-delete via `--retention-years` and `--fiscal-year-end`
- **Data subject lookup** (Art. 15/17): modal, CPR hashed before query, bulk delete with audit logging
- **Disposition tagging** (Art. 5(1)(a)): Unreviewed / Retain (legal/legitimate/contract) / Delete-scheduled / Deleted — filter bar, preview panel, Excel export, headless auto-delete of scheduled items
- **Deletion audit log** (Art. 5(2)): every deletion logged with timestamp, actor, reason, legal basis
- **Article 30 report** (Art. 30): structured `.docx` export — summary, data categories, data inventory (staff and student sections), retention analysis, compliance trend, deletion audit log, methodology

#### User management
- Application mode (service account) and Delegated mode (device code flow)
- License-based role classification: 🎓 Student / 👔 Staff detected from O365 SKU IDs — no extra permissions needed
- Role filter buttons in accounts panel (All / 👔 Ansat / 🎓 Elev)
- Licensed users only — accounts without an assigned license are excluded
- Display name resolution: GUIDs and "Microsoft Konto" guest placeholders resolved to email address

#### Database (`m365_db.py`)
- SQLite persistence layer alongside JSON session cache
- Tables: `scans`, `flagged_items`, `cpr_index`, `pii_hits`, `dispositions`, `scan_history`, `deletion_log`
- CPR numbers stored as SHA-256 hashes only — never in plaintext
- Schema migration support via `_MIGRATIONS` + `user_version` pragma

#### Exports
- Excel export: 9 columns including Account, Role, Disposition; per-source sheets with auto-filter
- Article 30 Word document export
- Email report via SMTP (STARTTLS / SMTPS / plain); headless `--email-to` flag

#### Headless / scheduled mode
- `--headless --output DIR --settings FILE` for cron / Task Scheduler
- `--retention-years N --fiscal-year-end MM-DD` for automated retention enforcement
- `--email-to` for automated report delivery
- Non-interactive: deletes automatically; interactive (TTY): prompts for confirmation

#### Internationalisation
- Language files: English (`en`), Danish (`da`), German (`de`)
- Language switching applies in-place — no page reload, scan results preserved

#### Installation
- `install_windows.ps1`: Python, Tesseract, Poppler, venv — all local to project folder, no system PATH changes; all downloads via `curl.exe`
- `install_macos.sh`: Homebrew, Python 3.12, Tesseract, Poppler, spaCy model
- `Dockerfile` + `docker-compose.yml` for containerised deployment
- GitHub Actions: 4 parallel build jobs (Document Scanner + M365 × Windows + Linux), auto-release on `v*` tags

---

## Versioning policy

- **PATCH** (`1.0.x`) — bug fixes, translation updates, minor UI tweaks
- **MINOR** (`1.x.0`) — new feature, new suggestion from SUGGESTIONS.md implemented
- **MAJOR** (`x.0.0`) — breaking change: DB migration required, config format change, or Azure permission requirement change

To release a new version:

```bash
# 1. Update VERSION
echo "1.1.0" > VERSION

# 2. Update CHANGELOG (add new section above [1.0.0])

# 3. Commit and tag
git commit -am "Release 1.1.0"
git tag v1.1.0
git push && git push --tags
# GitHub Actions builds and publishes automatically
```
