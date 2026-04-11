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

## Gotchas

- **Profile editor accounts** — default to unchecked. Only explicitly saved `user_ids` are checked.
- **Date presets** — stored as `years * 365` (integer days). Do not use `* 365.25`.
- **`copyTokenLink` is async** — called from `onclick` attributes as a fire-and-forget (the Promise is unhandled, which is fine). It `await`s `_getShareBaseUrl()` to get the machine's LAN IP before building the URL. Do not make it synchronous or revert to `window.location.origin` directly.
