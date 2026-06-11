"""
Software update routes: check origin for new commits, apply the update,
and an optional auto-update background thread.

Only available when running from a git checkout — the frozen desktop
build (PyInstaller) reports supported=False and the UI hides the group.

Applying an update fast-forwards to origin/<branch>, reinstalls
dependencies if requirements.txt changed, then re-execs the process so
the new code is loaded. Local edits are stashed (kept), never discarded.
"""
from __future__ import annotations
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Blueprint, jsonify, request

from routes import state
from app_config import get_update_config, save_update_config

bp = Blueprint("updates", __name__)

_REPO_DIR = Path(__file__).parent.parent
_GIT_TIMEOUT = 30
_AUTO_CHECK_INTERVAL = 24 * 3600   # auto-update checks once per day
_last_auto_check = [0.0]


def _supported() -> bool:
    return (not getattr(sys, "frozen", False)) and (_REPO_DIR / ".git").exists()


def _git(*args: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=_REPO_DIR,
        capture_output=True, text=True, timeout=timeout,
    )


def _scan_running() -> bool:
    return state._scan_lock.locked() or state._google_scan_lock.locked()


def check_for_update() -> dict:
    """Fetch origin and compare HEAD against the tracked branch."""
    if not _supported():
        return {"supported": False}
    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
        fetch = _git("fetch", "origin", branch, timeout=60)
        if fetch.returncode != 0:
            return {"supported": True, "error": fetch.stderr.strip()[:300] or "git fetch failed"}
        local  = _git("rev-parse", "HEAD").stdout.strip()
        remote = _git("rev-parse", f"origin/{branch}").stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"supported": True, "error": str(e)[:300]}
    info = {
        "supported": True, "branch": branch,
        "current": local[:7], "latest": remote[:7],
        "up_to_date": local == remote, "commits": [],
    }
    if local != remote:
        lg = _git("log", "--oneline", f"HEAD..origin/{branch}")
        info["commits"] = lg.stdout.strip().splitlines()[:20]
    return info


def apply_update() -> dict:
    """Fast-forward to origin/<branch>; returns {"ok", "updated", ...}.

    Does NOT restart the process — callers decide (the route schedules a
    re-exec, the auto-update thread restarts directly).
    """
    chk = check_for_update()
    if not chk.get("supported"):
        return {"ok": False, "code": "unsupported",
                "error": "Updates require running from a git checkout."}
    if chk.get("error"):
        return {"ok": False, "code": "check_failed", "error": chk["error"]}
    if chk.get("up_to_date"):
        return {"ok": True, "updated": False, "current": chk["current"]}
    if _scan_running():
        return {"ok": False, "code": "scan_running",
                "error": "Cannot update while a scan is running."}

    branch = chk["branch"]
    try:
        if _git("diff-index", "--quiet", "HEAD", "--").returncode != 0:
            _git("stash", "push", "-m",
                 "auto-stash before update " + time.strftime("%Y-%m-%d %H:%M:%S"))
        reqs_changed = _git(
            "diff", "--quiet", f"HEAD..origin/{branch}", "--", "requirements.txt"
        ).returncode != 0
        merge = _git("merge", "--ff-only", f"origin/{branch}")
        if merge.returncode != 0:
            return {"ok": False, "code": "merge_failed",
                    "error": (merge.stderr.strip() or "git merge failed")[:300]}
        if reqs_changed:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "-r",
                 str(_REPO_DIR / "requirements.txt")],
                cwd=_REPO_DIR, capture_output=True, timeout=600,
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "code": "apply_failed", "error": str(e)[:300]}

    try:
        from gdpr_db import log_audit_event as _audit
        _audit("app_update", f"{chk['current']} -> {chk['latest']}",
               ip=(request.remote_addr if request else ""))
    except Exception:
        pass
    return {"ok": True, "updated": True,
            "from": chk["current"], "to": chk["latest"]}


def _mark_fds_cloexec() -> None:
    """Mark every fd above stderr close-on-exec.

    Werkzeug calls ``srv.socket.set_inheritable(True)`` unconditionally
    (for its debug reloader), so without this the listening socket leaks
    into the exec'd process: it sits on the port as a zombie listener no
    one accepts from, the port probe sees the port as busy, and the new
    server hops to port+1 while clients hang against the dead socket.
    """
    try:
        fds = [int(f) for f in os.listdir("/proc/self/fd")]   # Linux
    except (OSError, ValueError):
        fds = list(range(3, 4096))
    for fd in fds:
        if fd > 2:
            try:
                os.set_inheritable(fd, False)
            except OSError:
                pass


def _restart_self() -> None:
    """Re-exec the current process so the updated code is loaded.

    Keeps the same PID, so it works both under systemd and when launched
    manually via start_gdpr.sh.
    """
    _mark_fds_cloexec()
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except OSError:
        # Last resort: exit and rely on a supervisor (systemd Restart=) to
        # bring the app back up.
        os._exit(0)


def _schedule_restart(delay: float = 1.5) -> None:
    def _later():
        time.sleep(delay)
        _restart_self()
    threading.Thread(target=_later, daemon=True, name="update-restart").start()


# ── Routes ────────────────────────────────────────────────────────────────────

@bp.route("/api/update/check")
def update_check():
    return jsonify(check_for_update())


@bp.route("/api/update/apply", methods=["POST"])
def update_apply():
    res = apply_update()
    if res.get("updated"):
        res["restarting"] = True
        _schedule_restart()
    return jsonify(res), (200 if res.get("ok") else 409)


@bp.route("/api/update/settings", methods=["GET", "POST"])
def update_settings():
    if request.method == "GET":
        return jsonify({"supported": _supported(), **get_update_config()})
    data = request.get_json(silent=True) or {}
    save_update_config(bool(data.get("auto_update", False)))
    return jsonify({"ok": True})


# ── Auto-update background thread ─────────────────────────────────────────────

def _auto_update_loop() -> None:
    while True:
        time.sleep(3600)
        try:
            if not get_update_config().get("auto_update"):
                continue
            if time.time() - _last_auto_check[0] < _AUTO_CHECK_INTERVAL:
                continue
            _last_auto_check[0] = time.time()
            if _scan_running():
                _last_auto_check[0] = 0.0   # retry on the next hourly tick
                continue
            res = apply_update()
            if res.get("updated"):
                print(f"  Auto-update: {res['from']} -> {res['to']} — restarting")
                _restart_self()
        except Exception:
            pass


def start_auto_update_thread() -> bool:
    """Called once at startup from gdpr_scanner.py. No-op for frozen builds."""
    if not _supported():
        return False
    threading.Thread(target=_auto_update_loop, daemon=True, name="auto-update").start()
    return True
