"""
Shared mutable state for GDPR Scanner.

All modules (gdpr_scanner.py and route blueprints) import from here.
This avoids circular imports while keeping a single source of truth
for every global that routes need to read or write.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from m365_connector import M365Connector

# ── Auth ──────────────────────────────────────────────────────────────────────
connector: "M365Connector | None" = None
pending_flow: "dict | None" = None
auth_poll_result: "dict | None" = None

# ── Google Workspace ──────────────────────────────────────────────────────────
google_connector  = None   # GoogleConnector | PersonalGoogleConnector | None
google_pending_flow: "dict | None" = None
google_poll_result: "str | None"   = None

# ── Scan concurrency ──────────────────────────────────────────────────────────
import threading as _threading
_scan_lock        = _threading.Lock()
_scan_abort       = _threading.Event()
_google_scan_lock  = _threading.Lock()
_google_scan_abort = _threading.Event()

# ── Scan results (in-memory session cache) ────────────────────────────────────
flagged_items: list = []
scan_meta:     dict = {}

# ── i18n ─────────────────────────────────────────────────────────────────────
LANG: dict = {}

# ── Art. 9 keyword data ───────────────────────────────────────────────────────
compiled_keywords: list = []  # list of compiled re.Pattern
keyword_data:      dict = {}  # raw keyword dict from JSON
keyword_flat:      list = []  # flat list of keyword strings
