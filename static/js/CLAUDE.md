# static/js — JS Rules

## Profile dropdown — loader model
Profiles are **loaders**, not persistent modes. Selecting one pushes settings into the sidebar; the sidebar is always the live state.

- `_setProfileClearBtn(visible)` must be called alongside every assignment to `S._activeProfileId`.
- **Do not re-add a selectable `value=""` option to `#profileSelect`** — deliberately removed in v1.6.6.

## Profile editor source panel race condition
`_pmgmtSaveFullEdit` detects whether Google/file checkboxes have rendered by querying the DOM directly:
```javascript
const googleRendered = !!document.querySelector('#peSourcesPanel input[data-source-type="google"]');
const fileRendered   = !!document.querySelector('#peSourcesPanel input[data-source-type="file"]');
```
Never revert to `!!window._googleConnected` / `_fileSources.length > 0` — those async proxies can be `true` before the panel has rendered, silently clearing the user's source selection on save.

## Progress bar phase parsing
`_setProgressPhase(phase)` in `scan.js` parses the phase string against `_PHASE_SOURCE_MAP`:
1. Source found **and** ` — ` (em-dash) present → split, resolve via `_resolveDisplayName()`, update `S._progressCurrentUser`.
2. Source found **but no dash** → show pill + `S._progressCurrentUser` (handles sub-phases like folder counts).
3. No source match → plain text fallback.

`_PHASE_SOURCE_MAP` ordering matters — `Google Workspace` must appear before `Gmail` in the map. The email regex uses `/iu` flags — do not drop the `i`.

## Profile startup race conditions — profiles.js + users.js

`loadProfiles()` (fast, local file) resolves before `loadUsers()` (slow, Graph API). The user can select a profile before `S._allUsers` or the sources panel is populated.

- **`user_ids = "all"` must be deferred** — if `S._allUsers` is empty when `_applyProfile()` runs, set `window._pendingProfileAllUsers = true` instead of calling `.forEach()` on an empty array. `loadUsers()` checks this flag after populating `S._allUsers` and selects everyone. Do not remove this — reverting will silently leave all accounts unchecked whenever a profile is chosen on a fast machine before the user list loads.
- **Source checkboxes may not exist yet** — `_applyProfile()` calls `renderSourcesPanel()` first if `#sourcesPanel` contains no `input[data-source-id]` nodes. Same guard used in `loadUsers()`. Without it, `querySelectorAll` returns nothing and the profile's source selection is discarded; the next `renderSourcesPanel()` call re-renders all sources as checked (their default).

## SSE teardown — scan.js

- **Do not close `S.es` in `scan_done` if other scans are still running** — M365 (`scan_done`), Google (`google_scan_done`), and File (`file_scan_done`) each emit their own done event. Close `S.es` only when all concurrent scans have finished: `scan_done` checks `!S._googleScanRunning && !S._fileScanRunning`; `google_scan_done` checks `!S._m365ScanRunning && !S._fileScanRunning`; `file_scan_done` checks `!S._m365ScanRunning && !S._googleScanRunning`.
- **Scheduled scans** — `S._userStartedScan` is false for scheduler-triggered runs, so SSE is never closed and future scheduler events continue to arrive.
- **Two separate abort events** — `state._scan_abort` (M365 + file) and `state._google_scan_abort` (Google). `POST /api/scan/stop` sets **both**. `_check_abort()` inside `_run_google_scan` must use the module-level `_scan_abort` alias (`= state._google_scan_abort`), not `gdpr_scanner._scan_abort`.
- **`_check_abort()` emits `google_scan_done`, not `scan_cancelled`** — `scan_cancelled` unconditionally closes the SSE; `google_scan_done` checks whether other scans are still running before closing.
- **`scan_phase` replay sets running flags — handled by `sse_replay_done`** — the `scan_phase` handler sets running flags to `true` whenever all flags are `false` and a source keyword is found in the phase text. On page refresh this fires during SSE replay of a completed scan, temporarily making the scan appear running. The `sse_replay_done` handler retries `loadHistorySession(null)` if no scan is running and `S._historyRefScanId` is still `null` after replay. Do not remove either the flag-setting logic or the retry.
- **Google Drive uses a lazy generator, not `list()`** — `iter_drive_files()` iterated directly so `_check_abort()` fires between items. Wrapping in `list()` blocks the thread for the entire enumeration.

## Scan history browser — history.js + results.js

- **`S._historyRefScanId`** — `null` = live/SSE mode; positive int = viewing a past session. Set by `loadHistorySession()`; cleared by `exitHistoryMode()`.
- **Auto-load on page load** — `results.js` calls `window.loadHistorySession?.(null)` once when the SSE watchdog confirms `!status.running`. `_initialStatusChecked` guard ensures this fires at most once per page load. The `sse_replay_done` handler in `scan.js` retries if `loadHistorySession` bailed due to stale running flags set during replay.
- **History banner** (`#historyBanner`) — shown when `S._historyRefScanId` is set. Do not hide/show from outside `history.js`.
- **Session picker** (`#historyDropdown`) — rendered inside `[data-history-wrap]` so the outside-click handler works correctly. Do not move the picker outside this wrapper.
- **Cache invalidation** — `invalidateHistoryCache()` clears `_sessions` and `_latestRefScanId`. All three `*_done` SSE handlers call `window.invalidateHistoryCache?.()`.
- **Re-scan diff** — items present in the previous session but absent from the current one are tagged `_resolved: true`, rendered with `.card-resolved` and a green ✓ badge, and NOT added to `S.flaggedData` (grid-only, cannot be bulk-selected or exported).
- **Mode transitions** — `startScan()` calls `window.exitHistoryMode?.()` before clearing the grid.

## CPR cross-referencing — results.js

- **`_loadRelated(f)`** — async; hides `#previewRelated` if `f.cpr_count` is 0, otherwise fetches `/api/db/related/<id>?ref=N` and renders a clickable list with per-item shared-CPR badge. Called from `openPreview`.
- **`window._openRelated(id, itemData)`** — looks up `id` in `S.flaggedData` first, falls back to `itemData` from the API response for items not yet in the grid.

## Sources panel resize — log.js + sources.js

- **`_fitSourcesPanel()`** — called at the end of every `renderSourcesPanel()`. Clears inline height, reads `scrollHeight`, then restores a saved preference from `localStorage` (`gdpr_sources_h`) or pins to `scrollHeight`.
- **`_initSourcesResize()`** — attaches pointer-drag to `#sourcesResizeHandle`. Captures `scrollHeight` as hard max on `pointerdown`; saves to `localStorage` on release.
- **Do not add a fixed `max-height` or `height` to `#sourcesPanel` in HTML** — height controlled entirely by `_fitSourcesPanel()` at runtime.
- **Do not call `_fitSourcesPanel()` before the panel has rendered** — `scrollHeight` will be 0.

## Viewer mode — viewer.js

- **`window.VIEWER_MODE`** — injected by Jinja2. `auth.js` adds `viewer-mode` class to `<body>`; all hide rules are CSS (`body.viewer-mode …`) except `delBtn` which is also guarded in JS.
- **`window.VIEWER_SCOPE`** — injected alongside `VIEWER_MODE`. If `VIEWER_SCOPE.role` is set, `auth.js` pre-sets `#filterRole` and hides the dropdown.
- **Token onclick attributes** — Copy/Revoke buttons pass the token as a single-quoted JS string literal, never via `JSON.stringify` (which produces double-quoted strings that break `onclick="…"` attributes).
- **Share link base URL** — `_getShareBaseUrl()` fetches `/api/local_ip` (LAN IP via UDP probe to `8.8.8.8`) so copied links are routable from other machines. Both `createShareLink` and `copyTokenLink` are `async`. Do not revert to `window.location.origin` — that produces `127.0.0.1` links.
- **Settings Security pane** — Admin PIN and Viewer PIN groups live in `stPaneSecurity`. `switchSettingsTab('security')` triggers both `stLoadPinStatus()` and `stLoadViewerPinStatus()`.

## Gotchas

- **`scheduler.js` strings must use `t()`** — frequency labels, "Next", "Running...", "Disabled", empty-job text, and empty-history text all have translation keys. Do not hard-code English strings in `schedLoad()` or `schedRenderJobs()`.
- **Scheduler UI — `schedToggleReportOnly()`** — dims the Profile row, shows/hides `#schedReportOnlyHint`, and forces `#schedAutoEmail` checked. Called from the checkbox `onchange` handler and at the start of `schedAddJob()` / `schedEditJob()`.
- **Profile editor accounts** — default to unchecked. Only explicitly saved `user_ids` are checked.
- **Date presets** — stored as `years * 365` (integer days). Do not use `* 365.25`.
- **`copyTokenLink` is async** — called from `onclick` as fire-and-forget. Do not make it synchronous.
