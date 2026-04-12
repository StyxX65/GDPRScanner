# TODO — Pending features and sustainability

Quick overview of what's still to be done. Full details in [SUGGESTIONS.md](SUGGESTIONS.md).

---

## Recently completed

### Memory exhaustion during large M365 scans ✅
Six root causes fixed in `scan_engine.py` and `document_scanner.py`:
- Email body HTML stripped at collection time (`body` key deleted from each message dict before it enters `work_items`; plain text stored as `_precomputed_body` instead)
- `work_items` list converted to a `deque` before processing so each item is released immediately after `popleft()`
- `del content` added in file-processing branch as soon as raw bytes are no longer needed (before NER/PII counting)
- `del body_text` added after email body is fully consumed
- PDF OCR page images (`PIL.Image`) nulled out one by one after OCR instead of holding all pages in RAM
- Memory guard using `psutil` skips file downloads when < 300 MB RAM is available

**Still open:** The collection phase itself is still a "gather all, then process" loop. For very large tenants (>500k emails) the pre-extracted plain text in `work_items` could still be significant. The complete fix is to process each user's emails/files inline as they are fetched (generator/streaming pattern) rather than accumulating them into `work_items` first — estimated 1–2 days of refactor.

---

## Pending

### #15 — Scan profiles ✅
Named, reusable scan configurations. Full spec in SUGGESTIONS.md §15.  
**Size:** Large · **Priority:** High

### #23 — Google Workspace role classification + cross-platform identity mapping ✅
Full spec in SUGGESTIONS.md §23.  
**Size:** Large · **Priority:** Medium

### #27 — Migrate i18n format from `.lang` to JSON ✅
Full spec in SUGGESTIONS.md §27.  
**Size:** Medium · **Priority:** Low

### #29 — Rename `skus/` → `classification/` ✅
Full spec in SUGGESTIONS.md §29.  
**Size:** Small · **Priority:** Low

### #33 — Read-only viewer mode with PIN/token URL ✅
A shareable URL (token-protected) or numeric PIN that gives a DPO, school principal, or compliance coordinator read-only access to the results grid — with disposition tagging but without scan controls, credentials, or delete access. Full spec in SUGGESTIONS.md §33.  
**Size:** Medium · **Priority:** Medium

### OneDrive 404 errors — investigate and handle appropriately ✅
404 on `drive/root/delta` during delta scans was being broadcast as a red `scan_error`. Root cause: `_get()` hit `raise_for_status()` for 404s, which fell through to the generic `except Exception` handler in `_scan_user_onedrive`. The full-scan path silently swallowed the same 404 via `except Exception: return` in `_iter_drive_folder_for`.

Fixed by adding `M365DriveNotFound(M365Error)` exception, raising it from `_get()` on 404, and catching it explicitly in `_scan_user_onedrive` with a lower-severity `scan_phase` broadcast ("OneDrive (user): not provisioned — skipped") instead of a red error card.

---

### #32 — Windowed mode for Profiles, Sources, and Settings ✗ Won't do
The workflow is sequential (configure → scan → review), not parallel — there is no realistic scenario where a modal and the results grid need to be open simultaneously. The Sources panel is already visible in the sidebar. Option A (the least-work path) still loads the full 3800-line JS stack twice. Closed.

