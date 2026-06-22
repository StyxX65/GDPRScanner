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

**Google Drive delta scan** — `routes/google_scan.py` reads `scan_opts.get("delta", False)` (same flag as M365). Per user, delta key is `f"gdrive:{user_email}"` stored in `~/.gdprscanner/delta.json` alongside M365 tokens. First delta-enabled scan fetches all files then records a Changes API start page token via `conn.get_drive_start_token(user_email)`. Subsequent scans call `conn.get_drive_changes(user_email, token)` and update the token. Invalid/expired tokens fall back to full scan automatically.

**Google connector write-back** — `google_connector.py` exposes `get_drive_file_mime`, `download_drive_file_by_id`, `update_drive_file` on both connectors for in-place Drive redaction. These use `DRIVE_WRITE_SCOPES` (`drive`, not `drive.readonly`) — the service-account delegation must include this scope or the call raises 403.

**SFTP connector** — `sftp_connector.py` provides `SFTPScanner` with the same `iter_files()` interface as `FileScanner`. `run_file_scan()` in `scan_engine.py` checks `source.get("source_type") == "sftp"` and instantiates `SFTPScanner`; the rest of the pipeline is source-agnostic. Auth: `"password"` via OS keychain; `"key"` from `~/.gdprscanner/sftp_keys/<uuid>`. `SFTP_OK` flag guards graceful degradation if `paramiko` is not installed. Single-file I/O: `_ssh_connect()`, `read_file(remote_path)`, `write_file(remote_path, content)` — do not duplicate SSH setup outside these methods.

**Shared content processing** — all three scan engines funnel downloaded bytes through `cpr_detector._scan_bytes(content, filename)`. `scan_engine.py` uses `_scan_bytes_timeout` for PDFs (subprocess + hard timeout). Do not duplicate file-type handling in per-source code.

**`cpr_detector.SUPPORTED_EXTS` is the single source of truth** for which file extensions are scanned. `file_scanner.py` imports it as `DEFAULT_EXTENSIONS`. Do not maintain a separate extension list anywhere else.

**`_scan_bytes` injection pattern** — `scan_engine.py` defines no-op stubs at module level (avoids circular import). `gdpr_scanner.py` overwrites them at startup. `routes/google_scan.py` resolves them lazily via `gdpr_scanner.__getattr__`. Do not import them directly in those modules.

**Blueprints** in `routes/` — see `routes/CLAUDE.md` for SSE constraints, export, preview, scheduler, NER, audit log, viewer, software update, and other route-specific rules.

**Self-update (server only)** — `routes/updates.py` powers **Settings → General → Software update**: git fetch → ff-only merge → conditional `pip install` → `os.execv` restart (same PID; marks fds close-on-exec first so Werkzeug's inheritable listening socket doesn't leak and squat the port). Only enabled for git checkouts (`_supported()` is false for frozen desktop builds). `update_gdpr.sh` is the CLI/cron equivalent. Refused while a scan runs; optional daily auto-update thread (`config.json["auto_update"]`). Restart keeps port 5100 (the port probe uses `SO_REUSEADDR` + a 10s grace). See `routes/CLAUDE.md` → "Software update".

**Frontend:** `templates/index.html` (SPA), `static/style.css` (all styles), `static/js/*.js` (11 ES modules + `state.js`). `static/app.js` is an archived monolith — no longer loaded.

**Checkpoint / resume** — all three scan engines save progress to `~/.gdprscanner/checkpoint_{prefix}.json` every 25 items. Prefixes: `m365`, `google`, `file_{source_id}`. Use `_cp_path(prefix)` — do not hard-code filenames. The Scan button calls `checkCheckpoint(() => startScan(false))` so a resume banner is offered before any grid clearing. `POST /api/scan/clear_checkpoint` globs and deletes all `checkpoint_*.json` files.

**Data dir** `~/.gdprscanner/`: `scanner.db`, `config.json` (also holds `claude_api_key`/`claude_ner` and the `auto_update` flag), `settings.json`, `schedule.json`, `token.json`, `delta.json`, `checkpoint_m365.json`, `checkpoint_google.json`, `checkpoint_file_*.json`, `smtp.json`, `machine_id` (**never delete** — Fernet key), `role_overrides.json`, `google_sa.json`, `google.json`, `src_toggles.json`, `app.lock`, `viewer_tokens.json`. Static files are served with `SEND_FILE_MAX_AGE_DEFAULT=0` (ETag revalidation) so the UI is fresh after a self-update — do not re-add long static caching.

## Non-obvious files

| File | Why it's not obvious |
|---|---|
| `app_config.py` | All persistence — profiles, settings, SMTP, lang loading, viewer tokens + PIN |
| `routes/state.py` | Shared mutable state + scan locks (not a typical Flask state file) |
| `routes/google_scan.py` | Google scan execution lives here, not in `google_connector.py` |
| `routes/viewer.py` | Viewer token + PIN API; also owns brute-force rate-limit state |
| `static/js/viewer.js` | Share modal, token CRUD, viewer PIN settings UI. Also defines `window._copyText` (HTTP-safe clipboard helper reused by `log.js`) |
| `lang/da.json` | Primary language — source of truth is `en.json` |
| `build_gdpr.py` | Desktop app builder; contains embedded `LAUNCHER_CODE` for PyInstaller |
| `routes/updates.py` | Self-update routes + `os.execv` restart with fd-cleanup; git-checkout only |
| `update_gdpr.sh` | CLI/cron self-update (fetch, ff-merge, deps, service restart) |
| `docs/setup/ZORAXY_SETUP.md` | HTTPS via Zoraxy reverse proxy (LAN-only, Let's Encrypt DNS-01) |

## Tests

215 tests in `tests/`. No integration tests for live M365/Google connections.

**`tests/test_updates.py`** — 12 tests for the software-update routes (`routes/updates.py`). All git interaction goes through a mocked `_git()`; `_schedule_restart` is patched so no test re-execs the process, and `gdpr_db.log_audit_event` is patched so no test writes the real database. Includes `_mark_fds_cloexec` (the socket-leak guard for the restart).

**`tests/test_google_scan.py`** — 19 tests for the Google Workspace scan module. Route tests for `GET /api/google/scan/users`, `POST /api/google/scan/start`, `POST /api/google/scan/cancel`. Engine tests for `_run_google_scan` using synchronous invocation with mocked `broadcast`, `_scan_bytes`, `checkpoint.*`, `scan_engine._with_disposition`, and `gdpr_db.get_db`. The `clean_google_state` autouse fixture releases `_google_scan_lock` and clears `_google_scan_abort` after each test.

**`tests/test_route_integration.py`** — 54 Flask test-client tests covering security-sensitive paths: viewer token CRUD and scope validation, `GET /api/db/flagged` role/user scope enforcement, bulk disposition isolation, viewer PIN (set/verify/rate-limit/change/clear), interface PIN gate (multi-step flows require `session["interface_ok"] = True` after PIN set), scan lock release on `run_scan()` exception, `GET /api/db/sessions` shape and ordering, profile routes CRUD and rename. Uses a tmp-path `ScanDB` monkeypatched into `routes.database._get_db` — tests never touch the real database.

**Local-file scan fixtures** — `tests/fixtures/local_files/` holds 19 files (14 flagged, 5 true negatives). `generate_fixtures.py` regenerates the binary files. Audio fixtures need 2 silent MPEG frames so mutagen can sync; FLAC uses a hand-packed STREAMINFO + Vorbis comment block.

**`_CPR_PREFIX_NOISE` in `.docx` fixtures** — `scan_docx` concatenates all run texts with no separators. The fixture generator appends a trailing `" "` to every value run so CPRs are always surrounded by word boundaries. Do not remove this trailing space — the detection will silently regress.

## Scan filter options — scan_engine.py

All options live in the profile `options` dict and apply to **all three scan engines** (M365, Google, file scan).

- **`skip_gps_images` (bool, default `false`)** — images whose only PII is GPS coordinates are not flagged. GPS data still stored in `exif` field if flagged by another signal.
- **`min_cpr_count` (int, default `1`)** — minimum distinct CPR numbers before flagging. Deduplication uses `list(dict.fromkeys(c["formatted"] for c in cprs))` — do not revert to `dict.fromkeys(cprs)` (raises `TypeError: unhashable type: 'dict'`). Files with faces or EXIF PII are still flagged regardless.
- **`cpr_only` (bool, default `false`)** — skip items whose only hits are email addresses, phone numbers, faces, or EXIF/GPS metadata.
- **`ocr_lang` (str, default `"dan+eng"`)** — Tesseract language packs. Threaded through `_scan_bytes`/`_scan_bytes_timeout` → `document_scanner` and the PDF-OCR subprocess worker. Cache key already includes `lang`.
- **File scan** reads options from `source` dict keys directly. **M365 scan** reads from `scan_opts = options.get("options", {})`. Both paths apply the same `_cpr_qualifies` / `_exif_has_pii` logic.
- **UI:** sidebar `#optSkipGps`, `#optMinCpr`, `#optCprOnly`, `#optOcrLang`; profile editor `#peOptSkipGps`, `#peOptMinCpr`, `#peOptCprOnly`, `#peOptOcrLang`. All saved/loaded by `profiles.js`.

## Memory management — scan_engine.py

- **Email body stripped at collection time** — `_scan_user_email` stores body as `msg["_precomputed_body"]`, deletes `msg["body"]` and `msg["bodyPreview"]`. Processing loop reads `meta.pop("_precomputed_body", "")`. Do not re-add `body` to `$select` without also stripping it.
- **`body_excerpt`** — 500-char plain-text preview stored per flagged email; flows into `flagged_items`, checkpoint JSON, and DB. Do not remove before broadcasting — needed for preview on checkpoint resume.
- **`work_items` → `deque` before processing** — drained via `popleft()` so each item's memory is released immediately. Do not convert back to a list.
- **`del content` / `del body_text`** — raw bytes and body text deleted immediately after use. Both hit and no-hit paths have explicit deletes.
- **PDF OCR rendered page-by-page** — `convert_from_path(first_page=N, last_page=N)` inside the loop; only one page image in memory at a time. Do NOT revert to a bulk call — triggers OOM on large PDFs.
- **OCR memory guard** — `_ocr_mem_ok()` checks `psutil.virtual_memory().available >= 500 MB` before each page render.
- **Memory guard** — `psutil.virtual_memory().available` checked before each M365 file download; skips if < 300 MB free.

## Scan history browser — gdpr_db.py

- **`get_sessions(limit=50, window_seconds=300)`** — groups `scans` rows by 300 s window. Groups built ascending, returned descending. `ref_scan_id` is the highest `scan_id` in each group. Do not change window size independently of `get_session_items`.
- **`get_session_items(ref_scan_id=N)`** — anchors 300 s window to that scan's `started_at`. Window is **symmetric**: `started_at BETWEEN ref.started_at - 300 AND ref.started_at + 300`. Do not revert to a one-sided lower bound.
- **`get_related_items(item_id, ref_scan_id, window_seconds=300)`** — self-joins `cpr_index` to find items sharing ≥1 CPR hash. Uses same 300 s symmetric window — do not change independently.
- **`account_name` (display name) is persisted** (migration 11) so DB-loaded cards show the user badge. Legacy rows predating it have `account_name=''` — the frontend `_accountPill` resolves a fallback and still shows the group badge from `user_role`. `save_item` must keep writing `card["account_name"]` (both M365 and Google cards carry it).
- **Scans must be finalised or their items are invisible** — `get_session_items`, `get_open_items`, and `latest_scan_id` all filter on `finished_at IS NOT NULL`. The file scan finalises in a `finally`; M365 (`run_scan`) and Google (`_run_google_scan`) `return` early on abort, so each now calls `finish_scan` before that abort-return. A process kill (deploy/OOM/crash) mid-scan still strands a scan → **`finalize_orphan_scans()`** runs once at server startup (`gdpr_scanner.py` `__main__`, before the scheduler) and finalises every `finished_at IS NULL` scan (safe because nothing is scanning at boot). Do not add a scan-results query that ignores `finished_at` instead of fixing finalisation.
- **`get_open_items()`** — returns every flagged item with **no action taken**, across **all** scans (not just the latest session window). "Open" = no `dispositions` row, or one whose `status='unreviewed'`. Because `flagged_items` PK is `(id, scan_id)`, the same item recurs per scan; the query dedupes by `id`, keeping the row from the highest finished `scan_id`. This powers the **default landing view** so items don't drop out of sight once a newer scan opens a fresh session.
- **`GET /api/db/flagged`** — **with `?ref=N`** → `get_session_items(ref_scan_id=N)` (history mode); **without ref** → `get_open_items()` (default + viewer). Viewer scope enforcement applies to both. Do not change the no-ref `get_session_items()` default elsewhere (`export.py`, `scan_scheduler.py` still rely on latest-session for the current scan's report/email).
- See `static/js/CLAUDE.md` for the frontend history browser behaviour and `sse_replay_done` retry fix.

## Global gotchas

- **Pattern matching in Python** — when using `str.replace()` to patch JS/HTML, whitespace and quote style must match exactly. Use `in` check first and print if not found.
- **`__getattr__` on modules** — only resolves `module.name` access from outside, not bare name lookups inside function bodies. Always import directly.
- **`JSON.stringify` inside `onclick="…"` attributes** — produces double-quoted strings that terminate the HTML attribute early. Use single-quoted JS string literals instead, or `data-*` attributes read from the handler. When the object is embedded as an `onclick` payload, also `.replace(/"/g,'&quot;')` it (matches the delete/redact button pattern) so a `"` in a filename can't break out.
- **Escape scan-derived strings before `innerHTML`** — file names, account/display names, folders, and source labels come from scanned content and may contain markup. Pass them through `esc()` (in `results.js`) before embedding in `innerHTML` or `title=`/`alt=` attributes. Server-side SVG/HTML built from request params (e.g. `_placeholder_svg` for `/api/thumb`) must use `_html_esc`. Skipping either re-introduces stored/reflected XSS.
- **Secrets at rest use the machine-keyed Fernet** — the SMTP password and Claude API key are encrypted via `app_config._encrypt_password` / `_decrypt_password`. New secret-bearing config fields must follow the same pattern; read them through a decrypting accessor (e.g. `get_claude_api_key()`), never `_load_config().get(...)` directly.

## Directory-scoped rules

- `routes/CLAUDE.md` — SSE constraints, M365 exceptions, export, preview, audit log, email, scheduler, Claude NER, viewer route, Python gotchas
- `static/js/CLAUDE.md` — profile dropdown, progress bar, SSE teardown, history browser, CPR cross-referencing, sources panel resize, viewer JS, JS gotchas
- `templates/CLAUDE.md` — CSS variable names, sizing rules, badge standard, design rules
- `lang/CLAUDE.md` — i18n conventions
