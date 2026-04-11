"""
app_config.py — Configuration, i18n, keywords, profiles, settings,
                SMTP config, file sources, and Fernet encryption for GDPRScanner.
"""
from __future__ import annotations
import hashlib
import json
import logging
import re as _re
import time
import uuid as _uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)

from typing import Optional

# ── i18n ──────────────────────────────────────────────────────────────────────

def _load_lang() -> dict:
    import locale, sys as _sys, os as _os, subprocess as _sp
    from pathlib import Path as _Path
    _here = _Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else _Path(__file__).parent
    lang_dir = _here / "lang"
    lang_code = "en"
    try:
        if _sys.platform == "darwin":
            try:
                r = _sp.run(["defaults", "read", "-g", "AppleLocale"],
                            capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    lang_code = r.stdout.strip().split("_")[0].split("-")[0].lower()
            except Exception:
                pass
            if lang_code == "en":
                try:
                    r = _sp.run(["defaults", "read", "-g", "AppleLanguages"],
                                capture_output=True, text=True, timeout=3)
                    import re as _re
                    m = _re.search(r'"([a-z]{2})[-_]', r.stdout, _re.I)
                    if m:
                        lang_code = m.group(1).lower()
                except Exception:
                    pass
        else:
            loc = (locale.getlocale()[0] or _os.environ.get("LC_ALL") or
                   _os.environ.get("LANG") or "en")
            lang_code = loc.split("_")[0].split(".")[0].split("-")[0].lower() or "en"
    except Exception:
        lang_code = "en"

    def _parse(path) -> dict:
        import json as _json
        out = {}
        try:
            if path.suffix == ".json":
                out = _json.loads(path.read_text(encoding="utf-8"))
            else:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip()
        except Exception:
            pass
        return out

    for code in [lang_code, "en"]:
        # Prefer .json, fall back to .lang for backward compatibility
        for ext in [".json", ".lang"]:
            p = lang_dir / f"{code}{ext}"
            if p.exists():
                result = _parse(p)
                result["_lang_code"] = code
                logger.info("[i18n] loaded %s  (%d keys)", p, len(result))
                return result
    return {}

def _load_lang_forced(code: str) -> dict:
    import sys as _sys
    from pathlib import Path as _Path
    _here = _Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else _Path(__file__).parent
    lang_dir = _here / "lang"
    def _parse(path) -> dict:
        import json as _json
        out = {}
        try:
            if path.suffix == ".json":
                out = _json.loads(path.read_text(encoding="utf-8"))
            else:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip()
        except Exception:
            pass
        return out
    for c in [code, "en"]:
        for ext in [".json", ".lang"]:
            p = lang_dir / f"{c}{ext}"
            if p.exists():
                result = _parse(p)
                result["_lang_code"] = c
                return result
    return {}

_LANG_OVERRIDE_FILE = _DATA_DIR / "lang"

def _lang_override() -> "str | None":
    try:
        v = _LANG_OVERRIDE_FILE.read_text().strip()
        return v if v else None
    except Exception:
        return None

def _set_lang_override(code: str) -> None:
    try:
        _LANG_OVERRIDE_FILE.write_text(code.strip())
    except Exception:
        pass


# ── Display name resolver (used by scan_engine) ───────────────────────────────
import re as _re2

_GUID_RE = _re2.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re2.I
)
_GENERIC_DISPLAY_NAMES = {
    "microsoft konto", "microsoft account", "microsoftkonto",
    "microsoft-konto", "compte microsoft", "cuenta de microsoft",
}

def _resolve_display_name(display_name: str, email: str = "", upn: str = "") -> str:
    """Return the best human-readable name for a Microsoft 365 user."""
    dn = (display_name or "").strip()
    if not dn or _GUID_RE.match(dn) or dn.lower() in _GENERIC_DISPLAY_NAMES:
        return email or upn or dn
    return dn

LANG = _load_lang_forced(_lang_override()) if _lang_override() else _load_lang()
logger.info("[i18n] gdpr lang=%s  keys=%d", LANG.get("_lang_code", "?"), len(LANG))

# ── Article 9 sensitive keywords ──────────────────────────────────────────────
import re as _re

_KEYWORDS_PATH     = Path(__file__).parent / "keywords"
_keyword_data:     dict = {}
_keyword_flat:     list = []   # (keyword, category_key) kept for reference / len count
_compiled_keywords: dict = {}  # cat_key → compiled re.Pattern  (#13)
_KEYWORD_WINDOW    = 150        # characters around a keyword to check for CPR proximity

def _load_keywords(lang: str = "da") -> None:
    """Load keyword list from keywords/{lang}.json and compile one regex per
    Article 9 category.  Falls back to da.json if unavailable.

    Each category pattern is an alternation of all its keywords, sorted
    longest-first and anchored with negative-lookbehind/lookahead so that
    short tokens (≤4 chars) require a word boundary while longer ones are
    matched as substrings.  The compiled regex is ~10–50× faster than the
    previous sequential str.find() loop for large texts. (#13)
    """
    global _keyword_data, _keyword_flat, _compiled_keywords
    for candidate in [lang, "da"]:
        p = _KEYWORDS_PATH / f"{candidate}.json"
        if p.exists():
            try:
                import json as _kjson
                _keyword_data = _kjson.loads(p.read_text(encoding="utf-8"))
                flat: list = []
                categories: dict = {}
                for cat_key, cat_val in _keyword_data.items():
                    if cat_key.startswith("_") or not isinstance(cat_val, dict):
                        continue
                    kws = [kw.lower() for kw in cat_val.get("keywords", [])]
                    for kw in kws:
                        flat.append((kw, cat_key))
                    categories[cat_key] = kws

                _keyword_flat = sorted(flat, key=lambda x: -len(x[0]))

                # Compile one alternation regex per category (#13)
                compiled: dict = {}
                for cat, kws in categories.items():
                    if not kws:
                        continue
                    # Sort longest-first so the engine prefers the most specific match
                    sorted_kws = sorted(kws, key=len, reverse=True)
                    parts = []
                    for kw in sorted_kws:
                        esc = _re.escape(kw)
                        if len(kw) <= 4:
                            # Whole-word boundary for short tokens
                            parts.append(r"(?<!\w)" + esc + r"(?!\w)")
                        else:
                            parts.append(esc)
                    compiled[cat] = _re.compile(
                        "(?:" + "|".join(parts) + ")",
                        _re.IGNORECASE,
                    )
                _compiled_keywords = compiled

                logger.info("[keywords] Loaded %d keywords (%d categories compiled) from keywords/%s.json",
                            len(_keyword_flat), len(compiled), candidate)
                return
            except Exception as e:
                logger.warning("[keywords] Failed to load %s: %s", p, e)

_load_keywords(LANG.get("_lang_code", "da"))


def _check_special_category(text: str, cprs: list) -> list:
    """Return sorted list of Article 9 category keys detected near a CPR number.

    Uses compiled per-category regex patterns for efficient matching (#13).
    A keyword counts only when within _KEYWORD_WINDOW characters of a CPR
    in the same text.  If no CPRs are present, any keyword occurrence triggers.
    Returns e.g. ['health', 'criminal'] — empty list if none detected.
    """
    if not _compiled_keywords or not text:
        return []
    text_lower = text.lower()
    found_cats: set = set()

    # Locate CPR positions for proximity check
    cpr_positions: list = []
    if cprs:
        for m in _re.finditer(r"\d{6}[-\s]?\d{4}", text_lower):
            cpr_positions.append(m.start())

    for cat, pattern in _compiled_keywords.items():
        # Use compiled regex — single-pass alternation match per category
        for m in pattern.finditer(text_lower):
            idx = m.start()
            if not cpr_positions or any(
                abs(idx - cp) <= _KEYWORD_WINDOW for cp in cpr_positions
            ):
                found_cats.add(cat)
                break  # One match per category is enough

    return sorted(found_cats)


_CONFIG_FILE = _DATA_DIR / "config.json"

import hashlib as _hashlib

_ADMIN_PIN_KEY = "admin_pin_hash"

def _get_admin_pin_hash() -> str:
    """Return the stored admin PIN hash, or empty string if not set."""
    cfg = _load_config()
    return cfg.get(_ADMIN_PIN_KEY, "")

def _set_admin_pin(pin: str) -> None:
    """Hash and store the admin PIN in the config file."""
    h = _hashlib.sha256(pin.encode()).hexdigest()
    cfg = _load_config()
    cfg[_ADMIN_PIN_KEY] = h
    _save_config(cfg)

def _verify_admin_pin(pin: str) -> bool:
    """Return True if the PIN matches the stored hash."""
    stored = _get_admin_pin_hash()
    if not stored:
        return False
    return _hashlib.sha256(pin.encode()).hexdigest() == stored

def _admin_pin_is_set() -> bool:
    return bool(_get_admin_pin_hash())


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_config(cfg: dict):
    try:
        _CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ── Profile storage (15a) ─────────────────────────────────────────────────────
_SETTINGS_PATH     = _DATA_DIR / "settings.json"
_SRC_TOGGLES_PATH  = _DATA_DIR / "src_toggles.json"

def _load_src_toggles() -> dict:
    """Load persisted source toggle state."""
    try:
        if _SRC_TOGGLES_PATH.exists():
            return json.loads(_SRC_TOGGLES_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_src_toggles(state: dict) -> None:
    """Persist source toggle state."""
    try:
        existing = _load_src_toggles()
        existing.update(state)
        tmp = _SRC_TOGGLES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_SRC_TOGGLES_PATH)
    except Exception as e:
        logger.error("[src_toggles] write failed: %s", e)


def _profiles_load() -> list:
    """Return list of all profiles from settings file."""
    try:
        if not _SETTINGS_PATH.exists():
            return []
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        # Migrate: old flat settings → wrapped in a default profile
        if isinstance(data, dict) and "profiles" not in data and (
            "sources" in data or "user_ids" in data
        ):
            data = {"profiles": [_profile_from_settings(data, name="Default")]}
            _profiles_write(data)
        return data.get("profiles", [])
    except Exception:
        return []


def _profiles_write(data: dict) -> None:
    """Write the full settings dict (including profiles) atomically."""
    try:
        tmp = _SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        tmp.replace(_SETTINGS_PATH)
    except Exception as e:
        logger.error("[profiles] write failed: %s", e)


def _profiles_save_all(profiles: list) -> None:
    """Overwrite the profiles list, preserving any other top-level keys."""
    try:
        data = {}
        if _SETTINGS_PATH.exists():
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["profiles"] = profiles
    _profiles_write(data)


def _profile_from_settings(settings: dict, name: str = "Default",
                            description: str = "") -> dict:
    """Wrap a flat settings dict as a profile."""
    import uuid as _uuid
    return {
        "id":           str(_uuid.uuid4()),
        "name":         name,
        "description":  description,
        "sources":        settings.get("sources", []),
        "google_sources": settings.get("google_sources", []),
        "user_ids":       settings.get("user_ids", []),
        "options":        settings.get("options", {}),
        "retention_years":  settings.get("retention_years"),
        "fiscal_year_end":  settings.get("fiscal_year_end"),
        "email_to":       settings.get("email_to", ""),
        "file_sources":   settings.get("file_sources", []),
        "last_run":     settings.get("last_run"),
        "last_scan_id": settings.get("last_scan_id"),
    }


def _profile_get(name_or_id: str) -> dict | None:
    """Find a profile by name (case-insensitive) or ID."""
    for p in _profiles_load():
        if p.get("id") == name_or_id or \
           p.get("name", "").lower() == name_or_id.lower():
            return p
    return None


def _profile_save(profile: dict) -> dict:
    """Insert or update a profile. Assigns a new UUID if id is missing."""
    import uuid as _uuid
    if not profile.get("id"):
        profile["id"] = str(_uuid.uuid4())
    profiles = _profiles_load()
    for i, p in enumerate(profiles):
        if p.get("id") == profile["id"]:
            profiles[i] = profile
            _profiles_save_all(profiles)
            return profile
    profiles.append(profile)
    _profiles_save_all(profiles)
    return profile


def _profile_delete(name_or_id: str) -> bool:
    """Delete a profile by name or ID. Returns True if found and deleted."""
    profiles = _profiles_load()
    before   = len(profiles)
    profiles = [p for p in profiles
                if p.get("id") != name_or_id
                and p.get("name", "").lower() != name_or_id.lower()]
    if len(profiles) == before:
        return False
    _profiles_save_all(profiles)
    return True


def _profile_touch(profile_id: str, scan_id: int) -> None:
    """Update last_run and last_scan_id after a successful scan."""
    import datetime as _dt2
    profiles = _profiles_load()
    for p in profiles:
        if p.get("id") == profile_id:
            p["last_run"]     = _dt2.datetime.now().isoformat(timespec="seconds")
            p["last_scan_id"] = scan_id
            break
    _profiles_save_all(profiles)


# ── Legacy shim — keep _save_settings / _load_settings working ────────────────

def _save_settings(payload: dict, profile_name: str | None = None,
                   profile_id: str | None = None) -> None:
    """Save settings. Upserts the active profile (or 'Default' if none).
    profile_id takes precedence over profile_name when both are given."""
    profiles = _profiles_load()
    # Resolve profile: ID → name → first profile → "Default"
    existing = None
    if profile_id:
        existing = _profile_get(profile_id)
    if not existing and profile_name:
        existing = _profile_get(profile_name)
    if not existing and profiles:
        existing = profiles[0]
    name = existing["name"] if existing else (profile_name or "Default")
    merged = _profile_from_settings(payload, name=name,
                                     description=existing.get("description", "") if existing else "")
    if existing:
        merged["id"]           = existing["id"]
        merged["last_run"]     = existing.get("last_run")
        merged["last_scan_id"] = existing.get("last_scan_id")
        # Scan start payloads only include M365 sources/user_ids/options.
        # Preserve google_sources and file_sources so a single-source scan
        # doesn't clobber the profile's other source selections.
        _M365_IDS    = {"email", "onedrive", "sharepoint", "teams"}
        google_src   = payload.get("google_sources", existing.get("google_sources", []))
        file_src     = payload.get("file_sources") or existing.get("file_sources", [])
        merged["google_sources"] = google_src
        merged["file_sources"]   = file_src
        # Rebuild combined sources: incoming M365 selection + preserved google/file
        m365_src         = [s for s in merged.get("sources", []) if s in _M365_IDS]
        merged["sources"] = m365_src + google_src + file_src
    _profile_save(merged)


def _load_settings() -> dict | None:
    """Return the first (default) profile as a flat settings dict."""
    profiles = _profiles_load()
    if not profiles:
        return None
    p = profiles[0]
    return {
        "sources":          p.get("sources", []),
        "user_ids":         p.get("user_ids", []),
        "options":          p.get("options", {}),
        "retention_years":  p.get("retention_years"),
        "fiscal_year_end":  p.get("fiscal_year_end"),
        "email_to":         p.get("email_to", ""),
    }


# ── SMTP / email report sending ───────────────────────────────────────────────
_SMTP_CONFIG_PATH    = _DATA_DIR / "smtp.json"
_ROLE_OVERRIDES_PATH = _DATA_DIR / "role_overrides.json"


def _load_role_overrides() -> dict:
    """Return {user_id: 'student'|'staff'|'other'} manual overrides dict."""
    try:
        if _ROLE_OVERRIDES_PATH.exists():
            return json.loads(_ROLE_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_role_overrides(overrides: dict) -> None:
    """Atomically write the role overrides dict to disk."""
    try:
        tmp = _ROLE_OVERRIDES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_ROLE_OVERRIDES_PATH)
    except Exception as e:
        logger.error("[role_overrides] write failed: %s", e)


# ── File source settings (#8) ─────────────────────────────────────────────────
_FILE_SOURCES_PATH = _DATA_DIR / "file_sources.json"


def _load_file_sources() -> list:
    """Return saved file source definitions.

    Each entry: {id, label, path, smb_host, smb_user, smb_domain, keychain_key}
    """
    try:
        if _FILE_SOURCES_PATH.exists():
            return json.loads(_FILE_SOURCES_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_file_sources(sources: list) -> None:
    """Atomically write the file sources list to disk."""
    try:
        tmp = _FILE_SOURCES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_FILE_SOURCES_PATH)
    except Exception as e:
        logger.error("[file_sources] write failed: %s", e)

# ── Viewer tokens ────────────────────────────────────────────────────────────
# Read-only viewer tokens allow sharing scan results with a DPO or compliance
# officer without exposing scan controls or credentials.  Each token is a
# 64-character hex string stored in viewer_tokens.json alongside other data files.

_VIEWER_TOKENS_PATH = _DATA_DIR / "viewer_tokens.json"


def _load_viewer_tokens() -> list:
    """Return list of viewer token dicts (empty list if file missing or corrupt)."""
    try:
        if _VIEWER_TOKENS_PATH.exists():
            return json.loads(_VIEWER_TOKENS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_viewer_tokens(tokens: list) -> None:
    """Atomically write viewer tokens to disk."""
    try:
        tmp = _VIEWER_TOKENS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_VIEWER_TOKENS_PATH)
    except Exception as e:
        logger.error("[viewer_tokens] write failed: %s", e)


def create_viewer_token(label: str = "", expires_days: int | None = None) -> dict:
    """Generate a new viewer token, persist it, and return the token dict.

    Args:
        label:       Human-readable description (e.g. "DPO review April 2026").
        expires_days: Days until expiry.  None = no expiry.
    """
    import secrets as _secrets
    token = _secrets.token_hex(32)   # 64-char URL-safe hex string
    now   = time.time()
    entry: dict = {
        "token":        token,
        "label":        label or "",
        "created_at":   now,
        "expires_at":   now + expires_days * 86400 if expires_days else None,
        "last_used_at": None,
    }
    tokens = _load_viewer_tokens()
    tokens.append(entry)
    _save_viewer_tokens(tokens)
    return entry


def validate_viewer_token(token: str) -> dict | None:
    """Return the token dict if the token is valid and not expired, else None.

    Updates last_used_at as a best-effort side effect.
    """
    if not token:
        return None
    tokens = _load_viewer_tokens()
    now    = time.time()
    found: dict | None = None
    for entry in tokens:
        if entry.get("token") == token:
            exp = entry.get("expires_at")
            if exp is not None and now > exp:
                return None   # expired — treat as not found
            found = entry
            break
    if found is None:
        return None
    found["last_used_at"] = now
    _save_viewer_tokens(tokens)   # best-effort; ignore failures
    return found


def revoke_viewer_token(token: str) -> bool:
    """Remove a token from storage.  Returns True if found and removed."""
    tokens = _load_viewer_tokens()
    before = len(tokens)
    tokens = [t for t in tokens if t.get("token") != token]
    if len(tokens) == before:
        return False
    _save_viewer_tokens(tokens)
    return True


def cleanup_expired_viewer_tokens() -> int:
    """Delete all expired tokens from storage.  Returns count removed."""
    tokens  = _load_viewer_tokens()
    now     = time.time()
    active  = [t for t in tokens if t.get("expires_at") is None or now <= t["expires_at"]]
    removed = len(tokens) - len(active)
    if removed:
        _save_viewer_tokens(active)
    return removed


# ── Viewer PIN ───────────────────────────────────────────────────────────────
# A numeric PIN that grants a browser session read-only viewer access at /view.
# The PIN is stored as a salted SHA-256 hash inside viewer_tokens.json under a
# top-level "__pin__" key so it lives in the same file as the token list.

_PIN_META_KEY = "__pin__"


def _load_pin_store() -> dict:
    """Load the full viewer_tokens.json as a dict (tokens list + optional pin meta)."""
    try:
        if _VIEWER_TOKENS_PATH.exists():
            raw = json.loads(_VIEWER_TOKENS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                # Legacy format — just a list; promote to dict
                return {"tokens": raw}
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return {"tokens": []}


def _save_pin_store(store: dict) -> None:
    try:
        tmp = _VIEWER_TOKENS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_VIEWER_TOKENS_PATH)
    except Exception as e:
        logger.error("[viewer_pin] write failed: %s", e)


# Rewrite the token helpers to use the new store format transparently.
def _load_viewer_tokens() -> list:  # type: ignore[misc]  # noqa: F811
    return _load_pin_store().get("tokens", [])


def _save_viewer_tokens(tokens: list) -> None:  # type: ignore[misc]  # noqa: F811
    store = _load_pin_store()
    store["tokens"] = tokens
    _save_pin_store(store)


def get_viewer_pin_hash() -> "str | None":
    """Return the stored PIN hash dict, or None if no PIN is set."""
    return _load_pin_store().get(_PIN_META_KEY)


def set_viewer_pin(pin: str) -> None:
    """Hash and store a viewer PIN."""
    import hashlib as _hl, secrets as _sec
    if not pin:
        raise ValueError("PIN must not be empty")
    salt = _sec.token_hex(16)
    h    = _hl.sha256((salt + pin).encode()).hexdigest()
    store = _load_pin_store()
    store[_PIN_META_KEY] = {"hash": h, "salt": salt}
    _save_pin_store(store)


def verify_viewer_pin(pin: str) -> bool:
    """Return True if *pin* matches the stored hash."""
    import hashlib as _hl
    meta = get_viewer_pin_hash()
    if not meta:
        return False
    h = _hl.sha256((meta["salt"] + pin).encode()).hexdigest()
    return h == meta["hash"]


def clear_viewer_pin() -> None:
    """Remove the viewer PIN."""
    store = _load_pin_store()
    store.pop(_PIN_META_KEY, None)
    _save_pin_store(store)


# ── SMTP password encryption ─────────────────────────────────────────────────
# The SMTP password is encrypted at rest using Fernet symmetric encryption.
# The encryption key is derived from a stable machine-specific UUID stored in
# ~/.gdpr_scanner_machine_id.  This key is only usable on the same machine —
# the encrypted password cannot be decrypted if the config file is copied to
# another host.

_MACHINE_ID_PATH = _DATA_DIR / "machine_id"

try:
    from cryptography.fernet import Fernet as _Fernet
    import base64 as _b64
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

def _get_fernet() -> "Optional[_Fernet]":
    """Return a Fernet instance keyed to this machine, or None if unavailable."""
    if not _CRYPTO_OK:
        return None
    try:
        if _MACHINE_ID_PATH.exists():
            machine_key = _MACHINE_ID_PATH.read_bytes()
        else:
            machine_key = _Fernet.generate_key()
            _MACHINE_ID_PATH.write_bytes(machine_key)
            try:
                _MACHINE_ID_PATH.chmod(0o600)
            except Exception:
                pass
        return _Fernet(machine_key)
    except Exception:
        return None

def _encrypt_password(plaintext: str) -> str:
    """Encrypt a password string; returns a 'enc:' prefixed ciphertext string."""
    if not plaintext:
        return ""
    f = _get_fernet()
    if f is None:
        return plaintext  # fallback: store as-is (no cryptography lib)
    try:
        return "enc:" + f.encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext

def _decrypt_password(stored: str) -> str:
    """Decrypt a stored password; handles both encrypted and legacy plaintext."""
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        return stored  # legacy plaintext — return as-is
    f = _get_fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(stored[4:].encode()).decode()
    except Exception:
        return ""


def _load_smtp_config() -> dict:
    """Return saved SMTP config, decrypting the password field."""
    try:
        if _SMTP_CONFIG_PATH.exists():
            cfg = json.loads(_SMTP_CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("password"):
                cfg["password"] = _decrypt_password(cfg["password"])
            return cfg
    except Exception:
        pass
    return {}

def _save_smtp_config(cfg: dict) -> None:
    """Save SMTP config, encrypting the password field."""
    try:
        to_save = dict(cfg)
        if to_save.get("password"):
            to_save["password"] = _encrypt_password(to_save["password"])
        tmp = _SMTP_CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(to_save, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_SMTP_CONFIG_PATH)
        try:
            _SMTP_CONFIG_PATH.chmod(0o600)
        except Exception:
            pass
    except Exception as e:
        logger.error("[smtp] config save failed: %s", e)
