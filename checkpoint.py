"""
checkpoint.py — Scan checkpoint and delta-token persistence for GDPRScanner.

Provides save/load/clear for mid-scan checkpoints (so interrupted scans can
resume) and load/save for Microsoft Graph delta-link tokens.
"""
from __future__ import annotations
import hashlib
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)
_CHECKPOINT_PATH = _DATA_DIR / "checkpoint.json"

def _checkpoint_key(options: dict) -> str:
    """Stable hash of the scan options — used to detect when a checkpoint
    belongs to a different scan configuration and should be ignored."""
    sig = json.dumps({
        "sources":  sorted(options.get("sources", [])),
        "user_ids": sorted([u["id"] if isinstance(u, dict) else u for u in options.get("user_ids", [])]),
        "older_than_days": options.get("options", {}).get("older_than_days", 0),
    }, sort_keys=True)
    return hashlib.sha256(sig.encode()).hexdigest()[:16]

def _save_checkpoint(key: str, scanned_ids: set, flagged: list, meta: dict) -> None:
    """Write checkpoint to disk. Called periodically during scanning."""
    try:
        payload = {
            "key":         key,
            "scanned_ids": list(scanned_ids),
            "flagged":     flagged,
            "meta":        {k: v for k, v in meta.items() if k != "options"},
        }
        tmp = _CHECKPOINT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(_CHECKPOINT_PATH)
    except Exception as e:
        logger.error("[checkpoint] save failed: %s", e)

def _load_checkpoint(key: str) -> dict | None:
    """Load checkpoint if it matches the current scan key. Returns None on mismatch or error."""
    try:
        if not _CHECKPOINT_PATH.exists():
            return None
        payload = json.loads(_CHECKPOINT_PATH.read_text(encoding="utf-8"))
        if payload.get("key") != key:
            return None
        return payload
    except Exception:
        return None

def _clear_checkpoint() -> None:
    try:
        if _CHECKPOINT_PATH.exists():
            _CHECKPOINT_PATH.unlink()
    except Exception:
        pass

_DELTA_PATH = _DATA_DIR / "delta.json"

def _load_delta_tokens() -> dict:
    """Return saved delta token map {key: deltaLink_url}."""
    try:
        if _DELTA_PATH.exists():
            return json.loads(_DELTA_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_delta_tokens(tokens: dict) -> None:
    """Persist delta tokens atomically."""
    try:
        tmp = _DELTA_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_DELTA_PATH)
    except Exception as e:
        logger.error("[delta] save failed: %s", e)

# ── Broadcast ─────────────────────────────────────────────────────────────────
