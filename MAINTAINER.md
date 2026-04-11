# Maintainer Guide

*Written for future Henrik — assuming Python proficiency, returning after time away.*

---

## The short version

When something breaks, the structure tells you where to look.
When you want to add something, `SUGGESTIONS.md` has the context.
When you're unsure if a change broke anything, run `pytest tests/`.

---

## Project structure

```
gdpr_scanner.py        Entry point. Flask app, route definitions, blueprint
                       registration, CLI argument handling. Thin coordinator —
                       it imports from the modules below and re-exports them.

sse.py                 Server-Sent Events. broadcast(), the SSE queues, and
                       the replay buffer. Touch this if live progress breaks.

checkpoint.py          Scan checkpoint and delta token persistence. Touch this
                       if resume/incremental scanning breaks.

app_config.py          Everything configuration: i18n loading, Article 9
                       keywords, admin PIN, scan profiles, SMTP config, file
                       source definitions, Fernet encryption. Touch this if
                       settings, language, or profiles break.

cpr_detector.py        CPR detection engine. _scan_bytes() dispatches to the
                       right scanner by file type. Touch this if detection
                       accuracy changes or file type support is needed.

scan_engine.py         M365 and file-system scan orchestration. run_scan() and
                       run_file_scan(). The most complex file — ~1000 lines.
                       Touch this for scan behaviour, collection logic, or
                       new M365 sources.

gdpr_db.py             SQLite persistence layer. ScanDB class. Touch this for
                       DB schema changes, new tables, or query logic.

document_scanner.py    CPR regex, NER, OCR, face detection, PDF/DOCX/XLSX
                       scanning. Pre-existing module — treat as a dependency.
                       Avoid modifying unless you really need to.

m365_connector.py      Microsoft Graph API client. Auth, token refresh, all
                       the iter_* fetchers. Touch this for M365 API changes.

google_connector.py    Google Workspace connector. Service account auth, Gmail
                       and Drive iterators. Touch this for Google API changes.

routes/                Flask blueprints — one file per functional area.
  auth.py              M365 sign-in / sign-out / device code flow
  scan.py              /api/scan/start, /api/scan/stop, /api/scan/status
  export.py            Excel and Article 30 Word export
  database.py          DB query endpoints (stats, trend, overdue, subject lookup)
  users.py             User listing, role classification, SKU debug
  sources.py           File source management (local and SMB)
  profiles.py          Scan profile CRUD
  email.py             Email report sending via SMTP / Graph API
  scheduler.py         APScheduler integration
  google_auth.py       Google service account connect / disconnect
  google_scan.py       Google Workspace scan start / cancel / users
  app_routes.py        Misc: about, language selector, settings, delta status

tests/                 pytest test suite — 112 tests, all should pass.
  test_document_scanner.py   CPR detection accuracy and false positive checks
  test_app_config.py         i18n, keywords, config, profiles, encryption
  test_checkpoint.py         Checkpoint and delta token persistence
  test_db.py                 Database round-trips, CPR hashing, dispositions
```

---

## When something breaks

**Scan finds nothing / wrong count**
→ `cpr_detector.py` → `_scan_bytes()` and `_scan_text_direct()`
→ `scan_engine.py` → `run_scan()` for M365, `run_file_scan()` for files

**Progress bar / live log not updating**
→ `sse.py` → `broadcast()`
→ `gdpr_scanner.py` → `scan_stream()` — check `sse._current_scan_id`
→ `static/app.js` → `_attachScanListeners()` and `scan_progress` handler

**Cards not appearing after scan**
→ `static/app.js` → `scan_file_flagged` handler → calls `applyFilters()`
→ `static/app.js` → `scan_done` handler → shows `filterBar`

**Export (Excel / Art.30) fails**
→ `routes/export.py` → checks `state.flagged_items`, falls back to DB
→ If DB is empty, a scan has not been run or results were cleared

**Authentication / sign-in issues**
→ `routes/auth.py` for M365
→ `routes/google_auth.py` for Google Workspace
→ `gdpr_scanner.py` — `_connector = _state.connector = ...` must stay dual-assigned

**Settings stats show 0 (Scanned / Flagged / Scans)**
→ `routes/database.py` → `db_stats()` — queries `flagged_items` and `scans` directly
→ Stats populate from existing DB on app start — no re-scan needed
→ If still 0 after a completed scan: check `~/.gdpr_scanner.db` exists and is not empty

**File scan results not persisting to DB**
→ `scan_engine.py` → `run_file_scan()` — must call `_db.begin_scan()` not `start_scan()`
→ Check terminal output for `[db] begin_scan failed` to confirm

**Settings / profiles / language not loading**
→ `app_config.py`
→ Config files live in `~/` — see the migration shim in `gdpr_scanner.py` for paths

**Scheduled scans not running or not showing in UI**
→ `scan_scheduler.py` / `scheduler.py`
→ `routes/scheduler.py`
→ Schedule config: `~/.gdpr_scanner_schedule.json`

---

## Running the tests

```bash
cd GDPRScanner_v1.6.x
pytest tests/
```

Run this before every release and after any change to:
- `document_scanner.py` — CPR detection
- `cpr_detector.py` — file type dispatch
- `gdpr_db.py` — database layer

A failing CPR detection test is a compliance issue, not just a software bug.

---

## Key data files (all in `~/`)

All data files live in **`~/.gdprscanner/`** (created automatically on first run).
Existing `~/.gdpr_scanner_*` files are migrated automatically.

| File | Contents |
|---|---|
| `scanner.db` | SQLite — all scan results, CPR index, dispositions, history |
| `config.json` | Azure client ID / tenant ID |
| `settings.json` | Last-used scan options |
| `schedule.json` | Scheduled scan configuration |
| `token.json` | Cached MSAL token (delegated mode) |
| `delta.json` | Microsoft Graph delta tokens |
| `checkpoint.json` | Mid-scan checkpoint (deleted on completion) |
| `smtp.json` | SMTP config (password Fernet-encrypted) |
| `machine_id` | Fernet key for SMTP password — never move without this |
| `role_overrides.json` | Manual staff/student role overrides |
| `google_sa.json` | Google service account key (chmod 600) |
| `google.json` | Google admin email and source toggle state |
| `src_toggles.json` | Source panel toggle state (Email, OneDrive, Gmail, etc.) |

---

## The files you will rarely touch

- `document_scanner.py` — treat as a dependency
- `build_gdpr.py` — only when adding new `.py` files to the project (bundle the new file in the `datas` list)
- `install_windows.ps1` / `install_macos.sh` — only when adding new pip dependencies

---

## Adding a new pip dependency

1. Add to `requirements.txt` with a version pin and a comment
2. Add to `install_windows.ps1` (the packages array)
3. Add to `install_macos.sh` (the packages array)
4. If building the app: no change needed — PyInstaller follows imports automatically

---

## The documents that have the history

| Document | What it contains |
|---|---|
| `SUGGESTIONS.md` | Every feature idea, why it was or wasn't implemented, current status |
| `CHANGELOG.md` | What changed in each version, including root causes of bugs fixed |
| `CONTRIBUTING.md` | How to contribute, code style, translation guide |
| `DEPENDENCIES.md` | What each dependency is for and why it was chosen |

When you're unsure why something was done a certain way, read `SUGGESTIONS.md` first.
When you're debugging a regression, read `CHANGELOG.md` for the version where it appeared.

---

## The one thing to know about the module split

`gdpr_scanner.py` imports from all five sub-modules and re-exports them.
The Flask blueprints in `routes/` use `__getattr__` to lazily resolve names
from `gdpr_scanner` — so they work unchanged even though the code moved.

If you add a new function to `app_config.py` or `cpr_detector.py` and need
it accessible from a route blueprint, add it to the `from app_config import (...)`
block near the top of `gdpr_scanner.py`.

---

*This project was built by Henrik Højmark with AI assistance (Claude by Anthropic)
as a pair-programming tool. All design decisions were made by the author.*
