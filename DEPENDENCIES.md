# Python Dependencies

All Python modules used in the GDPR Scanner project, with a short explanation of each.

## Third-party packages (install via `pip install -r requirements.txt`)

### Web server
| Module | Purpose |
|---|---|
| `flask` | Web server and API routing for both the GDPRScanner UI |

### Microsoft 365 authentication and API
| Module | Purpose |
|---|---|
| `msal` | Microsoft Authentication Library — handles OAuth2 device code flow (delegated) and client credentials (application) for Microsoft Graph API access |
| `requests` | HTTP client used for all Microsoft Graph API calls |

### PDF handling
| Module | Purpose |
|---|---|
| `pdfplumber` | Text extraction from PDFs with a selectable text layer — fast and accurate for native PDFs |
| `pdf2image` | Converts PDF pages to images (via Poppler) for OCR processing of scanned/image-based PDFs |
| `pytesseract` | Python wrapper for the Tesseract OCR engine — extracts text from rasterised PDF pages and images |
| `pypdf` | PDF metadata reading and low-level page manipulation |
| `reportlab` | Fallback PDF redaction via overlay rendering — used when PyMuPDF is unavailable |
| `pymupdf` (fitz) | Physically removes the text layer from PDFs — preferred GDPR-compliant redaction method |

### Document formats
| Module | Purpose |
|---|---|
| `python-docx` | Read and write `.docx` Word documents; also used to generate the Article 30 Register of Processing Activities report |
| `openpyxl` | Read and write `.xlsx` Excel files — used for the scan result export workbook |
| `img2pdf` | Converts images to PDF for archiving redacted output |

### Image processing and face detection
| Module | Purpose |
|---|---|
| `opencv-python` (cv2) | Face detection in images via Haar cascade classifiers; also used for face blurring during anonymisation |
| `numpy` | Array operations required internally by OpenCV |
| `Pillow` (PIL) | Image manipulation — thumbnail generation, format conversion, image resizing |

### NLP / Named Entity Recognition
| Module | Purpose |
|---|---|
| `spacy` | NLP engine for Danish Named Entity Recognition — detects person names, addresses, and organisations in text. Requires the `da_core_news_lg` model (~500 MB) |

### Archive scanning
| Module | Purpose |
|---|---|
| `py7zr` | 7-Zip archive support — allows the scanner to inspect `.7z` compressed files |

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
| `sqlite3` | SQLite database — stores scan results, CPR index (hashed), dispositions, deletion audit log, and scan history in `~/.gdpr_scanner.db` |
| `json` | Config files, checkpoint files, language files, API request/response serialisation |
| `zipfile` | Database export/import archive creation and reading; also used in the PyInstaller build process |
| `csv` | CSV file scanning support in the Document Scanner |

### Security and hashing
| Module | Purpose |
|---|---|
| `hashlib` | SHA-256 hashing of CPR numbers before storage — raw CPR values are never written to the database |
| `secrets` | Cryptographically secure random values (used in auth state parameters) |

### File system and paths
| Module | Purpose |
|---|---|
| `pathlib` | Cross-platform file and directory path handling throughout the codebase |
| `tempfile` | Temporary files for PDF and image processing — avoids leaving artefacts on disk |
| `shutil` | File copy and directory tree operations used in the build scripts |

### Networking and email
| Module | Purpose |
|---|---|
| `smtplib` | SMTP email delivery for the headless report feature — supports STARTTLS and SMTPS/SSL |
| `email` | Email message construction (MIME) for the SMTP report feature |

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

### I/O and streams
| Module | Purpose |
|---|---|
| `io` | In-memory byte streams for generating Excel and Word documents without writing to disk |
| `struct` | Binary data unpacking (used in some PDF processing paths) |

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
| `argparse` | CLI argument parsing for `--headless`, `--reset-db`, `--export-db`, `--import-db` etc. |
| `sys` | Python runtime access — sys.exit(), sys.path, sys.version |
| `os` | Environment variables and low-level file operations |

### Encoding and serialisation
| Module | Purpose |
|---|---|
| `base64` | Encodes thumbnail images as base64 strings for embedding in JSON API responses |
| `struct` | Binary format parsing used in some document processing paths |

---

## External system dependencies (not Python packages)

These must be installed separately — the installers (`install_windows.ps1`, `install_macos.sh`) handle this automatically.

| Tool | Purpose |
|---|---|
| Tesseract OCR | The OCR engine called by `pytesseract` — required for scanning image-based PDFs |
| Tesseract language packs | `dan` (Danish) and `eng` (English) language data files for Tesseract |
| Poppler | PDF rendering tools (`pdftoppm`, `pdfinfo`) required by `pdf2image` |
