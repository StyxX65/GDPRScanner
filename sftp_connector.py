"""
sftp_connector.py — SFTP file iterator for GDPR Scanner.

Provides SFTPScanner.iter_files() which yields (relative_path, bytes, metadata)
for files on an SFTP/SSH server, using the same interface as FileScanner so that
run_file_scan() in scan_engine.py works identically for all three source types.

Optional dependency:
    paramiko>=3.4   — SSH/SFTP client (pip install paramiko)

If paramiko is not installed, SFTP_OK is False and callers must check before use.
"""

from __future__ import annotations

import stat
import time
from pathlib import PurePosixPath
from typing import Iterator

from file_scanner import SKIP_DIRS, MAX_FILE_BYTES, _skip, _error, KEYCHAIN_SERVICE

# ── Optional dependency ───────────────────────────────────────────────────────

try:
    import paramiko
    SFTP_OK = True
except ImportError:
    SFTP_OK = False

try:
    import keyring as _keyring
    _KEYRING_OK = True
except ImportError:
    _KEYRING_OK = False


# ── Credential helpers ────────────────────────────────────────────────────────

def get_sftp_password(host: str, user: str, keychain_key: str | None = None) -> str | None:
    """Return SFTP password or key passphrase from OS keychain."""
    if not _KEYRING_OK:
        return None
    account = keychain_key or f"sftp:{user}@{host}"
    try:
        return _keyring.get_password(KEYCHAIN_SERVICE, account) or None
    except Exception:
        return None


def store_sftp_password(host: str, user: str, password: str,
                        keychain_key: str | None = None) -> bool:
    """Store SFTP password or passphrase in the OS keychain. Returns True on success."""
    if not _KEYRING_OK:
        return False
    account = keychain_key or f"sftp:{user}@{host}"
    try:
        _keyring.set_password(KEYCHAIN_SERVICE, account, password)
        return True
    except Exception:
        return False


# ── SFTPScanner ───────────────────────────────────────────────────────────────

class SFTPScanner:
    """SFTP file iterator — identical iter_files() interface to FileScanner."""

    def __init__(
        self,
        host: str,
        root_path: str,
        username: str,
        port: int = 22,
        auth_type: str = "password",   # "password" | "key"
        password: str | None = None,
        key_path: str | None = None,
        passphrase: str | None = None,
        keychain_key: str | None = None,
        max_file_bytes: int = MAX_FILE_BYTES,
        label: str = "",
    ):
        self.host           = host
        self.port           = port
        self.root_path      = root_path.rstrip("/") or "/"
        self.username       = username
        self.auth_type      = auth_type
        self.key_path       = key_path
        self.keychain_key   = keychain_key
        self.max_file_bytes = max_file_bytes
        self.label          = label or f"{username}@{host}"

        # Resolve credentials from keychain if not provided directly
        self._password   = password
        self._passphrase = passphrase
        if not self._password and auth_type == "password":
            self._password = get_sftp_password(host, username, keychain_key)
        if not self._passphrase and auth_type == "key" and key_path:
            self._passphrase = get_sftp_password(host, username, keychain_key)

    @staticmethod
    def sftp_available() -> bool:
        return SFTP_OK

    @property
    def source_type(self) -> str:
        return "sftp"

    # ── Public ────────────────────────────────────────────────────────────────

    def iter_files(
        self,
        extensions: set[str] | None = None,
        progress_cb=None,
    ) -> Iterator[tuple[str, bytes | None, dict]]:
        """Yield (relative_path, content_bytes, metadata) for every scannable file.

        Same contract as FileScanner.iter_files() — oversized and unreadable files
        yield a sentinel with content=None and meta['skipped']=True.
        """
        if not SFTP_OK:
            raise RuntimeError("paramiko not installed — run: pip install paramiko")

        from cpr_detector import SUPPORTED_EXTS as DEFAULT_EXTENSIONS
        exts = extensions or DEFAULT_EXTENSIONS

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": self.host,
            "port":     self.port,
            "username": self.username,
            "timeout":  30,
        }

        if self.auth_type == "key" and self.key_path:
            pkey = _load_pkey(self.key_path, self._passphrase)
            connect_kwargs["pkey"] = pkey
        else:
            connect_kwargs["password"] = self._password or ""
            # Disable agent and key lookup when using password so paramiko doesn't
            # prompt interactively when the server advertises pubkey auth.
            connect_kwargs["look_for_keys"]   = False
            connect_kwargs["allow_agent"]      = False

        ssh.connect(**connect_kwargs)
        try:
            sftp = ssh.open_sftp()
            try:
                yield from self._walk(sftp, self.root_path, exts, progress_cb)
            finally:
                sftp.close()
        finally:
            ssh.close()

    # ── Private walker ────────────────────────────────────────────────────────

    def _walk(
        self,
        sftp,
        directory: str,
        exts: set[str],
        progress_cb,
    ) -> Iterator[tuple[str, bytes | None, dict]]:
        source_root = f"sftp://{self.username}@{self.host}{self.root_path}"

        try:
            entries = sftp.listdir_attr(directory)
        except OSError as e:
            rel = _rel(directory, self.root_path) or "."
            yield _error(rel, str(e), "sftp", source_root)
            return

        for attr in entries:
            name = attr.filename
            if name.startswith("."):
                continue
            if name.lower() in SKIP_DIRS:
                continue

            full_remote = f"{directory}/{name}".replace("//", "/")
            rel = _rel(full_remote, self.root_path)

            if attr.st_mode is not None and stat.S_ISDIR(attr.st_mode):
                yield from self._walk(sftp, full_remote, exts, progress_cb)
                continue

            ext = PurePosixPath(name).suffix.lower()
            if ext not in exts:
                continue

            size = attr.st_size or 0
            if size > self.max_file_bytes:
                yield _skip(rel, size, "sftp", source_root)
                continue

            if progress_cb:
                progress_cb(rel)

            modified = (
                time.strftime("%Y-%m-%d", time.gmtime(attr.st_mtime))
                if attr.st_mtime else ""
            )
            meta = {
                "size_kb":     round(size / 1024, 1),
                "modified":    modified,
                "source_type": "sftp",
                "source_root": source_root,
                "full_path":   full_remote,
                "skipped":     False,
            }

            try:
                with sftp.open(full_remote, "rb") as fh:
                    content = fh.read(self.max_file_bytes)
                yield rel, content, meta
            except OSError as e:
                yield _error(rel, str(e), "sftp", source_root)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rel(full_path: str, root: str) -> str:
    """Return path relative to root, stripping leading slash."""
    if full_path.startswith(root):
        return full_path[len(root):].lstrip("/")
    return full_path.lstrip("/")


def _load_pkey(key_path: str, passphrase: str | None):
    """Load a private key from disk, trying RSA → Ed25519 → ECDSA → DSS."""
    for cls in (
        paramiko.RSAKey,
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.DSSKey,
    ):
        try:
            return cls.from_private_key_file(key_path, password=passphrase)
        except paramiko.ssh_exception.SSHException:
            continue
        except FileNotFoundError:
            raise
    raise ValueError(f"Unrecognised private key format: {key_path}")
