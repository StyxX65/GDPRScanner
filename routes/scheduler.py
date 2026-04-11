"""
Scheduler API routes — multi-job CRUD, status, history, run-now.
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request
import sys, os, threading

bp = Blueprint("scheduler", __name__)

# Return JSON for any unhandled exception in this blueprint
@bp.errorhandler(Exception)
def _handle_error(e):
    import traceback; traceback.print_exc()
    return jsonify({"error": str(e)}), 500

# Ensure the project root is on sys.path so `import scheduler` finds
# our scheduler.py and not any stdlib module.
def _sm():
    import scan_scheduler as _s
    return _s


def _sched():
    import scan_scheduler as _s
    return _s.scan_scheduler

def _db():
    import gdpr_scanner as _m
    return _m._get_db() if _m.DB_OK else None


# ── Job list ──────────────────────────────────────────────────────────────────

@bp.route("/api/scheduler/jobs", methods=["GET"])
def scheduler_jobs_list():
    return jsonify({"jobs": _sm().load_jobs()})


@bp.route("/api/scheduler/jobs/save", methods=["POST"])
def scheduler_jobs_save():
    try:
        sm   = _sm()
        data = request.get_json() or {}
        jobs = sm.load_jobs()
        job_id = (data.get("id") or "").strip()
        if job_id:
            for i, j in enumerate(jobs):
                if j["id"] == job_id:
                    jobs[i] = {**sm._DEFAULT_JOB, **j, **data}
                    sm.save_jobs(jobs)
                    try:
                        _sched().reload()
                    except Exception:
                        pass
                    return jsonify({"ok": True, "job": jobs[i]})
        # New job
        job = sm._new_job(data)
        jobs.append(job)
        sm.save_jobs(jobs)
        try:
            _sched().reload()
        except Exception:
            pass
        return jsonify({"ok": True, "job": job})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@bp.route("/api/scheduler/jobs/delete", methods=["POST"])
def scheduler_jobs_delete():
    try:
        sm     = _sm()
        job_id = (request.get_json() or {}).get("id", "")
        if not job_id:
            return jsonify({"error": "id required"}), 400
        jobs = [j for j in sm.load_jobs() if j["id"] != job_id]
        sm.save_jobs(jobs)
        try:
            _sched().reload()
        except Exception:
            pass
        return jsonify({"ok": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Run now ───────────────────────────────────────────────────────────────────

@bp.route("/api/scheduler/jobs/run_now", methods=["POST"])
def scheduler_jobs_run_now():
    job_id = (request.get_json() or {}).get("id", "")
    s = _sched()
    if job_id in s._running_jobs:
        return jsonify({"error": "Job already running"}), 409
    if s.is_running:
        return jsonify({"error": "Another scan is already running"}), 409
    threading.Thread(target=s._execute_scan, args=[job_id], daemon=True).start()
    return jsonify({"status": "started"})


# ── Status ────────────────────────────────────────────────────────────────────

@bp.route("/api/scheduler/status")
def scheduler_status():
    return jsonify(_sched().get_status())


# ── History ───────────────────────────────────────────────────────────────────

@bp.route("/api/scheduler/history")
def scheduler_history():
    db = _db()
    if not db:
        return jsonify({"runs": []})
    try:
        limit  = int(request.args.get("limit", 20))
        job_id = request.args.get("job_id")
        try:
            runs = db.get_schedule_runs(limit=limit, job_id=job_id)
        except TypeError:
            runs = db.get_schedule_runs(limit=limit)
        return jsonify({"runs": runs})
    except Exception as e:
        return jsonify({"runs": [], "error": str(e)})


# ── Backward-compat single-job endpoints ─────────────────────────────────────

@bp.route("/api/scheduler/config", methods=["GET"])
def scheduler_config_get():
    return jsonify(_sm().load_schedule_config())


@bp.route("/api/scheduler/config", methods=["POST"])
def scheduler_config_save():
    sm   = _sm()
    data = request.get_json() or {}
    merged = {**sm.load_schedule_config(), **data}
    sm.save_schedule_config(merged)
    s = _sched()
    s.reload()
    return jsonify({"status": "saved", "config": merged,
                    "next_run": s.next_run_time()})


@bp.route("/api/scheduler/run_now", methods=["POST"])
def scheduler_run_now():
    s = _sched()
    if s.is_running:
        return jsonify({"error": "Scheduled scan already running"}), 409
    threading.Thread(target=s._execute_scan, args=[None], daemon=True).start()
    return jsonify({"status": "started"})
