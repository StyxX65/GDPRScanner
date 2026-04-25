# SUGGESTIONS — Feature ideas and implementation history

This document tracks every significant feature idea: what was proposed, whether it was implemented, and why decisions were made the way they were. Read this before adding a feature — the reasoning behind past decisions is often non-obvious.

**Status key:** ✅ Done · ✗ Won't do · ○ Open

---

## §1 — M365 email, OneDrive, SharePoint, Teams scanning ✅

Core premise: scan Microsoft 365 tenants for CPR numbers across all major storage surfaces — Exchange mailboxes (all folders, recursive), OneDrive personal drives, SharePoint document libraries, and Teams channel file storage — using the Microsoft Graph API.

**Implemented:** v1.0.0. The `m365_connector.py` client handles auth (application mode + delegated device-code flow), delta tokens, attachment download, and all four scan surfaces. Results stream card-by-card via SSE.

---

## §2 — Incremental / delta scanning ✅

Re-scanning a large tenant on every run is too slow for regular compliance use. Microsoft Graph provides `/delta` endpoints for Exchange, OneDrive, and SharePoint that return only items changed since the last sync token.

**Implemented:** v1.0.0. Delta tokens saved per-user in `~/.gdprscanner/delta.json`. Checkpoint saves mid-scan progress so interrupted runs can resume. `M365DeltaTokenExpired` exception handles the 410 Gone case by falling back to a full scan.

---

## §3 — Article 9 special category detection ✅

CPR numbers alone do not tell you whether the data is especially sensitive. Files containing health diagnoses, criminal records, trade union membership, etc. alongside CPR numbers carry significantly higher GDPR risk and may trigger DPIA requirements (Art. 35).

**Implemented:** v1.2.0. `keywords/da.json` (459 Danish keywords, 9 Art. 9 categories). Proximity filter: a keyword only triggers when within 150 characters of a CPR number, or always if no CPRs are in the document. Purple `⚠ Art. 9` badge on result cards. Art. 30 export gains a DPIA warning when Art. 9 items are present.

**Why proximity:** Pure keyword presence is too noisy — every GDPR policy document would be flagged. Proximity to a CPR number is a meaningful signal that the document actually concerns a specific individual.

---

## §4 — Data subject lookup (Art. 15/17) ✅

Schools must be able to answer subject access requests: "what data do you hold about me?" and delete it on request (Art. 17). This requires a cross-source query by CPR number.

**Implemented:** v1.0.0. SHA-256 hash of the CPR query compared against stored hashes — the plaintext CPR is never written to the database. Bulk delete with audit logging. Result count and source breakdown returned.

---

## §5 — Disposition tagging and review workflow ✅

Without a way to mark items as reviewed, every scan produces the same undifferentiated pile. Compliance officers need to track what has been actioned, what is being retained, and what is scheduled for deletion.

**Implemented:** v1.0.0. Five disposition states: Unreviewed / Retain (legal basis / legitimate interest / contract) / Delete-scheduled / Deleted. Filter bar, preview panel dropdown, Excel export column. Headless auto-delete runs on `delete-scheduled` items during scheduled scans.

---

## §6 — Article 30 processing register export ✅

Danish public authorities are required to maintain a GDPR Article 30 processing register. Generating one manually from scan results is error-prone and time-consuming.

**Implemented:** v1.0.0. Structured `.docx` export with summary, data categories, staff/student inventory split, retention analysis, compliance trend, deletion audit log, and methodology section. Updated in every major feature release to include new sources (Google, local/SMB), new risk categories (EXIF GPS, faces), and new fields.

---

## §7 — Retention policy enforcement ✅

GDPR Art. 5(1)(e) requires personal data not be kept longer than necessary. Schools often use a rolling retention policy (e.g. 5 years) or a fiscal-year-end cutoff (e.g. Dec 31 per Bogføringsloven).

**Implemented:** v1.0.0. Configurable retention years + fiscal year end. `🗓 Overdue` badge on cards whose modified date exceeds the cutoff. Bulk delete quick filter. Headless `--retention-years` + `--fiscal-year-end` flags for automated enforcement. Auto-retention flag on scheduled scans.

---

## §8 — Local folder and SMB/CIFS network share scanning ✅

Most Danish schools also have file servers (Windows Server, Synology NAS, QNAP) that are not covered by Microsoft 365 or Google Workspace. CPR numbers stored in shared drives are a significant risk.

**Implemented:** v1.4.0. `file_scanner.py` — unified local + SMB iterator. `smbprotocol` for direct SMB2/3 without requiring a mount. Credential storage via OS keychain (`keyring`). Results write to the same database as M365/Google items. Source badges: `📁 Local` / `🌐 Network`.

**Why smbprotocol instead of requiring a mount:** mounts require elevated privileges and are not available in the packaged desktop app. `smbprotocol` connects directly over TCP.

---

## §9 — Biometric photo scanning (Art. 9) ✅

Photographs of identifiable people are biometric data under GDPR Art. 9 regardless of whether they contain CPR numbers. Schools routinely have student photos in OneDrive and SharePoint.

**Implemented:** v1.3.0. Optional `scan_photos` flag (opt-in — slower). `_detect_photo_faces()` uses OpenCV Haar cascade detection via `document_scanner`. Items flagged when `face_count > 0` even without CPR hits. `📷 N faces` badge on cards.

**Opt-in rationale:** Haar cascade detection on large tenants adds significant scan time. Enable for targeted compliance audits, not routine scans.

---

## §10 — Google Workspace scanning (Gmail + Drive) ✅

Mixed Microsoft/Google environments are common in Danish schools. Gmail and Google Drive are outside the M365 scan scope.

**Implemented:** v1.5.9. `google_connector.py` — service account OAuth with domain-wide delegation. Gmail message + attachment iterator. Drive file iterator with automatic export of native Docs/Sheets/Slides → DOCX/XLSX/PPTX before scanning. Results write to the same database with `source_type = "gmail"` or `"gdrive"`.

---

## §11 — Database export and import ✅

Compliance records need to be portable — for archiving, sharing with a DPO tool, or migrating between installations.

**Implemented:** v1.2.3. `GET /api/db/export` streams a ZIP of 8 JSON files (CPR hashes only, thumbnails stripped). `POST /api/db/import` supports merge (dispositions + deletion log only) or replace (full wipe and restore). CLI flags: `--export-db`, `--import-db`, `--import-mode`.

---

## §12 — Internationalisation (i18n) ✅

The scanner is used by Danish, German, and English-speaking staff. Hardcoded Danish strings exclude other users.

**Implemented:** v1.0.0 with `.lang` key-value files. Migrated to flat JSON in v1.6.3 (§27). Language switching applied in-place — no page reload, scan results preserved. Three languages: Danish (primary), English, German.

---

## §13 — Article 9 keyword matching compiled to regex ✅

Sequential `str.find()` over 459 keywords becomes measurable overhead when scanning large email bodies across thousands of items.

**Implemented:** v1.2.3. `_load_keywords()` compiles one `re.Pattern` per Article 9 category at startup using a longest-first alternation. Short keywords retain word-boundary anchors to prevent substring false positives. ~10–50× faster for large tenants.

---

## §14 — Manual role overrides ✅

Microsoft SKU IDs are not exhaustive — new licences, benefit add-ons, and custom arrangements mean some users are always misclassified. Admins need a way to correct individual users without waiting for a SKU map update.

**Implemented:** v1.3.2. Click the role badge on any user row to cycle: auto → student → staff → other → clear. Overrides persisted to `~/.gdprscanner/role_overrides.json`. Applied at display time and scan time so all role-filtered views are correct.

---

## §15 — Named, reusable scan profiles ✅

Running the same scan repeatedly (e.g. all staff accounts, Email + OneDrive only, 5-year retention) requires reconfiguring the sidebar every time. Profiles should capture the full scan state and be reusable in both UI and headless/scheduled runs.

**Implemented across multiple releases:**
- §15a (v1.2.1) — backend profile storage, migration from flat settings, profile CRUD API
- §15b (v1.2.1) — CLI flags: `--list-profiles`, `--save-profile`, `--delete-profile`, `--profile`
- §15c (v1.2.2) — profile dropdown in topbar + 💾 save button
- §15d (v1.2.3) — profile management modal (list, use, duplicate, delete)
- §15e (v1.6.3/v1.6.4) — full two-panel editor (all sidebar sections mirrored, including Google and file sources)
- §15f (v1.6.3) — scheduler uses profiles including file sources; `file_sources` saved in profiles

---

## §16 — Unified source management modal ✅

Azure credentials, per-source toggles, and file source management were split across three separate sidebar locations. The credential form in particular belonged in a modal, not exposed in the main UI.

**Implemented:** v1.4.1. Single **⚙ Sources** button opens a tabbed modal: Microsoft 365 tab (credentials + per-source visibility toggles), Google Workspace tab, File sources tab. The sidebar shows only the source panel with the configured sources — no credentials visible.

---

## §17 — Unified source management modal ✅

*(See §16 — these are the same feature, §16 is the canonical entry.)*

---

## §18 — EXIF metadata extraction from images ✅

GPS coordinates in smartphone photos are Art. 9-adjacent data in a school context — they reveal where a student or staff member was. EXIF author/comment fields can contain personal data added by software (e.g. desktop publishing tools).

**Implemented:** v1.4.4. `_extract_exif()` extracts GPS (converted to decimal degrees + Google Maps link), author/artist/copyright/description/keywords/user-comment fields from JPEG, PNG, TIFF, WEBP, HEIC. Images flagged even without CPR when GPS or PII-bearing EXIF fields are present. Runs regardless of the `scan_photos` toggle (lightweight — no CV processing).

---

## §19 — Scheduled / automatic scans ✅

Manual scans require someone to remember to run them. GDPR compliance is an ongoing obligation — scanning should run automatically on a configurable cadence without requiring cron or Task Scheduler outside the app.

**Implemented:** v1.5.3. In-process APScheduler with one job per enabled schedule. Supports daily/weekly/monthly, time-of-day, profile selector, auto-email, auto-retention. Config in `~/.gdprscanner/schedule.json`. Multiple independent named jobs added in v1.5.4. Scheduled scans reuse the full `run_scan()` pipeline — checkpoint, delta, broadcast, DB.

---

## §20 — PDF OCR via multiprocessing ✅

Tesseract/Poppler subprocesses used for OCR on image-only PDFs cannot be killed from a Python thread. A hung OCR process blocks the scan thread indefinitely.

**Implemented:** v1.6.5. `_scan_bytes_timeout()` in `cpr_detector.py` spawns a fresh subprocess via `multiprocessing.get_context("spawn")` with a 60-second hard timeout. Process tree terminated if the timeout fires. Image-only PDF detection via `pdfplumber` (text layer check) before spawning avoids OCR entirely for scanned documents — the most common cause of hangs.

**Why spawn context (not fork):** `fork` inherits Flask's open file descriptors and threading state, causing deadlocks in multiprocessing workers on macOS. `spawn` starts clean.

---

## §21 — SSE event replay for mid-scan browser connections ✅

Opening the browser while a scan is already running (common for scheduled scans) showed nothing until the next SSE event fired. The in-progress result cards and log were lost.

**Implemented:** v1.5.6 (replay buffer) + v1.5.8 (scheduled scan visibility). `_sse_buffer: deque(maxlen=500)` stores all broadcast events. New clients receive the full buffer replay, then switch to live events. Module identity fix (`sys.modules["m365_scanner"] = sys.modules[__name__]`) ensures the scheduler broadcasts to the same SSE queues the browser is reading.

---

## §22 — SMB pre-fetch sliding window ✅

SMB scans were single-threaded: read file → scan → read next. On high-latency NAS connections the idle time waiting for the next read dominated scan time. A stalled NAS read also blocked the scan thread indefinitely.

**Implemented:** v1.6.5. `_smb_collect()` phase walks the tree (directory listing only). `_iter_smb()` phase feeds files through a 5-slot `ThreadPoolExecutor` with a 60-second per-file hard timeout. Stalled reads produce an error card and the scan continues.

---

## §23 — Google Workspace role classification + cross-platform identity mapping ✅

Google Workspace users need the same student/staff classification as M365 users for Art. 30 inventory splits and role-scoped exports. In a mixed environment, the same person has both an M365 UPN and a GWS email — they should appear as one person in the accounts list.

**Implemented:** v1.6.3.
- OU-based role classification: `classification/google_ou_roles.json` maps Organisational Unit paths to roles (edit to match your school's structure; default: `/Elever` → student, `/Personale` → staff).
- `google_connector.list_users()` fetches `orgUnitPath` via `projection=full` and classifies each user.
- Cross-platform identity: M365 and GWS accounts are matched by `displayName` (not email prefix — display names are maintained from the same AD source). Matched users show a `M365+GWS` badge and share a combined row in the accounts panel.

---

## §24 — Rename: M365 Scanner → GDPRScanner ✅

The tool now scans M365, Google Workspace, local file systems, and SMB shares. "M365 Scanner" was misleading for users setting up Google or file scanning.

**Implemented:** v1.6.0. All files renamed (`m365_scanner.py` → `gdpr_scanner.py`, etc.). Config files renamed on first startup via migration shim — existing data preserved automatically. `m365_connector.py` intentionally unchanged (accurately describes the Microsoft Graph connector).

---

## §25 — Split `gdpr_scanner.py` into focused modules ✅

`gdpr_scanner.py` was 9 600 lines. Every feature PR touched the same monolith, causing merge conflicts. Unit tests could not import scan logic without pulling in Flask, MSAL, and the entire app.

**Implemented:** v1.6.1. Five new modules: `sse.py`, `checkpoint.py`, `app_config.py`, `cpr_detector.py`, `scan_engine.py`. `gdpr_scanner.py` imports and re-exports them; blueprints use `__getattr__` for lazy resolution to avoid circular imports.

**Why `__getattr__` on the module:** blueprints were already resolving names from `gdpr_scanner` at call time. Swapping to direct imports would have required touching every blueprint route. The lazy hook keeps the diff minimal and reversible.

---

## §26 — pytest test suite ✅

Compliance software has no tolerance for regressions in CPR detection. Manual testing is not sufficient.

**Implemented:** v1.6.2. 128 tests across 4 modules: `test_document_scanner.py` (CPR detection accuracy and false positive checks), `test_app_config.py` (i18n, keywords, config, profiles, encryption), `test_checkpoint.py` (checkpoint and delta token persistence), `test_db.py` (scan lifecycle, CPR hash-only storage, dispositions). All tests pass in CI.

---

## §27 — Migrate i18n format from `.lang` to JSON ✅

`.lang` files are a bespoke key=value format with no tooling support. JSON is standard, diff-friendly, and parseable by any editor with a JSON schema plugin.

**Implemented:** v1.6.3. `lang/en.json`, `da.json`, `de.json` — 709 keys each, flat JSON. `app_config.py` loader prefers `.json`, falls back to `.lang` for backward compatibility. Old `.lang` files retained as fallback.

---

## §28 — Personal use disposition value ✅

Staff members sometimes store personal files (not work-related) on work equipment. These files are outside GDPR scope per Art. 2(2)(c) but reviewers currently had no way to record that determination — everything had to be "retain" or "delete".

**Implemented:** v1.6.2. New disposition: **Personal use — out of scope**. Art. 30 report labels it "Personal use — out of GDPR scope (Art. 2(2)(c))".

---

## §29 — Rename `skus/` → `classification/` ✅

`skus/` only described M365 SKU data. The directory now also contains Google Workspace OU role mappings — the name was misleading.

**Implemented:** v1.6.3. `skus/education.json` → `classification/m365_skus.json`. `skus/google_ou_roles.json` → `classification/google_ou_roles.json`. All path references updated.

---

## §30 — Personal Google account OAuth ✅

Service account + domain-wide delegation requires a Google Workspace admin to configure. Personal Gmail users and small organisations without Workspace admin access were excluded.

**Implemented:** v1.6.5. `PersonalGoogleConnector` — device-code OAuth flow (mirrors M365 delegated mode). Token persisted to `~/.gdprscanner/google_token.json`. `list_users()` returns a single-item list so the scan engine needs no changes. Auth-mode toggle in the Sources modal (Workspace / Personal account).

---

## §31 — Built-in user manual ✅

The scanner is used by school administrators and municipal compliance officers with no technical background. External documentation links go stale and are not available offline.

**Implemented:** v1.6.5. `docs/manuals/MANUAL-EN.md` and `MANUAL-DA.md` — 14 sections covering all major features in plain language. `GET /manual` route converts Markdown to a self-contained HTML page with no external dependencies. **`?` button** in the topbar opens the manual in a dedicated window. Bundled in the PyInstaller app.

---

## §32 — Windowed mode for Profiles, Sources, and Settings ✗ Won't do

**Proposal:** open Profiles, Sources, and Settings as resizable windows instead of full-screen modals so the results grid remains visible alongside configuration.

**Why not:** The workflow is sequential — configure → scan → review. There is no realistic scenario where a configuration modal and the results grid need to be open simultaneously. Sources is already visible in the sidebar during scanning. The least-work path (Option A, inline iframe) still loads the full JS stack twice and introduces message-passing complexity. The UX gain does not justify the implementation cost or the ongoing maintenance burden.

---

## §33 — Read-only viewer mode with PIN/token URL ✅

DPOs, school principals, and compliance coordinators need to review scan results and tag dispositions without access to scan controls, Azure credentials, or settings. Giving them full admin access is not appropriate.

**Implemented:** v1.6.14. Token-based share links (`/view?token=…`) and PIN alternative. Viewer mode hides the entire sidebar, log panel, scan/stop buttons, and delete controls. Disposition tagging remains fully functional. Viewer tokens support expiry (7d/30d/90d/1yr/never). PIN stored as salted SHA-256 hash. Brute-force guard: 5 failures per IP per 5 minutes.

---

## §34 — User-scoped viewer tokens ✅

Role-scoped tokens (#33) let a DPO see all students or all staff. But an individual employee asked "what data do you have about me?" under Art. 15 should see only their own items — not everyone in their role group.

**Implemented:** v1.6.17. Token scope `{"user": ["alice@m365.dk", "alice@gws.dk"], "display_name": "Alice Smith"}` filters `flagged_items` by `account_id IN (list)`, covering both M365 and GWS items. Share modal gains a **User** scope option with searchable name autocomplete backed by the loaded account list. Viewer header shows the person's full name in a locked identity badge.

**Why a list of emails (not a single field):** the same person has different `account_id` values in M365 (`alice@school.dk` UPN) and Google Workspace (`alice.smith@school.dk` GWS email). Both must be included to cover items from either platform.

---

## §35 — Scan history browser ✅

After a page reload, the previous scan's results were gone — no way to return to them without running a new scan.

**Implemented:** v1.6.17. Past scan sessions grouped by 300-second concurrent-scan window. `GET /api/db/sessions` returns a newest-first list with timestamps, sources, item count, and delta flag. Session picker dropdown in a history banner above the filter bar. Auto-loads the most recent completed session on page load when no scan is running. Starting a new scan exits history mode.

---

## §36 — Interface PIN ✅

In school environments the scanner is often left running on a workstation in an IT room. Any passer-by could open `http://localhost:5100` and access scan results or credentials.

**Implemented:** v1.6.21. Optional 4–8 digit PIN set in **Settings → Security → Interface PIN**. Unauthenticated requests to the main UI or API redirect to `/login`. `/view` and viewer auth routes are completely exempt — reviewer links are unaffected. Salted SHA-256 hash stored in `config.json`. Rate-limited: 5 failures per IP per 5 minutes.

---

## §37 — Google Drive delta scan ✅

Google Drive scans always re-downloaded every file on every run, regardless of what had changed. This made repeated scans of large Google Drives impractical.

**Implemented:** v1.6.21. Uses the Google Drive Changes API. First delta-enabled run records a start page token per user (`gdrive:{email}` in `delta.json`). Subsequent runs call `conn.get_drive_changes()` and process only changed/new files. Invalid tokens fall back to a full scan automatically. Token save loads `delta.json` fresh before writing to avoid racing with concurrent M365 token saves.

---

## §38 — Route integration tests ✅

Security-sensitive paths (viewer token auth, role/user scope enforcement, interface PIN gate) had no automated coverage. The only way a role-scope regression would be caught was manually testing a share link — which nobody did, and a real bug went undetected (`row.get("role")` vs. `row.get("user_role")`).

**Implemented:** 44 Flask test-client tests in `tests/test_route_integration.py` covering: viewer token CRUD and scope validation, `GET /api/db/flagged` role and user scope enforcement, bulk disposition isolation (untouched items stay unreviewed), viewer PIN (set/verify/rate-limit/change/clear), interface PIN gate with multi-step flows, scan lock always released on `run_scan()` exception, `GET /api/db/sessions` shape and newest-first ordering. All tests run against a tmp-path in-memory database — no cloud credentials required.

**Bugs caught and fixed:**
- `routes/database.py` role scope filter used `row.get("role")` — column is `user_role`. Role-scoped tokens returned an empty list for all users.
- `gdpr_db.get_session_items(ref_scan_id=N)` had no upper time bound — historical session queries included all subsequent scans. Fixed with `BETWEEN ref - 300 AND ref + 300`.

**Why test the interface PIN gate separately:** the `before_request` hook in `gdpr_scanner.py` blocks ALL API routes (including `/api/interface/pin` itself) once a PIN is set. Multi-step PIN tests must inject `session["interface_ok"] = True` after the first PIN-set request — otherwise the gate blocks subsequent requests in the same test.

---

## Open ideas

### Streaming / generator scan pattern for very large tenants

Current M365 scan: collect all work items first (all users' emails + files), then process. For tenants >500k emails the `work_items` deque can still be several GB even after stripping email HTML. The fix is to process each user's items inline as they are fetched — generator/streaming pattern — so memory is bounded to one user's items at a time.

**Estimate:** 1–2 days. Requires careful refactoring of `run_scan()` in `scan_engine.py`. Not urgent until a tenant of that size is encountered.

### Bulk redaction

Write redacted copies of flagged files with CPR numbers replaced by `XXX XXXX-XXXX`. Would require writing back to OneDrive/SharePoint/Google Drive (upload with the same filename). Legally complex — redaction must be audited. Low priority until a school explicitly requests it.

### Email notification on scan completion (non-scheduled) ✅

Auto-email now fires on manual scans when **Email report after manual scan** is enabled in Settings → Email report. Toggle stored as `auto_email_manual` in `smtp.json`. Implemented in `routes/scan.py` — `_maybe_send_auto_email()` is called from the `_run()` thread after `run_scan()` returns. Same Graph-first → SMTP-fallback pattern as scheduled scans. Only fires when there are flagged items and at least one recipient is configured.

### Phase 2 PII: name-based roster lookup

Flag documents containing the full names of students or staff — even when no CPR is present. Implementation outline:

1. **Roster source** — pull names from the M365 directory (`/users?$select=displayName`), the GWS directory (`admin.list_users`), or a user-uploaded CSV. Store as a flat list of `(first, last)` pairs, minimum length threshold (~5 chars per part) to suppress common first-name noise.
2. **Multi-pattern search** — build an Aho-Corasick automaton from the roster at scan start (`pyahocorasick`, ~50 KB, optional dep). Run each extracted text through the automaton; a hit qualifies only when the match falls on a word boundary and both first + last name appear within a configurable window (e.g. 100 characters apart).
3. **Integration** — same `_find_emails_phones`-style helper in `cpr_detector.py`; roster loaded once per scan run and passed as a parameter. New `name_count` column in `flagged_items` (DB migration). New `name-badge` in the UI. Opt-in profile toggle like `scan_emails`.
4. **NER fallback** — optionally run `spaCy` `da_core_news_sm` (~200 MB) when no roster is available to detect PERSON entities. Much higher false-positive rate; only useful as a discovery tool.

**Why deferred:** requires a roster-management UI (upload CSV, choose directory source, refresh cadence), and false-positive rate depends heavily on roster quality. Name-only matches also carry lower legal weight than CPR hits. Implement after a school explicitly requests it.
