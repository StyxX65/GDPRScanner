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

- **`S._historyRefScanId`** — `null` = live/SSE mode **or** the default open-items view; positive int = viewing a past session. Set by `loadHistorySession()`; cleared by `exitHistoryMode()`.
- **`loadHistorySession(null)` → `loadOpenItems()`** — passing `null` no longer resolves to the latest session. It now loads **all open (unactioned) items across every scan** via `GET /api/db/flagged` (no `ref`), leaves `_historyRefScanId` null, and shows no history banner. The "Open items" banner button (`onclick="loadHistorySession(null)"`, key `history_btn_latest`) therefore returns to this open-items view. Specific sessions are still loaded with a positive `ref`, which keeps the re-scan resolved-diff. Do not revert `null` to "resolve latest ref" — that reintroduces the "only the last scan is shown" complaint.
- **Auto-load on page load** — `_sseWatchdog()` in `results.js` calls `window.loadHistorySession?.(null)` whenever `/api/scan/status` reports neither `running` (M365 + file lock) nor `google_running` (Google lock) **and** nothing is shown yet (`!S._historyRefScanId && !S.flaggedData.length`). This is **not one-shot** — it retries on every 4s poll until a session is restored, because (a) the replay buffer is empty after a server restart so `sse_replay_done` never fires, and (b) a completed scan's replayed `scan_phase` can leave a running flag set that would otherwise block the load forever. Because both locks are confirmed free, the watchdog clears the stale `_m365/_google/_fileScanRunning` flags before calling. Do not revert to a one-shot `_initialStatusChecked` gate — that reintroduces the "blank grid after refresh/restart" bug. `/api/scan/status` **must** report `google_running` separately; `running` alone misses live Google scans. The `sse_replay_done` handler in `scan.js` still retries for the non-empty-buffer (no-restart) case.
- **History banner** (`#historyBanner`) — shown when `S._historyRefScanId` is set. Do not hide/show from outside `history.js`.
- **Session picker** (`#historyDropdown`) — rendered inside `[data-history-wrap]` so the outside-click handler works correctly. Do not move the picker outside this wrapper.
- **Cache invalidation** — `invalidateHistoryCache()` clears `_sessions` and `_latestRefScanId`. All three `*_done` SSE handlers call `window.invalidateHistoryCache?.()`.
- **Re-scan diff** — items present in the previous session but absent from the current one are tagged `_resolved: true`, rendered with `.card-resolved` and a green ✓ badge, and NOT added to `S.flaggedData` (grid-only, cannot be bulk-selected or exported).
- **Mode transitions** — `startScan()` calls `window.exitHistoryMode?.()` before clearing the grid.
- **`renderGrid(files)` hides the landing cards** — whenever `files.length > 0` it hides `#emptyState` and `#lastScanSummary` and shows `#grid`. This is centralised here because the live `scan_file_flagged` handler (`scan.js`) shows the grid but does NOT clear those panels, so results would render *underneath* a still-visible landing/last-scan card until a manual refresh. Do not move this hiding back into individual callers — every render path (live SSE, `loadOpenItems`, history, filters) must clear the landing. The empty case (`files.length === 0`) is left untouched so callers still control the empty/landing state.

## Card user/group badge — results.js

- **`_accountPill(f)`** builds the account/role pill for both card layouts (list + grid). The **group badge is driven by `f.user_role`** (`student`/`staff`) alone, so it renders even with no display name — items from scans saved before `account_name` was persisted (DB migration 11) have only `user_role` + `account_id`. The user label resolves best-effort: `f.account_name` → `S._allUsers` match (by `id` or `email`) → email-style `account_id` → omit. Do not re-nest the role badge inside an `account_name` check (the old bug) — that hides the group badge for legacy items. Both layouts call `_accountPill(f)`; keep them sharing the one helper.

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
- **Share link base URL** — `_getShareBaseUrl()` uses `window.location.origin` whenever the page is served over HTTPS or from a non-localhost host (a reverse-proxied hostname or LAN IP is already routable, and rewriting it to `http://<LAN-IP>` would bypass the proxy's TLS). Only when browsing at `localhost`/`127.0.0.1` over HTTP does it fetch `/api/local_ip` (LAN IP via UDP probe to `8.8.8.8`) so copied links work from other machines. The result is cached in `_shareBaseUrl` so Copy buttons stay within the click gesture. Both `createShareLink` and `copyTokenLink` are `async`. Do not make it return bare `window.location.origin` unconditionally — that reintroduces unusable `127.0.0.1` links.
- **Settings Security pane** — Admin PIN and Viewer PIN groups live in `stPaneSecurity`. `switchSettingsTab('security')` triggers both `stLoadPinStatus()` and `stLoadViewerPinStatus()`.

## Gotchas

- **`navigator.clipboard` is `undefined` over plain HTTP** — the app is normally reached at `http://<LAN-IP>:5100`, a non-secure context where the Clipboard API does not exist, so calling `navigator.clipboard.writeText(...)` throws synchronously (a `.catch()` on it never runs). Always copy via `window._copyText(text, btn)` (defined in `viewer.js`) — it feature-detects the API and falls back to `document.execCommand('copy')`, then to a `prompt()`. Because `execCommand` needs a user gesture, don't `await` network calls between the click and the copy; `_getShareBaseUrl()` caches its result for this reason.

- **`scheduler.js` strings must use `t()`** — frequency labels, "Next", "Running...", "Disabled", empty-job text, and empty-history text all have translation keys. Do not hard-code English strings in `schedLoad()` or `schedRenderJobs()`.
- **Scheduler UI — `schedToggleReportOnly()`** — dims the Profile row, shows/hides `#schedReportOnlyHint`, and forces `#schedAutoEmail` checked. Called from the checkbox `onchange` handler and at the start of `schedAddJob()` / `schedEditJob()`.
- **Profile editor accounts** — default to unchecked. Only explicitly saved `user_ids` are checked.
- **Date presets** — stored as `years * 365` (integer days). Do not use `* 365.25`.
- **`copyTokenLink` is async** — called from `onclick` as fire-and-forget. Do not make it synchronous.
- **Escape scan-derived strings with `esc()`** — `results.js` defines `esc()` (escapes `& < > " '`). Every value that originates from scanned content (`f.name`, `f.account_name`, `f.folder`, `f.source`, `f.modified`, `label`, image `alt`, and the same fields on `item`/related rows) must pass through `esc()` before going into `innerHTML` or a `title=`/`alt=` attribute. These are attacker-influenceable (e.g. a file named with markup), so an unescaped interpolation is stored XSS — including in shared read-only viewer sessions. Numeric counts (`cpr_count`, `size_kb`) don't need it. When embedding an object in an `onclick` payload, also `.replace(/"/g,'&quot;')` the `JSON.stringify(...)`.
