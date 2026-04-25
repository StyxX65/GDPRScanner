"""
cpr_detector.py — File scanning and CPR/PII detection for GDPRScanner.

Provides:
  _scan_bytes(content, filename)         — dispatch to correct scanner by file type
  _scan_text_direct(text)                — scan a plain text string
  _extract_exif(content, filename)       — extract PII-bearing EXIF tags from images
  _extract_video_metadata(content, fn)   — extract PII-bearing metadata from video files
  _extract_audio_metadata(content, fn)   — extract PII-bearing tags from audio files
  _detect_photo_faces(content, fn)       — count faces in an image (OpenCV)
  _get_pii_counts(text)                  — NER-based PII type counts
  _make_thumb(content, filename)         — JPEG thumbnail as base64 string
  _placeholder_svg(ext, name)            — SVG file-type icon

Globals SCANNER_OK, PIL_OK, PHOTO_EXTS, VIDEO_EXTS, AUDIO_EXTS, SUPPORTED_EXTS, ds, PILImage, LANG,
and _check_special_category are injected at startup by gdpr_scanner.py via
`from cpr_detector import *` AFTER those names are defined.  This keeps the
module cleanly importable in isolation for unit tests (#26) while preserving
the existing runtime behaviour.
"""
from __future__ import annotations
import base64
import hashlib
import io
import re
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

VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".flv", ".webm",
}
AUDIO_EXTS = {
    ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".wav", ".opus", ".aiff", ".aif",
}
SUPPORTED_EXTS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".csv",
    ".txt", ".eml", ".msg",
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp",
} | VIDEO_EXTS | AUDIO_EXTS
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


def _extract_video_metadata(content: bytes, filename: str) -> dict:
    """Extract PII-bearing metadata from a video file.

    Returns the same structure as _extract_exif so callers can treat both
    identically:
        gps        — {lat, lon, lat_ref, lon_ref, maps_url} or None
        pii_fields — {label: value} for title/artist/comment/description
        author     — str or None
        datetime   — str or None
        device     — str or None
        has_pii    — bool

    MP4/MOV/M4V: reads QuickTime/MPEG-4 tags via mutagen (no system deps).
    GPS is extracted from the ©xyz QuickTime atom (ISO 6709 string written by
    iPhones and Android devices: "+55.6763+012.5681+005.000/").
    AVI: parses the RIFF INFO list chunk without any external library.
    All other extensions: returns empty result immediately.
    """
    result: dict = {"gps": None, "pii_fields": {}, "author": None,
                    "datetime": None, "device": None, "has_pii": False}
    ext = Path(filename).suffix.lower()

    if ext in {".mp4", ".mov", ".m4v"}:
        _extract_mp4_tags(content, result)
    elif ext == ".avi":
        _extract_avi_info(content, result)

    return result


def _extract_mp4_tags(content: bytes, result: dict) -> None:
    """Populate result dict from MPEG-4/QuickTime container tags via mutagen."""
    try:
        import mutagen.mp4
        tags = mutagen.mp4.MP4(io.BytesIO(content)).tags
        if not tags:
            return

        # Text fields that may contain personal data
        _tag_label = {
            "©nam": "Title",
            "©cmt": "Comment",
            "©des": "Description",
            "desc": "Description",
            "©lyr": "Lyrics",
        }
        for tag, label in _tag_label.items():
            val = tags.get(tag)
            if val:
                text = str(val[0]).strip() if isinstance(val, list) else str(val).strip()
                if len(text) >= _EXIF_PII_MIN_LEN:
                    result["pii_fields"][label] = text
                    result["has_pii"] = True

        # Author — prefer ©ART (artist), fall back to album artist
        for tag in ("©ART", "aART"):
            val = tags.get(tag)
            if val:
                author = str(val[0]).strip() if isinstance(val, list) else str(val).strip()
                if len(author) >= _EXIF_PII_MIN_LEN:
                    result["author"] = author
                    result["pii_fields"]["Artist"] = author
                    result["has_pii"] = True
                break

        # Recording date
        val = tags.get("©day")
        if val:
            result["datetime"] = str(val[0]).strip() if isinstance(val, list) else str(val).strip()

        # Device (QuickTime-specific tags written by iPhones)
        make  = tags.get("©mak")
        model = tags.get("©mod")
        if make or model:
            result["device"] = " ".join(
                str(v[0] if isinstance(v, list) else v).strip()
                for v in (make, model) if v
            )

        # GPS — QuickTime ©xyz atom: "+55.6763+012.5681+005.000/" (ISO 6709)
        import re as _re
        for gps_tag in ("©xyz", "com.apple.quicktime.location.ISO6709"):
            val = tags.get(gps_tag)
            if val:
                gps_str = str(val[0] if isinstance(val, list) else val).strip()
                m = _re.match(r'([+-]\d+\.?\d*)([+-]\d+\.?\d*)', gps_str)
                if m:
                    lat = round(float(m.group(1)), 7)
                    lon = round(float(m.group(2)), 7)
                    result["gps"] = {
                        "lat":      lat,
                        "lon":      lon,
                        "lat_ref":  "N" if lat >= 0 else "S",
                        "lon_ref":  "E" if lon >= 0 else "W",
                        "maps_url": f"https://www.google.com/maps?q={lat},{lon}",
                    }
                    result["has_pii"] = True
                break
    except Exception:
        pass


def _extract_avi_info(content: bytes, result: dict) -> None:
    """Populate result dict from RIFF INFO list chunk in an AVI file."""
    try:
        import struct
        if len(content) < 12 or content[:4] != b"RIFF":
            return
        # Walk top-level RIFF chunks looking for the INFO LIST
        i = 12
        while i + 8 <= len(content):
            chunk_id   = content[i:i+4]
            chunk_size = struct.unpack_from("<I", content, i + 4)[0]
            if chunk_id == b"LIST" and content[i+8:i+12] == b"INFO":
                _parse_riff_info(content, i + 12, i + 8 + chunk_size, result)
                break
            i += 8 + chunk_size + (chunk_size & 1)  # RIFF chunks are word-aligned
    except Exception:
        pass


def _parse_riff_info(content: bytes, start: int, end: int, result: dict) -> None:
    import struct
    _info_labels = {
        b"INAM": "Title",
        b"IART": "Artist",
        b"ICMT": "Comment",
        b"ISBJ": "Subject",
        b"ICRD": "Date",
    }
    i = start
    while i + 8 <= end and i + 8 <= len(content):
        sub_id   = content[i:i+4]
        sub_size = struct.unpack_from("<I", content, i + 4)[0]
        label    = _info_labels.get(sub_id)
        if label:
            raw = content[i+8 : i+8+sub_size]
            val = raw.decode("utf-8", errors="replace").strip("\x00 ")
            if val and len(val) >= _EXIF_PII_MIN_LEN:
                result["pii_fields"][label] = val
                result["has_pii"] = True
                if label == "Artist" and not result["author"]:
                    result["author"] = val
                if label == "Date" and not result["datetime"]:
                    result["datetime"] = val
        i += 8 + sub_size + (sub_size & 1)


def _extract_audio_metadata(content: bytes, filename: str) -> dict:
    """Extract PII-bearing tags from an audio file.

    Returns the same structure as _extract_exif / _extract_video_metadata.
    No GPS extraction — GPS is not embedded in audio containers in practice.

    Uses mutagen.File(easy=True) which normalises tags to lowercase keys for
    MP3 (ID3), M4A/AAC (MPEG-4), FLAC, OGG Vorbis, and AIFF.  WMA/ASF tags
    use mixed-case keys (e.g. "Title", "Author") — these are lowercased during
    normalisation so the same extraction logic covers all formats.
    """
    result: dict = {"gps": None, "pii_fields": {}, "author": None,
                    "datetime": None, "device": None, "has_pii": False}
    try:
        import mutagen
        f = mutagen.File(fileobj=io.BytesIO(content), filename=filename, easy=True)
        if not f or not f.tags:
            return result

        # Normalise all tags to {lowercase_key: str_value} regardless of format
        def _strval(v):
            return str(v[0] if isinstance(v, list) and v else v).strip()

        tags: dict[str, str] = {
            k.lower(): _strval(v) for k, v in f.tags.items()
        }

        # Fields that may contain personal names or descriptions
        _pii_keys = {
            "title":           "Title",
            "artist":          "Artist",
            "albumartist":     "Album Artist",
            "composer":        "Composer",
            "lyricist":        "Lyricist",
            "conductor":       "Conductor",
            "author":          "Author",
            "copyright":       "Copyright",
            "comment":         "Comment",
            "description":     "Description",
            # WMA/ASF mixed-case keys survive as lowercase after normalisation
            "wm/albumartist":  "Album Artist",
            "wm/composer":     "Composer",
            "wm/conductor":    "Conductor",
            "wm/lyrics":       "Lyrics",
        }
        seen: set[str] = set()  # avoid duplicate label entries
        for key, label in _pii_keys.items():
            val = tags.get(key, "")
            if val and len(val) >= _EXIF_PII_MIN_LEN and label not in seen:
                result["pii_fields"][label] = val
                result["has_pii"] = True
                seen.add(label)

        # Author — most specific personal name field wins
        for key in ("artist", "author", "albumartist", "wm/albumartist", "composer"):
            val = tags.get(key, "")
            if val and len(val) >= _EXIF_PII_MIN_LEN:
                result["author"] = val
                break

        # Recording / release date
        for key in ("date", "year", "wm/year"):
            val = tags.get(key, "")
            if val:
                result["datetime"] = val
                break

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


_EMAIL_RE = re.compile(
    r'\b[a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'
)
_PHONE_RE = re.compile(
    r'(?:'
    r'(?:\+45|0045)[\s\-]?[2-9]\d{3}[\s\-]?\d{4}'      # +45/0045 DDDD DDDD
    r'|(?:\+45|0045)[\s\-]?[2-9]\d(?:[\s\-]\d{2}){3}'  # +45/0045 DD DD DD DD
    r'|\b[2-9]\d{7}\b'                                    # 8 consecutive digits
    r'|\b[2-9]\d{3}[\s\-]\d{4}\b'                        # DDDD DDDD
    r'|\b[2-9]\d(?:[\s\-]\d{2}){3}\b'                    # DD DD DD DD
    r')'
)


def _extract_text_from_bytes(content: bytes, filename: str) -> str:
    """Extract plain text from file bytes for email/phone pattern matching.

    Returns empty string for binary media files (photos, video, audio) and
    on any parse error — callers must never raise from this function.
    """
    ext = Path(filename).suffix.lower()
    try:
        if ext in {".txt", ".csv", ".eml", ".msg"}:
            return content.decode("utf-8", errors="replace")
        if ext in {".docx", ".doc"}:
            from docx import Document as _Doc
            doc = _Doc(io.BytesIO(content))
            parts = [p.text for p in doc.paragraphs]
            for tbl in doc.tables:
                for row in tbl.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
            return "\n".join(parts)
        if ext in {".xlsx", ".xlsm"}:
            import openpyxl as _xl
            wb = _xl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            parts = [
                str(cell.value)
                for ws in wb.worksheets
                for row in ws.iter_rows()
                for cell in row
                if cell.value is not None
            ]
            wb.close()
            return " ".join(parts)
        if ext == ".pdf":
            import pdfplumber as _pp
            with _pp.open(io.BytesIO(content)) as pdf:
                parts = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(parts)
    except Exception:
        pass
    if ext not in PHOTO_EXTS | VIDEO_EXTS | AUDIO_EXTS:
        try:
            return content.decode("utf-8", errors="replace")
        except Exception:
            pass
    return ""


def _find_emails_phones(text: str) -> dict:
    """Extract unique email addresses and Danish phone numbers from text.

    Returns {"emails": [{"formatted": str}, ...], "phones": [{"formatted": str}, ...]}.
    Phones are normalised to digit-only strings (preserving a leading '+').
    """
    if not text:
        return {"emails": [], "phones": []}
    emails = list(dict.fromkeys(m.group(0).lower() for m in _EMAIL_RE.finditer(text)))
    phones = list(dict.fromkeys(
        ('+' + re.sub(r'[\s\-]', '', m.group(0)[1:]) if m.group(0).lstrip().startswith('+')
         else re.sub(r'[\s\-]', '', m.group(0)))
        for m in _PHONE_RE.finditer(text)
    ))
    return {
        "emails": [{"formatted": e} for e in emails],
        "phones": [{"formatted": p} for p in phones],
    }


def _scan_bytes(content: bytes, filename: str, poppler_path=None) -> dict:
    """Scan raw bytes for CPRs, emails, and phone numbers. Returns result dict."""
    if not SCANNER_OK:
        return {"cprs": [], "dates": [], "emails": [], "phones": [], "error": "scanner not available"}
    ext = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    result: dict = {"cprs": [], "dates": []}
    try:
        if ext == ".pdf":
            # Check if the PDF has a text layer before running full scan_pdf.
            # Image-only PDFs (scanned documents) have no text and would trigger
            # Tesseract OCR subprocesses that hang indefinitely on some files.
            try:
                import pdfplumber as _pp
                with _pp.open(io.BytesIO(content)) as _pdf:
                    has_text = any(ds.is_text_page(p) for p in _pdf.pages)
                if not has_text:
                    return {"cprs": [], "dates": [], "emails": [], "phones": []}
            except Exception:
                pass  # if pdfplumber fails, fall through to full scan_pdf
            result = ds.scan_pdf(tmp_path, poppler_path=poppler_path)
        elif ext in {".docx", ".doc"}:
            result = ds.scan_docx(tmp_path)
        elif ext in {".xlsx", ".xlsm"}:
            result = ds.scan_xlsx(tmp_path)
        elif ext == ".csv":
            result = ds.scan_csv(tmp_path)
        elif ext == ".txt":
            text = content.decode("utf-8", errors="replace")
            cprs, dates = ds.extract_matches(text, 1, "text")
            result = {"cprs": cprs, "dates": dates}
        elif ext in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}:
            result = ds.scan_image(tmp_path)
        else:
            try:
                text = content.decode("utf-8", errors="replace")
                cprs, dates = ds.extract_matches(text, 1, "text")
                result = {"cprs": cprs, "dates": dates}
            except Exception:
                pass
    except Exception as e:
        result = {"cprs": [], "dates": [], "error": str(e)}
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass
    ep = _find_emails_phones(_extract_text_from_bytes(content, filename))
    result["emails"] = ep["emails"]
    result["phones"] = ep["phones"]
    return result

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
    """Scan a plain text string for CPRs, emails, and phone numbers.

    Uses ds.extract_matches() directly rather than ds.scan_text() because
    scan_text() calls extract_cpr_and_dates() which is not defined in
    document_scanner.py (pre-existing bug).
    """
    if not text:
        return {"cprs": [], "dates": [], "emails": [], "phones": []}
    ep = _find_emails_phones(text)
    if not SCANNER_OK:
        return {"cprs": [], "dates": [], **ep}
    try:
        cprs, dates = ds.extract_matches(text, 1, "text")
        return {"cprs": cprs, "dates": dates, **ep}
    except Exception:
        return {"cprs": [], "dates": [], **ep}

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
