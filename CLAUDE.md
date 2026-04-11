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
- **`viewer_tokens.json` format** — stored as `{"tokens": [...], "__pin__": {"hash": "…", "salt": "…"}}`. The old bare-list format is migrated transparently on first write. Do not write the file as a bare list.
- **`app.secret_key`** — derived from `machine_id` bytes so Flask sessions survive restarts. Set once at startup in `gdpr_scanner.py`; do not override it.
- **`GET /api/db/flagged`** — returns `get_session_items()` (last completed scan session, joined with dispositions). Used exclusively by `_loadViewerResults()` in `results.js`. Do not confuse with `get_flagged_items()` (single scan_id, no disposition join).
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

## Memory management — scan_engine.py

Large M365 tenants can generate enormous memory pressure. Key rules to preserve:

- **Email body stripped at collection time** — `_scan_user_email` calls `conn.get_message_body_text(msg)`, stores the result as `msg["_precomputed_body"]`, then deletes `msg["body"]` and `msg["bodyPreview"]` before appending to `work_items`. The processing loop reads `meta.pop("_precomputed_body", "")`. Do not re-add `body` to the `$select` query without also stripping it here.
- **`work_items` → `deque` before processing** — converted with `deque(work_items)` and drained via `popleft()` so each item's memory is released immediately after processing. Do not convert back to a list or iterate with `enumerate()`.
- **`del content` in file branch** — raw download bytes are deleted as soon as `content.decode()` is done (before NER/PII counting). Both the hit and no-hit paths have explicit `del content`.
- **`del body_text` in email branch** — deleted after `_broadcast_card` call.
- **PDF OCR images freed page-by-page** — in `document_scanner.scan_pdf`, `images[page_num-1] = None` immediately after OCR. Do not cache or accumulate page images.
- **Memory guard** — `psutil.virtual_memory().available` checked before each M365 file download; scan skips the file if < 300 MB free.

## Global gotchas

- **Pattern matching in Python** — when using `str.replace()` to patch JS/HTML, whitespace and quote style must match exactly. Use `in` check first and print if not found.
- **`__getattr__` on modules** — only resolves `module.name` access from outside, not bare name lookups inside function bodies. Always import directly.
- **`JSON.stringify` inside `onclick="…"` attributes** — produces double-quoted strings that terminate the HTML attribute early. Use single-quoted JS string literals instead, or `data-*` attributes read from the handler.

## Directory-scoped rules

- `routes/CLAUDE.md` — SSE constraints, scan_progress source field, file_sources, Python gotchas
- `static/js/CLAUDE.md` — profile dropdown, progress bar phase parsing, JS gotchas
- `templates/CLAUDE.md` — CSS variable names, sizing rules, badge standard, design rules
- `lang/CLAUDE.md` — i18n conventions
