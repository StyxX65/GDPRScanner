"""
Scheduler — in-process APScheduler wrapper for automated GDPR scans.

Supports multiple independent named scan jobs.
Config stored in ~/.gdpr_scanner_schedule.json as {"jobs": [...]}.
Old single-job format is migrated automatically on first load.
Run history persisted in the SQLite DB (schedule_runs table).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_OK = True
except ImportError:
    APSCHEDULER_OK = False

# ── Config file ───────────────────────────────────────────────────────────────
_DATA_DIR      = Path.home() / ".gdprscanner"
_DATA_DIR.mkdir(exist_ok=True)
_SCHEDULE_PATH = _DATA_DIR / "schedule.json"

_DEFAULT_JOB: dict[str, Any] = {
    "id":              "",
    "name":            "Scheduled scan",
    "enabled":         False,
    "frequency":       "daily",
    "day_of_week":     "mon",
    "day_of_month":    1,
    "hour":            2,
    "minute":          0,
    "profile_id":      "",
    "auto_email":      False,
    "auto_retention":  False,
    "retention_years": None,
    "fiscal_year_end": None,
}

_DEFAULT_CONFIG = _DEFAULT_JOB  # backward-compat alias


def _new_job(overrides: dict | None = None) -> dict:
    job = dict(_DEFAULT_JOB)
    job["id"] = str(uuid.uuid4())
    if overrides:
        job.update(overrides)
    return job


def load_jobs() -> list[dict]:
    """Return list of job dicts. Migrates old single-job format automatically.
    Also assigns UUIDs to any jobs that were saved without one."""
    try:
        if _SCHEDULE_PATH.exists():
            data = json.loads(_SCHEDULE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "jobs" in data:
                jobs = [{**_DEFAULT_JOB, **j} for j in data["jobs"]]
                # Ensure every job has a non-empty id
                changed = False
                for j in jobs:
                    if not j.get("id"):
                        j["id"] = str(uuid.uuid4())
                        changed = True
                if changed:
                    _save_jobs_file(jobs)
                return jobs
            # Old format: migrate to single-job list
            if isinstance(data, dict):
                job = _new_job({**data, "name": "Scheduled scan"})
                _save_jobs_file([job])
                return [job]
    except Exception:
        pass
    return []


def save_jobs(jobs: list[dict]) -> None:
    _save_jobs_file(jobs)


def _save_jobs_file(jobs: list[dict]) -> None:
    tmp = _SCHEDULE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"jobs": jobs}, indent=2), encoding="utf-8")
    tmp.replace(_SCHEDULE_PATH)
    try:
        _SCHEDULE_PATH.chmod(0o600)
    except OSError:
        pass


# Backward-compat shims
def load_schedule_config() -> dict:
    jobs = load_jobs()
    return jobs[0] if jobs else dict(_DEFAULT_JOB)


def save_schedule_config(cfg: dict) -> None:
    jobs = load_jobs()
    if jobs:
        jobs[0] = {**_DEFAULT_JOB, **cfg}
    else:
        jobs = [_new_job(cfg)]
    save_jobs(jobs)


def _build_trigger(job: dict) -> "CronTrigger":
    freq   = job.get("frequency", "daily")
    hour   = int(job.get("hour", 2))
    minute = int(job.get("minute", 0))
    if freq == "weekly":
        return CronTrigger(day_of_week=job.get("day_of_week", "mon"),
                           hour=hour, minute=minute)
    elif freq == "monthly":
        return CronTrigger(day=int(job.get("day_of_month", 1)),
                           hour=hour, minute=minute)
    return CronTrigger(hour=hour, minute=minute)


def _ap_id(job_id: str) -> str:
    return f"gdpr_scan_{job_id}"


# ── Scheduler class ───────────────────────────────────────────────────────────

class ScanScheduler:

    def __init__(self):
        self._scheduler: BackgroundScheduler | None = None
        self._lock = threading.Lock()
        self._last_runs: dict[str, dict] = {}
        self._running_jobs: set[str] = set()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> bool:
        if not APSCHEDULER_OK:
            return False
        self._scheduler = BackgroundScheduler(
            daemon=True,
            job_defaults={"coalesce": True, "max_instances": 1,
                          "misfire_grace_time": 3600},
        )
        self._scheduler.start()
        self.reload()
        return True

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def reload(self):
        if not self._scheduler:
            return
        for job in self._scheduler.get_jobs():
            if job.id.startswith("gdpr_scan_"):
                self._scheduler.remove_job(job.id)
        for job_cfg in load_jobs():
            if job_cfg.get("enabled"):
                self._scheduler.add_job(
                    self._execute_scan,
                    trigger=_build_trigger(job_cfg),
                    id=_ap_id(job_cfg["id"]),
                    name=job_cfg.get("name", "GDPR scheduled scan"),
                    args=[job_cfg["id"]],
                    replace_existing=True,
                )

    def next_run_time(self, job_id: str | None = None) -> str | None:
        if not self._scheduler:
            return None
        if job_id:
            job = self._scheduler.get_job(_ap_id(job_id))
            if job and job.next_run_time:
                return job.next_run_time.isoformat()
            return None
        times = [j.next_run_time for j in self._scheduler.get_jobs()
                 if j.id.startswith("gdpr_scan_") and j.next_run_time]
        return min(times).isoformat() if times else None

    @property
    def is_running(self) -> bool:
        return bool(self._running_jobs)

    def get_status(self) -> dict:
        jobs = load_jobs()
        job_statuses = []
        for j in jobs:
            jid = j["id"]
            job_statuses.append({
                "id":         jid,
                "name":       j.get("name", ""),
                "enabled":    j.get("enabled", False),
                "next_run":   self.next_run_time(jid),
                "is_running": jid in self._running_jobs,
                "last_run":   self._last_runs.get(jid),
            })
        return {
            "available":  APSCHEDULER_OK,
            "jobs":       job_statuses,
            "enabled":    any(j.get("enabled") for j in jobs),
            "next_run":   self.next_run_time(),
            "is_running": bool(self._running_jobs),
        }

    # ── Execute scan ──────────────────────────────────────────────────────

    def _execute_scan(self, job_id: str | None = None):
        jobs = load_jobs()
        if not jobs:
            return
        if job_id:
            job_cfg = next((j for j in jobs if j["id"] == job_id), None)
            if not job_cfg:
                return
        else:
            job_cfg = jobs[0]
            job_id  = job_cfg["id"]

        if job_id in self._running_jobs:
            return
        with self._lock:
            if job_id in self._running_jobs:
                return
            self._running_jobs.add(job_id)

        run = {
            "started_at": time.time(), "finished_at": None,
            "status": "running",
            "job_id": job_id, "job_name": job_cfg.get("name", ""),
            "profile_id": job_cfg.get("profile_id", ""),
            "flagged": 0, "scanned": 0, "emailed": 0, "error": "",
        }
        self._last_runs[job_id] = run
        db_run_id: int | None = None
        _m = None
        logger.info("[scheduler] Starting job '%s'", job_cfg.get("name", ""))

        try:
            import gdpr_scanner as _m
            try:
                db = _m._get_db()
                if db:
                    try:
                        db_run_id = db.begin_schedule_run(
                            profile_id=job_cfg.get("profile_id", ""),
                            job_id=job_id,
                            job_name=job_cfg.get("name", ""),
                        )
                    except TypeError:
                        db_run_id = db.begin_schedule_run(
                            profile_id=job_cfg.get("profile_id", ""))
            except Exception:
                pass

            _m.broadcast("scheduler_started", {
                "time": datetime.now(timezone.utc).isoformat(),
                "job_name": job_cfg.get("name", ""),
            })

            from routes import state
            # If connector not set, attempt to restore from saved config
            if not state.connector or not state.connector.is_authenticated():
                try:
                    cfg_saved = _m._load_config()
                    cid    = cfg_saved.get("client_id", "")
                    tid    = cfg_saved.get("tenant_id", "")
                    secret = cfg_saved.get("client_secret", "")
                    if cid and tid:
                        from m365_connector import M365Connector
                        conn = M365Connector(cid, tid, client_secret=secret)
                        if conn.is_app_mode:
                            conn.authenticate_app_mode()
                        if conn.is_authenticated():
                            state.connector = conn
                except Exception as _e:
                    pass
            if not state.connector or not state.connector.is_authenticated():
                raise RuntimeError("Not authenticated")

            if not _m._scan_lock.acquire(blocking=False):
                logger.info("[scheduler] Scan already running — skipping job '%s'", job_cfg.get("name", job_id))
                _m.broadcast("scheduler_debug", {"msg": f"Skipped — a scan is already running"})
                return

            try:
                # Sync connector into gdpr_scanner's module global —
                # run_scan() reads _connector directly, not state.connector
                _m._connector = state.connector
                _m._scan_abort.clear()
                options = self._build_options(job_cfg)
                options.setdefault("options", {})["_scheduled"] = True
                # Fire M365 scan if M365 sources are included
                m365_sources = [s for s in options.get("sources", [])
                                if s in ("email","onedrive","sharepoint","teams")]
                if m365_sources:
                    opts_m365 = dict(options, sources=m365_sources)
                    _m.run_scan(opts_m365)
                # Fire file scan for each file source in the profile
                # file_sources may be IDs (strings) or full dicts — resolve either
                _all_file_sources = {s["id"]: s for s in (_m._load_file_sources() or []) if isinstance(s, dict)}
                for fs in options.get("file_sources", []):
                    # Resolve string IDs to full source dicts
                    if isinstance(fs, str):
                        fs = _all_file_sources.get(fs, {"path": fs, "label": fs})
                    if not isinstance(fs, dict) or not fs.get("path"):
                        logger.warning("[scheduler] skipping invalid file source: %r", fs)
                        continue
                    try:
                        _m.run_file_scan(fs)
                    except Exception as _fse:
                        import traceback as _tb2
                        _label = fs.get('label', fs.get('path', str(fs)))
                        logger.error("[scheduler] file scan error (%s): %s\n%s", _label, _fse, _tb2.format_exc())
            finally:
                _m._scan_lock.release()

            # Fire Google scan if Google sources are in the profile and
            # a Google connector is available.
            google_sources = options.get("google_sources", [])
            if not google_sources:
                # Legacy profiles store everything in sources[]
                google_sources = [s for s in options.get("sources", [])
                                  if s in ("gmail", "gdrive")]
            if google_sources and state.google_connector:
                from routes.google_scan import (
                    _run_google_scan as _rgs,
                    _scan_lock       as _gsl,
                    _scan_abort      as _gsa,
                )
                if _gsl.acquire(blocking=False):
                    try:
                        _gsa.clear()
                        logger.info("[scheduler] Starting Google scan — sources=%s", google_sources)
                        _rgs({
                            "sources":     google_sources,
                            "user_emails": [],  # empty → scan all workspace users
                            "options":     options.get("options", {}),
                        })
                    except Exception as _ge:
                        import traceback as _tb3
                        logger.error("[scheduler] Google scan error: %s\n%s", _ge, _tb3.format_exc())
                    finally:
                        _gsl.release()
                else:
                    logger.info("[scheduler] Google scan already running — skipping")

            run["flagged"] = len(_m.flagged_items)
            run["scanned"] = _m.scan_meta.get("total_scanned", 0)
            run["status"]  = "completed"
            logger.info("[scheduler] Job '%s' completed — %d flagged, %d scanned",
                        job_cfg.get("name", ""), run["flagged"], run["scanned"])

            if job_cfg.get("auto_email") and state.flagged_items:
                try:
                    self._send_email_report(job_cfg)
                    run["emailed"] = 1
                except Exception as e:
                    run["error"] = f"Scan OK, email failed: {e}"

            if job_cfg.get("auto_retention") and job_cfg.get("retention_years"):
                try:
                    self._run_retention(job_cfg)
                except Exception as e:
                    err = f"Retention failed: {e}"
                    run["error"] = f"{run['error']} | {err}" if run["error"] else err

            _m.broadcast("scheduler_done", {
                "flagged": run["flagged"], "scanned": run["scanned"],
                "emailed": run["emailed"], "job_name": job_cfg.get("name", ""),
            })

        except Exception as e:
            import traceback as _tb
            _tb_str = _tb.format_exc()
            logger.error("[scheduler] Job failed:\n%s", _tb_str)
            run["status"] = "failed"
            run["error"]  = str(e)
            try:
                if _m:
                    # Include last 3 lines of traceback in UI for diagnosis
                    _tb_lines = _tb_str.strip().splitlines()
                    _tb_short = ' | '.join(_tb_lines[-4:]) if len(_tb_lines) >= 4 else _tb_str
                    _m.broadcast("scheduler_error", {"error": str(e) + ' | ' + _tb_short})
            except Exception:
                pass

        finally:
            run["finished_at"] = time.time()
            self._last_runs[job_id] = run
            self._running_jobs.discard(job_id)
            if db_run_id and _m:
                try:
                    db = _m._get_db()
                    if db:
                        db.finish_schedule_run(db_run_id, **{
                            k: run[k] for k in
                            ("status", "flagged", "scanned", "emailed", "error")
                        })
                except Exception:
                    pass

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_options(self, job_cfg: dict) -> dict:
        import gdpr_scanner as _m
        pid = job_cfg.get("profile_id", "")
        logger.info("[scheduler] Job '%s' — profile_id='%s'", job_cfg.get("name", ""), pid)
        if pid:
            p = _m._profile_get(pid)
            if p:
                # Derive google_sources from dedicated field; fall back to
                # filtering the combined sources array for legacy profiles.
                _all_src = p.get("sources", [])
                _gs_fallback = [s for s in _all_src if s in ("gmail", "gdrive")]
                opts = {"sources":        _all_src,
                        "user_ids":       p.get("user_ids", []),
                        "options":        p.get("options", {}),
                        "file_sources":   p.get("file_sources", []),
                        "google_sources": p.get("google_sources", _gs_fallback)}
                logger.info("[scheduler]   Profile '%s': sources=%s, users=%d",
                            p.get("name", pid), opts["sources"], len(opts.get("user_ids", [])))
                _m.broadcast("scheduler_debug", {
                    "msg": f"Using profile '{p.get('name',pid)}': sources={opts['sources']}, users={len(opts.get("user_ids",[]))}"})
                return opts
            logger.info("[scheduler]   Profile '%s' not found — using saved settings", pid)
            _m.broadcast("scheduler_debug", {"msg": f"Profile id '{pid}' not found — falling back to saved settings"})
        saved = _m._load_settings()
        if saved:
            logger.info("[scheduler]   Saved settings: sources=%s, users=%d",
                        saved.get("sources"), len(saved.get("user_ids", [])))
            _m.broadcast("scheduler_debug", {
                "msg": f"Using saved settings: sources={saved.get('sources')}, users={len(saved.get('user_ids',[]))}"})
        return saved or {"sources": ["email", "onedrive"], "user_ids": [], "options": {}}

    def _send_email_report(self, job_cfg: dict):
        import gdpr_scanner as _m
        xl_bytes, fname = _m._build_excel_bytes()
        smtp_cfg   = _m._load_smtp_config()
        recipients = smtp_cfg.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.replace(";", ",").split(",") if r.strip()]
        if not recipients:
            raise RuntimeError("No email recipients configured")
        job_name = job_cfg.get("name", "scheduled scan")
        subject  = f"GDPR Scanner — {job_name} {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        body = (
            "<html><body style='font-family:Arial,sans-serif;color:#333;padding:24px'>"
            "<h2 style='color:#1F3864'>&#128336; GDPR Scanner — scheduled scan report</h2>"
            f"<p>Job: <strong>{job_name}</strong></p>"
            f"<p>Scan completed. {len(_m.flagged_items)} item(s) flagged.</p>"
            f"<p>Report attached: {fname}</p></body></html>")
        from routes.email import _send_email_graph
        from routes import state
        if state.connector and state.connector.is_authenticated():
            try:
                _send_email_graph(subject, body, recipients,
                                  attachment_bytes=xl_bytes, attachment_name=fname)
                return
            except Exception:
                pass
        _m._send_report_email(xl_bytes, fname, smtp_cfg, recipients)

    def _run_retention(self, job_cfg: dict):
        import gdpr_scanner as _m
        if not _m.DB_OK:
            return
        db = _m._get_db()
        if not db:
            return
        overdue = db.get_overdue_items(int(job_cfg["retention_years"]),
                                       fiscal_year_end=job_cfg.get("fiscal_year_end"))
        if overdue:
            _m._do_retention_delete(overdue)


# ── Module-level singleton ────────────────────────────────────────────────────
scan_scheduler = ScanScheduler()
