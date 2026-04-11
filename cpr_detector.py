"""
cpr_detector.py — File scanning and CPR/PII detection for GDPRScanner.

Provides:
  _scan_bytes(content, filename)    — dispatch to correct scanner by file type
  _scan_text_direct(text)           — scan a plain text string
  _extract_exif(content, filename)  — extract PII-bearing EXIF tags from images
  _detect_photo_faces(content, fn)  — count faces in an image (OpenCV)
  _get_pii_counts(text)             — NER-based PII type counts
  _make_thumb(content, filename)    — JPEG thumbnail as base64 string
  _placeholder_svg(ext, name)       — SVG file-type icon

Globals SCANNER_OK, PIL_OK, PHOTO_EXTS, SUPPORTED_EXTS, ds, PILImage, LANG,
and _check_special_category are injected at startup by gdpr_scanner.py via
`from cpr_detector import *` AFTER those names are defined.  This keeps the
module cleanly importable in isolation for unit tests (#26) while preserving
the existing runtime behaviour.
"""
from __future__ import annotations
import base64
import hashlib
import io
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

# Only one PDF subprocess may run at a time — each spawned process loads
# ~150-300 MB of Python libs (pdfplumber, pdf2image, pytesseract).
# Serialising them prevents overlapping subprocesses from exhausting RAM.
_pdf_subprocess_sem = threading.Semaphore(1)

# ── Lazy fallbacks for standalone / test imports ──────────────────────────────
# When imported in isolation (e.g. pytest), these defaults prevent NameErrors.
# gdpr_scanner.py overwrites them at startup via explicit assignment.
try:
    import document_scanner as ds
    SCANNER_OK = True
except ImportError:
    ds = None  # type: ignore[assignment]
    SCANNER_OK = False

try:
    from PIL import Image as PILImage
    PIL_OK = True
except ImportError:
    PILImage = None  # type: ignore[assignment]
    PIL_OK = False

SUPPORTED_EXTS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".csv",
    ".txt", ".eml", ".msg",
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp",
}
PHOTO_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif",
}
LANG: dict = {}

def _check_special_category(text: str, cprs: list) -> list:
    """Stub — overwritten by app_config._check_special_category at startup."""
    return []


# EXIF tags that may contain PII
# EXIF tags that may contain genuinely personal data (name, description, keywords).
# Deliberately excludes hardware/OS fields (HostComputer, Software, Make, Model,
# DocumentName, PageName) that are set automatically by the OS on every screenshot
# and carry no personal information about an individual.
_EXIF_PII_TAGS = {
    "Artist", "Copyright", "ImageDescription", "UserComment",
    "XPAuthor", "XPSubject", "XPComment", "XPKeywords",
}

# Minimum character length for a PII field value to be considered meaningful.
# Prevents single-letter or empty values from triggering a flag.
_EXIF_PII_MIN_LEN = 3

def _extract_exif(content: bytes, filename: str) -> dict:
    """Extract EXIF metadata from an image file.

    Returns a dict with keys:
        gps       — {lat, lon, lat_ref, lon_ref, maps_url} or None
        pii_fields — {tag: value} for fields containing potential PII
        author    — str or None
        datetime  — str or None
        device    — str or None
        has_pii   — bool
    """
    result = {"gps": None, "pii_fields": {}, "author": None,
              "datetime": None, "device": None, "has_pii": False}

    if not PIL_OK:
        return result

    try:
        from PIL import Image as _Img, ExifTags as _ExifTags
        import io
        img = _Img.open(io.BytesIO(content))

        # Get raw EXIF
        raw = getattr(img, "_getexif", lambda: None)()
        if not raw:
            # Try newer Pillow API
            exif_data = img.getexif()
            raw = {k: v for k, v in exif_data.items()}

        if not raw:
            return result

        tag_names = {v: k for k, v in _ExifTags.TAGS.items()}

        # Build human-readable dict
        named = {}
        for tag_id, value in raw.items():
            tag = _ExifTags.TAGS.get(tag_id, str(tag_id))
            named[tag] = value

        # Author / description fields
        for field in _EXIF_PII_TAGS:
            val = named.get(field)
            if val:
                try:
                    # UserComment is bytes with encoding prefix
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace").strip("\x00 ")
                    elif not isinstance(val, str):
                        val = str(val)
                    if val.strip() and len(val.strip()) >= _EXIF_PII_MIN_LEN:
                        result["pii_fields"][field] = val.strip()
                        result["has_pii"] = True
                except Exception:
                    pass

        if named.get("Artist"):
            result["author"] = str(named["Artist"])
        elif named.get("XPAuthor"):
            result["author"] = str(named["XPAuthor"])

        if named.get("DateTimeOriginal"):
            result["datetime"] = str(named["DateTimeOriginal"])
        elif named.get("DateTime"):
            result["datetime"] = str(named["DateTime"])

        make  = named.get("Make", "")
        model = named.get("Model", "")
        if make or model:
            result["device"] = f"{make} {model}".strip()

        # GPS
        gps_raw = named.get("GPSInfo")
        if gps_raw and isinstance(gps_raw, dict):
            try:
                gps_tags = {_ExifTags.GPSTAGS.get(k, k): v for k, v in gps_raw.items()}

                def _dms_to_decimal(dms, ref):
                    if not dms or len(dms) < 3:
                        return None
                    deg, mn, sec = dms
                    # Pillow may return IFDRational objects
                    deg = float(deg); mn = float(mn); sec = float(sec)
                    dec = deg + mn / 60 + sec / 3600
                    if ref in ("S", "W"):
                        dec = -dec
                    return round(dec, 7)

                lat = _dms_to_decimal(
                    gps_tags.get("GPSLatitude"),
                    gps_tags.get("GPSLatitudeRef", "N"),
                )
                lon = _dms_to_decimal(
                    gps_tags.get("GPSLongitude"),
                    gps_tags.get("GPSLongitudeRef", "E"),
                )
                if lat is not None and lon is not None:
                    result["gps"] = {
                        "lat":      lat,
                        "lon":      lon,
                        "lat_ref":  gps_tags.get("GPSLatitudeRef", "N"),
                        "lon_ref":  gps_tags.get("GPSLongitudeRef", "E"),
                        "maps_url": f"https://www.google.com/maps?q={lat},{lon}",
                    }
                    result["has_pii"] = True
            except Exception:
                pass

    except Exception:
        pass

    return result



    """Detect faces in an image file using OpenCV Haar cascades.

    Returns the number of faces detected, or 0 if cv2 is unavailable,
    the file is not a supported image format, or decoding fails.
    Face detection is intentionally strict (minNeighbors=8, min_size=80px) to
    reduce false positives on background textures, labels, and artwork.
    Haar cascades are tuned for compliance flagging, not exhaustive detection.  (#9)
    """
    if not SCANNER_OK:
        return 0
    try:
        cv2_mod = getattr(ds, "_get_cv2", None)
        if cv2_mod is None:
            return 0
        cv2, np = ds._get_cv2()
        if cv2 is None or np is None:
            return 0
    except Exception:
        return 0

    try:
        # Decode image bytes → cv2 BGR array
        arr = np.frombuffer(content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            # imdecode failed (e.g. HEIC without codec) — try PIL fallback
            if PIL_OK:
                try:
                    from PIL import Image as _PILImg
                    import io as _io
                    pil_img = _PILImg.open(_io.BytesIO(content)).convert("RGB")
                    pil_arr = np.array(pil_img)
                    img = cv2.cvtColor(pil_arr, cv2.COLOR_RGB2BGR)
                except Exception:
                    return 0
            else:
                return 0

        faces = ds.detect_faces_cv2(img, min_size=80, neighbors=8)
        return len(faces)
    except Exception:
        return 0

def _detect_photo_faces(content: bytes, filename: str) -> int:
    """Detect faces in an image file using OpenCV Haar cascades.

    Returns the number of faces detected, or 0 if cv2 is unavailable,
    the file is not a supported image format, or decoding fails.
    Face detection is intentionally strict (minNeighbors=8, min_size=80px) to
    reduce false positives on background textures, labels, and artwork.
    Haar cascades are tuned for compliance flagging, not exhaustive detection.  (#9)
    """
    if not SCANNER_OK:
        return 0
    try:
        cv2_mod = getattr(ds, "_get_cv2", None)
        if cv2_mod is None:
            return 0
        cv2, np = ds._get_cv2()
        if cv2 is None or np is None:
            return 0
    except Exception:
        return 0

    try:
        arr = np.frombuffer(content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            if PIL_OK:
                try:
                    from PIL import Image as _PILImg
                    import io as _io
                    pil_img = _PILImg.open(_io.BytesIO(content)).convert("RGB")
                    pil_arr = np.array(pil_img)
                    img = cv2.cvtColor(pil_arr, cv2.COLOR_RGB2BGR)
                except Exception:
                    return 0
            else:
                return 0

        faces = ds.detect_faces_cv2(img, min_size=80, neighbors=8)
        return len(faces)
    except Exception:
        return 0


def _scan_bytes(content: bytes, filename: str, poppler_path=None) -> dict:
    """Scan raw bytes for CPRs. Returns scanner result dict."""
    if not SCANNER_OK:
        return {"cprs": [], "dates": [], "error": "scanner not available"}
    ext = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        if ext == ".pdf":
            # Check if the PDF has a text layer before running full scan_pdf.
            # Image-only PDFs (scanned documents) have no text and would trigger
            # Tesseract OCR subprocesses that hang indefinitely on some files.
            try:
                import pdfplumber as _pp, io as _io
                with _pp.open(_io.BytesIO(content)) as _pdf:
                    has_text = any(ds.is_text_page(p) for p in _pdf.pages)
                if not has_text:
                    return {"cprs": [], "dates": []}  # image-only PDF — no CPRs possible
            except Exception:
                pass  # if pdfplumber fails, fall through to full scan_pdf
            return ds.scan_pdf(tmp_path, poppler_path=poppler_path)
        elif ext in {".docx", ".doc"}:
            return ds.scan_docx(tmp_path)
        elif ext in {".xlsx", ".xlsm"}:
            return ds.scan_xlsx(tmp_path)
        elif ext == ".csv":
            return ds.scan_csv(tmp_path)
        elif ext == ".txt":
            text = content.decode("utf-8", errors="replace")
            cprs, dates = ds.extract_matches(text, 1, "text")
            return {"cprs": cprs, "dates": dates}
        elif ext in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}:
            return ds.scan_image(tmp_path)
        else:
            # Try plain text
            try:
                text = content.decode("utf-8", errors="replace")
                cprs, dates = ds.extract_matches(text, 1, "text")
                return {"cprs": cprs, "dates": dates}
            except Exception:
                return {"cprs": [], "dates": []}
    except Exception as e:
        return {"cprs": [], "dates": [], "error": str(e)}
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

def _worker_scan_pdf(pdf_path_str: str, result_q) -> None:
    """Worker executed in a spawned subprocess — must be a module-level function."""
    try:
        import document_scanner as _ds
        from pathlib import Path as _Path
        result_q.put(_ds.scan_pdf(_Path(pdf_path_str)))
    except Exception as e:
        result_q.put({"cprs": [], "dates": [], "error": str(e)})


def _scan_bytes_timeout(content: bytes, filename: str, timeout: int = 60) -> dict:
    """Like _scan_bytes but runs PDF scanning in a spawned subprocess with a hard timeout.

    For non-PDF files delegates straight to _scan_bytes.  For PDFs it writes the
    bytes to a temp file, spawns a fresh Python process (spawn context — safe on
    macOS/Flask), and joins with *timeout* seconds.  If the worker is still alive
    after the timeout it is forcibly terminated so the scan thread is never blocked.
    """
    ext = Path(filename).suffix.lower()
    if ext != ".pdf":
        return _scan_bytes(content, filename)

    import multiprocessing
    ctx = multiprocessing.get_context("spawn")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path_str = tmp.name
    del content  # written to temp file — release raw bytes before subprocess loads

    try:
        with _pdf_subprocess_sem:
            q = ctx.Queue()
            p = ctx.Process(target=_worker_scan_pdf, args=(tmp_path_str, q))
            p.start()
            p.join(timeout)
            if p.is_alive():
                p.terminate()
                p.join()
                return {"cprs": [], "dates": [], "error": f"PDF OCR timed out after {timeout}s"}
            try:
                return q.get_nowait()
            except Exception:
                return {"cprs": [], "dates": [], "error": "Worker returned no result"}
    finally:
        try:
            Path(tmp_path_str).unlink()
        except Exception:
            pass


def _scan_text_direct(text: str) -> dict:
    """Scan a plain text string for CPRs using extract_matches.
    
    Uses ds.extract_matches() directly rather than ds.scan_text() because
    scan_text() calls extract_cpr_and_dates() which is not defined in
    document_scanner.py (pre-existing bug).
    """
    if not SCANNER_OK or not text:
        return {"cprs": [], "dates": []}
    try:
        cprs, dates = ds.extract_matches(text, 1, "text")
        return {"cprs": cprs, "dates": dates}
    except Exception:
        return {"cprs": [], "dates": []}

def _html_esc(s: str) -> str:
    """HTML-escape a string for safe inline embedding."""
    import html as _h
    return _h.escape(str(s))


def _get_pii_counts(text: str) -> dict:
    """Run count_pii_types on text if the scanner is available."""
    if not SCANNER_OK:
        return {}
    try:
        return ds.count_pii_types(text, use_ner=True)
    except Exception:
        return {}


def _make_thumb(content: bytes, filename: str) -> str:
    """Make a small base64 thumbnail from image bytes, or return SVG placeholder."""
    ext = Path(filename).suffix.lower()
    if not PIL_OK or ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return _placeholder_svg(ext, filename)
    try:
        img = PILImage.open(io.BytesIO(content)).convert("RGB")
        img.thumbnail((280, 360), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return _placeholder_svg(ext, filename)

def _placeholder_svg(ext: str, name: str) -> str:
    colors = {
        ".pdf":  ("#E8453C", "PDF"),  ".docx": ("#2B7CD3", "DOCX"),
        ".doc":  ("#2B7CD3", "DOC"),  ".xlsx": ("#1E7145", "XLSX"),
        ".xlsm": ("#1E7145", "XLSM"), ".csv":  ("#6B7280", "CSV"),
        ".eml":  ("#8B44AD", "EML"),  ".msg":  ("#8B44AD", "MSG"),
        ".txt":  ("#6B7280", "TXT"),
    }
    bg, label = colors.get(ext, ("#9CA3AF", ext.upper().lstrip(".")))
    short = name[:22] + "…" if len(name) > 22 else name
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="280" height="360">
  <rect width="280" height="360" fill="{bg}"/>
  <rect x="20" y="20" width="240" height="280" rx="8" fill="rgba(255,255,255,0.12)"/>
  <text x="140" y="170" font-family="monospace" font-size="52" font-weight="bold"
        fill="#fff" text-anchor="middle" opacity="0.9">{label}</text>
  <text x="140" y="320" font-family="monospace" font-size="13"
        fill="#fff" text-anchor="middle" opacity="0.7">{short}</text>
</svg>"""
    return base64.b64encode(svg.encode()).decode()

# ── Main scan runner ──────────────────────────────────────────────────────────
