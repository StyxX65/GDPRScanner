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

128 tests in `tests/`. No integration tests for Flask routes or live M365/Google connections.

## Viewer mode (#33) — routes/viewer.py + static/js/viewer.js

Read-only access for DPOs and reviewers. Key invariants:

- **`/view` auth chain** — token (`?token=`) → session cookie (`session["viewer_ok"]`) → PIN form (if PIN configured) → 403. Never skip this order.
- **`window.VIEWER_MODE`** — injected by Jinja2 in `index.html`. `auth.js` reads it at startup; adds `viewer-mode` class to `<body>`. All hide rules are CSS (`body.viewer-mode …`), not scattered JS checks — except `delBtn` in the card builder which is also guarded in JS. Hidden in viewer mode: `.sidebar` (entire left panel), `#logWrap`, `#progressBar`, scan/stop/profile/bulk-delete buttons, share button.
- **`window.VIEWER_SCOPE`** — injected alongside `VIEWER_MODE`. Contains the scope dict from the token (e.g. `{"role": "student"}`). Empty object `{}` means unrestricted. `auth.js` reads it at startup; if `VIEWER_SCOPE.role` is set, it pre-sets `#filterRole` to that value and hides the dropdown so the viewer cannot change it.
- **Token scope** — stored as `"scope": {"role": "student"|"staff"}` or `"scope": {}` in each token dict inside `viewer_tokens.json`. Enforced in two places: server-side (`GET /api/db/flagged` skips items whose `role` column does not match `session["viewer_scope"].role`) and client-side (the `#filterRole` dropdown is locked). Server-side is the authoritative guard.
- **`session["viewer_scope"]`** — set when a token is validated at `/view`. Persists for the browser session alongside `session["viewer_ok"]`. Reads from `session.get("viewer_scope", {})` in `/api/db/flagged` — defaults to `{}` (unrestricted) for PIN-authenticated sessions and legacy tokens without a scope key.
- **`viewer_tokens.json` format** — stored as `{"tokens": [...], "__pin__": {"hash": "…", "salt": "…"}}`. Token dicts now include `"scope": {}`. The old bare-list format and tokens without a `scope` key are handled transparently (`t.get("scope", {})`). Do not write the file as a bare list.
- **`app.secret_key`** — derived from `machine_id` bytes so Flask sessions survive restarts. Set once at startup in `gdpr_scanner.py`; do not override it.
- **`GET /api/db/flagged`** — returns `get_session_items()` (last completed scan session, joined with dispositions), filtered by `session["viewer_scope"].role` when set. Used exclusively by `_loadViewerResults()` in `results.js`. Do not confuse with `get_flagged_items()` (single scan_id, no disposition join).
- **Rate-limit state** (`_pin_attempts` dict in `routes/viewer.py`) — in-memory only, resets on server restart. Intentional — a restart clears lockouts without a persistent store.
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
- **`min_cpr_count` (int, default `1`)** — Minimum number of **distinct** CPR numbers in a file before it is flagged. Deduplication uses `list(dict.fromkeys(cprs))` to preserve order. Files with faces or EXIF PII are still flagged regardless of CPR count — the threshold gates only CPR-based hits.
- **File scan** reads both from `source` dict keys (passed directly from the `/api/file_scan/start` payload). **M365 scan** reads both from `scan_opts = options.get("options", {})`. Both paths apply the same `_cpr_qualifies` / `_exif_has_pii` logic before the flagging gate.
- **UI:** sidebar controls `#optSkipGps` (toggle) and `#optMinCpr` (number); profile editor controls `#peOptSkipGps` and `#peOptMinCpr`. Both are saved/loaded by `profiles.js`.

## Memory management — scan_engine.py

Large M365 tenants can generate enormous memory pressure. Key rules to preserve:

- **Email body stripped at collection time** — `_scan_user_email` calls `conn.get_message_body_text(msg)`, stores the result as `msg["_precomputed_body"]`, then deletes `msg["body"]` and `msg["bodyPreview"]` before appending to `work_items`. The processing loop reads `meta.pop("_precomputed_body", "")`. Do not re-add `body` to the `$select` query without also stripping it here.
- **`work_items` → `deque` before processing** — converted with `deque(work_items)` and drained via `popleft()` so each item's memory is released immediately after processing. Do not convert back to a list or iterate with `enumerate()`.
- **`del content` in file branch** — raw download bytes are deleted as soon as `content.decode()` is done (before NER/PII counting). Both the hit and no-hit paths have explicit `del content`.
- **`del body_text` in email branch** — deleted after `_broadcast_card` call.
- **PDF OCR images freed page-by-page** — in `document_scanner.scan_pdf`, `images[page_num-1] = None` immediately after OCR. Do not cache or accumulate page images.
- **Memory guard** — `psutil.virtual_memory().available` checked before each M365 file download; scan skips the file if < 300 MB free.

## Export — routes/export.py

- **`GDPRDb.get_session_sources()`** — returns a `set` of source-key strings (e.g. `{"gmail", "gdrive", "email"}`) for every scan in the current session window. Used by both `_build_excel_bytes()` and `_build_article30_docx()` to include zero-hit sources in summary tables. Do not derive the scanned-source set from `by_source` alone — that dict only contains sources with flagged items.
- **Excel Summary sheet vs. per-source tabs** — the Summary sheet shows all scanned sources (even with 0 items). Per-source tabs are only created for sources with items; an empty tab has no value.
- **ART.30 breakdown table** — iterates `scanned_sources` (not `by_source`) so Gmail, Google Drive, etc. appear with `0 | 0 | 0 | —` when the scan found nothing.
- **Role-filtered exports** — `_build_excel_bytes(role='')` and `_build_article30_docx(role='')` accept `role='student'` or `role='staff'`. A local `_items` list is built at the top of each function and used everywhere instead of `state.flagged_items` directly — GPS sheet, External transfers sheet, and Art.30 staff/student tables all see only the filtered subset. Route handlers read `request.args.get('role', '')` and forward it. Filenames get `_elever` / `_ansatte` suffix. The `#filterRole` dropdown in the filter bar drives both the client-side grid filter and the export URL param — do not separate them.

## SSE teardown — static/js/scan.js

- **Do not close `S.es` in `scan_done` if other scans are still running** — M365 (`scan_done`), Google (`google_scan_done`), and File (`file_scan_done`) each emit their own done event. If M365 finishes first and the SSE is closed, the remaining done events are never received and the UI hangs at 100% indefinitely.
- **Rule:** close `S.es` (and reset `S._userStartedScan`) only inside the branch where *all* concurrent scans have finished: `scan_done` checks `!S._googleScanRunning && !S._fileScanRunning`; `google_scan_done` checks `!S._m365ScanRunning && !S._fileScanRunning`; `file_scan_done` checks `!S._m365ScanRunning && !S._googleScanRunning`.
- **Scheduled scans** — `S._userStartedScan` is false for scheduler-triggered runs, so the SSE connection is never closed and future scheduler events continue to arrive.

## Global gotchas

- **Pattern matching in Python** — when using `str.replace()` to patch JS/HTML, whitespace and quote style must match exactly. Use `in` check first and print if not found.
- **`__getattr__` on modules** — only resolves `module.name` access from outside, not bare name lookups inside function bodies. Always import directly.
- **`JSON.stringify` inside `onclick="…"` attributes** — produces double-quoted strings that terminate the HTML attribute early. Use single-quoted JS string literals instead, or `data-*` attributes read from the handler.

## Directory-scoped rules

- `routes/CLAUDE.md` — SSE constraints, scan_progress source field, file_sources, Python gotchas
- `static/js/CLAUDE.md` — profile dropdown, progress bar phase parsing, JS gotchas
- `templates/CLAUDE.md` — CSS variable names, sizing rules, badge standard, design rules
- `lang/CLAUDE.md` — i18n conventions
