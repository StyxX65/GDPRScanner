"""
sse.py — Server-Sent Events for GDPRScanner.

Provides:
  broadcast(event, data)  — push an event to all connected browsers
  _sse_queues             — list of per-connection Queue objects
  _sse_buffer             — deque replay buffer for late-connecting browsers
  _current_scan_id        — injected into every broadcast message
"""
from __future__ import annotations
import json
import logging
import queue
from collections import deque

logger = logging.getLogger(__name__)

# ── SSE state ─────────────────────────────────────────────────────────────────
_sse_queues: list      = []
_sse_buffer: deque     = deque(maxlen=500)
_current_scan_id: str  = ""

def broadcast(event: str, data: dict):
    global _current_scan_id
    if _current_scan_id:
        data = {**data, "scan_id": _current_scan_id}
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    _sse_buffer.append(msg)  # buffer for SSE replay on reconnect
    for q in list(_sse_queues):
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass
    # Clear scan_id after scan_done so replay knows the scan is finished
    if event == "scan_done" and _current_scan_id:
        _current_scan_id = ""
    # When no browser is watching (e.g. scheduled scan), log key events
    if not _sse_queues:
        if event == "scan_phase":
            logger.info("[scan] %s", data.get("phase", ""))
        elif event == "scan_progress":
            file = data.get("file") or data.get("name", "")
            if file:
                logger.info("[scan] %s/%s — %s", data.get("completed", ""), data.get("total", ""), file)
        elif event in ("scan_error", "scheduler_error"):
            logger.error("[scan] %s", data.get("error", "") or data.get("file", ""))
        elif event == "scan_done":
            logger.info("[scan] Done — %d flagged, %d scanned",
                        data.get("flagged_count", 0), data.get("total_scanned", 0))
        elif event == "scheduler_started":
            logger.info("[scan] Scheduler started — %s", data.get("job_name", ""))
        elif event == "scheduler_done":
            logger.info("[scan] Scheduler done — %d flagged", data.get("flagged", 0))

