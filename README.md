# GDPRScanner

Scans Microsoft 365, Google Workspace, and local/network file systems for Danish
CPR numbers and personal data (PII). Produces GDPR compliance reports and supports
Article 30 record-keeping obligations.

---

**Developed by Henrik Højmark**

This project was built with substantial assistance from AI (Claude by Anthropic),
used as a pair-programming tool throughout development. All design decisions,
requirements, testing, and validation were made by the author. The AI generated
code under direction — the same way a developer might use a senior colleague or
an IDE with intelligent completion. The result is the author's work.

---

`gdpr_scanner.py` scans Microsoft 365 cloud sources — Exchange email (including all subfolders), OneDrive, SharePoint, and Teams — for Danish CPR numbers and PII. It connects to the Microsoft Graph API and does not require local file access.

### What it does (M365)

- **Scans Exchange mailboxes** — email body and attachments, across **all folders and subfolders** recursively (Inbox, custom folders, nested folders). System folders (Deleted Items, Junk, Drafts, Sent, etc.) are automatically skipped using Exchange `wellKnownName` identifiers (language-independent — works correctly for Danish, German, and other locales)
- **OneDrive, SharePoint, Teams** — scans files in all connected sources
- **Subfolder prioritisation** — custom subfolders are scanned before Inbox to prevent a large Inbox from exhausting the per-user email cap
- **EML attachment preview** — email attachments with CPR hits are listed in the preview panel with per-attachment CPR counts
- **Folder path in results** — each email result shows its full folder path (e.g. `Inbox / Ansøgninger pædagog SFO`) in the card and in Excel export
- **Delete items** — flagged results can be deleted directly from the UI, individually or in bulk
- **CPR false-positive reduction** — strict CPR validation
- **Excel export** — multi-tab `.xlsx` report with per-source breakdown, auto-filters, and URL hyperlinks. Columns include: Name, CPR Hits, Face count, GPS (✔ if GPS in EXIF), Special category, EXIF author, Folder, Account, Role, Disposition, Date Modified, Size (KB), URL. A dedicated **GPS locations** sheet lists all items with GPS coordinates including a Google Maps link. Separate tabs for Outlook (Exchange), OneDrive, SharePoint, Teams, Gmail, Google Drive, local folders, and SMB/network shares. Summary sheet shows counts by source and GPS item total. When M365, Google Workspace, and file scans run concurrently, all results are captured in the export — not just the last completed scan
- **Progressive streaming** — results stream card-by-card via Server-Sent Events as the scan runs
- **Token auto-refresh** — expired tokens are detected and silently refreshed mid-scan without interrupting the UI
- **Incremental / resumable scans** — interrupted scans save a checkpoint; the next run resumes from where it stopped rather than starting over
- **Delta scan** — uses Graph `/delta` endpoints to fetch only changed items since the last scan, cutting API quota usage and scan time on large tenants
- **Headless / scheduled mode** — `--headless` flag runs a non-interactive scan and writes an Excel report to disk; combine with cron or Windows Task Scheduler for fully automated compliance scans. **Settings → Scheduler** supports multiple named scan jobs, each with its own frequency (daily/weekly/monthly), time, profile, auto-email, and retention settings. Enable/disable each job with an inline toggle. In application mode, scheduled jobs reconnect automatically without requiring the browser to be open
- **EXIF metadata extraction** — GPS coordinates, author, description, device extracted from all scanned images. GPS badge on cards when location data is present. Collapsible EXIF panel in local file previews. No extra dependencies — uses `Pillow` which is already required.
- **`--purge`** — permanently deletes all data files created by the scanner (database, credentials, cache); use before decommissioning
- **`--export-db`** / **`--import-db`** — export the database to a ZIP archive or restore from one; supports `--import-mode merge` (default) and `--import-mode replace`
- **`--reset-db`** — wipe and recreate the database; also clears the checkpoint and delta tokens
- **Email report** — send the Excel report by email directly from the UI or via `--email-to` in headless mode. Prefers **Microsoft Graph API** when connected to M365 (no SMTP AUTH needed — requires `Mail.Send` permission). Falls back to `smtplib` SMTP with STARTTLS/SSL support. A **Test** button verifies end-to-end delivery.
- **Account name on cards** — when scanning multiple users, each card displays the owner's display name so results from different mailboxes are instantly distinguishable
- **Retention policy enforcement** — flag items older than a configurable retention period with a Overdue badge; supports both rolling and fiscal-year-aligned cutoffs (e.g. Bogføringsloven Dec 31); headless auto-delete via `--retention-years`
- **Data subject lookup** — find all flagged items containing a specific CPR number across all scans; CPR is SHA-256 hashed before querying — never stored in plaintext
- **Disposition tagging** — compliance officers can tag each flagged item with a legal basis (retain / delete-scheduled / deleted) directly from the preview panel; **bulk disposition tagging** lets you select multiple cards with checkboxes and apply a disposition to all of them at once. A stats bar above the grid shows total · unreviewed · retain · delete counts and the percentage reviewed
- **Interface PIN** — optional session-level PIN that gates the main scanner interface (`/`). Set a 4–8 digit PIN in **Settings → Security → Interface PIN**; unauthenticated visitors are redirected to `/login`. The `/view` viewer route and all viewer API endpoints are exempt — reviewers are unaffected. Salted SHA-256 hash; brute-force protection (5 attempts / 5 min per IP)
- **Read-only viewer mode** — share scan results with a DPO or manager via a secure token URL (`/view?token=…`) or a numeric PIN; viewers see the full results grid and disposition panel but cannot scan, delete, or change settings. Tokens can be **role-scoped** (Ansatte / Elever) so a recipient only sees items for their group, or **user-scoped** so an individual employee only sees their own flagged files (supports dual M365 + Google Workspace identity)
- **Article 30 report** — one-click export of a structured Word document (`.docx`) satisfying the GDPR Article 30 register of processing activities obligation
- **SQLite results database** — scan results, CPR index, PII breakdown, disposition decisions, and scan history are persisted to `~/.gdprscanner/scanner.db` alongside the JSON cache, enabling cross-scan queries and trend tracking
- **Built-in user manual** — click the **?** button in the top bar to open the manual in a dedicated window. Available in Danish and English. Printable via the browser's print function. Served from `MANUAL-DA.md` / `MANUAL-EN.md` at `/manual?lang=da|en` — always in sync with the installed version, no internet required. In the packaged desktop app the manual opens as a native pywebview window; in the browser it opens as a popup.

---

## Microsoft 365

See [M365_SETUP.md](docs/setup/M365_SETUP.md) for step-by-step instructions — app registration, permissions, authentication modes, and headless configuration.

---

### M365 Web UI

```
python gdpr_scanner.py [--port PORT]
```

> The scanner expects `templates/` and `static/` in the same directory as `gdpr_scanner.py`. Flask serves `templates/index.html` as the UI. The JavaScript is split across 12 ES modules in `static/js/` (`state.js` + 11 feature modules loaded as `<script type="module">`). All API routes live in `routes/` as Flask Blueprints registered at startup.

Default port: **5100**. If that port is already in use the server auto-increments (5101, 5102, …) and logs which port was chosen. Override with `--port N`. Only one instance may run at a time — a second launch exits immediately with an error rather than corrupting the shared database.

#### Sources panel

The sidebar sources panel lists all configured scan sources. Click **Sources** to open the unified Source Management modal. The panel is collapsible (▾/▸ toggle, state persisted) and resizable — drag the handle at the bottom edge to shrink it; the maximum height is automatically capped to show all available sources with no empty space.

**Microsoft 365 tab** — Azure credentials (Client ID, Tenant ID, Client Secret), auth mode (Application / Delegated), and per-source visibility toggles (Email, OneDrive, SharePoint, Teams). Sources toggled off are hidden from the sidebar panel and excluded from scans.

**Google Workspace tab** — Two authentication modes: **Workspace** (service account with domain-wide delegation — scans all users) and **Personal account** (OAuth 2.0 device-code flow — scans the signed-in account only). Once connected, per-source toggles control whether Gmail and/or Google Drive appear in the sidebar panel and are included in scans. See [GOOGLE_SETUP.md](docs/setup/GOOGLE_SETUP.md) for setup instructions.

**File sources tab** — Add local folder paths or SMB/CIFS network shares with a name, path, and optional SMB credentials. Each saved source appears as a checkbox in the sidebar panel (local, SMB/network). Use the **Edit** button on each row to update credentials or rename a source without deleting it.

**Skipped automatically:** `.recycle`, `.sync`, `.btsync`, `.trash`, `.git`, `node_modules`, `System Volume Information`, and other system/sync folders. Hidden directories (`.` prefix) are skipped too.

**PDF scanning in file scans:** PDFs are scanned in a dedicated subprocess spawned via `multiprocessing.get_context("spawn")` with a 60-second hard timeout. If a PDF's OCR (Tesseract/Poppler) stalls, the subprocess is terminated and the file is skipped with an error card — the scan thread is never blocked. The `spawn` context is required on macOS + Flask to avoid duplicating the server socket.

**Preview panel** — opens to the right of the results grid when a card is clicked. The panel is resizable: drag the left edge to adjust its width (min 280 px, max 70% of window). Width is remembered for the session. Click **×** to close.

**Local file preview** — clicking a result card renders the file content inline:

| Type | Preview |
|---|---|
| PDF | First 5 pages as text via `pdfplumber`, CPR numbers highlighted |
| XLSX / XLSM / CSV | First 50 rows as a table (up to 3 sheets for Excel) |
| DOCX / DOC | First 80 paragraphs as text, CPR numbers highlighted |
| Images | Inline image + collapsible EXIF metadata panel (GPS, author, device, datetime) |
| TXT / EML / MD / log | Full text with CPR highlights |

Sources from all tabs can be selected independently in the sidebar before scanning. The selection is saved as part of scan profiles.

#### User accounts panel

In Delegated mode, accounts are added via the device code flow. In Application mode, the scanner fetches all users in the tenant. Users are listed with checkboxes — all unchecked by default. Use **All / None** to select or deselect everyone, filter by name with the search field, or add a user manually by email with the **+** button.

**Role classification** — users are automatically classified as Student or Staff based on their Microsoft 365 licence. Role badges appear on every account row, on result cards, and in the Article 30 report (separate Staff and Student inventory tables).

Role detection works in two passes:
1. **`skuPartNumber` fragment match** (preferred) — strings like `STANDARDWOFFPACK_FACULTY` are stable across all Microsoft licensing generations (EA, A1/A3/A5, new commerce/CSP). Runs first whenever part numbers are available.
2. **SKU ID lookup** from `classification/m365_skus.json` — fallback for when part numbers are unavailable or for licences with no recognisable fragment (e.g. Power Automate Free assigned to faculty).

**Filter buttons** — **All / Ansat / Elev** filter the accounts list before selecting who to scan.

**SKU debug** — the magnifying-glass button next to the role filters opens a modal listing every unique SKU ID in the tenant, colour-coded student / staff / unknown. Unknown IDs can be copied directly into `classification/m365_skus.json` and take effect on the next restart.

**Manual role override** — if auto-classification is wrong for a specific user, click the role badge (role badge) on their row to cycle through `student → staff → other → (clear)`. Overrides are stored in `~/.gdpr_scanner_role_overrides.json` and persist across restarts. A pencil indicator appears on overridden rows. Click through until the pencil disappears to revert to auto-detection.

**`classification/m365_skus.json`** — the SKU ID and fragment file lives in the `classification/` folder alongside `lang/` and `keywords/`. Edit it to add new or tenant-specific SKU IDs without any code change; the file is reloaded on every restart.

#### Date filter

A date-from picker limits the scan to items modified after the selected date. Quick presets: **1 yr / 2 yr / 5 yr / 10 yr / Any**. Selecting "Any" sets the date to today (no cutoff).

#### Options

| Option | Default | Description |
|---|---|---|
| Scan email body | On | Scan the plain-text body of each email |
| Scan attachments | On | Scan PDF/Word/Excel attachments inside emails |
| Max attachment size | **20 MB** | Skip attachments larger than this threshold |
| Max emails per user | **2000** | Cap per mailbox to avoid very long scans |
| **Δ Delta scan** | Off | Fetch only changed items since the last scan — hover the **?** for details (see [Delta scan](#delta-scan) below) |
| **Scan photos for faces** | Off | Detect faces in image files and flag as Art. 9 biometric data — hover the **?** for details (see [Photo scanning](#photo--biometric-scanning) below) |
| **Ignore GPS in images** | Off | Skip images whose only PII signal is an embedded GPS coordinate. Useful for student scans where smartphones embed location in every camera photo. GPS is still shown in the detail card if the image is flagged for another reason (faces, EXIF author). |
| **Min. CPR count per file** | **1** | Only flag a file if it contains at least this many *distinct* CPR numbers. Set to 2 to suppress false positives in student scans (e.g. a student's own consent form with a single CPR) while still reporting class lists and grade sheets with multiple CPRs. |
| **Retention policy** | Off | Flag items older than N years — hover the **?** for details (see [Retention policy](#retention-policy-enforcement)) |

#### Results grid

Each flagged item appears as a card showing:
- File / subject name
- CPR hit count badge
- Source badge (Email / OneDrive / SharePoint / Teams)
- Source account with role badge (**Student** / **Staff**)
- Modified / received date
- **Folder path** — shown for emails (e.g. ` Inbox / Ansøgninger pædagog SFO`)
- **Account name** — owner's display name shown on every card when scanning multiple users
- **Overdue badge** — amber badge on items exceeding the configured retention cutoff
- **Art.9** badge — purple pill listing detected Article 9 special categories (health, criminal, biometric, etc.)
- ** N faces** badge — teal pill on image files where face detection found identifiable persons (biometric data)
- **Ext.** / **** badge — external email recipient or externally shared file (Art. 44–46 transfer risk)
- **delete button** — appears on hover (grid view) or always visible (list view)

**Disposition stats bar** — always visible above the results grid when items are loaded. Shows: Total · Unreviewed · Retain · Delete · percentage reviewed. Updates live after every disposition save.

**Select mode** — click **Vælg** in the filter bar to enter bulk-selection mode. Per-card checkboxes appear; a bulk tag bar at the bottom of the grid shows the count of selected items, a **Select all visible** button, a disposition dropdown, and an **Apply** button. Click **Done** to exit select mode.

**Filter bar** — always visible above both the results grid and the preview panel. Narrow results by source, disposition, transfer risk, risk level, and role:

| Filter | Options |
|---|---|
| Source | All / Email / OneDrive / SharePoint / Teams |
| Disposition | All / Unreviewed / Retain (legal/legitimate/contract) / Delete-scheduled / Deleted |
| Transfer risk | All / External recipient / External share / Shared |
| Risk level | All risk levels / Art. 9 special category / Photos / biometric |
| **Role** | **All roles / Ansatte (staff) / Elever (students)** |

The Role filter also scopes exports — selecting **Elever** before clicking **Excel** or **Art.30** produces a report containing only student items. The exported filename gets an `_elever` or `_ansatte` suffix so recipients can distinguish the files.

#### Scan history browser

Review results from any past scan session without running a new scan. A **Sessions** button appears in the banner above the results grid once a scan has completed.

- Click **Sessions** to open the session picker — lists all past scans with date, sources, and item count. Each entry shows a **Δ** badge for delta scans and a **Latest** badge for the most recent session.
- Click any session row to load its results into the grid. A history banner replaces the progress bar, showing the session date, sources scanned, and item count.
- **Latest scan** button in the banner jumps back to the most recent session.
- Starting a new scan automatically exits history mode and switches to live SSE results.
- All filters, dispositions, and exports work normally while browsing history — the Role filter and viewer-scope enforcement still apply.
- Viewer tokens work with history mode: `GET /api/db/flagged?ref=N` applies scope filtering the same way as the live endpoint.

#### Delete items

Individual items can be deleted directly from their card (hover to reveal , confirm). Emails are moved to Deleted Items; files go to the recycle bin.

The **Delete** button in the filter bar opens the **Bulk Delete** modal, which lets you filter by:

| Criterion | Description |
|---|---|
| Source type | Email / OneDrive / SharePoint / Teams / All |
| Min CPR hits | Only delete items with at least N CPR numbers found |
| Older than date | Only delete items older than a given date |

The **Filter overdue** quick button pre-populates the date filter with the exact retention cutoff from the database, making it one click to select all overdue items for deletion.

A live preview shows how many items match before you confirm. Errors are reported per-item in the log panel.

> **Requires write permissions** — see [Azure permissions](#azure-permissions) above.

#### Excel export

The **⬇ Excel** button exports all current results to a `.xlsx` file (`m365_scan_YYYYMMDD_HHMMSS.xlsx`) with five sheets:

| Sheet | Contents |
|---|---|
| Summary | Scan timestamp, total count, per-source breakdown |
| Email | Flagged emails — Name/Subject, CPR Hits, **Folder**, Source Account, Date Modified, Size, URL |
| OneDrive | Flagged OneDrive files |
| SharePoint | Flagged SharePoint files |
| Teams | Flagged Teams files |

In macOS app builds, the export opens a native Save dialog instead of a browser download.

The **Art.30** button generates a **GDPR Article 30 Register of Processing Activities** as a structured Word document (`.docx`). See [Article 30 report](#article-30-report) below.

#### Email report

Configure email delivery in **Settings → Email report**. Click **Save** to store your SMTP settings, **Test** to send a real test email to the configured recipients, and **Send now** to dispatch the latest scan report. When connected to Microsoft 365, the scanner sends via the **Graph API** (`Mail.Send` permission required — add it in Azure AD → App registrations → API permissions). SMTP is used as a fallback when Graph is unavailable.

| Field | Description |
|---|---|
| SMTP host | e.g. `smtp.office365.com`, `smtp.gmail.com` |
| Port | `587` for STARTTLS (default), `465` for SMTPS/SSL |
| Username | SMTP login — usually your sender email address |
| Password | Saved to `~/.gdpr_scanner_smtp.json` (permissions 600). Encrypted at rest using Fernet — key in `~/.gdpr_scanner_machine_id` (chmod 0o600, never share) |
| Graph API | When connected to M365, email is sent via `/me/sendMail` (delegated) or `/users/{sender}/sendMail` (app mode) — no SMTP password needed. Requires `Mail.Send` Graph permission with admin consent. |
| From address | Sender address (defaults to username if blank) |
| STARTTLS | Enable STARTTLS on port 587 (recommended) |
| SSL | Use SMTPS on port 465 instead |
| Recipients | Comma or semicolon separated list of addresses |

Click **Save** to persist the settings. The password is stored separately from scan settings and never returned to the browser — subsequent loads show "(password saved)". Click **Send now** to email the report immediately with the current results.

> **No extra dependencies** — uses Python's built-in `smtplib`. Works with Office 365, Gmail, and any standard SMTP server.

#### About

Click **About** in the sidebar footer to see app version, Python version, MSAL version, Requests version, and openpyxl version.

---

## Google Workspace

See [GOOGLE_SETUP.md](docs/setup/GOOGLE_SETUP.md) for step-by-step instructions — service account creation, domain-wide delegation, OAuth scopes, and OU-based role classification.

---

### Incremental / resumable scans

If a scan is stopped (via **■ Stop** or by closing the app) before it finishes, a checkpoint is saved to `~/.gdpr_scanner_checkpoint.json`. The next time you click **▶ Scan** with the same configuration, a banner appears above the progress bar:

```
⏸  Previous scan interrupted — 847 scanned, 12 found  [Resume]  [Start fresh]
```

- **Resume** — skips the 847 already-scanned items, re-emits the 12 previously found cards immediately, and continues from where it left off
- **Start fresh** — discards the checkpoint and starts a new full scan

The checkpoint is keyed by a hash of the scan configuration (sources + users + date cutoff). Changing any of those settings automatically starts fresh. The checkpoint is deleted automatically when a scan completes successfully.

---

### Delta scan

Delta scan uses the Microsoft Graph `/delta` API (M365) and the Google Drive **Changes API** (Google Workspace) to fetch only items that have **changed since the last scan**, dramatically reducing API quota usage and scan time on large tenants.

#### How it works

1. Run one **full scan** first (Delta checkbox off) — this establishes baseline delta tokens
2. Tick **Δ Delta scan** and run again — only items added, modified, or deleted since the previous scan are fetched and CPR-scanned
3. Delta tokens are saved automatically to `~/.gdpr_scanner_delta.json` after each successful scan
4. To force a full rescan, click **Clear tokens** under the checkbox (or delete the file)

Delta tokens are stored **per-source**:

| Token key | Covers |
|---|---|
| `onedrive:{user_id}` | One user's OneDrive drive |
| `sharepoint:{drive_id}` | One SharePoint document library |
| `teams:{drive_id}` | One Teams channel file store |
| `email:{user_id}:{folder_id}` | One mail folder for one user |
| `gdrive:{email}` | One Google Workspace user's Google Drive |

If a token expires (Graph returns HTTP 410 Gone), that source falls back to a full collection automatically and a fresh token is saved. Other sources are unaffected.

If a user's OneDrive returns HTTP 404 during a delta scan (no licence assigned, service plan disabled, or drive never provisioned because the account has never signed in), the user is silently skipped with a grey log entry — no red error card is shown. Full scans already skipped these users silently; delta scans now behave the same way.

Deleted items returned by delta (items with a `deleted` or `@removed` marker) are skipped during CPR scanning.

After each delta scan, the log panel shows:
```
Scan complete — 3 flagged of 41  (Δ delta — 6 source(s) indexed)
```

#### Delta in headless mode

Pass `"delta": true` inside the `options` block of your `--settings` JSON to enable delta for scheduled scans:

```json
{
  "options": { "delta": true, "older_than_days": 365 }
}
```

---

### Headless mode (scheduled / automated scans)

> **Note:** The scheduler engine lives in `scan_scheduler.py`.

Run the scanner without a browser UI for cron jobs and Windows Task Scheduler:

```bash
python gdpr_scanner.py --headless --output ~/Reports/ --settings settings.json
```

See [M365_SETUP.md](docs/setup/M365_SETUP.md) for the full settings file format, CLI flags, and SMTP configuration.


---

### SQLite results database

Scan results are persisted to `~/.gdprscanner/scanner.db` (SQLite) automatically after every scan, alongside the existing JSON session cache. The database enables cross-scan queries, trend tracking, and compliance workflows that are impractical with JSON alone.

**Tables:**

| Table | Contents |
|---|---|
| `scans` | One row per completed scan run — sources, user count, options, delta flag |
| `flagged_items` | One row per flagged file or email — full card data |
| `cpr_index` | `(SHA-256(cpr), item_id, scan_id)` — CPR numbers stored as hashes only, never plaintext |
| `pii_hits` | Per-type PII counts per item (phone, IBAN, name, address, etc.) |
| `dispositions` | Compliance officer decisions per item |
| `scan_history` | Aggregated stats per scan for trend tracking |

**API endpoints:** `GET /api/db/stats`, `GET /api/db/trend`, `GET /api/db/scans`, `POST /api/db/subject`, `GET /api/db/overdue`, `POST /api/db/disposition`, `GET /api/db/disposition/<id>`, `GET /api/db/sessions`, `GET /api/db/flagged`

If `gdpr_db.py` is not present, the scanner falls back to JSON-only mode silently.

---

### Data subject lookup

The **Data subject lookup** button in the sidebar opens a modal where you can search for all flagged items containing a specific CPR number across all scans.

- Enter a CPR number in `DDMMYY-XXXX` format and press Enter or click **Search**
- Results show file/email name, source type, date, and CPR hit count
- **Delete all for this person** button triggers bulk deletion of all matching items and refreshes the grid
- The CPR number is SHA-256 hashed before querying — it is never stored in plaintext in the database or logs

This directly supports the GDPR **right of access (Article 15)** and **right to erasure (Article 17)**.

---

### Disposition tagging

Every flagged item can be tagged with a compliance decision from the preview panel. Open any card, and the **Disposition** dropdown appears below the metadata strip.

| Value | Meaning |
|---|---|
| Unreviewed | Default — not yet assessed |
| Retain — legal obligation | Must keep (e.g. Bogføringsloven) |
| Retain — legitimate interest | Justified retention, documented |
| Retain — contract | Part of an active contract |
| Delete — scheduled | Mark for deletion at next cleanup run |
| Deleted | Already actioned |

Dispositions are saved to the `dispositions` table in the SQLite database and included in the Article 30 report.

#### Bulk disposition tagging

Click **Vælg** in the filter bar to enter select mode. Per-card checkboxes appear. Select individual cards or use **Select all visible** to select every card matching the current filters. Choose a disposition from the bulk tag bar at the bottom of the grid and click **Apply** — the selected items are updated in a single request to `POST /api/db/disposition/bulk`. Click **Done** to exit select mode.

A **disposition stats bar** above the results grid shows totals at a glance and updates after every save.

---

### Retention policy enforcement

Enable **Retention policy** in the options panel to flag items that exceed your retention threshold.

**Settings:**

| Setting | Description |
|---|---|
| Retention years | How many years to retain (default: 5) |
| Fiscal year end | Rolling (from today) / 31 Dec (Bogføringsloven) / 30 Jun / 31 Mar |

**Two cutoff modes:**

- **Rolling** — exactly N years before today. Correct for GDPR general data minimisation.
- **Fiscal year** — N years before the last completed fiscal year end. Correct for Bogføringsloven, which requires records for 5 years *from the end of the financial year*. A document from January 2020 with a Dec 31 FY must be kept until **31 December 2025**, not just until January 2025.

A live hint below the settings shows the exact cutoff date before you scan.

After scanning, items older than the cutoff receive an amber **Overdue** badge on their card. In the bulk-delete modal, **Filter overdue** pre-fills the date filter with the exact cutoff for one-click selection.

**Headless mode:**
```bash
python gdpr_scanner.py --headless --output ~/Reports/   --retention-years 5 --fiscal-year-end 12-31
```
Non-interactive (cron): deletes automatically. Interactive (TTY): prompts for confirmation.

---

### Scan profiles

Named, reusable scan configurations — save the current sidebar state as a profile, then load it in one click or run it headlessly by name.

- **Save** — prompts for a name and saves all current settings (sources, options, user selection, retention) as a profile
- **Profile dropdown** — switch between saved profiles; applying a profile populates the entire sidebar instantly
- **Profiles button** — opens the profile management modal to rename, edit description, duplicate, or delete profiles
- Profiles persist across restarts in `~/.gdprscanner/settings.json`

**Headless profile usage:**
```bash
python gdpr_scanner.py --headless --profile "Nightly email scan"
python gdpr_scanner.py --list-profiles
python gdpr_scanner.py --save-profile "Weekly full scan" --sources email onedrive
python gdpr_scanner.py --delete-profile "Old scan"
```

---

### Photo / biometric scanning

Enable ** Scan photos for faces** in the Options panel to detect photographs of identifiable persons in OneDrive, SharePoint, and Teams files.

- **Formats:** `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.webp`, `.heic`, `.heif`
- **Face detection:** OpenCV Haar cascade (`minNeighbors=8`, `min_size=80px` — conservative; requires " Scan photos for faces" opt-in)
- **EXIF extraction** — always-on for images regardless of the face detection toggle:
  - **GPS coordinates** — extracted and converted to decimal degrees; GPS badge on cards; Google Maps link in preview
  - **PII fields** — Author, Artist, Copyright, Description, UserComment, Keywords checked for content
  - **Device** — camera make/model
  - Images with GPS or PII-bearing EXIF are flagged even without CPR hits
  - `special_category` gains `gps_location` and/or `exif_pii` entries
- **GDPR classification:** Images with detected faces are automatically tagged as **Art. 9 biometric data** — the same heightened protection as health or criminal records
- ** N faces badge** — teal pill on cards; filterable via " Photos / biometric" in the Risk level dropdown
- **Article 30 report** — dedicated section listing all photo items with a 4-bullet retention guidance block (purpose limitation, pupil consent under Databeskyttelsesloven §6, website removal, archiving)
- **Excel export** — Face count column added
- **Performance:** Slower than CPR scanning — opt-in only. Recommended for targeted scans of known image folders rather than full-tenant scans

> **Datatilsynet guidance:** Danish schools have received enforcement actions specifically for unlawful retention of pupil photographs. Pupils under 15 require parental consent (Databeskyttelsesloven §6).

---

### Article 9 special categories

The scanner detects keywords from nine GDPR Article 9 special categories in proximity to CPR numbers:

| Category | Examples |
|---|---|
| Health | diagnose, sygemelding, behandling, medicin, psykiatri |
| Mental health | depression, angst, stress, selvskade |
| Criminal records | straffeoplysning, dom, straffeattest, sigtelse |
| Trade union | fagforening, tillidsrepræsentant, overenskomst |
| Religion | kirke, moské, religiøs, konfirmation |
| Ethnicity | nationalitet, herkomst, etnicitet |
| Political opinions | politisk, parti, valgkreds |
| Biometric | fingeraftryk, ansigtsgenkendelse, biometrisk |
| Sexual orientation | seksuel orientering |

Keywords are loaded from `keywords/da.json` (Danish). English (`en.json`) and German (`de.json`) files can be added without code changes. Detection uses compiled per-category regex patterns for efficient matching.

---

### Database export / import

**Export** and **Import** buttons in the sidebar ** Database** section back up or restore the entire compliance record.

```bash
# CLI equivalents
python gdpr_scanner.py --export-db ~/compliance/gdpr_export_2026.zip
python gdpr_scanner.py --import-db ~/compliance/gdpr_export_2026.zip
python gdpr_scanner.py --import-db ~/compliance/gdpr_export_2026.zip --import-mode replace --yes
```

**Export ZIP contents:**

| File | Contents |
|---|---|
| `export_meta.json` | Export date, schema version, row counts |
| `scans.json` | Scan run summaries |
| `flagged_items.json` | Flagged items — thumbnails stripped |
| `cpr_index.json` | CPR hashes (SHA-256 only) |
| `pii_hits.json` | Per-type PII counts |
| `dispositions.json` | Compliance decisions with legal basis |
| `scan_history.json` | Aggregated trend data |
| `deletion_log.json` | Full deletion audit trail |

**Import modes:** `merge` (default — adds dispositions and deletion log only, safe on live DB) or `replace` (full restore, requires `--yes`).

---

### Article 30 report

The **Art.30** button in the filter bar generates a GDPR **Article 30 Register of Processing Activities** as a Word document (`.docx`).

**Document sections:**

| Section | Contents |
|---|---|
| Summary | Scan date, items scanned, flagged count, CPR hits, estimated data subjects, overdue count, Art. 9 item count, photo/biometric count; per-source breakdown |
| Data categories | Every detected PII type with hit counts and GDPR classification (Art. 9 vs Art. 4) |
| Data inventory | Full item list sorted overdue-first; separate **Staff** and **Student** tables; name, source, account, date, CPR hits, disposition |
| Retention analysis | Separate table of overdue items *(if any)* |
| Art. 9 special categories | Item list with detected category breakdown *(if any)* |
| Photographs / biometric data | Photo item list with face counts and 4-bullet retention guidance *(if photo scanning was enabled)* |
| Compliance trend | Last 10 scans with flagged/overdue counts *(if scan history exists)* |
| Deletion audit log | Every deletion with timestamp, actor, reason, and legal basis |
| Methodology | Scanning approach and GDPR articles referenced (Art. 5, 9, 15, 17, 30) |

The document is dated and can be stored as evidence of ongoing compliance activity for supervisory authorities.

> **Requires** `python-docx` — included in `requirements.txt`.

---

### Building the desktop app

`build_gdpr.py` packages `gdpr_scanner.py` + `m365_connector.py` + `lang/` into a standalone native app using PyInstaller + pywebview.

```bash
python build_gdpr.py              # build for the current platform
python build_gdpr.py --icons-only # regenerate icon_gdpr.icns / icon_gdpr.ico
```

| Platform | Output | Native window |
|---|---|---|
| macOS | `dist/GDPRScanner.app` | WKWebView |
| Windows | `dist/GDPRScanner/GDPRScanner.exe` | WebView2 (Edge) |
| Linux | `dist/GDPRScanner/GDPRScanner` | GTK WebKit |

> **Cross-compilation is not supported** — build on the target platform, or use the pre-built binaries from the [GitHub Releases](../../releases) page.

**GitHub Actions** builds all three platforms automatically on every push to `main` and on `v*` tags. Pre-built zips are attached to each release:

| File | Platform |
|---|---|
| `GDPRScanner_windows_x64.zip` | Windows 10/11 x64 |
| `GDPRScanner_linux_x86_64.zip` | Ubuntu 22.04+ / Debian |
| `GDPRScanner_macos_x86_64.zip` | macOS 12+ Intel / Apple Silicon (Rosetta) |

> **macOS Gatekeeper:** the app is unsigned. On first launch right-click → **Open** to bypass the security warning.

---

## Internationalisation

Language files live in `lang/` alongside the scripts. As of v1.6.3 they are JSON files:

| File | Language |
|---|---|
| `lang/en.json` | English |
| `lang/da.json` | Danish |
| `lang/de.json` | German |

**Auto-detection:** On macOS and Linux the system locale is read from `defaults read -g AppleLocale` / `$LANG`. The detected language is used automatically.

**Manual override:** Create `~/.document_scanner_lang` (or `~/.m365_scanner_lang` for M365) containing just the language code, e.g. `da`. This persists across restarts.

**In-app switcher:** A language selector appears in the sidebar footer. Selecting a language saves the override and applies the new translations **in place** — the page does not reload and scan results are preserved.

**Adding a language:** Copy `lang/en.json`, translate all values, save as e.g. `lang/fr.json`. The app picks it up automatically on next start.

**Exchange folder names** are returned by Microsoft Graph in the account's own language (e.g. "Indbakke" for Danish users) and are displayed as-is. System folders are skipped using Exchange `wellKnownName` identifiers which are always in English regardless of locale, so skip logic is language-independent.

---

## Open Source

GDPR Scanner is open source software, licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

This means you are free to use, study, modify, and distribute the software. If you run a modified version as a network service (e.g. a hosted GDPR compliance tool), you must publish the source of your modifications under the same licence.

A **commercial licence** is available for organisations that need to deploy the software as a managed service without the AGPL source disclosure requirement. Contact the maintainers for details.

> **Disclaimer:** This tool is intended to assist with GDPR compliance activities. It does not constitute legal advice. You are responsible for ensuring your use complies with applicable law.

### Contributing

Contributions are welcome — bug fixes, new language files, performance improvements, and items from [SUGGESTIONS.md](SUGGESTIONS.md).

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request. For security vulnerabilities, follow the process in [SECURITY.md](SECURITY.md) — do not file public issues.

```bash
# Quick start for contributors
git clone https://github.com/your-org/gdpr-scanner.git
cd gdpr-scanner
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python gdpr_scanner.py    # GDPRScanner on port 5100 (auto-increments if in use)
```

### Test suite

GDPRScanner ships with a `pytest` test suite covering the CPR detection engine, configuration layer, checkpoint persistence, and the SQLite database.

```bash
pip install pytest
pytest tests/
```

**128 tests across 4 modules — all expected to pass.**

| Module | Tests | Covers |
|---|---|---|
| `tests/test_document_scanner.py` | 36 | `is_valid_cpr`, `extract_matches`, `scan_docx`, `scan_xlsx`, `_scan_bytes` — CPR detection, false-positive suppression, binary crash safety |
| `tests/test_app_config.py` | 34 | i18n loading, Article 9 keyword detection, config round-trip, admin PIN, profiles CRUD, Fernet encryption |
| `tests/test_checkpoint.py` | 18 | Checkpoint key stability, save/load/clear, wrong-key isolation, delta token round-trip |
| `tests/test_db.py` | 24 | Scan lifecycle, CPR hash-only storage, data subject lookup, dispositions, export/import cycle |

Each new module (`cpr_detector.py`, `app_config.py`, `checkpoint.py`, `gdpr_db.py`) is importable in isolation without Flask or MSAL — tests run without any cloud credentials or a running server.

The test suite should be run before every release and after any change to `document_scanner.py`, `cpr_detector.py`, or `gdpr_db.py`. CPR detection is the legal core of the tool — a false negative means a real GDPR violation goes undetected.

### Roadmap

See [SUGGESTIONS.md](SUGGESTIONS.md) for the full feature roadmap with implementation status.

---

## Project files

| File | Description |
|---|---|
| `gdpr_scanner.py` | Flask entry point — scan orchestration, SSE route (`/api/scan/stream`), root route |
| `scan_engine.py` | M365 and local/SMB scan logic — `run_scan()`, `run_file_scan()` |
| `app_config.py` | All persistence — profiles, settings, SMTP config, lang loading, Fernet encryption |
| `sse.py` | SSE broadcast queue and `_current_scan_id` |
| `checkpoint.py` | Mid-scan checkpoint save/load, `_checkpoint_key()` |
| `cpr_detector.py` | CPR pattern matching and validation |
| `document_scanner.py` | Core scanning, redaction, OCR, NER, and PII detection engine |
| `gdpr_db.py` | SQLite persistence layer — scan results, CPR index, PII hits, dispositions, scan history |
| `m365_connector.py` | Microsoft Graph API client — auth, token refresh, email/OneDrive/SharePoint/Teams fetchers, delete methods |
| `google_connector.py` | Google Workspace API client — Gmail, Drive, Admin SDK |
| `file_scanner.py` | Unified local + SMB/CIFS file iterator — `FileScanner.iter_files()` yields `(path, bytes, metadata)`. SMB reads use a 1-slot sliding-window `ThreadPoolExecutor` (`PREFETCH_WINDOW=1`) with a 60-second per-file timeout. |
| `scan_scheduler.py` | In-process APScheduler wrapper — multi-job scheduled scan engine |
| `templates/index.html` | Single-page HTML shell — Jinja2 template. Two variables: `app_version`, `lang_json`. |
| `static/style.css` | All application CSS — custom properties, layout, components, light/dark themes |
| `static/js/state.js` | Shared mutable state module (`export const S`) — imported by all 12 feature modules |
| `static/js/*.js` | 12 ES modules: `ui`, `log`, `users`, `auth`, `profiles`, `scan`, `results`, `sources`, `scheduler`, `connector`, `viewer`, `history` |
| `static/app.js` | Archived JS monolith — no longer loaded |
| `routes/__init__.py` | Blueprint package marker |
| `routes/state.py` | Shared mutable state (`connector`, `flagged_items`, `LANG`, scan locks) — imported by all blueprints |
| `routes/auth.py` | `/api/auth/*` — M365 connect, status, sign-out, config |
| `routes/google_auth.py` | `/api/google/*` — Google Workspace connect, status, sign-out |
| `routes/google_scan.py` | `/api/google/scan/*` — Google scan execution |
| `routes/scan.py` | `/api/scan/*` — start/stop, checkpoint, settings, src toggles |
| `routes/users.py` | `/api/users/*` — listing, role overrides, license debug |
| `routes/sources.py` | `/api/file_sources/*` and `/api/file_scan/start` |
| `routes/profiles.py` | `/api/profiles/*` and `/api/delta/*` |
| `routes/scheduler.py` | `/api/scheduler/*` — job CRUD, status, history, run-now |
| `routes/email.py` | `/api/smtp/*` and `/api/send_report` |
| `routes/database.py` | `/api/db/*`, `/api/admin/*`, `/api/preview`, `/api/thumb` |
| `routes/export.py` | `/api/export_excel`, `/api/export_article30`, `/api/delete_bulk` |
| `routes/viewer.py` | `/view`, `/api/viewer/tokens`, `/api/viewer/pin` — read-only viewer mode: token + PIN auth, share-link management, role-scoped and user-scoped tokens |
| `routes/app_routes.py` | `/api/about`, `/api/langs`, `/api/lang`, `/manual` |
| `docs/manuals/MANUAL-EN.md` | End-user manual in English (15 sections) — served at `/manual?lang=en` |
| `docs/manuals/MANUAL-DA.md` | End-user manual in Danish (15 sections) — served at `/manual?lang=da` |
| `docs/setup/M365_SETUP.md` | Step-by-step Microsoft 365 setup guide |
| `docs/setup/GOOGLE_SETUP.md` | Step-by-step Google Workspace setup guide |
| `build_gdpr.py` | PyInstaller build script — generates `m365_launcher.py`, packages desktop app |
| `lang/en.json` | English translations (source of truth) |
| `lang/da.json` | Danish translations (primary language) |
| `lang/de.json` | German translations |
| `keywords/da.json` | Danish Article 9 special-category keyword list (454 keywords, 9 categories) |
| `classification/m365_skus.json` | Microsoft Education SKU IDs and part-number fragments for student/staff role classification — edit to add new SKUs without code changes |
| `classification/google_ou_roles.json` | Google OU path → role mapping |
| `requirements.txt` | Python dependency list — use with `pip install -r requirements.txt` |
| `run_tests.sh` | Activates venv and runs the full test suite; forwards any extra args to pytest |
| `install_macos.sh` | Bash installer — Homebrew, Python 3.12, Tesseract, Poppler, `./venv`, spaCy model |
| `install_windows.ps1` | PowerShell installer — Chocolatey, Python 3.12, Tesseract, Poppler, `.\\venv`, spaCy model |
| `VERSION` | Current version number — single source of truth |
| `CHANGELOG.md` | Release history and versioning policy |
| `LICENSE` | GNU Affero General Public License v3.0 |
| `CONTRIBUTING.md` | Development setup, code style guide, and pull request process |
| `SECURITY.md` | How to report security vulnerabilities responsibly |
| `.gitignore` | Excludes credentials, databases, venv, and build artifacts from version control |
