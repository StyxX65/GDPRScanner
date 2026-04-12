# Python Dependencies

All Python modules used in the GDPR Scanner project, with a short explanation of each.

## Third-party packages (install via `pip install -r requirements.txt`)

### Web server
| Module | Purpose |
|---|---|
| `flask` | Web server and API routing for the GDPRScanner UI |

### Microsoft 365 authentication and API
| Module | Purpose |
|---|---|
| `msal` | Microsoft Authentication Library — handles OAuth2 device code flow (delegated) and client credentials (application) for Microsoft Graph API access |
| `requests` | HTTP client used for all Microsoft Graph API calls |

### Google Workspace scanning
| Module | Purpose |
|---|---|
| `google-auth` | Service account authentication and domain-wide delegation for Google APIs |
| `google-auth-httplib2` | HTTP transport adapter for `google-auth` |
| `google-api-python-client` | Gmail API, Google Drive API, and Admin Directory API client |

### SMB / file system scanning
| Module | Purpose |
|---|---|
| `smbprotocol` | SMB2/3 network share scanning without requiring a mounted drive — used for Windows file server sources |
| `keyring` | OS keychain credential storage for SMB passwords |
| `python-dotenv` | `.env` file fallback for headless SMB credentials when no keychain is available |

### PDF handling
| Module | Purpose |
|---|---|
| `pdfplumber` | Text extraction from PDFs with a selectable text layer — fast and accurate for native PDFs |
| `pymupdf` (fitz) | Physically removes the text layer from PDFs — preferred GDPR-compliant redaction method |
| `pdf2image` *(optional)* | Converts PDF pages to images (via Poppler) for OCR processing of scanned/image-based PDFs |
| `pytesseract` *(optional)* | Python wrapper for the Tesseract OCR engine — extracts text from rasterised PDF pages and images |
| `pypdf` *(optional)* | PDF metadata reading and low-level page manipulation — used in the `document_scanner.py` redaction path |
| `reportlab` *(optional)* | Fallback PDF redaction via overlay rendering — used when PyMuPDF is unavailable |

> Optional packages are not in `requirements.txt`. Install them manually if you need OCR or the standalone `document_scanner.py` CLI.

### Document formats
| Module | Purpose |
|---|---|
| `python-docx` | Read and write `.docx` Word documents; also used to generate the Article 30 Register of Processing Activities report |
| `openpyxl` | Read and write `.xlsx` Excel files — used for the scan result export workbook |

### Image processing and face detection
| Module | Purpose |
|---|---|
| `opencv-python` (cv2) | Face detection in images via Haar cascade classifiers; also used for face blurring during anonymisation |
| `numpy` | Array operations required internally by OpenCV |
| `Pillow` (PIL) | Image manipulation — thumbnail generation, format conversion, EXIF metadata extraction |

### NLP / Named Entity Recognition
| Module | Purpose |
|---|---|
| `spacy` | NLP engine for Danish Named Entity Recognition — detects person names, addresses, and organisations in text. Requires the `da_core_news_lg` model (~500 MB) |

### Encryption
| Module | Purpose |
|---|---|
| `cryptography` | Fernet symmetric encryption — encrypts SMTP passwords at rest in `~/.gdprscanner/smtp.json`; the Fernet key is derived from `~/.gdprscanner/machine_id` |

### Scheduling
| Module | Purpose |
|---|---|
| `APScheduler` | In-process background scheduler — drives the scheduled scan feature (`schedule.json`). Uses `BackgroundScheduler` with `CronTrigger` |

### System monitoring
| Module | Purpose |
|---|---|
| `psutil` | Available-memory probe in `scan_engine.py` — skips file downloads when free RAM drops below 300 MB to prevent OOM crashes on large tenants |

### Desktop app packaging
| Module | Purpose |
|---|---|
| `pywebview` | Renders the Flask web UI inside a native OS window, creating a macOS `.app` or Windows `.exe` without requiring a browser |
| `pystray` | System tray icon integration for the desktop app builds |
| `pyinstaller` | Packages the Python application and all dependencies into a standalone executable |
| `pyinstaller-hooks-contrib` | Community-maintained hooks that help PyInstaller correctly bundle complex packages like spaCy and OpenCV |

---

## Standard library modules (no installation needed)

### Data storage
| Module | Purpose |
|---|---|
| `sqlite3` | SQLite database — stores scan results, CPR index (hashed), dispositions, deletion audit log, and scan history in `~/.gdprscanner/scanner.db` |
| `json` | Config files, checkpoint files, language files, API request/response serialisation |
| `zipfile` | Database export/import archive creation and reading; also used in the PyInstaller build process |
| `csv` | CSV file scanning support |

### Security and hashing
| Module | Purpose |
|---|---|
| `hashlib` | SHA-256 hashing of CPR numbers before storage — raw CPR values are never written to the database |
| `secrets` | Cryptographically secure random values — used for viewer token generation and auth state parameters |
| `uuid` | UUID generation for viewer tokens and scan session identifiers |

### File system and paths
| Module | Purpose |
|---|---|
| `pathlib` | Cross-platform file and directory path handling throughout the codebase |
| `tempfile` | Temporary files for PDF and image processing — avoids leaving artefacts on disk |
| `shutil` | File copy and directory tree operations used in the build scripts |

### Networking and email
| Module | Purpose |
|---|---|
| `smtplib` | SMTP email delivery for the scheduled report feature — supports STARTTLS and SMTPS/SSL |
| `email` | Email message construction (MIME) for the SMTP report feature |
| `socket` | UDP probe to determine the machine's LAN IP address — used to build routable share links for viewer tokens |

### Text and pattern matching
| Module | Purpose |
|---|---|
| `re` | Regular expression engine — CPR pattern matching, phone numbers, IBANs, email addresses, Danish bank account numbers |

### Concurrency
| Module | Purpose |
|---|---|
| `threading` | Background scan thread so the Flask web UI stays responsive during long scans |
| `queue` | Server-Sent Events message queue — passes scan results from the background thread to the browser |
| `concurrent.futures` | `ProcessPoolExecutor` for parallel OCR processing of multi-page PDFs |
| `gc` | Explicit garbage collection after large scan batches to release memory promptly |

### I/O and streams
| Module | Purpose |
|---|---|
| `io` | In-memory byte streams for generating Excel and Word documents without writing to disk |
| `struct` | Binary data unpacking used in some PDF processing paths |

### Date and time
| Module | Purpose |
|---|---|
| `time` | Unix timestamps for scan records, audit log entries, and token expiry tracking |
| `datetime` | Human-readable date/time formatting for reports, filenames, and retention cutoff calculations |

### System and process
| Module | Purpose |
|---|---|
| `platform` | Detects the operating system for macOS/Windows-specific code paths |
| `subprocess` | Launches Tesseract and Poppler as external processes for OCR and PDF rendering |
| `argparse` | CLI argument parsing for `--headless`, `--reset-db`, `--export-db`, `--import-db`, etc. |
| `sys` | Python runtime access — `sys.exit()`, `sys.path`, `sys.version` |
| `os` | Environment variables and low-level file operations |
| `logging` | Application-level logging — routes warnings and errors to stderr and rotating file handlers |

### Encoding and serialisation
| Module | Purpose |
|---|---|
| `base64` | Encodes thumbnail images as base64 strings for embedding in JSON API responses |

---

## External system dependencies (not Python packages)

These must be installed separately — the installers (`install_windows.ps1`, `install_macos.sh`) handle this automatically.

| Tool | Purpose |
|---|---|
| Tesseract OCR | The OCR engine called by `pytesseract` — required for scanning image-based PDFs |
| Tesseract language packs | `dan` (Danish) and `eng` (English) language data files for Tesseract |
| Poppler | PDF rendering tools (`pdftoppm`, `pdfinfo`) required by `pdf2image` |
