# Routes — Architecture Rules

## SSE constraints
SSE routes must live in `gdpr_scanner.py`, not blueprints — blueprints can't stream.

M365 scan emits `scan_done`; Google emits `google_scan_done`; file scan emits `file_scan_done`. Never mix them up.

**`scan_start` is M365-only** — `run_scan()` broadcasts `scan_start`; `run_file_scan()` and `routes/google_scan.py` must NOT. The `scan_start` handler in `_attachSchedulerListeners` (scan.js) unconditionally sets `S._m365ScanRunning = true`. If a file scan emits `scan_start`, the flag is set with no matching `scan_done` to clear it — `file_scan_done` checks `!S._m365ScanRunning` before re-enabling the scan button, so the button stays disabled permanently after the scan completes.

## scan_progress source field
All three scan engines must include `"source": "m365"` / `"google"` / `"file"` in every `scan_progress` SSE event. Never remove this field — the frontend uses it to route progress to the correct segment.

## file_sources
`file_sources` in profiles are stored as source ID strings by the JS frontend. The scheduler resolves them via `_load_file_sources()` before calling `run_file_scan()`.

## Circular import prohibition
`scan_engine.py` and `gdpr_scanner.py` must not import each other. `scan_engine` imports from `sse`, `checkpoint`, `app_config`, `cpr_detector`; `gdpr_scanner` imports scan functions from `scan_engine`.

## `_scan_bytes` injection
`scan_engine.py` declares stub versions of `_scan_bytes` / `_scan_bytes_timeout` at module level. `gdpr_scanner.py` replaces them with the real `cpr_detector` implementations at startup. `routes/google_scan.py` pulls them from `gdpr_scanner` via `__getattr__`. Never import these directly in blueprint or engine modules — that breaks the circular-import barrier.

## Gotchas

- **`_load_settings()` return** — does NOT include `file_sources`. Returns only: sources, user_ids, options, retention_years, fiscal_year_end, email_to.
- **`_save_settings()` clobbers profile fields** — called on every M365 scan start with only M365 sources/user_ids/options. The fix in `app_config.py` preserves `google_sources` and `file_sources` and rebuilds `sources` as `m365_src + google_src + file_src`. Do not simplify away this merge logic.
- **`loadLastScanSummary()` timing** — must only be called after the first `/api/scan/status` poll resolves (inside `_sseWatchdog` in `results.js`, guarded by `_initialStatusChecked`). Calling it on `DOMContentLoaded` shows a stale "no results" card during a live scan after a hard refresh.
