# GDPRScanner — GDPR Improvement Suggestions

These suggestions are grounded in GDPR requirements and the current state of the scanner. Items are ordered by compliance impact. All build on existing infrastructure (CPR detection, NER, Excel export, headless mode, delta scan, SQLite DB).

> **Note:** File and config names currently use the `m365_scanner` / `m365_` prefix throughout. These will be renamed to `gdpr_scanner` / `gdpr_` as part of suggestion #24.

---

## 1. Retention policy enforcement ✅

**GDPR reference:** Article 5(1)(e) — storage limitation

**What was done:**

- **Options panel** — 🗓 Retention policy toggle with configurable years (default 5) and fiscal year end selector: Rolling (today) / 31 Dec Bogføringsloven / 30 Jun / 31 Mar. Live cutoff hint updates as settings change.
- **`overdue_cutoff(years, fiscal_year_end)`** — standalone helper in `m365_db.py` computing the correct cutoff in two modes:
  - *Rolling*: exactly N years before today — correct for GDPR data minimisation
  - *Fiscal year*: N years before the last completed fiscal year end — correct for Bogføringsloven (e.g. Dec 31 FY: items from FY ending 2020-12-31 expired on 2025-12-31)
- **🗓 Overdue badge** — amber badge on cards in both grid and list view when an item's modified date falls before the cutoff. `markOverdueCards()` queries `/api/db/overdue` after each scan and re-renders affected cards.
- **Bulk delete** — **🗓 Filter overdue** quick button in the bulk-delete modal pre-populates the "Older than date" filter with the exact cutoff date from the DB. **Clear filters** button resets all filters.
- **`GET /api/db/overdue`** — accepts `years`, `fiscal_year_end`, `scan_id`; returns `{count, cutoff_date, cutoff_mode, items}`.
- **Headless auto-delete** — `--retention-years N` and `--fiscal-year-end MM-DD` CLI flags. Non-interactive (cron): deletes automatically. Interactive (TTY): prompts for confirmation. Reports deleted/failed counts.
- **`_do_retention_delete()`** — shared helper supporting email, OneDrive, SharePoint, and Teams items; removes from in-memory list and SQLite after each successful delete.

---

## 2. Article 30 report (Register of Processing Activities) ✅

**GDPR reference:** Article 30 — Records of processing activities

**What was done:** `_build_article30_docx()` in `m365_scanner.py` generates a structured Word document (`.docx`) via `python-docx`. Accessible via `GET /api/export_article30` and the **📋 Art.30** button in the filter bar.

**Document sections:**

| Section | Contents |
|---|---|
| Cover page | Title, generation timestamp |
| 1. Summary | Scan date, items scanned, flagged count, total CPR hits, estimated data subjects, overdue count; per-source breakdown table |
| 2. Data categories | Every detected PII type with hit counts and GDPR classification (Art. 9 vs Art. 4); CPR and sensitive entries highlighted |
| 3. Data inventory | Full item list (≤500 rows) sorted overdue-first; columns: name, source, account, modified date, CPR hits, compliance disposition; overdue rows amber-highlighted |
| 4. Retention analysis | Separate table of overdue items for easy review (only if overdue items exist) |
| 5. Compliance trend | Last 10 scans with date, flagged count, overdue count, scan type (only if scan history exists) |
| 6. Methodology | Scanning approach, GDPR articles referenced (Art. 5, 9, 15, 17, 30) |

**Data sources used:** `db.get_stats()`, `db.get_flagged_items()`, `db.get_overdue_items()`, `db.get_trend()`, `db.get_disposition()`, `pii_hits` table aggregation, `flagged_items` in-memory list (fallback when DB unavailable).

**Impact:** Directly satisfies the Article 30 obligation. Produces a dated, printable compliance document that can be shown to a supervisory authority on request.

---

## 3. Sensitive category detection (Article 9) ✅

**GDPR reference:** Article 9 — Processing of special categories of personal data

**Problem:** GDPR imposes stricter requirements on data revealing health, racial/ethnic origin, religious beliefs, trade union membership, and criminal records. The scanner currently treats all personal data at the same risk level.

**Fix:** Add a keyword list for each Article 9 category, checked in the same pass as CPR scanning. When a keyword match occurs near a personal identifier (within ~150 characters), the file is flagged as **Special category data** with a distinct badge and automatically elevated to HIGH risk.

**Danish keyword examples:**

| Category | Keywords |
|---|---|
| Health | diagnose, sygemelding, indlæggelse, behandling, medicin, handicap, psykiatri, kræft, diabetes |
| Criminal records | straffeoplysning, dom, straffeattest, sigtelse, fængsling, bøde |
| Trade union | fagforening, tillidsrepræsentant, strejke, overenskomst |
| Religion | kirke, moské, religiøs, baptism, konfirmation |
| Ethnicity | nationalitet, herkomst, etnicitet |

The keyword list is configurable and stored in `keywords/da.json` (following the same pattern as `lang/da.lang`). Additional language files (`keywords/en.json`, `keywords/de.json`) can be added without code changes. A `special_category` column should be added to `flagged_items` in the DB and included in `scan_history`.

**What was done:**

- `keywords/da.json` — 454 keywords across 9 Article 9 categories (health, mental health, criminal, trade union, religion, ethnicity, political, biometric, sexual orientation); stored in `keywords/` subfolder mirroring `lang/`
- `_load_keywords()` — loads keyword file at startup matching current language; falls back to `da.json`
- `_check_special_category(text, cprs)` — proximity-aware detection: keywords only trigger when within 150 characters of a CPR number (reduces false positives); short keywords (≤4 chars) use whole-word boundary matching to avoid substring matches
- Card badge — purple **⚠ Art.9 — health, mental_health** pill shown on flagged cards in grid view
- Filter bar — "Art. 9 only" dropdown option to filter the results grid
- Excel export — "Special category" column added to all per-source sheets
- Article 30 report — highlighted row in summary; dedicated section listing detected categories with count table and full item list (capped at 50)
- DB — `special_category` column (JSON array) added to `flagged_items` via migration #3; count written to `scan_history.special_category` after each scan
- Translated — EN / DA / DE (17 new keys per language)
- All tests pass: 10/10 detection scenarios including edge cases (no CPR fallback, substring false positive prevention)

**Impact:** Highest audit priority — supervisory authorities specifically look for Article 9 data.

---

## 4. Data subject index ✅

**GDPR reference:** Article 15 (right of access), Article 17 (right to erasure)

**What was done:** The SQLite layer (`m365_db.py`) implements the full backend:

- `cpr_index` table stores `(SHA-256(cpr), item_id, scan_id)` — CPR numbers are never stored in plaintext
- `lookup_data_subject(cpr)` returns all flagged items containing a given CPR across all scans
- `POST /api/db/subject` API endpoint accepts a CPR, hashes it, and returns matching items
- `delete_item_record()` removes items from the index when deleted from M365

**What was done (UI):**
- 🔍 **Data subject lookup** button in the sidebar opens a modal
- CPR input field (Enter-to-search), results list showing name, source type, date, and CPR hit count
- **Delete all for this person** button triggers bulk deletion with `reason="data-subject-request"`, refreshes grid
- All deletions logged in the `deletion_log` table with reason and actor
- CPR is SHA-256 hashed before querying — never stored or transmitted in plaintext

---

## 5. External sharing / data transfer detection ✅

**GDPR reference:** Article 44–46 — transfers to third countries

**Problem:** Emails forwarded to external domains or files shared outside the organisation represent potential unauthorised data transfers. The scanner does not currently distinguish between internal and external recipients.

**What was done:**

- **Email:** fetches `toRecipients` and `ccRecipients` from Graph API; compares recipient domains against the tenant domain (resolved from the signed-in user's UPN); flags items where any recipient is external with `transfer_risk = "external-recipient"`. Badge: **⚠ Ext.**
- **OneDrive / SharePoint / Teams:** fetches the `shared` property on all drive items; flags files with external sharing links (`scope: anonymous`) as `"external-share"` and organisation-wide links as `"shared"`. Badge: **🔗**
- **Filter bar dropdown** — "All items / External recipient / Externally shared / Shared" filters the results grid
- **Card badges** — orange `⚠ Ext.` pill for external email recipients; blue `🔗` pill for shared files
- **Excel export** — dedicated red-tabbed **External transfers** sheet with all flagged external items; highlighted row in the Summary sheet
- **DB** — `transfer_risk` column added to `flagged_items` via migration #2; persisted alongside all other card data
- **Translated** — EN / DA / DE

**Impact:** Identifies the highest-risk data exposure scenarios — data that has potentially already left the organisation's control.

---

## 6. Legal basis and disposition tagging ✅

**GDPR reference:** Article 5(1)(a) — lawfulness, Article 30

**What was done:** The SQLite layer implements the full backend:

- `dispositions` table stores `(item_id, status, legal_basis, notes, reviewed_by, reviewed_at)`
- `set_disposition()` / `get_disposition()` methods
- `POST /api/db/disposition` and `GET /api/db/disposition/<id>` API routes

**Disposition values:**

| Value | Meaning |
|---|---|
| `unreviewed` | Default |
| `retain-legal` | Must keep (e.g. Regnskabsloven) |
| `retain-legitimate` | Justified retention |
| `retain-contract` | Part of an active contract |
| `delete-scheduled` | Mark for deletion at next cleanup run |
| `deleted` | Already actioned |

**What was done (UI):**
- Disposition dropdown in the preview panel meta strip — loads current status on open, saves on click
- **Filter bar dropdown** — filter the results grid by disposition status alongside source and search
- Disposition cached on `flaggedData` items after first view — filter works without extra API calls
- Saving a disposition while a filter is active immediately re-applies the filter
- **Clear filters (×)** resets the disposition dropdown alongside search and source
- **Excel export** — Disposition column added to all per-source sheets
- **Headless auto-delete** — after each scan, items tagged `delete-scheduled` are automatically deleted (interactive: prompts for confirmation; non-interactive/cron: deletes automatically); each deletion is logged in the `deletion_log` table with `reason="bulk"` and actor identity

---

## 7. Compliance trend tracking ✅

**GDPR reference:** Article 5(2) — accountability principle

**What was done:** The SQLite layer implements the full backend:

- `scan_history` table records per-scan aggregates: `(scan_date, flagged_count, overdue_count, deleted_count, sources_json)`
- `finish_scan()` writes a history row automatically after every completed scan
- `get_trend(n)` returns the last N rows ordered by date
- `GET /api/db/trend` API endpoint

**What was done (UI):**
- Sparkline panel embedded in the sidebar Stats section, shown after first scan or on login if DB has history
- Blue solid line = flagged count over last 10 scans; amber dashed line = overdue count
- Shaded fill under the flagged line; dot on the latest data point
- Hover tooltip showing exact date, flagged count, and overdue count
- Trend change badge (↓ 17% / ↑ 5%) showing % movement vs previous scan in green/red
- Date labels at first, middle, and last scan
- Redraws on window resize; refreshes after every scan completes
- Hidden until at least 2 scans exist in the DB

---


## 8. File system scanning — local and network (SMB/CIFS) ✅

**GDPR reference:** Article 5(1)(c)(e) — data minimisation, storage limitation

**Background**

Many organisations store personal data on local workstations, external drives, and file servers (NAS devices accessible via SMB/CIFS) — not in Microsoft 365. Local and network file scanning share identical core logic: both ultimately hand a file path or byte stream to `document_scanner.py`. The only difference is how files are accessed. They are therefore treated as a single unified feature rather than two separate modules.

**Design — unified `FileScanner` connector**

```python
class FileScanner:
    def __init__(self, path, smb_host=None, smb_user=None, smb_password=None):
        self.is_smb = path.startswith("//") or path.startswith("\\\\")
        # SMB without mount: use smbprotocol directly
        # SMB with mount, or local path: use os.walk()

    def iter_files(self, extensions=None):
        # Yields (relative_path, bytes_or_stream, metadata) regardless of source
        ...
```

The scanner calls `iter_files()` without knowing whether the files are local or remote. Results go into the same SQLite database as M365 items with `source_type = "local"` or `"smb"`, so the Article 30 report and data subject lookup cover all sources in a single view.

**Connection approaches**

| Mode | How | When to use |
|---|---|---|
| Local path | `os.walk()` on any local or mounted path | Workstations, USB drives, already-mounted network shares |
| Native SMB (`smbprotocol`) | Direct connection without mounting — programmatic auth | Headless/scheduled scans, no admin rights to mount |

If `smbprotocol` is not installed, the scanner falls back gracefully to local-path mode with a warning. This keeps the dependency optional — users who only need local scanning don't need to install it.

**Credential security (SMB)**

| Method | How | Notes |
|---|---|---|
| OS keychain (`keyring`) | `keyring.set_password("gdpr-scanner-nas", user, pw)` | Best — password never touches the filesystem |
| Environment variables | `NAS_USER` / `NAS_PASSWORD` | Good for headless/cron |
| `.env` file (chmod 600) | `python-dotenv` | Acceptable fallback — already in `.gitignore` |
| Kerberos / NTLM | `smbprotocol` uses domain ticket | No stored credentials — best for domain environments |

**New optional dependencies**

```
smbprotocol>=1.13    # Native SMB2/3 — optional, falls back to local-only without it
keyring>=25.0        # OS keychain credential storage — optional
python-dotenv>=1.0   # .env file loading for headless mode — optional
```

**New CLI flags**

```bash
# Scan a local folder
python m365_scanner.py --scan-path ~/Documents

# Scan a network share (native SMB)
python m365_scanner.py --scan-path //nas.school.dk/shares \
  --smb-user "DOMAIN\henrik" --smb-keychain-key gdpr-scanner-nas

# Store SMB credentials in OS keychain (one-time setup)
python m365_scanner.py --smb-store-creds --smb-host nas.school.dk \
  --smb-user "DOMAIN\henrik"

# Combine with headless M365 scan
python m365_scanner.py --headless --scan-path //nas/shares \
  --smb-user "DOMAIN\henrik" --output ~/Reports/
```

**Impact:** Closes the most common blind spot — years of personal data sitting on old file servers and teacher workstations that have never been scanned. A school scanning both M365 and its file server in a single job gets a complete picture in one Article 30 report.

---

## 9. Photographs of pupils and staff (biometric data) ✅

**GDPR reference:** Article 9 (special categories — biometric data), Article 5(1)(b)(e) (purpose and storage limitation), Recital 38 (children), Databeskyttelsesloven §6

**Why this is different from ordinary personal data**

Photographs that can be used to uniquely identify a person qualify as **biometric data** under Article 9 GDPR — a special category requiring either explicit consent or one of the narrow legal bases in Article 9(2). This applies to school class photos, staff portraits, and any image where faces are clearly identifiable. A standard scan for CPR numbers will not detect photographs at all; this is a separate compliance risk that requires dedicated handling.

**Children require heightened protection**

Recital 38 specifically calls out children as deserving particular protection. In Denmark, Databeskyttelsesloven §6 sets the digital consent age at 15 — below that, a parent or guardian must give consent. Consent obtained in a school context is questionable in any case, given the power imbalance between school and family.

**Retention — no fixed statutory period**

Unlike accounting records, GDPR sets no specific number of years for school photographs. The applicable principles are:

| Principle | Implication for school photos |
|---|---|
| Purpose limitation (Art. 5(1)(b)) | Photos may only be kept while the original purpose remains valid. A class photo from 2018 documents the 2018 school year; after the pupil leaves, the purpose narrows sharply |
| Storage limitation (Art. 5(1)(e)) | Data must not be kept longer than necessary. No documented justification = must delete |
| Archiving / public interest (Art. 89) | Historical or cultural-heritage use can justify longer retention, but only with specific safeguards and typically requires the images to be non-individually identifiable or properly anonymised |

**Staff photographs**

The legal basis for staff photos is usually legitimate interest or the employment contract. Once a staff member leaves, retention requires a specific documented basis. Photos on public-facing websites (school homepage, social media) must be removed promptly after departure.

**Consent withdrawal**

If consent was the legal basis and a parent or former pupil withdraws it, the photo must be removed regardless of when it was taken. This applies to published photos (website, social media) immediately and to internal archives on request under Article 17.

**Datatilsynet guidance (Danish DPA)**

Datatilsynet has published specific guidance on schools and photography. The general position:
- Internal use (yearbooks, internal records) — retain for the duration of enrolment plus a short grace period; document the basis
- Website / social media — require valid consent; remove immediately on withdrawal
- Historical archive (pre-digital, cultural heritage) — assess case by case under Article 89
- Biometric use (facial recognition for access control) — strict rules, almost always requires explicit consent

**Proposed scanner feature**

Since CPR scanning cannot detect photographs, a separate detection pass is needed:

- **File type detection** — flag `.jpg`, `.jpeg`, `.png`, `.heic`, `.tiff`, `.mp4`, `.mov` files in OneDrive, SharePoint, and Teams as *potential biometric data*
- **Face detection** (already implemented in Document Scanner) — use OpenCV `haarcascade` to confirm at least one face is present before flagging
- **Age estimation heuristic** — optional: flag images with multiple faces (class photos) at higher risk than single portraits
- **Metadata** — check EXIF creation date; flag images older than the configurable retention threshold
- **Disposition tagging** — compliance officer reviews each flagged image and tags with legal basis (`retain-archive`, `retain-consent`, `delete-scheduled`, etc.)
- **Source note** — add image items to the Article 30 report under data category "Biometric data / photographs"

**Effort:** Medium — face detection is already available via OpenCV in the Document Scanner. The main work is wiring it into the M365 file scan pass and adding a dedicated results filter.

**Impact:** High — photographs are one of the most commonly overlooked GDPR risks in schools and public-sector organisations. Datatilsynet has issued enforcement actions against Danish schools specifically for unlawful retention of pupil photographs.

---

## 10. Google Workspace scanning (Gmail & Google Drive) ✅

**Background**

Many organisations run a mixed environment — Microsoft 365 for staff and administration, Google Workspace for some departments or as a legacy system. A scanner covering only M365 leaves Google data as a blind spot.

**What was done (v1.5.9)**

Option B (unified sources panel) was implemented:

- **`google_connector.py`** — service account auth with domain-wide delegation; `iter_gmail_messages()` yields message body + attachments; `iter_drive_files()` auto-exports native Docs/Sheets/Slides → DOCX/XLSX/PPTX before scanning; `list_users()` via Admin Directory API
- **`routes/google_auth.py`** — `/api/google/auth/status`, `/connect`, `/disconnect`; service account JSON key saved to `~/.gdpr_scanner_google_sa.json` (chmod 600); admin email persisted to `~/.gdpr_scanner_google.json`
- **`routes/google_scan.py`** — `/api/google/scan/start`, `/cancel`, `/users`; full scan loop reusing `_scan_bytes()` and `broadcast()` from the M365 engine; results written to the same SQLite DB with `source_type = "gmail"` or `"gdrive"`
- **Google Workspace tab** in Source Management activated (was "Coming soon" stub); service account key file upload; admin email field; Gmail and Google Drive source toggles; setup guide with required API scopes
- **Auto-restore** — connector rebuilt from saved key on startup
- **Dependencies added:** `google-auth>=2.0`, `google-auth-httplib2`, `google-api-python-client>=2.0` (optional — scanner starts without them)

**Known limitation (to address in #23)**

`routes/google_scan.py` currently writes `user_role: "other"` for all Google scan results. Role classification for Google accounts is covered by suggestion #23.

**Setup required in Google Workspace Admin Console:**
1. Create a Google Cloud project; enable Gmail API, Drive API, Admin SDK
2. Create a service account; download JSON key; enable domain-wide delegation
3. Add the service account client ID in Workspace Admin → Security → API Controls → Domain-wide delegation with scopes: `gmail.readonly`, `drive.readonly`, `admin.directory.user.readonly`

---

## 11. Database export / import ✅

**Background**

The SQLite database (`~/.m365_scanner.db`) accumulates scan history, flagged items, CPR index, dispositions, and the deletion audit log over time. Without export/import, there is no way to back it up, move it between machines, archive a completed compliance cycle, or share a snapshot with an auditor without transferring the raw database file.

**What was done (CLI)**

The core export and import logic is implemented in `m365_db.py` and wired into the CLI:

```bash
# Export — creates a structured ZIP archive
python m365_scanner.py --export-db ~/compliance/gdpr_export_2026.zip

# Import merge (default) — adds dispositions + deletion log, leaves existing data intact
python m365_scanner.py --import-db ~/compliance/gdpr_export_2026.zip

# Import replace — wipes DB first, then restores everything (prompts for confirm)
python m365_scanner.py --import-db ~/compliance/gdpr_export_2026.zip --import-mode replace --yes
```

**Export ZIP contents:**

| File | Contents |
|---|---|
| `export_meta.json` | Export date, schema version, row counts |
| `scans.json` | Scan run summaries |
| `flagged_items.json` | Flagged items — `thumb_b64` stripped to keep size small |
| `cpr_index.json` | CPR hashes (SHA-256 only — never raw CPR numbers) |
| `pii_hits.json` | Per-type PII counts per item |
| `dispositions.json` | Compliance decisions with legal basis and reviewer |
| `scan_history.json` | Aggregated trend data |
| `deletion_log.json` | Full deletion audit trail |

**Import modes:**

| Mode | Behaviour |
|---|---|
| `merge` (default) | Imports only `dispositions` and `deletion_log` — safe to run against a live DB |
| `replace` | Wipes the DB first, then imports all 7 tables — full backup/restore |

> ⚠ **Not fully tested in production yet.** The export/import cycle has been verified in unit tests (export → merge → replace all pass) but has not been tested against a real M365 scan database with thousands of rows, nor validated across different schema versions. Treat as beta — always keep a manual copy of `~/.m365_scanner.db` before running `--import-mode replace`.

**Known complication**

The `cpr_index` table is keyed by `(cpr_hash, item_id, scan_id)`. Importing into a DB with different scan IDs means the hashes are still valid for lookup but won't resolve to the correct scan context. Acceptable for archiving; a full fix requires remapping scan IDs on import.

**Remaining work**

- UI panel in the sidebar with **Export DB** and **Import DB** buttons (`GET /api/db/export`, `POST /api/db/import`)
- Import confirmation dialog showing row counts before proceeding
- Production testing with real scan databases
- Cross-version import testing (schema version mismatch handling)

**Impact:** Closes the gap between the scanner as a detection tool and a long-term compliance record. An auditor can request the export ZIP as evidence of ongoing GDPR monitoring activity.

---

## 12. ~~Network drive scanning (SMB / CIFS)~~ — retired

> Merged into **suggestion #8** (File system scanning — local and network). See #8 for the full specification including SMB connection approaches, credential security, and CLI flags.

---

## 13. Optimise Article 9 keyword matching with compiled regex ✅

**Background**

Suggestion #3 implemented Article 9 keyword detection using sequential `str.find()` calls — up to 459 iterations per flagged item. For typical school tenants (tens to a few hundred flagged items) the added cost is imperceptible (~1–5ms per item, ~100–500ms total). For larger tenants or tenants with many flagged items, the linear scan could add several seconds.

**Current approach**

```python
for kw, cat in _keyword_flat:          # up to 459 iterations
    idx = text_lower.find(kw, pos)     # sequential string search
```

**Proposed optimisation**

Compile one `re.search()` alternation per category at load time rather than looping `str.find()` at scan time:

```python
import re
_compiled_keywords: dict[str, re.Pattern] = {}

def _load_keywords(lang="da"):
    ...
    _compiled_keywords = {
        cat: re.compile(
            r"(?<![\w])" +                           # no preceding word char
            "(?:" + "|".join(re.escape(kw) for kw in sorted(kws, key=len, reverse=True)) + ")" +
            r"(?![\w])",                              # no following word char
            re.IGNORECASE
        )
        for cat, kws in categories.items()
    }
```

The regex engine uses optimised multi-pattern matching internally (similar to Aho-Corasick), making this roughly **10–50x faster** for large texts. The word-boundary anchors (`(?<![\w])` / `(?![\w])`) also reduce false positives from keywords that appear as substrings inside unrelated words.

**Impact by tenant size**

| Flagged items | Current (str.find) | Compiled regex | Saving |
|---|---|---|---|
| 100 | ~0.5s | ~0.01s | Negligible in both cases |
| 1,000 | ~5s | ~0.1s | ~5s |
| 10,000 | ~50s | ~1s | ~49s |

**When to implement**

Low priority for a typical school. Worth doing before releasing to larger organisations (universities, municipalities) where a single tenant scan may produce thousands of flagged items.

**Effort:** Small — change is confined to `_load_keywords()` and `_check_special_category()` in `m365_scanner.py`. No DB or UI changes needed.

---

## 14. Progress phase text improvements ✅

**Background**

Minor UI polish items related to the scan progress area.

**What was done:**

- **Phase text stuck after collection** — the blue phase text remained on the last "Collecting Teams…" message for the entire scan duration. Fixed by broadcasting a `scan_phase` event immediately after `scan_start`, replacing the collection message with "Scanner…" / "Scanning…" as soon as actual file scanning begins.

**Remaining ideas:**

- Show per-source progress counters in the phase text (e.g. "Scanning OneDrive — 42 / 180")
- Show current account name in the phase text during multi-user scans
- Animate phase text transitions with a subtle fade

---

## 15. Scan profiles — named, reusable scan configurations

**GDPR reference:** Article 5(2) — accountability; Article 30 — records of processing activities

**Background**

Currently all scan settings are stored as a single flat configuration. Scan profiles give each configuration a name, making them reusable from both the UI and headless CLI — enabling different scan schedules for different purposes without manual reconfiguration.

This feature is broken into 6 incremental steps that can each be shipped and tested independently.

---

### 15a. Backend profile storage ✅ *(Small)*

- Define the profile data structure (see below)
- Add `load_profiles()`, `save_profile()`, `delete_profile()`, `get_profile(name)` helpers
- On first run, migrate the existing flat `~/.m365_scanner_settings.json` to become a default profile named "Default"
- No UI changes — purely backend. Foundation for all subsequent steps.

**Profile data structure:**
```json
{
  "id": "uuid-1",
  "name": "Nightly email scan",
  "description": "Quick nightly CPR check on all Exchange mailboxes",
  "sources": ["email"],
  "user_ids": "all",
  "options": {
    "email_body": true,
    "attachments": false,
    "older_than_days": 0
  },
  "retention_years": null,
  "fiscal_year_end": null,
  "email_to": "compliance@school.dk",
  "file_sources": [],
  "last_run": "2026-03-19T02:00:00",
  "last_scan_id": 42
}
```

---

### 15b. CLI profile support ✅ *(Small)*

Immediately useful for headless/cron runs without any UI work:

```bash
# Run a named profile headlessly
python m365_scanner.py --headless --profile "Full compliance scan"

# List available profiles
python m365_scanner.py --list-profiles

# Save current settings as a new profile
python m365_scanner.py --save-profile "Nightly email" --sources email --email-to compliance@school.dk

# Delete a profile
python m365_scanner.py --delete-profile "Old scan"
```

Cron example — different profiles on different schedules:
```bash
0 2 * * *   ./venv/bin/python m365_scanner.py --headless --profile "Nightly email scan"
0 3 * * 1   ./venv/bin/python m365_scanner.py --headless --profile "Weekly M365 scan"
0 4 1 * *   ./venv/bin/python m365_scanner.py --headless --profile "Monthly full scan"
```

---

### 15c. ~~Profile selector in topbar~~ — dropped

The profile management modal (15d) already lets you select, edit, and run profiles. The scheduler (#19) handles automated runs. A topbar dropdown would add UI complexity for a workflow most users do infrequently.

**Dropped.** If you have a genuinely elegant solution that adds clear value without cluttering the topbar, open an issue — but the bar is high.

---

### 15d. Profile management modal ✅

- "Manage profiles" button opens a modal listing all profiles with last run date, sources summary, and edit/duplicate/delete buttons
- Creating a new profile copies the current sidebar state
- Makes profiles fully self-service from the UI without needing to edit JSON manually

---

### 15e. Full profile editor panel *(Medium)*

- Dedicated edit panel mirroring all sidebar options but saving to a named profile rather than applying immediately
- Without this, profiles can only be created from the current sidebar state — sufficient for most users but not ideal
- Polish step — implement after 15c and 15d are stable

---

### 15f. File source integration ✅

- ✅ `file_sources` array stored in profile data structure
- ✅ File sources defined once, reused across profiles (interactive UI)
- ✅ `saveProfile()` now saves actual checked file sources (was hardcoded `[]`)
- ✅ Scheduled scans now fire `run_file_scan()` for each file source in the profile
- ⏳ Profile editor does not yet show a dedicated file sources section (editing requires re-saving from sidebar)

---

**Article 30 integration (all steps)**

The Article 30 report includes the profile name and description in the scan metadata section, providing an audit trail of which configuration produced which results.

**Overall impact:** Transforms the scanner from a single-purpose tool into a multi-schedule compliance platform. Steps 15a + 15b alone deliver immediate CLI value with minimal effort.


---

## 16. Student/Staff role classification ✅

**GDPR reference:** Art. 30 (records of processing activities), Databeskyttelsesloven §6 (children under 15)

**What was done:**

- **Automatic role detection** — users are classified as 🎓 Student or 👔 Staff at login based on their Microsoft 365 licences, without requiring extra Azure permissions
- **Two-pass classification** in `m365_connector.classify_user_role()`:
  1. **`skuPartNumber` fragment match** (preferred) — strings like `STANDARDWOFFPACK_FACULTY` are stable across all Microsoft licensing generations; runs first whenever part numbers are available via `get_subscribed_skus()` or `build_sku_map_from_users()`
  2. **SKU ID lookup** from `classification/m365_skus.json` — fallback for when part numbers are unavailable or for licences with no recognisable fragment (e.g. Power Automate Free)
- **`classification/m365_skus.json`** — external file in `classification/` folder (mirrors `lang/`, `keywords/`); edit to add new SKU IDs without code changes; bundled into PyInstaller app via `build_m365.py`
- **Three-tier `get_subscribed_skus()`** — tries `/subscribedSkus` (admin), `/me/licenseDetails` (User.Read), then `build_sku_map_from_users()` (per-user sampling spread across full list) so part numbers are discovered regardless of permission level
- **Manual role override** — click the role badge (🎓/👔/❓) on any user row to cycle `student → staff → other → (clear)`; stored in `~/.m365_scanner_role_overrides.json`; ✎ indicator shows overridden rows; applied at both display time and scan time
- **🔍 SKU debug modal** — button next to role filters shows all tenant SKU IDs colour-coded known/unknown; unknown IDs are selectable text for pasting into `m365_skus.json`
- **Role filter buttons** — **All / 👔 Ansat / 🎓 Elev** filter the accounts list
- **Role badges on cards** — 🎓/👔 pill on every result card in grid and list view
- **Article 30 report** — Data Inventory section split into separate Staff and Student tables; parental consent note for students under 15 (Databeskyttelsesloven §6)
- **Excel export** — Role column on all per-source sheets
- **Translated** — EN / DA / DE

**Impact:** Required for Article 30 compliance in Danish schools — the staff/student distinction is legally significant under Databeskyttelsesloven §6.

---

## 17. Unified source management modal ✅

**Background**

The current sidebar has three separate, disconnected places for source configuration:
- The M365 connection panel (Azure credentials)
- The hardcoded Email / OneDrive / SharePoint / Teams checkboxes
- The 📁 File sources "Manage" button (local paths and SMB shares)

As the scanner grows to support more connectors (Google Workspace, local file systems, SMB), this fragmentation becomes unwieldy. A user who only scans local file servers should not be confronted with M365 connection UI. A user who only uses M365 should not see file source clutter.

**Proposed design — single ⚙ Sources button in the sidebar**

Replace the current patchwork with a single **"⚙ Sources"** button that opens a unified source management modal. The left column sources panel becomes a clean, read-only list of *active* sources with their status indicators.

**Modal sections:**

| Section | Contents |
|---|---|
| **Microsoft 365** | Azure app credentials (client ID, tenant ID, secret), auth mode toggle (Application / Delegated), per-source toggles (Email, OneDrive, SharePoint, Teams), visibility toggle (show/hide in sidebar) |
| **Google Workspace** | Google OAuth credentials (client ID, secret), per-source toggles (Gmail, Google Drive), visibility toggle — greyed out with "Coming soon" until implemented |
| **File sources** | Full list of saved local/SMB sources with Add/Edit/Delete; each has a visibility toggle |
| **Sidebar display** | Drag-to-reorder the sources shown in the left column; set which appear by default |

**Sidebar behaviour after this change:**

- Sources panel shows only sources the user has *enabled* for display
- Each row has a status dot (green = connected, amber = credential issue, grey = disabled)
- Scrolls at 5 visible rows as already implemented
- The panel is purely for selection — all configuration is in the modal

**Impact:** Cleaner onboarding (new users see only what's relevant), easier multi-connector setups, and a natural home for future connectors (Dropbox, SharePoint on-premises, SFTP) without adding more sidebar clutter.

---


## 18. EXIF metadata extraction from images ✅

**GDPR reference:** Art. 4 (personal data — location, identity), Art. 9 (biometric + location context)

**Background**

EXIF (Exchangeable Image File Format) metadata is embedded in JPEG, TIFF, and HEIC images by cameras and smartphones. It frequently contains:

- **GPS coordinates** — exact latitude/longitude where the photo was taken; personal data under Art. 4 and a significant privacy risk for photos of children or staff
- **Author / Artist / Copyright** — name of the photographer
- **Description / Subject / Keywords / Comment** — free-text fields that may contain names, diagnoses, or other PII
- **Device identifiers** — camera make/model, serial number, software
- **Timestamps** — DateTimeOriginal, DateTimeDigitized

**What was implemented:**

- **`_extract_exif(content: bytes, filename: str) -> dict`** — extracts structured EXIF data using `PIL.Image` (already a dependency). Returns GPS, author, description, timestamps, and device info.
- **GPS extraction** — converts DMS (degrees/minutes/seconds) rational values to decimal degrees; adds a Google Maps link.
- **PII fields** — Author, Artist, Copyright, Description, UserComment, ImageDescription, Subject, Keywords checked for content.
- **Risk classification:**
  - GPS present → `"gps"` added to `special_category`; card gets 🌍 GPS badge
  - PII-bearing EXIF fields → `"exif_pii"` added to `special_category`
- **Preview panel** — EXIF data shown in a collapsible section below the image with GPS map link
- **Art. 30 report** — photos with GPS are called out in the biometric/photo section with coordinates and map links
- **Excel export** — `gps_lat`, `gps_lon` columns added to image rows
- **No new dependencies** — uses `Pillow` which is already required

---


## 19. Scheduled / automatic scans ✅

**GDPR reference:** Art. 5(2) — accountability; Art. 32 — security of processing; Art. 25 — data protection by design

**Background**

A one-off scan is useful for an audit, but ongoing GDPR compliance requires regular, repeatable scanning. Personal data accumulates continuously — new emails arrive, files are uploaded, staff change. A scheduler removes the need for manual intervention and provides a documented, reproducible compliance cadence.

**Status:** Fully implemented in v1.5.5 (multi-job support, inline toggle, next-run display, auth fix). Settings → Scheduler tab supports multiple independent named scan jobs. Old single-job config files are migrated automatically.

**Proposed update to the existing Scheduler tab:**

**Each scheduled scan is a named job with:**
- **Name** — e.g. "Nightly tenant scan", "Weekly NAS archive"
- **Frequency** — daily, weekly, monthly, or custom cron expression
- **Time of day** — run at off-peak hours (e.g. 02:00)
- **Sources** — which sources to include (links to a saved profile)
- **Email report** — automatically send the Excel report after each run (uses existing SMTP config)
- **Retention** — optionally apply retention policy enforcement as part of the run
- **Enabled / disabled** toggle per job

**Settings → Scheduler tab UI:**

```
Scheduled scans
┌──────────────────────────────────────────────────────┐
│ ✔  Nightly tenant scan     Daily 02:00   Next: 01:23 │
│ ✔  Weekly NAS archive      Mon   03:00   Next: 6d    │
│ ✗  Ad-hoc test             Manual        Last: never  │
│ + Add scheduled scan                                   │
└──────────────────────────────────────────────────────┘
```

Each row has an enable/disable toggle, edit (✏) and delete buttons. Schedule configuration (name, frequency, profile, email) lives exclusively in the job editor modal — nothing schedule-related appears in the sidebar.

**Persistence:**
- All scheduled scan definitions stored in `~/.m365_scanner_schedule.json` (list)
- Last run time, next run time, and run history in the existing SQLite DB (`scan_schedules` table)
- Missed runs flagged in the UI (e.g. "Last run was 3 days ago — missed?")

**Log** — scheduled scans appear in the scan log with a 🕐 prefix

**Implementation notes:**
- `APScheduler` (MIT licence) is the most straightforward — `pip install apscheduler`
- Alternatively use `schedule` (simpler, no persistence) or a system-level cron job calling the existing CLI
- The scanner already supports `--scan-path`, `--smb-user`, and profile-based configuration via CLI — a cron-based approach using the CLI requires no new code, just documentation
- An in-process scheduler is more user-friendly (visible in the UI, no system access needed)

**Effort:** Medium — APScheduler integration + Settings tab + DB table + email trigger hook

---


## 20. PDF scanning in local/SMB file scans (multiprocessing timeout) ✅ Done

**What was done:**

PDFs were excluded from local/SMB file scans because Tesseract/Poppler subprocesses could not be stopped from a Python thread, causing indefinite hangs. Fixed by spawning each PDF scan in a dedicated process with a 60-second hard timeout.

**Implementation:**

- **`cpr_detector.py`** — `_worker_scan_pdf()` (module-level, required for `spawn` context) calls `document_scanner.scan_pdf()` and returns via a `multiprocessing.Queue`. `_scan_bytes_timeout()` writes PDF bytes to a temp file, spawns the worker via `multiprocessing.get_context("spawn")`, joins with 60s timeout, terminates if exceeded. Non-PDF files delegate to `_scan_bytes()` directly.
- **`scan_engine.py`** — `run_file_scan()` calls `_scan_bytes_timeout()` instead of `_scan_bytes()`. Stub added to module-level injected globals.
- **`gdpr_scanner.py`** — `_scan_bytes_timeout` imported from `cpr_detector` and injected into `scan_engine`.
- **`file_scanner.py`** — `.pdf` removed from `FILE_SCAN_EXTENSIONS` exclusion; all default extensions now included.

Key design choice: content is written to a temp file before spawning (avoids pickling up to 50 MB through the queue). `spawn` context is required on macOS + Flask to avoid duplicating the server socket.

---




## 21. SSE event replay for late-connecting browsers ✅

**Status:** Fully implemented in v1.5.8. Both manual and scheduled scans now
replay buffered SSE events to late-connecting browsers. Scheduled scans show
full live progress in the browser (progress bar, phase text, flagged cards, log
entries) exactly like manual scans.

**Background**

`broadcast()` pushes scan progress events (phase updates, flagged items, log
messages) over Server-Sent Events (SSE) to connected browser tabs. If a
scheduled scan starts before the browser is open, all events fire into the
void — the live log is empty when the user opens the UI mid-scan.

This affects scheduled scans specifically, but also manual scans started
in one tab and watched from another.

**What was done:**

**Module identity fix (critical):**
- When run as `python m365_scanner.py`, the module loads as `__main__`. The
  scheduler's `import m365_scanner as _m` loaded a **second copy** with its own
  empty `_sse_queues` — events from scheduled scans never reached the browser.
- **Fix:** `sys.modules["m365_scanner"] = sys.modules[__name__]` at the top of
  the module ensures all imports share one instance.

**SSE event replay:**
- **`_current_scan_id`** — unique timestamp-based ID (`scan_1711612345678` /
  `filescan_1711612345678`) set at the start of every scan and injected into
  every SSE event by `broadcast()`. Cleared automatically after `scan_done`.
- **`scan_stream()` replay filter** — on connect, replays only buffer events
  matching the current `scan_id` (avoids stale replay from a previous scan).
  Emits `sse_replay` / `sse_replay_done` marker events to bracket the
  replayed block.
- **`GET /api/scan/status`** — lightweight endpoint returning `{running, scan_id}`.
  Used by the polling watchdog and page-load check.

**Shared SSE listeners:**
- **`_attachScanListeners(es)`** / **`_attachSchedulerListeners(es)`** — shared
  JS functions used by both `startScan()` and `_autoConnectSSEIfRunning()`.
  Eliminates the duplication that caused the original bug.
- **`_attachSchedulerListeners`** now shows the progress bar on
  `scheduler_started` and hides it on `scheduler_done` / `scheduler_error`.
  Also listens for `scan_start` as a fallback to activate the progress UI if
  `scheduler_started` was missed (e.g. browser reconnected mid-scan).

**SSE connection resilience:**
- **Polling watchdog** (`_sseWatchdog`) — checks `/api/scan/status` every 4s.
  When a running scan is detected, ensures the SSE connection is alive via
  `_ensureSSE()` and shows the progress UI. Solves the problem of idle SSE
  connections being silently dropped by Flask/Werkzeug.
- **`_ensureSSE()`** — opens or reopens the SSE connection if dead
  (`readyState === CLOSED`), attaches all listeners.
- **`_userStartedScan` flag** — `scan_done` only closes the SSE connection for
  user-initiated scans; scheduled scans keep it alive for future events.
- **`es.onerror` fix** — no longer silently nulls `es` (EventSource
  auto-reconnects; nulling it broke reconnection).

**Other fixes:**
- **`scan_complete` → `scan_done`** — `run_file_scan()` was broadcasting
  `scan_complete` on finish, but the JS only listens for `scan_done`. Renamed
  for consistency with matching payload shape.
- **Resume scan profile fix** — `startScan()` now sends `profile_id` in the
  POST body; `_save_settings()` accepts `profile_id` so the correct profile is
  updated instead of always writing to Default.
- **i18n** — `m365_sse_reconnecting` and `m365_sse_replay_note` added (EN/DA/DE).
- **Diagnostic logging** — `[run_scan]` prints sources, user count, app_mode,
  and a sample user entry. Browser console logs `[SSE]` prefixed messages for
  all event types.

**Impact:** Closes the last gap in scheduled scan observability — scheduled
scans now show full live progress in the browser, and opening the browser
mid-scan replays buffered events.

---


## 22. Pre-fetch cache for SMB/local file scans ✅ Done

**What was done:**

SMB file reads now run in a `ThreadPoolExecutor` sliding window (`PREFETCH_WINDOW = 5`) with a per-read `SMB_READ_TIMEOUT = 60` second hard deadline. A stalled read yields an error sentinel and the scan continues — the scan thread is never blocked.

**Implementation (`file_scanner.py` only):**

- `_smb_collect()` — new method that walks the SMB directory tree (listing only, no reads), yielding `(display_rel, smb_path, size, modified, source_root)` tuples. Over-size files and directory-listing errors are emitted as `_COLLECT_SKIP` / `_COLLECT_ERROR` sentinels.
- `_iter_smb()` rewritten in two phases:
  1. Calls `_smb_collect()` to build the full candidate list (fast).
  2. Resolves sentinels immediately (yielded without entering the executor), then feeds real candidates through a `ThreadPoolExecutor` sliding window. `fut.result(timeout=SMB_READ_TIMEOUT)` gives each read a hard deadline; timed-out futures are cancelled and produce an error card in the UI.
- Local scanner (`_iter_local`) is untouched — local reads are fast and don't need buffering.
- No new dependencies.


## 22b. OOM on large SMB scans — Partially mitigated (v1.6.8 / v1.6.10)

**v1.6.8:** `PREFETCH_WINDOW` 5→2, `MAX_FILE_BYTES` 50→20 MB, PDF semaphore(1), GWS `del buf` before yield.

**v1.6.10:** Three additional buffer-lifetime fixes:
- `del content` in `_scan_bytes_timeout` after temp-file write — frees the 20 MB PDF buffer before the subprocess spawns its 150–300 MB heap
- `del content` in `run_file_scan` after thumbnail — frees raw bytes before card dict build and next iteration
- `PREFETCH_WINDOW` 2→1 — halves peak concurrent SMB read buffers (2 × 20 MB → 1 × 20 MB)

**Remaining risk:** under a very large SMB scan with many back-to-back PDFs the combined main-process + subprocess peak can still exceed available RAM on memory-constrained machines. If OOM recurs, `tracemalloc` profiling on a live scan is the next diagnostic step.

---

## 23. Google Workspace role classification + cross-platform identity mapping

**What was done (v1.6.2) — Phase 1**

- `classification/google_ou_roles.json` — OU prefix → role mapping file (same pattern as `classification/m365_skus.json`). Edit to match your school's OU structure; no code change required.
- `google_connector.py` — `list_users()` now fetches `orgUnitPath` (via `projection=full`) and calls `classify_ou_role()` to return `userRole` for each user
- `routes/google_scan.py` — role map built from `list_users()` result; each scan card now gets the correct `user_role` (`staff` / `student` / `other`) instead of always `"other"`
- Default mapping: `/Elever` → student, `/Personale` → staff (matches Gudenaaskolen.dk OU structure shown in screenshot)

**Background**

M365 staff/student role classification is fully implemented in suggestion #16
(licence SKU matching, manual overrides, Article 30 split by role). However,
Google Workspace scan results currently always write `user_role: "other"` —
and there is no mechanism to link the same person's M365 and Google identities
when both platforms are in use.

This suggestion extends role classification to Google Workspace and adds
cross-platform identity mapping for mixed deployments.

**Two real-world scenarios addressed**

| Scenario | Description |
|---|---|
| B | Google Workspace only — staff and students in same Workspace domain |
| C | Mixed M365 + Google, possibly different users on each platform |

Scenario C is the hard case: a municipality might have staff in M365 and
students in Google, or the same person on both platforms with different email
addresses and no shared identity provider. Scenario A (M365 only) is already
fully covered by #16.

---

**Proposed implementation — two phases**

### Phase 1 — Google role classification at scan time (small effort, high value)

Pull role from Google Directory during `list_users()`, before scanning begins.
No manual configuration required for standard Workspace deployments.

**Google Workspace — `google_connector.py` `list_users()`:**

| Signal | Mapping |
|---|---|
| `orgUnitPath` starts with `/Students/` or `/Elever/` | → `student` |
| `orgUnitPath` starts with `/Staff/` or `/Lærere/` or `/Ansatte/` | → `staff` |
| Primary email domain matches a configurable domain → role | → configurable |
| Member of a Google Group matching a configurable pattern | → role from group |

OU path prefixes and group name patterns are configurable in the Admin Settings
modal (a new "Role mapping" sub-tab under General).

**UI changes (Phase 1):**
- Google scan cards show role badge `👩‍🏫 Staff` / `🎒 Student` / `—` (M365 cards already do via #16)
- `user_role` written correctly for Google results (`staff` / `student` / `unknown`) instead of `"other"`
- Role filter and Article 30 role columns already exist from #16 — no additional UI work needed

---

### Phase 2 — Group/OU mapping rules + manual overrides + cross-platform identity (medium effort)

**Group/OU mapping rules UI** (Settings → Role mapping tab):

A rule list where each rule has:
```
IF  [field]          [operator]  [value]        THEN  [role]
IF  orgUnitPath      starts with /Elever         →    student
IF  group            member of   all-staff@...   →    staff
IF  department       contains    Lærer           →    staff
IF  email domain     equals      skole.dk        →    student
```

Rules evaluated in order; first match wins. Covers the mixed-platform case:
if staff are always `@kommune.dk` and students always `@skole.dk`, a single
domain rule classifies everyone with zero directory API calls.

**Manual override** (Users panel, per-user dropdown):

```
Auto (staff)  ▼
  Auto (staff)
  Staff
  Student
  Ignore       ← skips account entirely during scan (service accounts, shared mailboxes)
```

Stored in a new `user_roles` SQLite table. Survives restarts. "Ignore" is
immediately useful for service accounts and shared mailboxes that pollute
results.

**Cross-platform identity linking** (for Scenario C):

New `user_identities` table in `m365_db.py`:

```sql
CREATE TABLE user_identities (
    id            INTEGER PRIMARY KEY,
    canonical_id  TEXT NOT NULL,   -- internal UUID assigned by scanner
    platform      TEXT NOT NULL,   -- "m365" | "google"
    email         TEXT NOT NULL,
    display_name  TEXT,
    role          TEXT,            -- staff | student | unknown
    UNIQUE(platform, email)
);
```

Matching heuristics (applied automatically, in priority order):
1. Exact email match across platforms (most common — same address on both)
2. Same display name + same domain-suffix group
3. Manual link: drag one user card onto another in the Users panel to merge

Once linked, Article 30 reports and data subject lookups treat both accounts
as a single person entry:
> **Henrik Nielsen** — M365: 3 OneDrive files · Google: 12 Gmail messages · Role: Staff

**Dependencies to add:** none (all using existing APIs and DB patterns)

---

**Files to change**

| File | Change |
|---|---|
| `m365_connector.py` | `list_users()` returns `role` field derived from licenses/dept/groups |
| `google_connector.py` | `list_users()` returns `role` field derived from `orgUnitPath`/groups |
| `m365_db.py` | Add `user_roles` and `user_identities` tables; DB migration |
| `scan_engine.py` | Pass `role` through to `_broadcast_card()`; apply manual overrides before scan (file will exist after #25 splits `m365_scanner.py`) |
| `routes/google_scan.py` | Same role pass-through as M365 scan engine |
| `routes/app_routes.py` | New endpoints: `GET /api/user_roles`, `POST /api/user_roles/set`, `POST /api/user_roles/link` |
| `templates/index.html` | Role badge CSS; role filter pill; Settings → Role mapping tab |
| `static/app.js` | Role filter logic; role mapping rules editor; manual override dropdown; identity link drag-handle |
| `lang/*.lang` | i18n keys for role labels and mapping UI |

**Effort estimate:** Phase 1 ≈ 1 session · Phase 2 ≈ 2–3 sessions

**GDPR articles addressed:** Art. 5(1)(f) integrity and confidentiality,
Art. 25 data protection by design, Art. 30 records of processing activities
(role-segmented register), Art. 32 security of processing

---

---

## 24. Rename — M365 Scanner → GDPRScanner ✅

**What was done (v1.6.0)**

- `m365_scanner.py` → `gdpr_scanner.py`; `m365_db.py` → `gdpr_db.py`; `build_m365.*` → `build_gdpr.*`
- All `~/.m365_scanner_*` config and data paths renamed to `~/.gdpr_scanner_*`
- Migration shim in `gdpr_scanner.py` silently renames existing files on first startup — scan history, credentials, settings, and role overrides preserved automatically
- UI title, sidebar heading, About panel, document output strings, install scripts, CI workflow, README, CONTRIBUTING, DEPENDENCIES all updated
- `m365_connector.py` intentionally unchanged — the prefix correctly describes the Microsoft Graph connector
- i18n keys describing M365-specific UI (Azure credential fields, device code flow) intentionally keep `m365_` prefix

**Background**

The tool was originally built to scan Microsoft 365. It now scans M365, Google
Workspace, local file systems, and SMB network shares, and produces GDPR
compliance reports. The name "M365 Scanner" is actively misleading to new
users and limits adoption outside Microsoft-centric environments.

**Scope of changes**

This is a purely mechanical rename — no behaviour changes.

| What changes | From | To |
|---|---|---|
| Main entry point | `m365_scanner.py` | `gdpr_scanner.py` |
| M365 connector | `m365_connector.py` | `m365_connector.py` *(keep — it is specific to M365)* |
| Config file | `~/.m365_scanner.json` | `~/.gdpr_scanner.json` |
| Token cache | `~/.m365_scanner_token.json` | `~/.gdpr_scanner_token.json` |
| Database | `~/.m365_scanner.db` | `~/.gdpr_scanner.db` |
| Role overrides | `~/.m365_scanner_role_overrides.json` | `~/.gdpr_scanner_role_overrides.json` |
| Delta tokens | `~/.m365_scanner_delta.json` | `~/.gdpr_scanner_delta.json` |
| Settings | `~/.m365_scanner_settings.json` | `~/.gdpr_scanner_settings.json` |
| i18n key prefix | `m365_` | `gdpr_` *(or keep `m365_` for M365-specific keys)* |
| Window title | M365 Scanner | GDPRScanner |
| `<title>` in HTML | M365 Scanner | GDPRScanner |
| Sidebar heading | ☁️ M365 Scanner | 🔍 GDPRScanner |
| Build script | `build_m365.py`, `build_m365.sh` | `build_gdpr.py`, `build_gdpr.sh` |
| Install scripts | `install_windows.ps1`, `install_macos.sh` | *(rename optional — keep for compatibility)* |
| README | throughout | update all references |
| SUGGESTIONS.md | throughout | update all `m365_scanner.py` references |

**Migration shim (one-time, on first startup after rename)**

```python
# In gdpr_scanner.py startup — runs once, then removes itself
_OLD_FILES = {
    Path.home() / ".m365_scanner.json":               Path.home() / ".gdpr_scanner.json",
    Path.home() / ".m365_scanner.db":                 Path.home() / ".gdpr_scanner.db",
    Path.home() / ".m365_scanner_token.json":         Path.home() / ".gdpr_scanner_token.json",
    Path.home() / ".m365_scanner_delta.json":         Path.home() / ".gdpr_scanner_delta.json",
    Path.home() / ".m365_scanner_settings.json":      Path.home() / ".gdpr_scanner_settings.json",
    Path.home() / ".m365_scanner_role_overrides.json":Path.home() / ".gdpr_scanner_role_overrides.json",
}
for old, new in _OLD_FILES.items():
    if old.exists() and not new.exists():
        old.rename(new)
        print(f"[migrate] {old.name} → {new.name}")
```

This ensures existing users do not lose their scan history, credentials, or
settings when upgrading.

**i18n key strategy**

Keep the `m365_` prefix for keys that are genuinely M365-specific (auth
screens, Azure credential labels). Update keys that describe general scanner
behaviour (`m365_scan_start` → `gdpr_scan_start`, `m365_settings_title` →
`gdpr_settings_title`). This avoids a big-bang translation churn — only
~30% of keys are general rather than M365-specific.

**Files to change**

| File | Change |
|---|---|
| `m365_scanner.py` | Rename to `gdpr_scanner.py`; update all internal `m365_` references |
| `build_m365.py` / `build_m365.sh` | Rename; update entry point reference |
| `install_windows.ps1` / `install_macos.sh` | Update script name and entry point |
| `templates/index.html` | `<title>`, sidebar heading, `m365_scanner` → `gdpr_scanner` in JS paths |
| `lang/en.lang`, `da.lang`, `de.lang` | Rename ~50 general keys from `m365_` to `gdpr_` prefix |
| `README.md` | Full text update |
| `SUGGESTIONS.md` | Replace remaining `m365_scanner.py` references |

**Effort:** Small — 1 session. Mostly find-and-replace with careful handling
of the migration shim and i18n key renames.

---

## 25. Split `gdpr_scanner.py` into focused modules ✅

**Background**

`m365_scanner.py` (to be renamed `gdpr_scanner.py` in #24) is currently ~4800
lines and contains Flask app setup, scan orchestration, SSE, CPR detection,
file type dispatch, config, checkpointing, delta tokens, image scanning, and
more. This makes the file hard to navigate, impossible to unit-test in
isolation, and increasingly fragile as new scan sources are added.

The Blueprint refactoring (#17) successfully separated the route layer. This
suggestion applies the same principle to the core application layer.

**Proposed module structure**

```
gdpr_scanner.py        (~150 lines)
  Flask app init, blueprint registration, CLI arg parsing, __main__ block.
  Imports everything else. Entry point only.

scan_engine.py         (~1200 lines)
  run_m365_scan(), run_file_scan(), run_google_scan()
  _broadcast_card(), _check_special_category(), _check_transfer_risk()
  _after_cutoff(), _eta(), _check_abort()
  Checkpointing calls delegated to checkpoint.py

cpr_detector.py        (~600 lines)
  _scan_bytes() — top-level dispatcher
  _scan_pdf(), _scan_docx(), _scan_xlsx(), _scan_image(), _scan_text()
  CPR regex, modulo-11 validation
  This is the most important module to isolate — it is the legal core
  of the tool and the highest-value target for unit tests (#26)

checkpoint.py          (~150 lines)
  _save_checkpoint(), _load_checkpoint(), _checkpoint_key()
  _load_delta_tokens(), _save_delta_tokens()

app_config.py          (~120 lines)
  _load_config(), _save_config()
  _load_file_sources(), _save_file_sources()
  _load_keywords(), _load_lang()

sse.py                 (~80 lines)
  broadcast(), _sse_queues, _sse_buffer, _current_scan_id
  /api/stream SSE endpoint
```

**Approach**

The `routes/` blueprints already use `__getattr__` lazy loading to resolve
globals from `m365_scanner`. After the split, they resolve from `gdpr_scanner`
(which re-exports everything from the sub-modules). No blueprint changes
needed.

Split in order of lowest risk first:
1. `sse.py` — self-contained, no dependencies on other scanner code
2. `app_config.py` — pure file I/O, no Flask or scan dependencies
3. `checkpoint.py` — depends only on Path and json
4. `cpr_detector.py` — depends on document_scanner, PIL, no Flask
5. `scan_engine.py` — depends on all of the above; split last

Each step: move code → update imports → run smoke test → commit.

**What does NOT move**

- Flask `app` object stays in `gdpr_scanner.py` (blueprints register against it)
- `_connector`, `_scan_lock`, `_scan_abort` stay in `gdpr_scanner.py` or `routes/state.py`
- `LANG`, `flagged_items`, `scan_meta` stay in `routes/state.py` (already there)

**Effort:** Medium — 1 session if done carefully in the order above. The
biggest risk is circular imports; the `__getattr__` pattern already in place
prevents most of them.

---

## 26. Test suite — pytest for CPR detection, connectors, and DB ✅

**Background**

There are currently zero tests in the repository. For a GDPR compliance tool
that DPOs and auditors may rely on, this is a credibility gap — especially for
CPR detection, where a false negative means a real violation goes undetected.
The split in #25 makes isolated unit testing practical for the first time.

**Test modules, in priority order**

### `tests/test_cpr_detector.py` *(highest priority — legal core)*

```python
# Known valid CPR numbers
def test_valid_cpr_detected(): ...
def test_cpr_in_table_cell_detected(): ...
def test_cpr_in_pdf_text_layer(): ...
def test_cpr_split_across_line_break(): ...

# Modulo-11 validation
def test_valid_checksum_accepted(): ...
def test_invalid_checksum_rejected(): ...
def test_exempt_dates_bypass_modulo11(): ...   # post-2007 CPRs exempt

# Date range validation
def test_future_date_rejected(): ...
def test_implausible_date_rejected(): ...      # e.g. month 13

# False positive prevention
def test_phone_number_not_flagged(): ...       # 12 34 56 78
def test_account_number_not_flagged(): ...     # looks like CPR with dashes
def test_zip_plus4_not_flagged(): ...

# File type dispatch
def test_scan_docx_with_cpr(): ...
def test_scan_xlsx_cpr_in_cell(): ...
def test_scan_pdf_cpr_in_text_layer(): ...
def test_scan_plaintext(): ...
def test_empty_file_returns_empty(): ...
def test_binary_garbage_does_not_crash(): ...
```

### `tests/test_m365_connector.py` *(mock-based — no real API calls)*

```python
def test_classify_user_role_faculty_sku(): ...
def test_classify_user_role_student_sku(): ...
def test_classify_user_role_unknown_sku(): ...
def test_pagination_follows_next_link(): ...
def test_403_raises_permission_error(): ...
def test_token_refresh_on_expiry(): ...
def test_app_mode_vs_delegated_mode(): ...
```

### `tests/test_google_connector.py`

```python
def test_service_account_key_validation(): ...
def test_invalid_key_type_rejected(): ...
def test_iter_gmail_respects_max_messages(): ...
def test_drive_export_map_docs_to_docx(): ...
def test_drive_skips_oversized_files(): ...
def test_list_users_filters_suspended(): ...
```

### `tests/test_db.py`

```python
def test_begin_end_scan_round_trip(): ...
def test_save_and_retrieve_flagged_item(): ...
def test_cpr_index_stores_hash_not_plaintext(): ...
def test_lookup_data_subject_returns_items(): ...
def test_disposition_set_and_get(): ...
def test_export_import_merge_cycle(): ...
def test_export_import_replace_cycle(): ...
def test_migration_from_prior_schema_version(): ...
```

**Framework and conventions**

- `pytest` + `unittest.mock` — no new runtime dependencies
- Fixtures in `tests/conftest.py`: `tmp_db`, `sample_docx`, `sample_pdf`,
  `mock_m365_connector`, `mock_google_connector`
- All tests runnable with `pytest tests/` from the project root
- CI target: all `test_cpr_detector.py` tests must pass before any release
- Mock strategy for connectors: patch at the `requests.get` / `googleapiclient`
  level so tests are fast and require no credentials

**CPR test corpus**

A `tests/fixtures/` folder with:
- `sample_with_cpr.docx` — Word file containing 3 known CPR numbers
- `sample_with_cpr.pdf` — PDF with text layer containing 1 CPR
- `sample_no_cpr.xlsx` — Excel file with account numbers that look like CPRs
- `sample_art9.txt` — text file with CPR adjacent to Article 9 keywords
- `sample_binary.bin` — garbage bytes (must not crash scanner)

**Effort:** ~1 session for `test_cpr_detector.py` + `test_db.py`.
Connector tests add another session once #25 is complete (modules need to be
importable in isolation first).

## 27. Migrate i18n format from `.lang` to JSON

**Background**

The current `.lang` format is a flat `key = value` text file with a custom
loader. It works well for the current scale (3 languages, ~700 keys) and has
no dependencies. This suggestion tracks a potential migration for when the
format becomes a limiting factor.

**Current state**

- Server-side loader in `app_config.py` parses `.lang` files into a Python dict
- The `/api/lang` endpoint converts that dict to JSON for the browser anyway
- Keys use prefix namespacing (`m365_`, `gdpr_`) as a poor-man's hierarchy
- Three language files: `en.lang`, `da.lang`, `de.lang`

**Why JSON would be better at scale**

- The browser already receives JSON — removing the conversion step simplifies
  `app_config.py` and makes lang files directly usable in JS unit tests
- Nested keys (`{"scan": {"start": "Start scan"}}`) would replace the
  prefix convention with real structure
- Standard tooling (VS Code JSON schema, linters) would work out of the box
- Easier to validate completeness across languages programmatically

**Why not now**

- The existing format works and the loader is already written
- A migration touches every key in all three lang files plus the loader —
  high effort, zero user-visible benefit
- Three languages and ~700 keys is well within the comfort zone of flat files

**Trigger condition:** consider when adding a 4th language, when key count
exceeds ~1500, or when a contributor wants to use professional translation
tooling (Poedit, Weblate, Transifex) that expects standard formats.

**Effort:** Small (loader rewrite + file conversion script) — but the rename
touches every lang file so best done in one clean pass, not incrementally.


## 28. Disposition: personal-use — out of scope ✅

**Background**

Staff members often use work equipment (OneDrive, email) for private purposes.
A scan will surface these files alongside genuine work records. The organisation
has no compliance obligation over personal files — in fact, scanning them may
itself be a GDPR issue (Article 2(2)(c) excludes processing by a natural person
in the course of a purely personal activity from GDPR scope entirely).

There was no way to mark a flagged item as "this is private, not our business"
without using a work-specific disposition like "retain-legal" which is
semantically wrong.

**What was done (v1.6.2)**

Added `personal-use` as a disposition value:

| Value | Meaning |
|---|---|
| `personal-use` | Private use of work equipment — outside GDPR scope per Art. 2(2)(c) |

- Added to both disposition dropdowns in the UI (filter bar and preview panel)
- Added to Art. 30 report disposition map with the legal citation
- Added to all three lang files (EN / DA / DE)
- Article 30 report labels it "Personal use — out of GDPR scope (Art. 2(2)(c))"

**GDPR basis:** Article 2(2)(c) — GDPR does not apply to processing by a natural
person in the course of a purely personal or household activity.


## 29. Rename `skus/` → `classification/`

**Background**

The `classification/` folder was created to hold Microsoft Education SKU ID mappings
(`m365_skus.json`). It now also holds Google Workspace OU role mappings
(`google_ou_roles.json`), and may grow further as more platforms are added.
The name "skus" is Microsoft-specific and misleading for a multi-platform tool.

**Proposed rename**

`classification/` → `classification/`

Optionally sub-divided as the folder grows:
```
classification/
  m365_skus.json          # M365 SKU → role (currently classification/m365_skus.json)
  google_ou_roles.json    # Google OU → role (currently classification/google_ou_roles.json)
```

**Files to change**

| File | Change |
|---|---|
| `classification/` directory | Rename to `classification/` |
| `m365_connector.py` | Update path constant `_SKU_DIR` or equivalent |
| `google_connector.py` | Update `_OU_ROLES_PATH` constant |
| `build_gdpr.py` | Update `skus_dir` reference in `datas` list |
| `install_windows.ps1` / `install_macos.sh` | Update any references |
| `MAINTAINER.md` | Update file listing |

**Trigger condition:** do this when #23 Phase 2 lands, or when a third
classification file is added — whichever comes first. Not worth doing in
isolation.

**Effort:** Tiny — pure rename, no logic changes.



## 30. Google personal account (OAuth) support ✅ Done

**GDPR reference:** Art. 5(1)(f) — integrity and confidentiality; Art. 32 — security of processing

**What:** Personal Google accounts can now be scanned without a service account or Workspace admin. A device-code OAuth flow (mirrors M365 delegated mode) lets a user sign in interactively with their own Google account and scan their own Gmail and Google Drive.

**Why:** Mirrors the M365 delegated mode. Useful for individuals, small organisations, or situations where a Google Workspace admin is unavailable.

**Implementation:**
- Auth-mode toggle (Workspace / Personal account) in the Google connection panel
- Personal section: OAuth 2.0 client ID + secret (from a GCP Desktop App credential); device-code box shows `user_code` + `verification_url` inline
- `PersonalGoogleConnector` class in `google_connector.py` — same public interface as `GoogleConnector`; `get_device_code_flow()` / `complete_device_code_flow()` hit Google's device-auth endpoint directly via `requests`; token refresh via `google.oauth2.credentials.Credentials`
- `list_users()` returns a single-item list (the signed-in user from `/oauth2/v2/userinfo`) — scan engine unchanged
- `_gmail_iter()` / `_drive_iter()` extracted as shared module-level helpers; both connector classes delegate to them
- Token persisted to `~/.gdprscanner/google_token.json` (chmod 600)
- Four new API endpoints: `GET /api/google/personal/status`, `POST /api/google/personal/start`, `POST /api/google/personal/poll`, `POST /api/google/personal/signout`
- Backend poll pattern identical to M365 delegated: background thread blocks on `complete_device_code_flow`, frontend polls every 3 s
- Scopes: `gmail.readonly`, `drive.readonly`
- 14 new i18n keys in `en.json`, `da.json`, `de.json`

**Size:** Medium  
**Priority:** Low — service account covers institutional use cases well


---

## 31. Built-in user manual accessible from the interface ✅ Done

**What:** End-user documentation accessible directly from the running application — no external site, no separate PDF, printable from the browser.

**Why:** The scanner is used by school administrators and municipal compliance officers who are not technically minded. A built-in manual reduces support burden and ensures the right version of the documentation is always paired with the installed version.

**Implementation:**
- `MANUAL-EN.md` and `MANUAL-DA.md` — standalone Markdown manuals covering all major features in plain language. 14 sections each: Getting started, Sources panel, Running a scan, Understanding results, Reviewing results, Bulk actions, Profiles, Scheduler, Export & email, Article 30 report, Data subject lookup, Settings, Retention policy, FAQ.
- `GET /manual` route in `routes/app_routes.py` — reads `?lang=da|en` (defaults to the current UI language), finds the appropriate `.md` file relative to the project root, converts it to a fully self-contained HTML page, and returns it.
- `_md_to_html(md)` — zero-external-dependency Markdown-to-HTML converter using only Python's `re` and `html` stdlib modules. Handles: headings with anchor IDs, fenced code blocks, tables, ordered/unordered lists, blockquotes, bold, italic, inline code, links, horizontal rules.
- Manual page features: max-width 860 px readable layout, language switcher (DA ↔ EN), 🖨 print button (calls `window.print()`), `@media print` CSS that hides the toolbar, forces page breaks before `<h2>` sections, and appends external link URLs for paper printing.
- `?` button in the topbar (right of the theme toggle) — `window.open('/manual?lang=...', '_blank')` with the current `langSelect` value. Opens in a new tab without interrupting any in-progress scan.
- No new dependencies. The manual route is stateless and always up to date with the installed version.

**Size:** Small  
**Priority:** Medium — reduces support requests; required for regulated-sector deployments


---

## 32. Windowed mode for Profiles, Sources, and Settings

**What:** Replace the three modal dialogs (Profiler, Kilder, Indstillinger) with dedicated windows — either native pywebview windows (in the packaged desktop app) or browser popups (in the web UI).

**Why:** Modals are blocking and interrupt the main workspace. A compliance officer reviewing scan results should be able to check or edit a profile without losing their place in the results grid. Separate windows allow the main view and the configuration panel to be visible simultaneously — useful on multi-monitor setups common in school admin offices.

**Three implementation options were evaluated:**

**Option A — Main app URL with `?panel=X` query param** *(least work)*
- The existing modal HTML/CSS/JS is reused unchanged.
- A new window opens `http://localhost:5100/?panel=profiles` — the JS detects the param on load and auto-opens the relevant modal.
- In the packaged app: `pywebview.api.open_panel("profiles")` creates a second native window (same pattern as the manual viewer).
- State sync (e.g. "profile saved, refresh main window") via `postMessage` or `localStorage` events.
- **Pro:** Zero modal rewrite. **Con:** Each popup loads the full ~3800-line app; two JS instances share the same Flask server.
- **Estimated effort:** 1–2 days.

**Option B — Dedicated Flask routes serving lightweight standalone pages** *(most work, cleanest)*
- `/panel/profiles`, `/panel/sources`, `/panel/settings` — each a minimal self-contained HTML page talking to the existing API endpoints.
- **Pro:** Clean separation, small pages, no duplicate state. **Con:** All three modal JS sections must be rewritten as standalone pages; shared utilities (i18n, `_esc`, rendering helpers) must be extracted or replicated.
- **Estimated effort:** 15–20 days (Profiles: 3–4 d, Sources: 5–6 d, Settings: 4–5 d, shared infra: 1–2 d, QA: 2–3 d).

**Option C — Side drawer instead of popup** *(no new windows, best UX for single-monitor)*
- Modals become slide-in side drawers that don't block the main results grid.
- **Pro:** No window management complexity, works identically in app and browser, no state sync needed. **Con:** Not a true separate window.
- **Estimated effort:** 2–3 days.

**Decision:** Won't do. The workflow is sequential (configure → scan → review) — there is no realistic scenario where a modal and the results grid need to be open simultaneously. The Sources panel is already permanently visible in the sidebar, covering the main configuration need during result review. Option A (the least-work path) would still load the full ~3800-line JS stack in a second window, sharing the same Flask server — poor value for a configuration-only panel. Closed 2026-04-10.

**Size:** Option A: Small · Option B: Large · Option C: Small  
**Priority:** N/A — closed

---

## 33. Read-only viewer mode with PIN/token URL ✅

**GDPR reference:** Art. 5(2) — accountability; Art. 30 — records of processing activities

**Problem:** The scanner is operated by IT, but the people who need to review results and make compliance decisions (DPO, school principal, municipal data protection coordinator) are different people. Currently the only way to share results is to export to Excel or Word — a static snapshot. There is no way to give a stakeholder live access to the results grid (with disposition tagging) without also giving them full access to scan controls, credentials, and settings.

**What:** A token-protected URL that opens a read-only view of the scan results. The viewer can browse the results grid, open previews, and tag dispositions — but cannot start or stop scans, view or change credentials, access settings, or delete items.

**How it works:**

1. **Token generation** — a new **Share** button in the top bar (or Settings) generates a random URL-safe token (e.g. 32-byte hex) and stores it in `~/.gdprscanner/viewer_tokens.json` with an optional expiry date. The full URL is displayed and copyable: `http://host:5100/view?token=abc123…`
2. **Token validation** — a `@viewer_token_required` decorator checks `request.args.get("token")` or a session cookie against the stored tokens. Invalid or expired tokens return 403.
3. **Restricted route** — `/view` serves a stripped version of `index.html` (or the same template with JS feature flags) that hides the scan controls, credentials, source management, settings, and delete buttons. Disposition tagging remains enabled — this is the primary action a reviewer needs.
4. **PIN alternative** — optionally, instead of (or alongside) a token URL, a numeric PIN can be set in Settings. Entering the PIN in a login prompt grants the same read-only session for the browser's session duration.
5. **Expiry** — tokens can be time-limited (e.g. 7 days, 30 days, no expiry). Expired tokens are silently rejected and cleaned up on next startup.
6. **Scope** — viewer sees the most recent completed scan's results from the DB, identical to what the operator sees in the main results grid. Live scan progress is not shown.

**What the viewer can do:**
- Browse results grid (filter, sort, search)
- Open item preview (file preview, email preview, EXIF, face count)
- Tag dispositions (retain / delete-scheduled / deleted / personal-use)
- Export to Excel and Article 30 Word doc

**What the viewer cannot do:**
- Start, stop, or configure scans
- View or change M365 / Google credentials
- Access source management or settings
- Delete items from M365 / Google / file systems
- Generate or revoke viewer tokens

**Implementation notes:**
- Simplest path: serve the same `index.html` but inject a `window.VIEWER_MODE = true` JS global. All feature modules check this flag to hide/disable restricted controls. No second template needed.
- Token storage in `viewer_tokens.json` (alongside other data files in `~/.gdprscanner/`) keeps it simple and consistent with existing persistence.
- No new dependencies — `secrets.token_hex(32)` for token generation, existing Flask session for PIN-based sessions.
- The `/view` route and token validation live in `routes/auth.py` or a new `routes/viewer.py`.

**Size:** Medium — ~3–5 days (token generation + storage + validation decorator + JS viewer-mode flag + UI hiding + PIN flow + Settings panel entry).  
**Priority:** Medium — directly supports the multi-stakeholder review workflow common in schools and municipalities.

---

## Summary table

| # | Effort | GDPR Article | Impact | Status |
|---|---|---|---|---|
| 1 | Small | Art. 5(1)(e) — storage limitation | High | ✅ Done |
| 2 | Medium | Art. 30 — processing register | High | ✅ Done |
| 3 | Medium | Art. 9 — special categories | High | ✅ Done |
| 4 | Medium | Art. 15/17 — access/erasure rights | High | ✅ Done |
| 5 | Medium | Art. 44–46 — data transfers | Medium | ✅ Done |
| 6 | Small | Art. 5(1)(a) / Art. 30 — lawfulness | Medium | ✅ Done |
| 7 | Small | Art. 5(2) — accountability | Medium | ✅ Done |
| 8 | Large | Art. 5(1)(c)(e) — data minimisation | High | ✅ Done |
| 9 | Medium | Art. 9 — biometric data (photos) | High | ✅ Done |
| 10 | Large | Google Workspace scanning (Gmail & Drive) | High | ✅ Done |
| 11 | Medium | Art. 5(2) — accountability | Medium | ✅ Done |
| 12 | — | — | — | ~~Retired — merged into #8~~ |
| 13 | Small | Performance | Low | ✅ Done |
| 14 | Tiny  | UI polish | Low | ✅ Done (phase text) |
| 15a | Small  | Art. 5(2) — accountability | High | ✅ Done |
| 15b | Small  | Art. 5(2) — accountability | High | ✅ Done |
| 15c | — | — | — | ~~Dropped~~ |
| 15d | Medium | Art. 5(2) — accountability | High | ✅ Done |
| 15e | Medium | Art. 5(2) — accountability | Medium | ✅ Done |
| 15f | Large  | Art. 5(2) — accountability | High | ✅ Done |
| 16  | Medium | Art. 30, Databeskyttelsesloven §6 | High | ✅ Done |
| 17  | Medium | UX / configurability | Medium | ✅ Done |
| 18  | Small  | Art. 4, Art. 9 — EXIF / location | High | ✅ Done |
| 19  | Medium | Art. 5(2), Art. 25, Art. 32 — scheduled compliance | High | ✅ Done (v1.5.5) |
| 20  | Small  | File scan quality — PDF OCR via multiprocessing | Medium | ✅ Done |
| 21  | Small  | UX — SSE event replay for late-connecting browsers | Medium | ✅ Done |
| 22  | Medium | File scan reliability — SMB pre-fetch cache | Low | ✅ Done |
| 23  | Medium/Large | Art. 5, 25, 30, 32 — Google Workspace role classification + cross-platform identity mapping | High | ✅ Done |
| 24  | Small        | Codebase hygiene — rename M365 Scanner → GDPRScanner | Medium | ✅ Done |
| 25  | Medium       | Codebase hygiene — split `gdpr_scanner.py` into focused modules | Medium | ✅ Done |
| 26  | Medium       | Quality — pytest suite for CPR detection, connectors, DB | High | ✅ Done |
| 27  | Small        | Codebase hygiene — migrate i18n from `.lang` to JSON | Low | ✅ Done |
| 28  | Tiny         | Compliance UX — personal-use disposition value | Medium | ✅ Done |
| 29  | Tiny         | Codebase hygiene — rename `skus/` → `classification/` | Low | ✅ Done |
| 30  | Medium | Personal Google account OAuth (delegated mode like M365) | Low | ✅ Done |
| 31  | Small  | Built-in user manual accessible from the interface | Medium | ✅ Done |
| 32  | Small–Large (option-dependent) | UX — windowed mode for Profiles, Sources, Settings | Low | ✗ Won't do |
| 33  | Medium | Compliance UX — read-only viewer mode with PIN/token URL | Medium | ✅ Done |

---
