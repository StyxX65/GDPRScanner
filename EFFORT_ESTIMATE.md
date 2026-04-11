# GDPRScanner — Build Effort Estimate

Estimated man-hours to build this project from scratch, based on static analysis of v1.6.13.

---

## Codebase Stats

| Metric | Count |
|---|---|
| Source files (excl. dist / build / venv) | ~70 |
| Lines of code (Python + JS + HTML + CSS) | ~25,400 |
| Test lines | ~1,280 (128 tests) |
| Language files | ~2,300 lines (DA / EN / DE) |
| Current version | v1.6.13 |

---

## Estimate by Component

| Component | Key Files | LOC | Hours |
|---|---|---|---|
| **CPR detector** — regex, modulo-11 validation, context filtering, false-positive suppression | `cpr_detector.py` | 446 | 40–60 |
| **Document scanner** — PDF text + OCR, Word, Excel, PowerPoint, images; memory-safe page-by-page processing | `document_scanner.py` | 2,659 | 160–240 |
| **Microsoft 365 connector** — Exchange mail, OneDrive, SharePoint, Teams, delta sync, Microsoft Graph API, MSAL auth | `m365_connector.py`, `scan_engine.py`, `m365_launcher.py` | 2,748 | 240–320 |
| **Google Workspace connector** — Gmail, Google Drive, service account + OAuth 2.0 flows | `google_connector.py`, `routes/google_scan.py`, `routes/google_auth.py` | 1,300 | 120–160 |
| **File / SMB scanner** — local filesystem and network share scanning | `file_scanner.py` | 600 | 40–80 |
| **Database layer** — SQLite schema, migrations, scan sessions, dispositions, delta tracking | `gdpr_db.py` | 954 | 80–120 |
| **Export system** — formatted Excel reports, GDPR Article 30 Word documents | `routes/export.py` | 1,222 | 120–160 |
| **Flask app + SSE + orchestration** — server-sent events, scan threading, checkpointing, resume | `gdpr_scanner.py`, `sse.py`, `checkpoint.py` | 2,400 | 120–160 |
| **Frontend SPA** — 11 ES modules, real-time progress, results viewer, profiles, sources panel, viewer mode | `static/js/*.js`, `templates/index.html`, `static/style.css` | 7,800 | 200–280 |
| **App config + persistence + encryption** — profiles, settings, SMTP, Fernet key, viewer tokens + PIN | `app_config.py` | 794 | 40–80 |
| **Desktop app builder** — PyInstaller packaging for macOS and Windows, embedded webview | `build_gdpr.py` | 1,095 | 80–120 |
| **Scheduler** — cron-like scheduled scans, background thread management | `scan_scheduler.py`, `routes/scheduler.py`, `static/js/scheduler.js` | 1,084 | 40–80 |
| **Auth + viewer mode + roles** — M365 / Google OAuth, viewer tokens, PIN brute-force protection, SKU role classification | `routes/auth.py`, `routes/viewer.py`, `static/js/auth.js`, `static/js/viewer.js` | 750 | 80–120 |
| **Multi-language support** — Danish, English, German UI strings | `lang/da.json`, `lang/en.json`, `lang/de.json` | 2,300 | 40–60 |
| **Test suite** — 128 unit tests | `tests/` | 1,282 | 40–80 |
| **Documentation + CI/CD + install scripts** — GitHub Actions, macOS / Windows installers, user manuals | `docs/`, `.github/`, `*.sh`, `*.ps1` | — | 40–60 |

---

## Total Estimate

| Scenario | Hours | Calendar time (1 dev, 40 hrs/wk) | Calendar time (2-person team) |
|---|---|---|---|
| **Low** | ~1,500 | ~9 months | ~5 months |
| **Mid** | ~2,000 | ~12 months | ~6 months |
| **High** | ~2,500 | ~15 months | ~8 months |

The mid estimate (~2,000 hours) is the most realistic for a single senior developer building iteratively toward a v1.6 release.

---

## Complexity Drivers

These factors push the estimate beyond what raw line counts suggest:

- **Microsoft Graph API** — Exchange, SharePoint, and Teams scanning involve underdocumented API behaviour, throttling, delta-token management, and permission edge cases. Research and debugging overhead is substantial.
- **CPR validation domain knowledge** — Danish modulo-11 rules, context-aware false-positive filtering, and handling of anonymised or test numbers requires specialised understanding.
- **Memory management at scale** — The `deque`-drain pattern, page-by-page OCR image freeing, and pre-scan memory guards (`psutil`) are non-obvious and emerged through iteration on large tenants.
- **Cross-platform desktop packaging** — Producing a signed `.app` for macOS and an `.exe` for Windows via PyInstaller, with an embedded webview, is a significant and ongoing maintenance burden.
- **SSE + Flask threading** — Correct scan locking, SSE fan-out, and safe state sharing across threads is difficult to get right without subtle race conditions.
- **Version iteration** — v1.6.13 represents at least 13 significant release cycles. The first working prototype likely consumed roughly half the total hours; the accumulated refinement accounts for the rest.

---

*Generated 2026-04-11 based on static analysis of GDPRScanner v1.6.13.*
