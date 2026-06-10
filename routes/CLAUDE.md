# Routes — Architecture Rules

## SSE constraints
SSE routes must live in `gdpr_scanner.py`, not blueprints — blueprints can't stream.

M365 scan emits `scan_done`; Google emits `google_scan_done`; file scan emits `file_scan_done`. Never mix them up.

**`scan_start` is M365-only** — `run_scan()` broadcasts `scan_start`; `run_file_scan()` and `routes/google_scan.py` must NOT. The `scan_start` handler in `_attachSchedulerListeners` (scan.js) unconditionally sets `S._m365ScanRunning = true`. If a file scan emits `scan_start`, the flag is set with no matching `scan_done` to clear it — `file_scan_done` checks `!S._m365ScanRunning` before re-enabling the scan button, so the button stays disabled permanently after the scan completes.

## scan_progress source field
All three scan engines must include `"source": "m365"` / `"google"` / `"file"` in every `scan_progress` SSE event. Never remove this field — the frontend uses it to route progress to the correct segment.

## file_sources
`file_sources` in profiles are stored as source ID strings by the JS frontend. The scheduler resolves them via `_load_file_sources()` before calling `run_file_scan()`.

## Circular import prohibition
`scan_engine.py` and `gdpr_scanner.py` must not import each other. `scan_engine` imports from `sse`, `checkpoint`, `app_config`, `cpr_detector`; `gdpr_scanner` imports scan functions from `scan_engine`.

## `_scan_bytes` injection
`scan_engine.py` declares stub versions of `_scan_bytes` / `_scan_bytes_timeout` at module level. `gdpr_scanner.py` replaces them with the real `cpr_detector` implementations at startup. `routes/google_scan.py` pulls them from `gdpr_scanner` via `__getattr__`. Never import these directly in blueprint or engine modules — that breaks the circular-import barrier.

## M365 connector exceptions — m365_connector.py

Exception hierarchy (all inherit `M365Error(Exception)`):

| Exception | Trigger | Handler |
|---|---|---|
| `M365PermissionError` | 403 Forbidden | `scan_error` broadcast with human-readable permission hint |
| `M365DeltaTokenExpired` | 410 Gone on delta endpoint | Caller clears token and falls back to full scan |
| `M365DriveNotFound` | 404 Not Found on any path | `scan_phase` broadcast ("not provisioned — skipped") in `_scan_user_onedrive`; full-scan path's `except Exception: return` also silences it |

**`M365DriveNotFound` — why it exists:** `_get()` previously fell through to `raise_for_status()` on 404, which was caught by the generic `except Exception` handler and broadcast as a red `scan_error`. Adding the specific exception makes the delta path consistent with the full-scan path: a user without a provisioned OneDrive is skipped silently. **Do not add a 404 handler to `_get()` that returns a fallback value** — that would silently mask genuine path bugs.

## Export — routes/export.py

- **`GDPRDb.get_session_sources()`** — returns a `set` of source-key strings for every scan in the current session window. Used by both `_build_excel_bytes()` and `_build_article30_docx()` to include zero-hit sources in summary tables. Do not derive the scanned-source set from `by_source` alone — that dict only contains sources with flagged items.
- **Excel Summary sheet** — shows all scanned sources (even with 0 items). Per-source tabs only created for sources with items.
- **ART.30 breakdown table** — iterates `scanned_sources` (not `by_source`) so Gmail, Drive, etc. appear with `0 | 0 | 0 | —` when the scan found nothing.
- **Role-filtered exports** — `_build_excel_bytes(role='')` and `_build_article30_docx(role='')` accept `role='student'` or `role='staff'`. A local `_items` list is built at the top of each function; GPS sheet, External transfers sheet, and Art.30 tables all see only the filtered subset. Filenames get `_elever` / `_ansatte` suffix.
- **`POST /api/redact_item`** — rewrites a file in-place with CPR numbers replaced by `██████-████` / `█` blocks, removes the card from the grid, logs a `"redacted"` disposition. Source types: `local` (DOCX/XLSX/CSV/TXT/PDF, written via temp+move), `onedrive`/`sharepoint`/`teams` (Graph download → redact → PUT, requires `Files.ReadWrite.All`), `gdrive` (Drive API, requires `drive` scope), `sftp` (paramiko read/write, item must still be in `state.flagged_items`), `smb` (smbprotocol `FILE_SUPERSEDE`). **Keep `_redactExts`/`_cloudRedactExts` in `results.js` and `_REDACT_EXTS`/`_GDRIVE_MIME_MAP`/`_ALL_REDACTABLE_TYPES` in `export.py` in sync** — the button and the route must agree.
- **PDF redaction** — `redact_pdf_secure` uses PyMuPDF `page.apply_redactions()` (physical removal). Falls back to reportlab overlay if PyMuPDF absent. Text pages use `find_cpr_char_bboxes`; scanned pages use OCR at 200 DPI + `find_cpr_image_bboxes`.

## Preview — routes/database.py

`GET /api/preview/<item_id>?source_type=…&account_id=…` dispatches by `source_type`:

- **`local` / `smb`** — re-reads from disk; renders images as data URIs, text/CSV/PDF/DOCX/XLSX inline.
- **`email`** — fetches M365 message body via Graph (requires `state.connector`).
- **`gmail`** — shows info card with "Open in Gmail" link (X-Frame-Options blocks embedding).
- **`gdrive`** — returns `https://drive.google.com/file/d/{id}/preview` iframe.
- **All other values** (M365 files) — calls Graph `/preview` POST; tries `drive_id`-based path first, then user-drive, then `/me/drive`.

**`_source_type` must be set in `google_scan.py`** — Gmail items need `meta["_source_type"] = "gmail"` and Drive items `"gdrive"` before `_broadcast_card`. Without it, cards fall through to the M365 branch, which calls Graph with a Gmail ID and gets a 404.

**`state.connector` guard** — only the `email` and M365 `else` branches require M365 auth. The `local`/`smb`/`gmail`/`gdrive` branches must not gate on `state.connector` — they work in Google-only deployments.

## Compliance audit log — gdpr_db.py + routes/

- **`audit_log` table** — created by `_DDL` (`CREATE TABLE IF NOT EXISTS`), auto-appears on next server start. Schema: `id, ts (Unix float), action, actor, detail, ip`.
- **`log_audit_event(action, detail, actor, ip)`** — module-level helper; silently no-ops on any exception. Import: `from gdpr_db import log_audit_event as _audit`.
- **`GET /api/audit_log?limit=200&action=<filter>`** — in `routes/app_routes.py`. No auth gate.
- **Recorded events** — `profile_save/delete`, `token_create/revoke`, `viewer_pin_set/change/clear`, `interface_pin_set/change/clear`, `source_add/update/delete`, `scheduler_job_save/delete`, `scan_start/stop`, `smtp_save`, `disposition`, `disposition_bulk`, `admin_pin_set/change`, `item_delete`, `item_redact`.
- **`actor` always empty** — no per-user login; field reserved for future use.

## Email sending — routes/email.py + m365_connector.py

- **`_post()` returns `{}` on empty body** — Graph `sendMail` returns HTTP 202 with no body; `r.json()` on empty raises `JSONDecodeError`. Do not revert to unconditional `r.json()`.
- **Graph preferred over SMTP** — `smtp_test` and `send_report` try `_send_email_graph()` first; fall back to SMTP only if Graph raises. If Graph fails and no SMTP host saved, the Graph exception surfaces directly.
- **Auto-email after manual scan** — `_maybe_send_auto_email()` in `routes/scan.py` called from the `_run()` thread after `run_scan()` returns. Reads `smtp_cfg.get("auto_email_manual")`; no-ops if false, no flagged items, or no recipients.
- **Gmail vs Google Workspace** — auth error handlers check if SMTP username ends in `@gmail.com`/`@googlemail.com`; custom domains are treated as Google Workspace and error message points to the Workspace admin console.

## Scheduler — scan_scheduler.py + routes/scheduler.py

- **Job config keys** — `id`, `name`, `enabled`, `frequency` (daily/weekly/monthly), `day_of_week`, `day_of_month`, `hour`, `minute`, `profile_id`, `auto_email`, `auto_retention`, `retention_years`, `fiscal_year_end`, `report_only`. Stored in `~/.gdprscanner/schedule.json`.
- **`_execute_scan(job_id)`** — acquires per-job lock (`_running_jobs` set), records DB run via `db.begin_schedule_run()`, runs M365 → file → Google pipeline, then emails and applies retention. DB run finalised in `finally`.
- **Report-only path** — when `report_only=True`, short-circuits before M365 auth check, populates `_m.flagged_items` from `db.get_session_items()` if empty, calls `_send_email_report()`. Does NOT acquire scan lock; fails with `RuntimeError("No scan results available")` if DB is also empty.
- **`_m.flagged_items` and `state.flagged_items` are the same object** — assigned at startup; in-place updates (`flagged_items[:] = ...`) propagate to both.
- **`scheduler_started` / `scheduler_done` SSE events** — separate from `scan_done` (M365). `scheduler_done` carries `flagged`, `scanned`, `emailed`, `job_name`.
- **Profile options merge into file sources** — scheduler unpacks `{**fs, **_fs_extra}` before calling `run_file_scan(fs)`. Do not pass `fs` directly — the file scan reads `source.get(...)` and silently falls back to defaults without the merge.

## Claude NER — document_scanner.py + app_config.py + routes/app_routes.py

Optional AI-powered NER replacing spaCy. Activated via `config.json` keys `claude_ner` (bool) and `claude_api_key` (str, **Fernet-encrypted at rest** with an `enc:` prefix — same scheme as the SMTP password).

- **`ANTHROPIC_OK`** — module-level flag in `document_scanner.py`; `True` if `anthropic` is importable. Guards all Claude code paths.
- **`_ner_claude(text, api_key)`** — calls `claude-haiku-4-5-20251001` in 8 000-char chunks. Thread-safe cache keyed by `hash(text)`, evicts oldest when > 2 000 entries.
- **Always read the key via `app_config.get_claude_api_key()`** — it decrypts and transparently handles legacy plaintext. Never read `config.json["claude_api_key"]` directly; `save_claude_config()` writes it encrypted.
- **`GET/POST /api/settings/claude`** — GET returns `{"enabled": bool, "api_key_set": bool}` (never exposes key). POST accepts `{"enabled": bool, "api_key": "..."}` — omitting `api_key` leaves stored key unchanged.
- **`POST /api/settings/claude/test`** — minimal 8-token API call; returns `{"ok": true}` or `{"ok": false, "error": "..."}`.
- **Do not import `anthropic` at module level outside `document_scanner.py`** — `routes/app_routes.py` imports it locally inside the function body so the server starts without the package.

## Viewer mode — routes/viewer.py

- **`/view` auth chain** — token (`?token=`) → session cookie (`session["viewer_ok"]`) → PIN form → 403. Never skip this order.
- **Token scope** — stored as `"scope": {"role": "student"|"staff"}`, `{"user": [...], "display_name": "..."}`, or `{}` in `viewer_tokens.json`. Enforced server-side in `GET /api/db/flagged`. **Column name is `user_role`** — do not use `role`.
- **`session["viewer_scope"]`** — set at `/view` token validation. `GET /api/db/flagged` reads `session.get("viewer_scope", {})` — defaults to `{}` (unrestricted) for PIN-authenticated sessions.
- **`viewer_tokens.json` format** — `{"tokens": [...], "__pin__": {"hash": "…", "salt": "…"}}`. Old bare-list format handled transparently. Do not write as bare list.
- **Rate-limit state** (`_pin_attempts` dict) — in-memory only, resets on server restart. Intentional.
- **User-scoped tokens** — `scope.user` always a list; legacy single-string coerced on read. File-scan items (`account_id = ""`) never appear in user-scoped views. `POST /api/viewer/tokens` rejects combined `role`+`user` scope with 400.
- **Date-range scoping** — `valid_from`/`valid_to` (YYYY-MM-DD) in scope dict; filtered via lexicographic string comparison in `GET /api/db/flagged`. Server validates format and enforces `valid_from ≤ valid_to`.
- **`app.secret_key`** — derived from `machine_id` bytes so sessions survive restarts. Set once at startup; do not override.
- **Flask binds to `0.0.0.0`** — `gdpr_scanner.py`, `m365_launcher.py`, and `build_gdpr.py` all use `host="0.0.0.0"`. Internal loopback URLs intentionally keep `127.0.0.1`.

## Gotchas

- **`_load_settings()` return** — does NOT include `file_sources`. Returns only: sources, user_ids, options, retention_years, fiscal_year_end, email_to.
- **`_save_settings()` clobbers profile fields** — called on every M365 scan start with only M365 sources/user_ids/options. The fix in `app_config.py` preserves `google_sources` and `file_sources` and rebuilds `sources` as `m365_src + google_src + file_src`. Do not simplify away this merge logic.
- **`loadLastScanSummary()` timing** — must only be called after the first `/api/scan/status` poll resolves (inside `_sseWatchdog` in `results.js`, guarded by `_initialStatusChecked`). Calling it on `DOMContentLoaded` shows a stale "no results" card during a live scan after a hard refresh.
