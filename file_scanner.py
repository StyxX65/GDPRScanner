"""
file_scanner.py — Unified local and SMB/CIFS file iterator for GDPR Scanner.

Provides FileScanner.iter_files() which yields (relative_path, bytes, metadata)
regardless of whether the source is a local path or a network share.

gdpr_scanner.py imports this module and calls iter_files() inside run_file_scan().
All CPR scanning, card broadcasting, and DB persistence stay in gdpr_scanner.py.

Optional dependencies:
    smbprotocol>=1.13   — native SMB2/3 without mounting (pip install smbprotocol)
    keyring>=25.0       — OS keychain credential storage  (pip install keyring)
    python-dotenv>=1.0  — .env file fallback              (pip install python-dotenv)

If smbprotocol is not installed, the scanner falls back to local-path mode.
"""

from __future__ import annotations

import os
import time
import uuid
import hashlib
from pathlib import Path, PurePosixPath
from typing import Iterator

# ── Optional dependency flags ─────────────────────────────────────────────────

try:
    import smbprotocol  # noqa: F401 — just checking availability
    from smbprotocol.connection import Connection
    from smbprotocol.session import Session
    from smbprotocol.tree import TreeConnect
    from smbprotocol.open import (
        Open, CreateDisposition, CreateOptions,
        FileAttributes, FilePipePrinterAccessMask, ShareAccess,
        ImpersonationLevel,
    )
    from smbprotocol.query_info import FileDirectoryInformation
    SMB_OK = True
except ImportError:
    SMB_OK = False

try:
    import keyring as _keyring
    KEYRING_OK = True
except ImportError:
    KEYRING_OK = False

try:
    from dotenv import dotenv_values as _dotenv_values
    DOTENV_OK = True
except ImportError:
    DOTENV_OK = False


# ── Public constants ──────────────────────────────────────────────────────────

KEYCHAIN_SERVICE = "gdpr-scanner-nas"

# File extensions passed through to _scan_bytes().  Matches SUPPORTED_EXTS in
# gdpr_scanner.py; kept here too so FileScanner can filter without importing it.
DEFAULT_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".csv",
    ".txt", ".eml", ".msg",
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp",
    ".heic", ".heif",
}

# Extensions for local/SMB file scans — PDFs now included; OCR runs in a spawned
# subprocess with a 60-second hard timeout via _scan_bytes_timeout so hanging
# Tesseract/Poppler processes can never block the scan thread indefinitely.
FILE_SCAN_EXTENSIONS = DEFAULT_EXTENSIONS

# Maximum file size to load into memory (bytes).  Files larger than this are
# skipped with a warning — same guard used by the M365 attachment scanner.
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB

# SMB pre-fetch sliding window (#22)
PREFETCH_WINDOW  = 1   # 1 SMB read in flight — halves peak concurrent buffer memory
SMB_READ_TIMEOUT = 60  # seconds before an individual SMB read is abandoned

# Directories to silently skip — system/sync/trash folders that never contain
# user documents and would only generate noise or permission errors.
SKIP_DIRS = {
    ".recycle", ".recycler", "recycler", "$recycle.bin", ".trash", ".trashes",
    ".sync", ".btsync", ".syncthing",
    ".git", ".svn", ".hg",
    "__pycache__", "node_modules",
    ".spotlight-v100", ".fseventsd", ".temporaryitems",
    "system volume information", "lost+found",
}


# ── Credential helpers ────────────────────────────────────────────────────────

def get_smb_password(smb_host: str, smb_user: str,
                     keychain_key: str | None = None) -> str | None:
    """Return SMB password from the best available source.

    Priority:
        1. OS keychain via keyring (keychain_key or smb_user as account name)
        2. NAS_PASSWORD environment variable
        3. .env file in the current working directory
    """
    # 1. OS keychain
    if KEYRING_OK:
        account = keychain_key or smb_user
        try:
            pw = _keyring.get_password(KEYCHAIN_SERVICE, account)
            if pw:
                return pw
        except Exception:
            pass

    # 2. Environment variable
    pw = os.environ.get("NAS_PASSWORD")
    if pw:
        return pw

    # 3. .env file
    if DOTENV_OK:
        env = _dotenv_values(".env")
        pw = env.get("NAS_PASSWORD")
        if pw:
            return pw

    return None


def store_smb_password(smb_host: str, smb_user: str,
                       password: str,
                       keychain_key: str | None = None) -> bool:
    """Store SMB password in the OS keychain.  Returns True on success."""
    if not KEYRING_OK:
        return False
    account = keychain_key or smb_user
    try:
        _keyring.set_password(KEYCHAIN_SERVICE, account, password)
        return True
    except Exception:
        return False


# ── FileScanner ───────────────────────────────────────────────────────────────

class FileScanner:
    """Unified local + SMB/CIFS file iterator."""

    FILE_SCAN_EXTENSIONS = FILE_SCAN_EXTENSIONS  # excludes .pdf
    """Unified iterator over local paths and SMB/CIFS network shares.

    Usage::

        fs = FileScanner("/mnt/data")
        for rel_path, content, meta in fs.iter_files():
            result = _scan_bytes(content, rel_path)
            ...

        fs = FileScanner("//nas.school.dk/shares",
                         smb_host="nas.school.dk",
                         smb_user="DOMAIN\\\\henrik",
                         smb_password="secret")
        for rel_path, content, meta in fs.iter_files():
            ...
    """

    def __init__(
        self,
        path: str,
        smb_host: str | None = None,
        smb_user: str | None = None,
        smb_password: str | None = None,
        smb_domain: str | None = None,
        keychain_key: str | None = None,
        max_file_bytes: int = MAX_FILE_BYTES,
    ):
        self.path           = path
        self.smb_user       = smb_user
        self.smb_domain     = smb_domain or ""
        self.keychain_key   = keychain_key
        self.max_file_bytes = max_file_bytes

        # Detect SMB path by prefix; auto-derive host if not provided
        _is_smb_path = path.startswith("//") or path.startswith("\\\\")
        if _is_smb_path and not smb_host:
            # Extract host from path: //host/share → host
            _norm = path.replace("\\", "/").lstrip("/")
            smb_host = _norm.split("/")[0] or None
        self.smb_host = smb_host

        self.is_smb = _is_smb_path and SMB_OK

        # Resolve password from keychain / env / .env if not provided directly
        self._password = smb_password
        if self.is_smb and not self._password:
            self._password = get_smb_password(
                smb_host or "", smb_user or "", keychain_key
            )

    # ── Public ────────────────────────────────────────────────────────────────

    def iter_files(
        self,
        extensions: set[str] | None = None,
        progress_cb=None,
    ) -> Iterator[tuple[str, bytes, dict]]:
        """Yield (relative_path, content_bytes, metadata) for every scannable file.

        Args:
            extensions:  Set of lowercase extensions to include, e.g. {".pdf", ".docx"}.
                         Defaults to DEFAULT_EXTENSIONS.
            progress_cb: Optional callable(rel_path) called before each file is read,
                         so the caller can update a progress indicator.

        Yields:
            rel_path  — path relative to the root (e.g. "subfolder/doc.pdf")
            content   — raw bytes of the file
            metadata  — dict with keys: size_kb, modified, source_type, source_root
        """
        exts = extensions or DEFAULT_EXTENSIONS

        if self.is_smb:
            yield from self._iter_smb(exts, progress_cb)
        else:
            yield from self._iter_local(exts, progress_cb)

    @property
    def source_type(self) -> str:
        return "smb" if self.is_smb else "local"

    @staticmethod
    def smb_available() -> bool:
        return SMB_OK

    # ── Local walker ──────────────────────────────────────────────────────────

    def _iter_local(self, exts: set[str], progress_cb) -> Iterator[tuple[str, bytes, dict]]:
        root = Path(self.path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Path not found: {root}")

        for dirpath, _dirs, filenames in os.walk(root):
            # Skip junk/system directories in-place
            _dirs[:] = [d for d in _dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                full = Path(dirpath) / fname
                ext  = full.suffix.lower()
                if ext not in exts:
                    continue

                try:
                    size = full.stat().st_size
                except OSError:
                    continue

                if size > self.max_file_bytes:
                    yield _skip(str(full.relative_to(root)), size, "local", str(root))
                    continue

                rel = str(full.relative_to(root))
                if progress_cb:
                    progress_cb(rel)

                try:
                    content  = full.read_bytes()
                    modified = time.strftime(
                        "%Y-%m-%d",
                        time.localtime(full.stat().st_mtime)
                    )
                    meta = {
                        "size_kb":     round(size / 1024, 1),
                        "modified":    modified,
                        "source_type": "local",
                        "source_root": str(root),
                        "full_path":   str(full),
                        "skipped":     False,
                    }
                    yield rel, content, meta
                except (OSError, PermissionError) as e:
                    yield _error(rel, str(e), "local", str(root))

    # ── SMB walker ────────────────────────────────────────────────────────────

    def _iter_smb(self, exts: set[str], progress_cb) -> Iterator[tuple[str, bytes, dict]]:
        """Walk an SMB share using smbprotocol with a sliding-window pre-fetcher.

        Directory traversal and file reads are decoupled:
          1. _smb_collect() walks the tree metadata-only (fast — no file I/O).
          2. A ThreadPoolExecutor submits _smb_read_file() calls up to
             PREFETCH_WINDOW at a time. Each future has SMB_READ_TIMEOUT seconds
             to complete; timed-out reads yield an error sentinel and are abandoned
             without blocking the scan thread.
        """
        if not SMB_OK:
            raise RuntimeError(
                "smbprotocol not installed — run: pip install smbprotocol"
            )

        # Parse //host/share/optional/subpath — normalise backslashes
        norm = self.path.replace("\\", "/").lstrip("/")
        parts = norm.split("/", 2)
        host  = parts[0] if len(parts) > 0 else self.smb_host or ""
        share = parts[1] if len(parts) > 1 else ""
        sub   = parts[2] if len(parts) > 2 else ""

        if not host or not share:
            raise ValueError(
                f"Cannot parse SMB path '{self.path}' — expected //host/share[/subpath]"
            )

        source_root = f"//{host}/{share}"

        conn = Connection(uuid.uuid4(), host, 445)
        conn.connect(timeout=30)
        try:
            session = Session(conn,
                              username=self.smb_user or "",
                              password=self._password or "",
                              require_encryption=False)
            session.connect()
            try:
                tree = TreeConnect(session, f"\\\\{host}\\{share}")
                tree.connect()
                try:
                    # Phase 1: collect all candidate file descriptors (no reads)
                    candidates = list(self._smb_collect(
                        tree, sub, sub, exts, source_root
                    ))

                    # Phase 2: resolve sentinels, then sliding-window parallel reads
                    # Sentinels from _smb_collect are yielded immediately; only real
                    # file entries enter the executor queue.
                    real_candidates = []
                    for item in candidates:
                        marker = item[0]
                        if marker is _COLLECT_ERROR:
                            yield _error(item[1] or ".", item[4], "smb", source_root)
                        elif marker is _COLLECT_SKIP:
                            yield _skip(item[1], item[2], "smb", source_root)
                        else:
                            real_candidates.append(item)

                    from concurrent.futures import ThreadPoolExecutor
                    from collections import deque

                    pending: deque = deque()  # (future, display_rel, size, modified, src_root)

                    def _submit_next(item):
                        display_rel, smb_path, size, modified, src_root = item
                        fut = executor.submit(_smb_read_file, tree, smb_path)
                        pending.append((fut, display_rel, size, modified, src_root))

                    with ThreadPoolExecutor(max_workers=PREFETCH_WINDOW) as executor:
                        it = iter(real_candidates)
                        # Seed the window
                        for item in it:
                            if progress_cb:
                                progress_cb(item[0])
                            _submit_next(item)
                            if len(pending) >= PREFETCH_WINDOW:
                                break

                        while pending:
                            fut, display_rel, size, modified, src_root = pending.popleft()

                            # Submit the next candidate to keep the window full
                            nxt = next(it, None)
                            if nxt is not None:
                                if progress_cb:
                                    progress_cb(nxt[0])
                                _submit_next(nxt)

                            try:
                                content = fut.result(timeout=SMB_READ_TIMEOUT)
                                meta = {
                                    "size_kb":     round(size / 1024, 1),
                                    "modified":    modified,
                                    "source_type": "smb",
                                    "source_root": src_root,
                                    "full_path":   f"{src_root}/{display_rel}",
                                    "skipped":     False,
                                }
                                yield display_rel, content, meta
                            except TimeoutError:
                                fut.cancel()
                                yield _error(display_rel,
                                             f"SMB read timed out after {SMB_READ_TIMEOUT}s",
                                             "smb", src_root)
                            except Exception as e:
                                err = str(e)
                                if "STATUS_END_OF_FILE" in err or "0xc0000011" in err:
                                    continue  # empty/placeholder — skip silently
                                yield _error(display_rel, err, "smb", src_root)

                finally:
                    tree.disconnect()
            finally:
                session.disconnect()
        finally:
            conn.disconnect()

    def _smb_collect(
        self,
        tree,
        directory: str,
        root_sub: str,
        exts: set[str],
        source_root: str,
    ) -> Iterator[tuple[str, str, int, str, str]]:
        """Recursively walk an SMB directory tree, yielding file descriptors only.

        Yields (display_rel, smb_path, size_bytes, modified_str, source_root).
        No file reads are performed — this is directory-listing only.
        Over-size files are yielded as _skip() sentinels via a side-channel;
        those are handled in _iter_smb before the prefetch loop.
        """
        query_path = directory.replace("/", "\\") if directory else ""
        pattern    = (query_path + "\\" if query_path else "") + "*"

        try:
            entries = _smb_list_dir(tree, pattern)
        except Exception as e:
            # Can't list directory — emit error sentinel via a special marker
            # _iter_smb won't see it; we raise so it propagates as a read error
            yield _COLLECT_ERROR, "", 0, "", source_root  # sentinel handled below
            return

        for entry in entries:
            name = entry["name"]
            if name in (".", ".."):
                continue

            rel = (directory + "/" + name) if directory else name
            display_rel = rel[len(root_sub):].lstrip("/") if root_sub else rel
            display_rel = display_rel or name

            is_dir = bool(entry["attributes"] & 0x10)
            size   = entry["size"]

            if is_dir:
                if name.lower() in SKIP_DIRS or (name.startswith(".") and name not in (".", "..")):
                    continue
                yield from self._smb_collect(tree, rel, root_sub, exts, source_root)
                continue

            ext = PurePosixPath(name).suffix.lower()
            if ext not in exts:
                continue

            if size > self.max_file_bytes:
                # Mark as over-size — _iter_smb skips before submitting to executor
                yield _COLLECT_SKIP, display_rel, size, "", source_root
                continue

            modified = _smb_ts(entry.get("last_write_time", 0))
            yield display_rel, rel.replace("/", "\\"), size, modified, source_root


# Sentinel strings for _smb_collect side-channel messages
_COLLECT_ERROR = "\x00__error__"
_COLLECT_SKIP  = "\x00__skip__"


# ── SMB helpers ───────────────────────────────────────────────────────────────

def uuid4_str() -> str:
    import uuid
    return str(uuid.uuid4())


def _smb_list_dir(tree, pattern: str) -> list[dict]:
    """List directory entries matching pattern on an SMB tree."""
    from smbprotocol.open import (
        Open, CreateDisposition, CreateOptions,
        FileAttributes, DirectoryAccessMask, ShareAccess,
        ImpersonationLevel, FileInformationClass,
    )
    from smbprotocol.file_info import FileDirectoryInformation
    import smbprotocol.exceptions as smb_exc

    # Open directory
    dir_path = "\\".join(pattern.replace("/", "\\").split("\\")[:-1])
    file_pattern = pattern.replace("/", "\\").split("\\")[-1] or "*"

    fh = Open(tree, dir_path or "")
    fh.create(
        ImpersonationLevel.Impersonation,
        DirectoryAccessMask.FILE_LIST_DIRECTORY |
        DirectoryAccessMask.FILE_READ_ATTRIBUTES,
        FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
        ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE |
        ShareAccess.FILE_SHARE_DELETE,
        CreateDisposition.FILE_OPEN,
        CreateOptions.FILE_DIRECTORY_FILE,
    )

    entries = []
    try:
        raw = fh.query_directory(
            pattern=file_pattern,
            file_information_class=FileInformationClass.FILE_DIRECTORY_INFORMATION,
            flags=0,
            max_output=65536,
        )
        for info in raw:
            fname = info["file_name"].get_value()
            if isinstance(fname, bytes):
                fname = fname.decode("utf-16-le", errors="replace").rstrip("\x00")
            attrs = info["file_attributes"].get_value()
            entries.append({
                "name":            fname,
                "attributes":      int(attrs) if not isinstance(attrs, int) else attrs,
                "size":            info["end_of_file"].get_value(),
                "last_write_time": info["last_write_time"].get_value(),
            })
    except smb_exc.SMBOSError:
        pass  # Empty directory or no match
    finally:
        try:
            fh.close(get_attributes=False)
        except Exception:
            pass

    return entries


def _smb_read_file(tree, smb_path: str) -> bytes:
    """Read a complete file from an SMB tree into bytes."""
    from smbprotocol.open import (
        Open, CreateDisposition, CreateOptions,
        FileAttributes, FilePipePrinterAccessMask, ShareAccess,
        ImpersonationLevel,
    )

    fh = Open(tree, smb_path)
    fh.create(
        ImpersonationLevel.Impersonation,
        FilePipePrinterAccessMask.FILE_READ_DATA |
        FilePipePrinterAccessMask.FILE_READ_ATTRIBUTES,
        FileAttributes.FILE_ATTRIBUTE_NORMAL,
        ShareAccess.FILE_SHARE_READ,
        CreateDisposition.FILE_OPEN,
        CreateOptions.FILE_NON_DIRECTORY_FILE,
    )
    try:
        chunks = []
        offset = 0
        chunk_size = 1024 * 1024  # 1 MB chunks
        while True:
            data = fh.read(offset, chunk_size)
            if not data:
                break
            chunks.append(bytes(data))
            offset += len(data)
            if len(data) < chunk_size:
                break
        return b"".join(chunks)
    finally:
        fh.close(get_attributes=False)


def _smb_ts(windows_ts: int) -> str:
    """Convert Windows FILETIME (100ns intervals since 1601-01-01) to YYYY-MM-DD."""
    if not windows_ts:
        return ""
    try:
        # FILETIME → Unix epoch
        unix_ts = (windows_ts - 116444736000000000) / 10_000_000
        return time.strftime("%Y-%m-%d", time.gmtime(unix_ts))
    except Exception:
        return ""


# ── Sentinel yield helpers ────────────────────────────────────────────────────

def _skip(rel: str, size: int, source_type: str, source_root: str):
    """Yield a skipped-file sentinel (content=None, meta['skipped']=True)."""
    return rel, None, {
        "size_kb":     round(size / 1024, 1),
        "modified":    "",
        "source_type": source_type,
        "source_root": source_root,
        "full_path":   f"{source_root}/{rel}",
        "skipped":     True,
        "skip_reason": f"File too large ({size // 1_048_576} MB)",
    }


def _error(rel: str, error: str, source_type: str, source_root: str):
    """Yield an error sentinel (content=None, meta['error']=...)."""
    return rel, None, {
        "size_kb":     0,
        "modified":    "",
        "source_type": source_type,
        "source_root": source_root,
        "full_path":   f"{source_root}/{rel}",
        "skipped":     True,
        "skip_reason": f"Error: {error}",
    }
