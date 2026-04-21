# GDPRScanner — Claude Code Context

A GDPR compliance scanner for Danish educational and municipal organisations. Scans Microsoft 365 (Exchange, OneDrive, SharePoint, Teams), Google Workspace (Gmail, Google Drive), and local/SMB file systems for CPR numbers and PII. Produces Excel reports, GDPR Article 30 Word documents, and supports disposition tagging, bulk deletion, scheduled scans, and multi-language UI.

## How to run

```bash
source venv/bin/activate
python gdpr_scanner.py          # http://0.0.0.0:5100 (all interfaces)
python -m pytest tests/ -q
```

## Architecture

**Entry point:** `gdpr_scanner.py` — Flask app, scan orchestration globals. SSE route must stay here — blueprints can't stream.

**Split modules:** `scan_engine.py` (M365 + file scan), `sse.py` (SSE broadcast), `checkpoint.py`, `app_config.py` (all persistence), `cpr_detector.py`

**Google Drive delta scan** — `routes/google_scan.py` reads `scan_opts.get("delta", False)` (same flag as M365). Per user, delta key is `f"gdrive:{user_email}"` stored in `~/.gdprscanner/delta.json` alongside M365 tokens. First delta-enabled scan fetches all files then records a Changes API start page token via `conn.get_drive_start_token(user_email)`. Subsequent scans call `conn.get_drive_changes(user_email, token)` (Changes API) and update the token. Token save loads the current file fresh before writing (`{**current_tokens, **_new_drive_tokens}`) to avoid overwriting M365 tokens written by a concurrent scan thread. Invalid/expired tokens fall back to full scan automatically. `google_scan_done` now includes `"delta": bool` and `"delta_sources": int`.

**Shared content processing** — all three scan engines (M365, Google, file) funnel downloaded bytes through a single function: `cpr_detector._scan_bytes(content, filename)`. It dispatches to the correct parser by file extension. `scan_engine.py` uses the `_scan_bytes_timeout` wrapper for PDFs (subprocess + hard timeout). `routes/google_scan.py` uses `_scan_bytes` directly. Do not duplicate file-type handling in per-source code.

**`_scan_bytes` injection pattern** — `scan_engine.py` defines a no-op stub for `_scan_bytes` / `_scan_bytes_timeout` at module level (avoids circular import). `gdpr_scanner.py` overwrites them with the real `cpr_detector` implementations at startup. `routes/google_scan.py` resolves them lazily via `gdpr_scanner.__getattr__`. This is intentional — do not try to import them directly in those modules.

**Blueprints** in `routes/` — see `routes/CLAUDE.md` for state/SSE rules.

**Frontend:** `templates/index.html` (SPA), `static/style.css` (all styles), `static/js/*.js` (11 ES modules + `state.js`). `static/app.js` is an archived monolith — no longer loaded.

**Data dir** `~/.gdprscanner/`: `scanner.db`, `config.json`, `settings.json`, `schedule.json`, `token.json`, `delta.json`, `checkpoint.json`, `smtp.json`, `machine_id` (**never delete** — Fernet key), `role_overrides.json`, `google_sa.json`, `google.json`, `src_toggles.json`, `app.lock`, `viewer_tokens.json`

## Non-obvious files

| File | Why it's not obvious |
|---|---|
| `app_config.py` | All persistence — profiles, settings, SMTP, lang loading, viewer tokens + PIN |
| `routes/state.py` | Shared mutable state + scan locks (not a typical Flask state file) |
| `routes/google_scan.py` | Google scan execution lives here, not in `google_connector.py` |
| `routes/viewer.py` | Viewer token + PIN API; also owns brute-force rate-limit state |
| `static/js/viewer.js` | Share modal, token CRUD, viewer PIN settings UI |
| `lang/da.json` | Primary language — source of truth is `en.json` |
| `build_gdpr.py` | Desktop app builder; contains embedded `LAUNCHER_CODE` for PyInstaller |

## Tests

172 tests in `tests/`. No integration tests for live M365/Google connections.

**`tests/test_route_integration.py`** — 44 Flask test-client tests covering security-sensitive paths: viewer token CRUD and scope validation, `GET /api/db/flagged` role/user scope enforcement, bulk disposition isolation, viewer PIN (set/verify/rate-limit/change/clear), interface PIN gate (multi-step flows require `session["interface_ok"] = True` after PIN set — the `before_request` hook blocks the same endpoint once a PIN exists), scan lock release on `run_scan()` exception, `GET /api/db/sessions` shape and ordering. Uses a tmp-path `ScanDB` monkeypatched into `routes.database._get_db` — tests never touch the real database. Interface PIN tests manipulate the real `config.json` via `setup_method`/`teardown_method` calling `clear_interface_pin()`.

**Local-file scan fixtures** — `tests/fixtures/local_files/` holds 13 documents for manual/UI-level testing of the file scanner. 10 should be flagged; 3 are true negatives. All CPR numbers verified against `is_valid_cpr`. `generate_fixtures.py` (requires `python-docx` + `openpyxl`, already in venv) regenerates the binary `.docx`/`.xlsx` files.

**`_CPR_PREFIX_NOISE` in `.docx` fixtures** — `scan_docx` builds a single string by concatenating all run texts with no separators between paragraphs. If a CPR value run is immediately followed by text from the next paragraph without a word boundary, `\b` in `CPR_PATTERN` fails and the number is silently missed. The fixture generator appends a trailing `" "` to every value run so CPRs are always surrounded by word boundaries after concatenation. Do not remove this trailing space — the detection will silently regress.

## Viewer mode (#33) — routes/viewer.py + static/js/viewer.js

Read-only access for DPOs and reviewers. Key invariants:

- **`/view` auth chain** — token (`?token=`) → session cookie (`session["viewer_ok"]`) → PIN form (if PIN configured) → 403. Never skip this order.
- **`window.VIEWER_MODE`** — injected by Jinja2 in `index.html`. `auth.js` reads it at startup; adds `viewer-mode` class to `<body>`. All hide rules are CSS (`body.viewer-mode …`), not scattered JS checks — except `delBtn` in the card builder which is also guarded in JS. Hidden in viewer mode: `.sidebar` (entire left panel), `#logWrap`, `#progressBar`, scan/stop/profile/bulk-delete buttons, share button.
- **`window.VIEWER_SCOPE`** — injected alongside `VIEWER_MODE`. Contains the scope dict from the token (e.g. `{"role": "student"}`). Empty object `{}` means unrestricted. `auth.js` reads it at startup; if `VIEWER_SCOPE.role` is set, it pre-sets `#filterRole` to that value and hides the dropdown so the viewer cannot change it.
- **Token scope** — stored as `"scope": {"role": "student"|"staff"}` or `"scope": {}` in each token dict inside `viewer_tokens.json`. Enforced in two places: server-side (`GET /api/db/flagged` skips items whose `user_role` column does not match `session["viewer_scope"].role`) and client-side (the `#filterRole` dropdown is locked). Server-side is the authoritative guard. **Column name is `user_role`** — do not use `role`; the DB row has no such key and the filter silently returns nothing.
- **`session["viewer_scope"]`** — set when a token is validated at `/view`. Persists for the browser session alongside `session["viewer_ok"]`. Reads from `session.get("viewer_scope", {})` in `/api/db/flagged` — defaults to `{}` (unrestricted) for PIN-authenticated sessions and legacy tokens without a scope key.
- **`viewer_tokens.json` format** — stored as `{"tokens": [...], "__pin__": {"hash": "…", "salt": "…"}}`. Token dicts now include `"scope": {}`. The old bare-list format and tokens without a `scope` key are handled transparently (`t.get("scope", {})`). Do not write the file as a bare list.
- **`app.secret_key`** — derived from `machine_id` bytes so Flask sessions survive restarts. Set once at startup in `gdpr_scanner.py`; do not override it.
- **`GET /api/db/flagged`** — returns `get_session_items()` (last completed scan session, joined with dispositions), filtered by `session["viewer_scope"].role` when set. Used exclusively by `_loadViewerResults()` in `results.js`. Do not confuse with `get_flagged_items()` (single scan_id, no disposition join).
- **Rate-limit state** (`_pin_attempts` dict in `routes/viewer.py`) — in-memory only, resets on server restart. Intentional — a restart clears lockouts without a persistent store.
- **User-scoped tokens (#34)** — scope `{"user": ["alice@m365.dk", "alice@gws.dk"], "display_name": "Alice Smith"}` filters `GET /api/db/flagged` by `account_id IN (list)`, covering both M365 and GWS items for the same person. `scope.user` is always stored as a list; a legacy single-string value is coerced to `[string]` on read. `scope.display_name` is used for UI only (badge, viewer header) — not for filtering. File-scan items (`account_id = ""`) never appear in user-scoped views. `POST /api/viewer/tokens` rejects combined `role`+`user` scope with 400. Share modal: scope-type `<select>` (`#shareScopeType`) reveals either the role dropdown (`#shareScopeRoleWrap`) or a name-search autocomplete (`#shareScopeUserWrap`). Autocomplete reads `S._allUsers`; selecting a row stores `{ emails, display_name }` in module-level `_selectedScopeUser`; editing the input manually clears it (free-text email fallback). In viewer mode, `auth.js` shows `#viewerIdentityBadge` with `VIEWER_SCOPE.display_name`.
- **Token onclick attributes** — Copy/Revoke buttons in `_renderTokenList()` pass the token as a single-quoted JS string literal (`'\'' + tok.token + '\''`), never via `JSON.stringify`. `JSON.stringify` produces double-quoted strings that break the surrounding `onclick="…"` HTML attribute.
- **Settings Security pane** — Admin PIN and Viewer PIN groups live in `stPaneSecurity`, not `stPaneGeneral`. `switchSettingsTab('security')` in `sources.js` triggers both `stLoadPinStatus()` and `stLoadViewerPinStatus()`. The Share modal Configure button opens `openSettings('security')`.
- **`stClearViewerPin` guard** — validates that the current-PIN field is non-empty client-side before sending the DELETE request; shows an inline error and focuses the field if empty.
- **Share link base URL** — `_getShareBaseUrl()` in `viewer.js` fetches `/api/local_ip` (returns the machine's LAN IP via a UDP probe to `8.8.8.8`) and substitutes it so copied links are routable from other machines. Falls back to `window.location.origin` on error. Both `createShareLink` and `copyTokenLink` are `async` and `await` this helper. Do not revert to a bare `window.location.origin` — that produces `127.0.0.1` links useless to remote viewers.
- **Flask binds to `0.0.0.0`** — `gdpr_scanner.py` default `--host`, `m365_launcher.py`, and `build_gdpr.py` all use `host="0.0.0.0"`. Internal loopback URLs (urllib exports, webview window, port probe) intentionally keep `127.0.0.1` — do not change those to `0.0.0.0`.

## Sources panel resize — static/js/log.js + sources.js

- **`_fitSourcesPanel()`** — called at the end of every `renderSourcesPanel()` call. Clears the panel's inline height, reads `scrollHeight` (natural content height), then either restores a saved smaller preference from `localStorage` (`gdpr_sources_h`) or pins the height to `scrollHeight`. This keeps the panel exactly as tall as needed to show all sources.
- **`_initSourcesResize()`** — attaches pointer-drag to `#sourcesResizeHandle`. On `pointerdown` it captures `scrollHeight` as the hard max; drag up shrinks, drag down is capped at that max. Saves to `localStorage` on release; clears the key if the user drags back to full height.
- **Do not add a fixed `max-height` or `height` to `#sourcesPanel` in HTML** — height is controlled entirely by `_fitSourcesPanel()` at runtime.
- **Do not call `_fitSourcesPanel()` before the panel has rendered** — `scrollHeight` will be 0. The call in `renderSourcesPanel()` is the correct hook; `_initSourcesResize()` only sets up the drag handler.

## Scan filter options — scan_engine.py

Both options live in the profile `options` dict and apply to **all three scan engines** (M365, Google, file scan).

- **`skip_gps_images` (bool, default `false`)** — When enabled, images whose only PII is GPS coordinates are not flagged. GPS data is still extracted and stored in the card `exif` field if the item is flagged by another signal (faces, EXIF author/comment). The `gps_location` special category is also suppressed. Evaluated via `_exif_has_pii` which rechecks `pii_fields` and `author` when GPS is skipped.
- **`min_cpr_count` (int, default `1`)** — Minimum number of **distinct** CPR numbers in a file before it is flagged. Deduplication uses `list(dict.fromkeys(c["formatted"] for c in cprs))` — `cprs` is a list of dicts from `extract_matches`, not strings. Do not revert to `dict.fromkeys(cprs)` — that raises `TypeError: unhashable type: 'dict'` on every file with CPR hits. Files with faces or EXIF PII are still flagged regardless of CPR count — the threshold gates only CPR-based hits.
- **File scan** reads both from `source` dict keys (passed directly from the `/api/file_scan/start` payload). **M365 scan** reads both from `scan_opts = options.get("options", {})`. Both paths apply the same `_cpr_qualifies` / `_exif_has_pii` logic before the flagging gate.
- **UI:** sidebar controls `#optSkipGps` (toggle) and `#optMinCpr` (number); profile editor controls `#peOptSkipGps` and `#peOptMinCpr`. Both are saved/loaded by `profiles.js`.

## M365 connector exceptions — m365_connector.py

Exception hierarchy (all inherit `M365Error(Exception)`):

| Exception | Trigger | Handler |
|---|---|---|
| `M365PermissionError` | 403 Forbidden | `scan_error` broadcast with human-readable permission hint |
| `M365DeltaTokenExpired` | 410 Gone on delta endpoint | Caller clears token and falls back to full scan |
| `M365DriveNotFound` | 404 Not Found on any path | `scan_phase` broadcast ("not provisioned — skipped") in `_scan_user_onedrive`; full-scan path's `except Exception: return` also silences it |

**`M365DriveNotFound` — why it exists:** `_get()` previously fell through to `raise_for_status()` on 404, which was caught by the generic `except Exception` handler in `_scan_user_onedrive` and broadcast as a red `scan_error`. The full-scan path (`_iter_drive_folder_for`) silently swallowed the same 404 via `except Exception: return`. Adding the specific exception makes the delta path consistent with the full-scan path: a user without a provisioned OneDrive is skipped without an error card. Common causes: no OneDrive licence, service plan disabled, drive never initialised (account never signed in), account suspended.

**Do not add a 404 handler to `_get()` that returns a fallback value** — that would silently mask genuine path bugs elsewhere. Raising `M365DriveNotFound` keeps the error visible to callers that need to act on it.

## Memory management — scan_engine.py

Large M365 tenants can generate enormous memory pressure. Key rules to preserve:

- **Email body stripped at collection time** — `_scan_user_email` calls `conn.get_message_body_text(msg)`, stores the result as `msg["_precomputed_body"]`, then deletes `msg["body"]` and `msg["bodyPreview"]` before appending to `work_items`. The processing loop reads `meta.pop("_precomputed_body", "")`. Do not re-add `body` to the `$select` query without also stripping it here.
- **`work_items` → `deque` before processing** — converted with `deque(work_items)` and drained via `popleft()` so each item's memory is released immediately after processing. Do not convert back to a list or iterate with `enumerate()`.
- **`del content` in file branch** — raw download bytes are deleted as soon as `content.decode()` is done (before NER/PII counting). Both the hit and no-hit paths have explicit `del content`.
- **`del body_text` in email branch** — deleted after `_broadcast_card` call.
- **PDF OCR rendered page-by-page** — `document_scanner.scan_pdf` (and the redact paths) call `convert_from_path(first_page=N, last_page=N)` inside the loop, so only one page image is in memory at a time. Do NOT move back to a bulk `convert_from_path()` call — that allocates all pages at once and triggers OOM kills on large PDFs.
- **OCR memory guard** — `_ocr_mem_ok()` checks `psutil.virtual_memory().available >= 500 MB` before each page render. Pages that would exceed this threshold are skipped with a printed warning and recorded as `"skipped"` in `page_methods`.
- **Memory guard** — `psutil.virtual_memory().available` checked before each M365 file download; scan skips the file if < 300 MB free.

## Export — routes/export.py

- **`GDPRDb.get_session_sources()`** — returns a `set` of source-key strings (e.g. `{"gmail", "gdrive", "email"}`) for every scan in the current session window. Used by both `_build_excel_bytes()` and `_build_article30_docx()` to include zero-hit sources in summary tables. Do not derive the scanned-source set from `by_source` alone — that dict only contains sources with flagged items.
- **Excel Summary sheet vs. per-source tabs** — the Summary sheet shows all scanned sources (even with 0 items). Per-source tabs are only created for sources with items; an empty tab has no value.
- **ART.30 breakdown table** — iterates `scanned_sources` (not `by_source`) so Gmail, Google Drive, etc. appear with `0 | 0 | 0 | —` when the scan found nothing.
- **Role-filtered exports** — `_build_excel_bytes(role='')` and `_build_article30_docx(role='')` accept `role='student'` or `role='staff'`. A local `_items` list is built at the top of each function and used everywhere instead of `state.flagged_items` directly — GPS sheet, External transfers sheet, and Art.30 staff/student tables all see only the filtered subset. Route handlers read `request.args.get('role', '')` and forward it. Filenames get `_elever` / `_ansatte` suffix. The `#filterRole` dropdown in the filter bar drives both the client-side grid filter and the export URL param — do not separate them.

## Scan history browser — static/js/history.js + gdpr_db.py + routes/database.py

Allows reviewing results from any past scan session without running a new scan. Key invariants:

- **`S._historyRefScanId`** — `null` = live/SSE mode; positive int = viewing a past session (the highest `scan_id` in that session's 300 s window). Set by `loadHistorySession()`; cleared to `null` by `exitHistoryMode()`.
- **`GET /api/db/sessions`** (`routes/database.py`) — calls `_get_db().get_sessions()`. Returns newest-first list; each entry has `ref_scan_id`, `started_at`, `finished_at`, `sources` (list of source-key strings), `flagged_count`, `total_scanned`, `delta` (bool). No auth restriction — viewer tokens share this endpoint.
- **`get_sessions(limit=50, window_seconds=300)`** (`gdpr_db.py`) — groups `scans` rows by 300 s window (same window logic as `get_session_items`). Groups are built ascending, returned descending. `ref_scan_id` is the highest `scan_id` in each group. Do not change the window size independently of `get_session_items`.
- **`get_session_items(ref_scan_id=N)`** (`gdpr_db.py`) — when `ref_scan_id` is given, anchors the 300 s window to that scan's `started_at`. Falls back to latest scan when `ref_scan_id=None`. Window is **symmetric**: `started_at BETWEEN ref.started_at - 300 AND ref.started_at + 300` — do not revert to a one-sided lower bound or historical sessions will include all newer scans.
- **`GET /api/db/flagged?ref=N`** — passes `ref_scan_id` to `get_session_items`; viewer scope enforcement (role/user filters) still applies. Used by both history mode and the normal post-scan viewer path.
- **History banner** (`#historyBanner`) — shown when `S._historyRefScanId` is set. Contains `#historyBannerText` (session date · sources · N items), `#historyPickerBtn` (opens `#historyDropdown`), and `#historyLatestBtn` (visible only when the viewed session is not the latest). Do not hide/show these elements from outside `history.js`.
- **Session picker** (`#historyDropdown`) — rendered inside `[data-history-wrap]` container so the outside-click handler (`document` listener, closes on clicks outside `[data-history-wrap]`) works correctly. Do not move the picker outside this wrapper.
- **Cache invalidation** — `_sessions` and `_latestRefScanId` are module-level in `history.js`. `invalidateHistoryCache()` clears both. All three `*_done` SSE handlers in `scan.js` call `window.invalidateHistoryCache?.()` so the picker reflects the newest scan after completion.
- **Auto-load on page load** — `results.js` calls `window.loadHistorySession?.(null)` once when the SSE watchdog confirms `!status.running`. `null` resolves to the latest completed session via `_fetchSessions()[0].ref_scan_id`. The `_initialStatusChecked` guard ensures this fires at most once per page load.
- **Mode transitions** — `startScan()` calls `window.exitHistoryMode?.()` before clearing the grid, so any history banner is dismissed and `S._historyRefScanId` is reset before SSE events start arriving.

## SSE teardown — static/js/scan.js

- **Do not close `S.es` in `scan_done` if other scans are still running** — M365 (`scan_done`), Google (`google_scan_done`), and File (`file_scan_done`) each emit their own done event. If M365 finishes first and the SSE is closed, the remaining done events are never received and the UI hangs at 100% indefinitely.
- **Rule:** close `S.es` (and reset `S._userStartedScan`) only inside the branch where *all* concurrent scans have finished: `scan_done` checks `!S._googleScanRunning && !S._fileScanRunning`; `google_scan_done` checks `!S._m365ScanRunning && !S._fileScanRunning`; `file_scan_done` checks `!S._m365ScanRunning && !S._googleScanRunning`.
- **Scheduled scans** — `S._userStartedScan` is false for scheduler-triggered runs, so the SSE connection is never closed and future scheduler events continue to arrive.
- **`scan_start` is M365-only** — `run_scan()` broadcasts `scan_start`; `run_file_scan()` and `routes/google_scan.py` must NOT. The `scan_start` handler in `_attachSchedulerListeners` unconditionally sets `S._m365ScanRunning = true`. If a file scan emits `scan_start`, the flag is set without a matching `scan_done` to clear it, and `file_scan_done` refuses to re-enable the scan button because `!S._m365ScanRunning` is false. Use `scan_phase` (file) and `google_scan_phase` (google) instead — these are routed correctly by the phase-source detection logic in `_attachScanListeners`.

## Email sending — routes/email.py + m365_connector.py

- **`_post()` returns `{}` on empty body** — `m365_connector._post()` returns `r.json() if r.content else {}`. The Graph `sendMail` endpoint returns HTTP 202 with **no body** on success; calling `r.json()` on an empty response raises `JSONDecodeError`. Do not change this back to an unconditional `r.json()` — it would falsely report every successful email send as an error.
- **Graph preferred over SMTP** — `smtp_test` and `send_report` both try `_send_email_graph()` first when `state.connector` is authenticated. Only falls back to SMTP if Graph raises. If Graph fails and no SMTP host is saved, the Graph exception is surfaced directly (not swallowed by the "No SMTP host" message).
- **Auto-email after manual scan** — `_maybe_send_auto_email()` in `routes/scan.py` is called from the `_run()` thread immediately after `run_scan()` returns. Reads `smtp_cfg.get("auto_email_manual")` from `smtp.json`; no-ops if the flag is false, no flagged items, or no recipients. Same Graph-first → SMTP-fallback pattern as the scheduler. Toggle: **Settings → Email report → Email report after manual scan** (`#st-smtpAutoEmail`), saved by `stSmtpSave()` in `scheduler.js`.
- **Gmail vs Google Workspace detection** — auth error handlers check whether the SMTP username ends in `@gmail.com` / `@googlemail.com`. If not, the account is treated as Google Workspace (custom domain) and the error message points to the Workspace admin console rather than the user's personal security settings.

## Global gotchas

- **Pattern matching in Python** — when using `str.replace()` to patch JS/HTML, whitespace and quote style must match exactly. Use `in` check first and print if not found.
- **`__getattr__` on modules** — only resolves `module.name` access from outside, not bare name lookups inside function bodies. Always import directly.
- **`JSON.stringify` inside `onclick="…"` attributes** — produces double-quoted strings that terminate the HTML attribute early. Use single-quoted JS string literals instead, or `data-*` attributes read from the handler.

## Directory-scoped rules

- `routes/CLAUDE.md` — SSE constraints, scan_progress source field, file_sources, Python gotchas
- `static/js/CLAUDE.md` — profile dropdown, progress bar phase parsing, JS gotchas
- `templates/CLAUDE.md` — CSS variable names, sizing rules, badge standard, design rules
- `lang/CLAUDE.md` — i18n conventions
