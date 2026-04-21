#!/usr/bin/env python3
"""
gdpr_db.py — SQLite persistence layer for GDPRScanner

Stores scan results alongside the existing JSON cache.  Neither replaces the
other: JSON is fast and portable, SQLite enables querying, trending, and the
data-subject index.

Database location: ~/.gdpr_scanner.db  (configurable via DB_PATH)

Schema
------
    scans          one row per completed scan run
    flagged_items  one row per flagged file / email
    cpr_index      (cpr_hash, item_id) — powers data-subject lookup
    pii_hits       per-type PII counts per item
    dispositions   compliance officer decisions per item
    scan_history   aggregated stats for trend tracking

Usage (from gdpr_scanner.py)
-----------------------------
    from gdpr_db import ScanDB
    db = ScanDB()
    scan_id = db.begin_scan(options)
    db.save_item(scan_id, card, cprs)      # called for each flagged card
    db.finish_scan(scan_id, total_scanned)
    db.close()
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Iterator

from pathlib import Path as _P
_DATA_DIR = _P.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)
DB_PATH = _DATA_DIR / "scanner.db"

# ── Retention cutoff helper ──────────────────────────────────────────────────

def overdue_cutoff(years: int = 5, fiscal_year_end: str | None = None) -> str:
    """Return the ISO date string before which items are considered overdue.

    Two modes:
    - Rolling (default, fiscal_year_end=None):
        Exactly N years before today.
        E.g. years=5 on 2026-03-17 -> 2021-03-17
        Correct for GDPR general data minimisation.

    - Fiscal year end (fiscal_year_end="MM-DD", e.g. "12-31"):
        N years before the most recently completed fiscal year end.
        E.g. years=5, FY end Dec 31, run on 2026-03-17:
          Last FY end = 2025-12-31  ->  cutoff = 2020-12-31
        Documents from the FY ending 2020-12-31 expire on 2025-12-31,
        so on 2026-03-17 they are overdue. This is correct for
        Bogforingsloven (Danish bookkeeping law) which requires records
        for 5 years from the END of the financial year.
    """
    from datetime import date, timedelta

    today = date.today()

    if fiscal_year_end:
        # Parse MM-DD
        try:
            month, day = (int(x) for x in fiscal_year_end.split("-"))
        except (ValueError, AttributeError):
            raise ValueError(f"fiscal_year_end must be MM-DD, got {fiscal_year_end!r}")

        # Find the most recently completed fiscal year end date
        fy_this_year = date(today.year, month, day)
        if fy_this_year >= today:
            # This year's FY end is in the future -- use last year's
            fy_end = date(today.year - 1, month, day)
        else:
            fy_end = fy_this_year

        # Cutoff is N years before that FY end
        cutoff = fy_end.replace(year=fy_end.year - years)
    else:
        # Rolling: exactly N years before today
        cutoff = today.replace(year=today.year - years)

    return cutoff.isoformat()


# ── Schema DDL ────────────────────────────────────────────────────────────────
_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    REAL    NOT NULL,
    finished_at   REAL,
    sources       TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    user_count    INTEGER NOT NULL DEFAULT 0,
    options       TEXT    NOT NULL DEFAULT '{}',   -- JSON object
    total_scanned INTEGER NOT NULL DEFAULT 0,
    flagged_count INTEGER NOT NULL DEFAULT 0,
    delta         INTEGER NOT NULL DEFAULT 0       -- 0=full, 1=delta
);

CREATE TABLE IF NOT EXISTS flagged_items (
    id          TEXT    NOT NULL,                  -- Graph item ID
    scan_id     INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT '',
    source_type TEXT    NOT NULL DEFAULT '',       -- email/onedrive/sharepoint/teams
    account_id  TEXT    NOT NULL DEFAULT '',
    folder      TEXT    NOT NULL DEFAULT '',
    url         TEXT    NOT NULL DEFAULT '',
    drive_id    TEXT    NOT NULL DEFAULT '',
    size_kb     REAL    NOT NULL DEFAULT 0,
    modified    TEXT    NOT NULL DEFAULT '',       -- YYYY-MM-DD
    cpr_count   INTEGER NOT NULL DEFAULT 0,
    risk        TEXT,
    user_role   TEXT    NOT NULL DEFAULT 'other',  -- student/staff/other                              -- LOW/MEDIUM/HIGH
    thumb_b64   TEXT    NOT NULL DEFAULT '',
    thumb_mime  TEXT    NOT NULL DEFAULT 'image/svg+xml',
    attachments TEXT    NOT NULL DEFAULT '[]',     -- JSON array
    scanned_at  REAL    NOT NULL,
    PRIMARY KEY (id, scan_id)
);

CREATE TABLE IF NOT EXISTS cpr_index (
    cpr_hash    TEXT    NOT NULL,                  -- SHA-256 of the raw CPR string
    item_id     TEXT    NOT NULL,
    scan_id     INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    first_seen  REAL    NOT NULL,
    PRIMARY KEY (cpr_hash, item_id, scan_id)
);

CREATE TABLE IF NOT EXISTS pii_hits (
    item_id     TEXT    NOT NULL,
    scan_id     INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    pii_type    TEXT    NOT NULL,                  -- phone/email/iban/name/address/org
    hit_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, scan_id, pii_type)
);

CREATE TABLE IF NOT EXISTS dispositions (
    item_id       TEXT    NOT NULL PRIMARY KEY,
    status        TEXT    NOT NULL DEFAULT 'unreviewed',
    legal_basis   TEXT,
    notes         TEXT,
    reviewed_by   TEXT,
    reviewed_at   REAL
);

CREATE TABLE IF NOT EXISTS scan_history (
    scan_id           INTEGER PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
    scan_date         TEXT    NOT NULL,            -- YYYY-MM-DD
    flagged_count     INTEGER NOT NULL DEFAULT 0,
    special_category  INTEGER NOT NULL DEFAULT 0,
    overdue_count     INTEGER NOT NULL DEFAULT 0,
    deleted_count     INTEGER NOT NULL DEFAULT 0,
    sources_json      TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS deletion_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    deleted_at    REAL    NOT NULL,                -- Unix timestamp
    item_id       TEXT    NOT NULL,
    item_name     TEXT    NOT NULL DEFAULT '',
    source_type   TEXT    NOT NULL DEFAULT '',     -- email/onedrive/sharepoint/teams
    account_id    TEXT    NOT NULL DEFAULT '',
    account_name  TEXT    NOT NULL DEFAULT '',
    cpr_count     INTEGER NOT NULL DEFAULT 0,
    reason        TEXT    NOT NULL DEFAULT 'manual',  -- manual/bulk/retention/data-subject-request
    legal_basis   TEXT    NOT NULL DEFAULT '',     -- from dispositions table if set
    deleted_by    TEXT    NOT NULL DEFAULT '',     -- authenticated user or "headless"
    scan_id       INTEGER                          -- which scan found this item (nullable)
);

CREATE INDEX IF NOT EXISTS idx_dellog_time    ON deletion_log(deleted_at);
CREATE INDEX IF NOT EXISTS idx_dellog_item    ON deletion_log(item_id);
CREATE INDEX IF NOT EXISTS idx_dellog_reason  ON deletion_log(reason);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_items_scan    ON flagged_items(scan_id);
CREATE INDEX IF NOT EXISTS idx_items_source  ON flagged_items(source_type);
CREATE INDEX IF NOT EXISTS idx_items_account ON flagged_items(account_id);
CREATE INDEX IF NOT EXISTS idx_items_risk    ON flagged_items(risk);
CREATE INDEX IF NOT EXISTS idx_cpr_hash      ON cpr_index(cpr_hash);
CREATE INDEX IF NOT EXISTS idx_cpr_item      ON cpr_index(item_id);
CREATE INDEX IF NOT EXISTS idx_history_date  ON scan_history(scan_date);
"""

# ── Migration helpers ─────────────────────────────────────────────────────────
_MIGRATIONS: list[tuple[int, str]] = [
    # (version, sql)
    # Each runs once and is recorded in the user_version pragma.
    (1, "ALTER TABLE flagged_items ADD COLUMN user_role TEXT NOT NULL DEFAULT 'other'"),
    (2, "ALTER TABLE flagged_items ADD COLUMN transfer_risk TEXT NOT NULL DEFAULT ''"),
    (3, "ALTER TABLE flagged_items ADD COLUMN special_category TEXT NOT NULL DEFAULT '[]'"),
    (4, "ALTER TABLE flagged_items ADD COLUMN face_count INTEGER NOT NULL DEFAULT 0"),
    (5, "ALTER TABLE flagged_items ADD COLUMN exif_json TEXT NOT NULL DEFAULT '{}'"),
    (6, "ALTER TABLE flagged_items ADD COLUMN full_path TEXT NOT NULL DEFAULT ''"),
    (7, """CREATE TABLE IF NOT EXISTS schedule_runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at  REAL    NOT NULL,
        finished_at REAL,
        status      TEXT    NOT NULL DEFAULT 'running',
        profile_id  TEXT    NOT NULL DEFAULT '',
        flagged     INTEGER NOT NULL DEFAULT 0,
        scanned     INTEGER NOT NULL DEFAULT 0,
        emailed     INTEGER NOT NULL DEFAULT 0,
        error       TEXT    NOT NULL DEFAULT ''
    )"""),
]


class ScanDB:
    """Thread-safe SQLite wrapper for GDPRScanner results."""

    def __init__(self, path: Path = DB_PATH):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._path),
                check_same_thread=False,
                timeout=15,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_DDL)
            self._conn.commit()
            self._run_migrations()
        return self._conn

    def _run_migrations(self) -> None:
        conn = self._conn
        cur_ver = conn.execute("PRAGMA user_version").fetchone()[0]
        for ver, sql in _MIGRATIONS:
            if ver > cur_ver:
                try:
                    conn.executescript(sql)
                except Exception:
                    pass  # column may already exist on fresh DBs
                conn.execute(f"PRAGMA user_version = {ver}")
                conn.commit()

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def reset(self) -> None:
        """Drop all tables and recreate the schema from scratch.

        This permanently deletes all scan results, CPR index, dispositions,
        deletion log, and scan history. Use with caution.
        Closes and reopens the connection so the fresh schema is in effect.
        """
        c = self._connect()
        tables = [
            "deletion_log", "pii_hits", "cpr_index",
            "dispositions", "scan_history", "flagged_items", "scans",
        ]
        for tbl in tables:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
        c.execute("PRAGMA user_version = 0")
        c.commit()
        # Reopen so _connect() rebuilds schema fresh
        self.close()
        self._connect()



    def begin_scan(self, options: dict) -> int:
        """Create a scan record and return its id."""
        c = self._connect()
        sources    = options.get("sources", [])
        user_ids   = options.get("user_ids", [])
        scan_opts  = options.get("options", {})
        delta      = 1 if scan_opts.get("delta") else 0
        cur = c.execute(
            """INSERT INTO scans
               (started_at, sources, user_count, options, delta)
               VALUES (?, ?, ?, ?, ?)""",
            (
                time.time(),
                json.dumps(sources),
                len(user_ids),
                json.dumps(scan_opts),
                delta,
            ),
        )
        c.commit()
        return cur.lastrowid

    def save_item(self, scan_id: int, card: dict, cprs: list | None = None,
                  pii_counts: dict | None = None) -> None:
        """Persist one flagged item and its CPR/PII data."""
        c = self._connect()
        now = time.time()

        c.execute(
            """INSERT OR REPLACE INTO flagged_items
               (id, scan_id, name, source, source_type, account_id, folder,
                url, drive_id, size_kb, modified, cpr_count, risk,
                thumb_b64, thumb_mime, attachments, user_role, transfer_risk,
                special_category, face_count, exif_json, full_path, scanned_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                card.get("id", ""),
                scan_id,
                card.get("name", ""),
                card.get("source", ""),
                card.get("source_type", ""),
                card.get("account_id", ""),
                card.get("folder", ""),
                card.get("url", ""),
                card.get("drive_id", ""),
                card.get("size_kb", 0),
                card.get("modified", ""),
                card.get("cpr_count", 0),
                card.get("risk"),
                card.get("thumb_b64", ""),
                card.get("thumb_mime", "image/svg+xml"),
                json.dumps(card.get("attachments", [])),
                card.get("user_role", "other"),
                card.get("transfer_risk", ""),
                json.dumps(card.get("special_category", [])),
                card.get("face_count", 0),
                json.dumps(card.get("exif", {})),
                card.get("full_path", ""),
                now,
            ),
        )

        # CPR index — store hash only (never store raw CPR numbers in DB)
        item_id = card.get("id", "")
        if cprs:
            for cpr in cprs:
                cpr_hash = hashlib.sha256(str(cpr).encode()).hexdigest()
                c.execute(
                    """INSERT OR IGNORE INTO cpr_index
                       (cpr_hash, item_id, scan_id, first_seen)
                       VALUES (?,?,?,?)""",
                    (cpr_hash, item_id, scan_id, now),
                )

        # PII hit counts
        if pii_counts:
            for pii_type, count in pii_counts.items():
                if count and count > 0:
                    c.execute(
                        """INSERT OR REPLACE INTO pii_hits
                           (item_id, scan_id, pii_type, hit_count)
                           VALUES (?,?,?,?)""",
                        (item_id, scan_id, pii_type, count),
                    )

        c.commit()

    def finish_scan(self, scan_id: int, total_scanned: int,
                    deleted_count: int = 0) -> None:
        """Mark scan as complete and write history row."""
        c = self._connect()
        now = time.time()

        flagged = c.execute(
            "SELECT COUNT(*) FROM flagged_items WHERE scan_id=?", (scan_id,)
        ).fetchone()[0]

        c.execute(
            """UPDATE scans SET finished_at=?, total_scanned=?, flagged_count=?
               WHERE id=?""",
            (now, total_scanned, flagged, scan_id),
        )

        # Per-source breakdown for history
        rows = c.execute(
            """SELECT source_type, COUNT(*) FROM flagged_items
               WHERE scan_id=? GROUP BY source_type""",
            (scan_id,),
        ).fetchall()
        sources_json = json.dumps({r[0]: r[1] for r in rows})

        # Count overdue items using rolling 5-year window (baseline for history)
        overdue = c.execute(
            """SELECT COUNT(*) FROM flagged_items
               WHERE scan_id=? AND modified != ''
               AND date(modified) < ?""",
            (scan_id, overdue_cutoff(5)),
        ).fetchone()[0]

        special_count = c.execute(
            """SELECT COUNT(*) FROM flagged_items
               WHERE scan_id=? AND special_category != '[]' AND special_category != ''""",
            (scan_id,),
        ).fetchone()[0]

        scan_date = time.strftime("%Y-%m-%d", time.localtime(now))
        c.execute(
            """INSERT OR REPLACE INTO scan_history
               (scan_id, scan_date, flagged_count, special_category,
                overdue_count, deleted_count, sources_json)
               VALUES (?,?,?,?,?,?,?)""",
            (scan_id, scan_date, flagged, special_count, overdue, deleted_count, sources_json),
        )

        c.commit()

    # ── Query helpers ─────────────────────────────────────────────────────────

    def latest_scan_id(self) -> int | None:
        """Return the id of the most recent completed scan."""
        row = self._connect().execute(
            "SELECT id FROM scans WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def get_flagged_items(self, scan_id: int | None = None) -> list[dict]:
        """Return flagged items for a scan (defaults to latest)."""
        sid = scan_id or self.latest_scan_id()
        if not sid:
            return []
        rows = self._connect().execute(
            """SELECT fi.*, COALESCE(d.status, 'unreviewed') AS disposition
               FROM flagged_items fi
               LEFT JOIN dispositions d ON d.item_id = fi.id
               WHERE fi.scan_id=? ORDER BY fi.cpr_count DESC""",
            (sid,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["attachments"] = json.loads(d.get("attachments") or "[]")
            result.append(d)
        return result

    def get_sessions(self, limit: int = 50, window_seconds: int = 300) -> list[dict]:
        """Return scan sessions (groups of concurrent scans) newest-first.

        Concurrent M365 + Google + File scans each get their own scan_id but start
        within seconds of each other.  This method groups them into logical sessions
        by the same 300-second window used by get_session_items().
        """
        rows = self._connect().execute(
            """SELECT id, started_at, finished_at, sources, flagged_count, total_scanned, delta
               FROM scans WHERE finished_at IS NOT NULL ORDER BY started_at ASC"""
        ).fetchall()
        # Group consecutive scans started within window_seconds of each other
        groups: list[list[dict]] = []
        for r in rows:
            d = dict(r)
            d["sources"] = json.loads(d.get("sources") or "[]")
            if groups and d["started_at"] - groups[-1][0]["started_at"] <= window_seconds:
                groups[-1].append(d)
            else:
                groups.append([d])
        # Build session summaries newest-first
        sessions: list[dict] = []
        for grp in reversed(groups):
            ref = grp[-1]   # highest scan_id in group (last in ASC order)
            sessions.append({
                "ref_scan_id":   ref["id"],
                "started_at":    grp[0]["started_at"],
                "finished_at":   ref.get("finished_at"),
                "sources":       list({s for g in grp for s in g["sources"]}),
                "flagged_count": sum(g["flagged_count"] or 0 for g in grp),
                "total_scanned": sum(g["total_scanned"] or 0 for g in grp),
                "delta":         any(bool(g["delta"]) for g in grp),
            })
            if len(sessions) >= limit:
                break
        return sessions

    def get_session_items(self, window_seconds: int = 300,
                          ref_scan_id: int | None = None) -> list[dict]:
        """Return flagged items from all scans in the same session as the latest scan.

        A session is all scans whose started_at is within *window_seconds* of the
        most recently started completed scan.  This captures concurrent M365, Google,
        and file scans which each create their own scan_id but start within seconds
        of each other.

        If *ref_scan_id* is given, the session is anchored to that scan's started_at
        instead of the latest scan.
        """
        if ref_scan_id:
            row = self._connect().execute(
                "SELECT started_at FROM scans WHERE id=?", (ref_scan_id,)
            ).fetchone()
        else:
            row = self._connect().execute(
                "SELECT started_at FROM scans WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return []
        latest_start = row[0]
        rows = self._connect().execute(
            """SELECT fi.*, COALESCE(d.status, 'unreviewed') AS disposition
               FROM flagged_items fi
               JOIN scans s ON fi.scan_id = s.id
               LEFT JOIN dispositions d ON d.item_id = fi.id
               WHERE s.started_at BETWEEN ? AND ? AND s.finished_at IS NOT NULL
               ORDER BY fi.cpr_count DESC""",
            (latest_start - window_seconds, latest_start + window_seconds),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["attachments"] = json.loads(d.get("attachments") or "[]")
            result.append(d)
        return result

    def get_session_sources(self, window_seconds: int = 300) -> set:
        """Return the union of all source keys scanned in the current session.

        Reads the ``sources`` JSON array stored in each scan record that belongs
        to the same session as the latest completed scan.  This is used by the
        export builders so they can show every scanned source in summary tables
        even when a source produced zero flagged items.
        """
        row = self._connect().execute(
            "SELECT started_at FROM scans WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return set()
        latest_start = row[0]
        rows = self._connect().execute(
            """SELECT sources FROM scans
               WHERE started_at >= ? AND finished_at IS NOT NULL""",
            (latest_start - window_seconds,),
        ).fetchall()
        result: set = set()
        for r in rows:
            try:
                result.update(json.loads(r[0] or "[]"))
            except Exception:
                pass
        return result

    def lookup_data_subject(self, cpr: str) -> list[dict]:
        """Find all flagged items containing a given CPR number (by hash)."""
        cpr_hash = hashlib.sha256(str(cpr).encode()).hexdigest()
        rows = self._connect().execute(
            """SELECT fi.*, ci.first_seen AS cpr_first_seen
               FROM cpr_index ci
               JOIN flagged_items fi ON fi.id = ci.item_id AND fi.scan_id = ci.scan_id
               WHERE ci.cpr_hash = ?
               ORDER BY fi.modified DESC""",
            (cpr_hash,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["attachments"] = json.loads(d.get("attachments") or "[]")
            result.append(d)
        return result

    def get_overdue_items(self, years: int = 5,
                          scan_id: int | None = None,
                          fiscal_year_end: str | None = None) -> list[dict]:
        """Return items older than the retention cutoff.

        Args:
            years:            Retention period in years (default 5).
            scan_id:          Scan to query (defaults to latest).
            fiscal_year_end:  "MM-DD" for fiscal-year-aligned cutoff
                              (e.g. "12-31" for Danish bookkeeping law).
                              None = rolling window from today.
        """
        sid = scan_id or self.latest_scan_id()
        if not sid:
            return []
        cutoff = overdue_cutoff(years, fiscal_year_end)
        rows = self._connect().execute(
            """SELECT * FROM flagged_items
               WHERE scan_id=? AND modified != ''
               AND date(modified) < ?
               ORDER BY modified ASC""",
            (sid, cutoff),
        ).fetchall()
        result = [dict(r) for r in rows]
        for r in result:
            r["cutoff_date"]  = cutoff
            r["cutoff_mode"]  = "fiscal" if fiscal_year_end else "rolling"
        return result

    def get_trend(self, last_n: int = 20) -> list[dict]:
        """Return the last N scan history rows for trend display."""
        rows = self._connect().execute(
            """SELECT sh.*, s.delta, s.sources
               FROM scan_history sh
               JOIN scans s ON s.id = sh.scan_id
               ORDER BY sh.scan_id DESC LIMIT ?""",
            (last_n,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def set_disposition(self, item_id: str, status: str,
                        legal_basis: str = "", notes: str = "",
                        reviewed_by: str = "") -> None:
        """Record a compliance officer's decision on an item."""
        self._connect().execute(
            """INSERT OR REPLACE INTO dispositions
               (item_id, status, legal_basis, notes, reviewed_by, reviewed_at)
               VALUES (?,?,?,?,?,?)""",
            (item_id, status, legal_basis, notes, reviewed_by, time.time()),
        )
        self._connect().commit()

    def get_disposition(self, item_id: str) -> dict | None:
        row = self._connect().execute(
            "SELECT * FROM dispositions WHERE item_id=?", (item_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_prior_disposition(self, item_id: str) -> str | None:
        """Return prior disposition status if set (not 'unreviewed'), else None."""
        row = self._connect().execute(
            "SELECT status FROM dispositions WHERE item_id=?", (item_id,)
        ).fetchone()
        if row and row[0] and row[0] != "unreviewed":
            return row[0]
        return None

    def get_stats(self, scan_id: int | None = None) -> dict:
        """Return summary stats for a scan."""
        sid = scan_id or self.latest_scan_id()
        if not sid:
            return {}
        c = self._connect()
        scan = c.execute("SELECT * FROM scans WHERE id=?", (sid,)).fetchone()
        if not scan:
            return {}
        by_source = c.execute(
            """SELECT source_type, COUNT(*), SUM(cpr_count)
               FROM flagged_items WHERE scan_id=? GROUP BY source_type""",
            (sid,),
        ).fetchall()
        unique_subjects = c.execute(
            "SELECT COUNT(DISTINCT cpr_hash) FROM cpr_index WHERE scan_id=?",
            (sid,),
        ).fetchone()[0]
        overdue = c.execute(
            """SELECT COUNT(*) FROM flagged_items
               WHERE scan_id=? AND modified != ''
               AND date(modified) < ?""",
            (sid, overdue_cutoff(5)),
        ).fetchone()[0]
        return {
            "scan_id":        sid,
            "started_at":     scan["started_at"],
            "finished_at":    scan["finished_at"],
            "total_scanned":  scan["total_scanned"],
            "flagged_count":  scan["flagged_count"],
            "unique_subjects": unique_subjects,
            "overdue_count":  overdue,
            "delta":          bool(scan["delta"]),
            "by_source": {
                r[0]: {"items": r[1], "cpr_hits": r[2]}
                for r in by_source
            },
        }

    def iter_all_items(self, scan_id: int | None = None) -> Iterator[dict]:
        """Iterate over flagged items without loading all into memory."""
        sid = scan_id or self.latest_scan_id()
        if not sid:
            return
        cur = self._connect().execute(
            "SELECT * FROM flagged_items WHERE scan_id=? ORDER BY id",
            (sid,),
        )
        for row in cur:
            d = dict(row)
            d["attachments"] = json.loads(d.get("attachments") or "[]")
            yield d

    def scans_list(self, limit: int = 50) -> list[dict]:
        """Return recent scan summaries."""
        rows = self._connect().execute(
            """SELECT id, started_at, finished_at, sources, user_count,
                      total_scanned, flagged_count, delta
               FROM scans
               WHERE finished_at IS NOT NULL
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["sources"] = json.loads(d.get("sources") or "[]")
            result.append(d)
        return result

    def log_deletion(self, item: dict, reason: str = "manual",
                     deleted_by: str = "", scan_id: int | None = None) -> None:
        """Write an immutable deletion audit record.

        Args:
            item:       flagged_item dict (or any dict with id, name, source_type, etc.)
            reason:     "manual" | "bulk" | "retention" | "data-subject-request"
            deleted_by: identity of the actor — authenticated M365 user UPN,
                        "headless" for scheduled runs, or "" for UI with no user context
            scan_id:    which scan originally found this item (optional)
        """
        c   = self._connect()
        now = time.time()

        # Pull legal_basis from dispositions table if available
        legal_basis = ""
        disp = self.get_disposition(item.get("id", ""))
        if disp:
            legal_basis = disp.get("legal_basis", "") or ""

        c.execute(
            """INSERT INTO deletion_log
               (deleted_at, item_id, item_name, source_type, account_id,
                account_name, cpr_count, reason, legal_basis, deleted_by, scan_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now,
                item.get("id", ""),
                item.get("name", ""),
                item.get("source_type", ""),
                item.get("account_id", ""),
                item.get("account_name", ""),
                item.get("cpr_count", 0),
                reason,
                legal_basis,
                deleted_by,
                scan_id,
            ),
        )
        c.commit()

    def get_deletion_log(self, limit: int = 500,
                         reason: str | None = None) -> list[dict]:
        """Return deletion audit records, most recent first."""
        c = self._connect()
        if reason:
            rows = c.execute(
                "SELECT * FROM deletion_log WHERE reason=? ORDER BY deleted_at DESC LIMIT ?",
                (reason, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM deletion_log ORDER BY deleted_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def deletion_log_stats(self) -> dict:
        """Return summary counts of the deletion log."""
        c = self._connect()
        total = c.execute("SELECT COUNT(*) FROM deletion_log").fetchone()[0]
        by_reason = {
            r[0]: r[1] for r in c.execute(
                "SELECT reason, COUNT(*) FROM deletion_log GROUP BY reason"
            ).fetchall()
        }
        cpr_deleted = c.execute(
            "SELECT SUM(cpr_count) FROM deletion_log"
        ).fetchone()[0] or 0
        return {"total": total, "by_reason": by_reason, "cpr_hits_deleted": cpr_deleted}

    def delete_item_record(self, item_id: str, scan_id: int | None = None) -> None:
        """Remove a flagged item from the DB (after it has been deleted in M365)."""
        c = self._connect()
        if scan_id:
            c.execute(
                "DELETE FROM flagged_items WHERE id=? AND scan_id=?",
                (item_id, scan_id),
            )
            c.execute(
                "DELETE FROM cpr_index WHERE item_id=? AND scan_id=?",
                (item_id, scan_id),
            )
        else:
            c.execute("DELETE FROM flagged_items WHERE id=?", (item_id,))
            c.execute("DELETE FROM cpr_index WHERE item_id=?", (item_id,))
        c.commit()


    # ── Scheduler runs ────────────────────────────────────────────────────────

    def begin_schedule_run(self, profile_id: str = "") -> int:
        """Insert a new schedule_runs row and return its id."""
        import time
        c = self._connect()
        cur = c.execute(
            "INSERT INTO schedule_runs (started_at, profile_id) VALUES (?, ?)",
            (time.time(), profile_id))
        c.commit()
        return cur.lastrowid

    def finish_schedule_run(self, run_id: int, *,
                            status: str = "completed",
                            flagged: int = 0, scanned: int = 0,
                            emailed: int = 0, error: str = "") -> None:
        import time
        c = self._connect()
        c.execute(
            """UPDATE schedule_runs
               SET finished_at=?, status=?, flagged=?, scanned=?, emailed=?, error=?
               WHERE id=?""",
            (time.time(), status, flagged, scanned, emailed, error, run_id))
        c.commit()

    def get_schedule_runs(self, limit: int = 20) -> list[dict]:
        c = self._connect()
        rows = c.execute(
            "SELECT * FROM schedule_runs ORDER BY started_at DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]


    def export_db(self, out_path: Path) -> dict:
        """Export the database to a structured ZIP archive.

        Contents:
            export_meta.json   — metadata (date, schema version, row counts)
            scans.json         — scan run summaries
            flagged_items.json — flagged items (thumb_b64 stripped)
            cpr_index.json     — CPR hashes (never raw CPR)
            pii_hits.json      — per-type PII counts
            dispositions.json  — compliance decisions
            scan_history.json  — aggregated trend data
            deletion_log.json  — full deletion audit trail

        Returns a summary dict with row counts.
        """
        import zipfile as _zf, json as _json, datetime as _dt

        c = self._connect()

        def _rows(table: str, strip_cols: list | None = None) -> list[dict]:
            rows = [dict(r) for r in c.execute(f"SELECT * FROM {table}").fetchall()]
            if strip_cols:
                for row in rows:
                    for col in strip_cols:
                        row.pop(col, None)
            return rows

        tables = {
            "scans":         _rows("scans"),
            "flagged_items": _rows("flagged_items", strip_cols=["thumb_b64"]),
            "cpr_index":     _rows("cpr_index"),
            "pii_hits":      _rows("pii_hits"),
            "dispositions":  _rows("dispositions"),
            "scan_history":  _rows("scan_history"),
            "deletion_log":  _rows("deletion_log"),
            "schedule_runs": _rows("schedule_runs"),
        }

        schema_ver = c.execute("PRAGMA user_version").fetchone()[0]
        meta = {
            "exported_at":    _dt.datetime.now().isoformat(),
            "schema_version": schema_ver,
            "db_path":        str(self._path),
            "row_counts":     {k: len(v) for k, v in tables.items()},
        }

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with _zf.ZipFile(out_path, "w", _zf.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.writestr("export_meta.json", _json.dumps(meta, indent=2))
            for name, rows in tables.items():
                zf.writestr(f"{name}.json", _json.dumps(rows, indent=2, default=str))

        return meta

    def import_db(self, zip_path: Path, mode: str = "merge") -> dict:
        """Import a previously exported ZIP archive into the database.

        Args:
            zip_path: Path to the export ZIP file.
            mode:     "merge"   — import dispositions and deletion_log into
                                  the current DB, leave existing data intact.
                      "replace" — wipe the DB first, then import everything.

        Returns a summary dict with imported row counts.
        """
        import zipfile as _zf, json as _json

        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"Export file not found: {zip_path}")

        with _zf.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if "export_meta.json" not in names:
                raise ValueError("Not a valid GDPRScanner export — missing export_meta.json")

            meta = _json.loads(zf.read("export_meta.json"))

            def _load(fname: str) -> list[dict]:
                if fname not in names:
                    return []
                return _json.loads(zf.read(fname))

            scans         = _load("scans.json")
            flagged_items = _load("flagged_items.json")
            cpr_index     = _load("cpr_index.json")
            pii_hits      = _load("pii_hits.json")
            dispositions  = _load("dispositions.json")
            scan_history  = _load("scan_history.json")
            deletion_log  = _load("deletion_log.json")
            schedule_runs = _load("schedule_runs.json")

        if mode == "replace":
            self.reset()

        c = self._connect()
        imported: dict[str, int] = {}

        if mode == "replace":
            # Full restore — import all tables
            for row in scans:
                try:
                    c.execute(
                        """INSERT OR IGNORE INTO scans
                           (id,started_at,finished_at,sources,user_count,
                            options,total_scanned,flagged_count,delta)
                           VALUES (:id,:started_at,:finished_at,:sources,:user_count,
                            :options,:total_scanned,:flagged_count,:delta)""", row)
                except Exception: pass
            imported["scans"] = len(scans)

            for row in flagged_items:
                row.setdefault("thumb_b64", "")
                row.setdefault("user_role", "other")
                try:
                    c.execute(
                        """INSERT OR IGNORE INTO flagged_items
                           (id,scan_id,name,source,source_type,account_id,folder,
                            url,drive_id,size_kb,modified,cpr_count,risk,
                            thumb_b64,thumb_mime,attachments,user_role,scanned_at)
                           VALUES (:id,:scan_id,:name,:source,:source_type,:account_id,
                            :folder,:url,:drive_id,:size_kb,:modified,:cpr_count,:risk,
                            :thumb_b64,:thumb_mime,:attachments,:user_role,:scanned_at)""", row)
                except Exception: pass
            imported["flagged_items"] = len(flagged_items)

            for row in cpr_index:
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO cpr_index (cpr_hash,item_id,scan_id,first_seen) "
                        "VALUES (:cpr_hash,:item_id,:scan_id,:first_seen)", row)
                except Exception: pass
            imported["cpr_index"] = len(cpr_index)

            for row in pii_hits:
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO pii_hits (item_id,scan_id,pii_type,hit_count) "
                        "VALUES (:item_id,:scan_id,:pii_type,:hit_count)", row)
                except Exception: pass
            imported["pii_hits"] = len(pii_hits)

            for row in scan_history:
                try:
                    c.execute(
                        """INSERT OR IGNORE INTO scan_history
                           (scan_id,scan_date,flagged_count,special_category,
                            overdue_count,deleted_count,sources_json)
                           VALUES (:scan_id,:scan_date,:flagged_count,:special_category,
                            :overdue_count,:deleted_count,:sources_json)""", row)
                except Exception: pass
            imported["scan_history"] = len(scan_history)

        # Both modes: merge dispositions and deletion_log
        for row in dispositions:
            try:
                c.execute(
                    """INSERT OR REPLACE INTO dispositions
                       (item_id,status,legal_basis,notes,reviewed_by,reviewed_at)
                       VALUES (:item_id,:status,:legal_basis,:notes,:reviewed_by,:reviewed_at)""",
                    row)
            except Exception: pass
        imported["dispositions"] = len(dispositions)

        for row in deletion_log:
            try:
                c.execute(
                    """INSERT OR IGNORE INTO deletion_log
                       (id,deleted_at,item_id,item_name,source_type,account_id,
                        account_name,cpr_count,reason,legal_basis,deleted_by,scan_id)
                       VALUES (:id,:deleted_at,:item_id,:item_name,:source_type,:account_id,
                        :account_name,:cpr_count,:reason,:legal_basis,:deleted_by,:scan_id)""",
                    row)
            except Exception: pass
        imported["deletion_log"] = len(deletion_log)

        for row in schedule_runs:
            try:
                c.execute(
                    """INSERT OR IGNORE INTO schedule_runs
                       (id,started_at,finished_at,status,profile_id,
                        flagged,scanned,emailed,error)
                       VALUES (:id,:started_at,:finished_at,:status,:profile_id,
                        :flagged,:scanned,:emailed,:error)""",
                    row)
            except Exception: pass
        imported["schedule_runs"] = len(schedule_runs)

        c.commit()
        return {"mode": mode, "exported_at": meta.get("exported_at"), "imported": imported}


# ── Module-level singleton ────────────────────────────────────────────────────
_db: ScanDB | None = None


def get_db(path: Path = DB_PATH) -> ScanDB:
    """Return the module-level ScanDB singleton, creating it if needed."""
    global _db
    if _db is None:
        _db = ScanDB(path)
    return _db
