import { S } from './state.js';
// ── Cards ─────────────────────────────────────────────────────────────────────
const SOURCE_BADGES = {
  email:      ['📧', 'badge-email',      'Outlook'],
  gmail:      ['📧', 'badge-gmail',      'Gmail'],
  gdrive:     ['📁', 'badge-gdrive',     'GDrive'],
  onedrive:   ['💾', 'badge-onedrive',   'OneDrive'],
  sharepoint: ['🌐', 'badge-sharepoint', 'SharePoint'],
  teams:      ['💬', 'badge-teams',      'Teams'],
  local:      ['📁', 'badge-local',      'Local'],
  smb:        ['🌐', 'badge-smb',        'Network'],
};

function appendCard(f) {
  const search = document.getElementById('filterSearch').value.trim().toLowerCase();
  const srcVal = document.getElementById('filterSource').value;
  if (search && !f.name.toLowerCase().includes(search)) return;
  if (srcVal  && f.source_type !== srcVal) return;

  const grid = document.getElementById('grid');
  const [icon, badgeCls, label] = SOURCE_BADGES[f.source_type] || ['📄', '', f.source_type];
  const src  = f.thumb_b64
    ? 'data:' + f.thumb_mime + ';base64,' + f.thumb_b64
    : '/api/thumb?name=' + encodeURIComponent(f.name) + '&type=' + encodeURIComponent(f.source_type);

  const card = document.createElement('div');
  card.className = 'card' + (S.isListView ? ' list-view' : '');
  card.dataset.id = f.id;
  card.onclick = () => openPreview(f);

  const delBtn = window.VIEWER_MODE ? '' : `<button class="card-delete-btn" title="${t('m365_delete_confirm','Delete')}" onclick="event.stopPropagation();deleteItem(${JSON.stringify(f).replace(/"/g,'&quot;')},this.closest('.card'))">🗑</button>`;

  if (S.isListView) {
    card.innerHTML = `
      <div style="font-size:24px; flex-shrink:0">${icon}</div>
      <div class="card-info list-info">
        <div class="card-name" title="${f.name}">${f.name}</div>
        <div class="card-meta">${f.size_kb} KB · ${f.modified || ''}${f.folder ? ' · 📂 ' + f.folder : ''}</div>
        <div class="card-source"><span class="source-badge ${badgeCls}">${label}</span> ${f.source || ''}${f.account_name ? ' · <span class="account-pill" title="' + f.account_name + '">' + (f.user_role === 'student' ? '<span class="role-badge">' + t('role_student','Elev') + '</span>' : f.user_role === 'staff' ? '<span class="role-badge">' + t('role_staff','Ansat') + '</span>' : '') + f.account_name + '</span>' : ''}${f.transfer_risk === 'external-recipient' ? ' <span class="role-pill" style="background:#7B2D00;color:#FFD0B0">⚠ Ext.</span>' : f.transfer_risk ? ' <span class="role-pill" style="background:#003D7B;color:#B0D4FF">🔗</span>' : ''}</div>
      </div>
      <span class="cpr-badge">${f.cpr_count} CPR</span>
      ${f.face_count > 0 ? '<span class="photo-face-badge">' + f.face_count + ' ' + t('m365_badge_faces', f.face_count === 1 ? 'face' : 'faces') + '</span> ' : ''}
      ${f.exif && f.exif.gps ? '<span class="photo-face-badge" style="background:#0a3a5a;color:#7ec8d0">🌍 GPS</span> ' : ''}
      ${f.special_category && f.special_category.length ? '<span class="special-cat-badge">⚠ Art.9 — ' + f.special_category.filter(function(s){return s !== 'gps_location' && s !== 'exif_pii';}).join(', ') + '</span> ' : ''}${f.overdue ? '<span class="overdue-badge">🗓 Overdue</span>' : ''}
      ${delBtn}`;
  } else {
    card.innerHTML = `
      <div class="thumb-wrap"><img src="${src}" alt="${f.name}" loading="lazy"></div>
      <div class="card-info">
        <div class="card-name" title="${f.name}">${f.name}</div>
        <div class="card-meta">${f.size_kb} KB · ${f.modified || ''}</div>
        ${f.folder ? `<div class="card-meta" style="font-size:10px" title="${f.folder}">📂 ${f.folder}</div>` : ''}
        <div class="card-source"><span class="source-badge ${badgeCls}">${label}</span>${f.account_name ? ' <span class="account-pill" title="' + f.account_name + '">' + (f.user_role === "student" ? '<span class="role-badge">' + t("role_student","Elev") + "</span>" : f.user_role === "staff" ? '<span class="role-badge">' + t("role_staff","Ansat") + "</span>" : "") + f.account_name + '</span>' : ''}${f.transfer_risk === "external-recipient" ? ' <span class="role-pill" style="background:#7B2D00;color:#FFD0B0">⚠ Ext.</span>' : f.transfer_risk ? ' <span class="role-pill" style="background:#003D7B;color:#B0D4FF">🔗</span>' : ''}</div>
        <span class="cpr-badge">${f.cpr_count} CPR</span>${f.face_count > 0 ? ' <span class="photo-face-badge">' + f.face_count + ' ' + t('m365_badge_faces', f.face_count === 1 ? 'face' : 'faces') + '</span>' : ''}${f.exif && f.exif.gps ? ' <span class="photo-face-badge" style="background:#0a3a5a;color:#7ec8d0">🌍 GPS</span>' : ''}${f.overdue ? ' <span class="overdue-badge">🗓 Overdue</span>' : ''}
      </div>
      ${delBtn}`;
  }
  grid.appendChild(card);
}

function renderGrid(files) {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  files.forEach(f => appendCard(f));
}

// ── Preview panel ─────────────────────────────────────────────────────────────
let _previewItemId = null;

async function openPreview(f) {
  // Highlight selected card
  document.querySelectorAll('.card.selected').forEach(c => c.classList.remove('selected'));
  const cardEl = document.querySelector(`.card[data-id="${CSS.escape(f.id)}"]`);
  if (cardEl) cardEl.classList.add('selected');

  const panel   = document.getElementById('previewPanel');
  const frame   = document.getElementById('previewFrame');
  const loading = document.getElementById('previewLoading');
  const title   = document.getElementById('previewTitle');
  const meta    = document.getElementById('previewMeta');

  panel.classList.remove('hidden');
  const _savedW = sessionStorage.getItem('gdpr_preview_width');
  if (_savedW) panel.style.width = _savedW + 'px';
  title.textContent = f.name;
  frame.style.display = 'none';
  loading.style.display = 'flex';
  loading.textContent = 'Loading preview…';

  meta.innerHTML = [
    f.account_name ? `<span style="font-weight:500">👤 ${f.account_name}</span>` : '',
    f.source   ? `<span>${f.source}</span>` : '',
    f.size_kb  ? `<span>${f.size_kb} KB</span>` : '',
    f.modified ? `<span>${f.modified}</span>` : '',
    f.cpr_count ? `<span style="color:var(--danger)">${f.cpr_count} CPR</span>` : '',
    f.url ? `<button class="preview-open-btn" onclick="window.open('${f.url}','_blank')">${t("m365_preview_open","Open in M365 ↗")}</button>` : '',
  ].filter(Boolean).join('');

  _previewItemId = f.id;
  loadDisposition(f.id);  // load disposition for this item (#6)

  try {
    const r = await fetch('/api/preview/' + encodeURIComponent(f.id)
      + '?source_type=' + encodeURIComponent(f.source_type || '')
      + '&account_id='  + encodeURIComponent(f.account_id  || ''));
    const d = await r.json();

    if (_previewItemId !== f.id) return; // stale — user clicked another card

    if (d.error) {
      loading.textContent = d.error;
      return;
    }

    if (d.type === 'local') {
      loading.style.display = 'none';
      frame.style.display = 'block';
      frame.srcdoc = `<html><body style="font-family:sans-serif;color:#ccc;background:#1e1e1e;padding:24px;display:flex;flex-direction:column;align-items:center;justify-content:center;height:80vh;gap:12px">
        <div style="font-size:40px">📁</div>
        <div style="font-size:14px;font-weight:600">${d.name || f.name}</div>
        <div style="font-size:11px;color:#888">${t('m365_preview_local_file','Local file — no cloud preview available')}</div>
        <div style="font-size:10px;color:#666;word-break:break-all;max-width:400px;text-align:center">${d.path || ''}</div>
      </body></html>`;
      return;
    }

    if (d.type === 'html' && d.html) {
      loading.style.display = 'none';
      frame.style.display = 'block';
      const theme = document.body.dataset.theme === 'dark' ? '#1e1e1e' : '#ffffff';
      const textColor = document.body.dataset.theme === 'dark' ? '#e0e0e0' : '#111111';
      const mutedColor = document.body.dataset.theme === 'dark' ? '#888' : '#666';
      frame.srcdoc = `<html><body style="margin:0;background:${theme};color:${textColor};font-family:sans-serif;--muted:${mutedColor};--text:${textColor};--mono:monospace">${d.html}</body></html>`;
      return;
    }

    if (d.type === 'info' && d.html) {
      loading.style.display = 'none';
      frame.style.display = 'block';
      const theme = document.body.dataset.theme === 'dark' ? '#1e1e1e' : '#ffffff';
      frame.srcdoc = `<html><body style="margin:0;padding:20px;background:${theme};color:#888;font-family:sans-serif">${d.html}</body></html>`;
      return;
    }

    if (d.type === 'iframe' && d.url) {
      frame.src = d.url;
      frame.onload = () => {
        loading.style.display = 'none';
        frame.style.display = 'block';
      };
    } else if (d.type === 'html') {
      const blob = new Blob([d.html], {type: 'text/html'});
      frame.src = URL.createObjectURL(blob);
      frame.onload = () => {
        loading.style.display = 'none';
        frame.style.display = 'block';
      };
    } else {
      loading.textContent = t('m365_preview_open','Open in M365') + ' — No preview available.';
    }
  } catch(e) {
    loading.textContent = 'Preview failed: ' + e.message;
  }
}

// ── Retention policy (#1) ────────────────────────────────────────────────────

function toggleRetentionPanel() {
  const enabled = document.getElementById('optRetention').checked;
  document.getElementById('retentionPanel').style.display = enabled ? 'block' : 'none';
  if (enabled) updateRetentionCutoffHint();
}

function updateRetentionCutoffHint() {
  const years  = parseInt(document.getElementById('optRetentionYears')?.value) || 5;
  const fyEnd  = document.getElementById('optFiscalYearEnd')?.value || '';
  const hint   = document.getElementById('retentionCutoffHint');
  if (!hint) return;
  // Compute cutoff client-side for instant feedback
  const today = new Date();
  let cutoff;
  if (fyEnd) {
    const [mm, dd] = fyEnd.split('-').map(Number);
    let fyEndDate = new Date(today.getFullYear(), mm - 1, dd);
    if (fyEndDate >= today) fyEndDate = new Date(today.getFullYear() - 1, mm - 1, dd);
    cutoff = new Date(fyEndDate); cutoff.setFullYear(cutoff.getFullYear() - years);
  } else {
    cutoff = new Date(today); cutoff.setFullYear(cutoff.getFullYear() - years);
  }
  const iso = cutoff.toISOString().split('T')[0];
  const mode = fyEnd ? t('m365_ret_mode_fiscal', 'fiscal year') : t('m365_ret_mode_rolling', 'rolling');
  hint.textContent = t('m365_ret_cutoff_hint', 'Items modified before') + ' ' + iso + ' (' + mode + ') ' + t('m365_ret_cutoff_flagged', 'will be flagged');
}

// Mark cards as overdue after scan completes or on load
async function markOverdueCards() {
  const retentionEnabled = document.getElementById('optRetention')?.checked;
  if (!retentionEnabled) return;
  const years  = parseInt(document.getElementById('optRetentionYears')?.value) || 5;
  const fyEnd  = document.getElementById('optFiscalYearEnd')?.value || '';
  try {
    const params = new URLSearchParams({years});
    if (fyEnd) params.set('fiscal_year_end', fyEnd);
    const r = await fetch('/api/db/overdue?' + params);
    const d = await r.json();
    if (!d.items) return;
    const overdueIds = new Set(d.items.map(i => i.id));
    // Mark S.flaggedData entries
    S.flaggedData.forEach(f => { f.overdue = overdueIds.has(f.id); });
    // Re-render to show badges
    renderGrid(S.filteredData.length ? S.filteredData : S.flaggedData);
    if (d.count > 0) {
      log('🗓 ' + d.count + ' ' + t('m365_overdue_found', 'overdue item(s) found') + ' (cutoff: ' + d.cutoff_date + ')', 'warn');
    }
  } catch(e) { /* DB not available -- skip */ }
}

// Pre-filter bulk delete to overdue items
async function preFilterOverdue() {
  const years  = parseInt(document.getElementById('optRetentionYears')?.value) || 5;
  const fyEnd  = document.getElementById('optFiscalYearEnd')?.value || '';
  try {
    const params = new URLSearchParams({years});
    if (fyEnd) params.set('fiscal_year_end', fyEnd);
    const r = await fetch('/api/db/overdue?' + params);
    const d = await r.json();
    if (d.cutoff_date) {
      document.getElementById('bdOlderThan').value = d.cutoff_date;
      updateBdPreview();
    }
  } catch(e) {
    // Fallback: compute client-side
    const today = new Date();
    const cutoff = new Date(today); cutoff.setFullYear(cutoff.getFullYear() - years);
    document.getElementById('bdOlderThan').value = cutoff.toISOString().split('T')[0];
    updateBdPreview();
  }
}

function clearBdFilters() {
  document.getElementById('bdSource').value = '';
  document.getElementById('bdMinCpr').value = '1';
  document.getElementById('bdOlderThan').value = '';
  updateBdPreview();
}

// ── Data subject lookup (#4) ──────────────────────────────────────────────

let _dsubItems = [];  // items from last lookup, for bulk delete

function openSubjectModal() {
  document.getElementById("dsubBackdrop").classList.add("open");
  document.getElementById("dsubInput").value = "";
  document.getElementById("dsubStatus").textContent = "";
  document.getElementById("dsubResults").innerHTML = "";
  document.getElementById("dsubDeleteBtn").style.display = "none";
  _dsubItems = [];
  setTimeout(() => document.getElementById("dsubInput").focus(), 80);
}

function closeDsubModal() {
  document.getElementById("dsubBackdrop").classList.remove("open");
}

async function runSubjectLookup() {
  const cpr = document.getElementById("dsubInput").value.trim();
  if (!cpr) return;
  const statusEl  = document.getElementById("dsubStatus");
  const resultsEl = document.getElementById("dsubResults");
  const deleteBtn = document.getElementById("dsubDeleteBtn");
  statusEl.textContent = t("m365_subject_searching", "Searching…");
  resultsEl.innerHTML  = "";
  deleteBtn.style.display = "none";
  _dsubItems = [];
  try {
    const r = await fetch("/api/db/subject", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({cpr})
    });
    const d = await r.json();
    if (d.error) { statusEl.textContent = d.error; return; }
    if (!d.count) {
      statusEl.textContent = t("m365_subject_not_found", "No flagged items found for this CPR number.");
      return;
    }
    statusEl.textContent = d.count + " " + t("m365_subject_found", "item(s) found");
    _dsubItems = d.items;
    resultsEl.innerHTML = d.items.map(item => `
      <div class="dsub-result-row">
        <div class="dsub-result-name" title="${item.name}">${item.name}</div>
        <div class="dsub-result-meta">${item.source_type || ""}</div>
        <div class="dsub-result-meta">${item.modified || ""}</div>
        <div class="dsub-result-meta" style="color:var(--danger)">${item.cpr_count} CPR</div>
      </div>
    `).join("");
    if (d.count > 0) deleteBtn.style.display = "block";
  } catch(e) {
    statusEl.textContent = "Error: " + e.message;
  }
}

async function deleteSubjectItems() {
  if (!_dsubItems.length) return;
  const count = _dsubItems.length;
  if (!confirm(`${count} ${t("m365_subject_delete_confirm", "item(s) will be permanently deleted. Continue?")}`))
    return;
  const ids = _dsubItems.map(i => i.id);
  const statusEl = document.getElementById("dsubStatus");
  statusEl.textContent = t("m365_bulk_deleting", "Deleting…");
  try {
    const r = await fetch("/api/delete_bulk", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ids, reason: "data-subject-request"})
    });
    const d = await r.json();
    statusEl.textContent = `${d.deleted || 0} ${t("m365_bulk_deleted","deleted")}`;
    document.getElementById("dsubDeleteBtn").style.display = "none";
    document.getElementById("dsubResults").innerHTML = "";
    _dsubItems = [];
    // Refresh grid
    S.flaggedData = S.flaggedData.filter(f => !ids.includes(f.id));
    S.filteredData = S.filteredData.filter(f => !ids.includes(f.id));
    renderGrid();
    updateStats();
  } catch(e) {
    statusEl.textContent = "Delete failed: " + e.message;
  }
}

// ── Disposition tagging (#6) ───────────────────────────────────────────────

let _dispositionItemId = null;

async function loadDisposition(itemId) {
  _dispositionItemId = itemId;
  const row = document.getElementById("dispositionRow");
  const sel = document.getElementById("dispositionSelect");
  const saved = document.getElementById("dispositionSaved");
  row.style.display = "flex";
  saved.textContent = "";
  try {
    const r = await fetch("/api/db/disposition/" + encodeURIComponent(itemId));
    const d = await r.json();
    if (d.error) return;  // DB not available -- hide row
    const status = d.status || "unreviewed";
    sel.value = status;
    // Cache on S.flaggedData item so the filter bar works without extra API calls
    const item = S.flaggedData.find(f => f.id === itemId);
    if (item) item.disposition = status;
  } catch(e) {
    row.style.display = "none";
  }
}

async function saveDisposition() {
  if (!_dispositionItemId) return;
  const status  = document.getElementById("dispositionSelect").value;
  const savedEl = document.getElementById("dispositionSaved");
  savedEl.textContent = "";
  try {
    await fetch("/api/db/disposition", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({item_id: _dispositionItemId, status})
    });
    savedEl.textContent = t("m365_disp_saved", "✓ Saved");
    setTimeout(() => { savedEl.textContent = ""; }, 2000);
    // Update cached value on the S.flaggedData item
    const item = S.flaggedData.find(f => f.id === _dispositionItemId);
    if (item) item.disposition = status;
    // Refresh card badge if a disposition filter is active
    const dispFilter = document.getElementById("filterDisposition")?.value;
    if (dispFilter) applyFilters();
  } catch(e) {
    savedEl.textContent = "Error";
  }
}

function closePreview() {
  const panel = document.getElementById('previewPanel');
  panel.style.width = '';   // clear inline width so CSS .hidden { width:0 } takes effect
  panel.classList.add('hidden');
  document.getElementById('previewFrame').src = '';
  document.querySelectorAll('.card.selected').forEach(c => c.classList.remove('selected'));
  _previewItemId = null;
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeAbout(); closeModeInfo(); closeBulkDelete(); closePreview(); closeDsubModal(); closeSmtpModal(); closeProfileMgmt(); closeImportDBModal(); closeFileSourcesModal(); closeSourcesMgmt(); closeSettings(); closePinPrompt(); }
});

// ── Delete ────────────────────────────────────────────────────────────────────

async function deleteItem(f, cardEl) {
  if (!confirm(t('m365_delete_confirm', 'Delete') + ' "' + f.name + '"?\n\n' + t('m365_delete_warning', 'This cannot be undone.'))) return;
  try {
    const r = await fetch('/api/delete_item', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: f.id, source_type: f.source_type, account_id: f.account_id, drive_id: f.drive_id})
    });
    const d = await r.json();
    if (d.ok) {
      S.flaggedData   = S.flaggedData.filter(x => x.id !== f.id);
      S.filteredData  = S.filteredData.filter(x => x.id !== f.id);
      if (cardEl) cardEl.remove();
      updateStats();
      log(t('m365_log_deleted', 'Deleted:') + ' ' + f.name, 'ok');
      if (_previewItemId === f.id) closePreview();
    } else {
      log(t('m365_log_delete_failed', 'Delete failed:') + ' ' + (d.error || '?'), 'err');
    }
  } catch(e) {
    log(t('m365_log_delete_failed', 'Delete failed:') + ' ' + e.message, 'err');
  }
}

// ── Bulk delete modal ─────────────────────────────────────────────────────────

function openBulkDelete() {
  applyI18n();
  updateBdPreview();
  document.getElementById('bulkDeleteBackdrop').classList.add('open');
}
function closeBulkDelete() {
  document.getElementById('bulkDeleteBackdrop').classList.remove('open');
  document.getElementById('bdProgress').textContent = '';
}

function _bdFilters() {
  return {
    source_type:     document.getElementById('bdSource').value,
    min_cpr:         parseInt(document.getElementById('bdMinCpr').value) || 1,
    older_than_date: document.getElementById('bdOlderThan').value,
  };
}

function _bdMatches() {
  const f = _bdFilters();
  return S.flaggedData.filter(x => {
    if (f.source_type && x.source_type !== f.source_type) return false;
    if (x.cpr_count < f.min_cpr) return false;
    if (f.older_than_date && x.modified > f.older_than_date) return false;
    return true;
  });
}

function updateBdPreview() {
  const matches = _bdMatches();
  const prev = document.getElementById('bdPreview');
  if (!prev) return;
  if (matches.length === 0) {
    prev.textContent = t('m365_bulk_no_match', 'No items match these criteria.');
    document.getElementById('bdConfirmBtn').disabled = true;
  } else {
    prev.innerHTML = `<strong style="color:var(--danger)">${matches.length}</strong> ${t('m365_bulk_match_count', 'item(s) will be deleted')}`;
    document.getElementById('bdConfirmBtn').disabled = false;
  }
}


// ── Auto-connect SSE on page load (#21) ──────────────────────────────────────
// ── SSE connection management ────────────────────────────────────────────────
// The browser keeps an SSE connection to /api/scan/stream for live scan events.
// Problem: idle SSE connections silently die (Flask/Werkzeug threading, proxies,
// OS TCP keepalive). EventSource auto-reconnects, but during the reconnect
// window a scheduled scan's events are lost.
//
// Solution: a polling watchdog checks /api/scan/status every few seconds.
// When it detects a running scan (manual or scheduled), it ensures the SSE
// connection is alive and the progress UI is visible.

let _sseWatchdogTimer = null;
let _initialStatusChecked = false;
const _SSE_POLL_INTERVAL = 4000;  // ms between status polls

function _ensureSSE() {
  // Open SSE if not already open or if the existing connection is dead
  if (S.es && S.es.readyState !== EventSource.CLOSED) return;
  if (S.es) { try { S.es.close(); } catch(_){} }
  console.log('[SSE] Opening connection to /api/scan/stream');
  S.es = new EventSource('/api/scan/stream');
  S.es.onopen = function() { console.log('[SSE] Connection established'); };
  S.es.onerror = function(e) {
    console.warn('[SSE] Connection error (will auto-reconnect)', e);
  };
  _attachScanListeners(S.es);
  _attachSchedulerListeners(S.es);
}

function _sseWatchdog() {
  fetch('/api/scan/status').then(function(r) { return r.json(); }).then(function(status) {
    if (status.running) {
      // A scan is in progress — make sure SSE is connected and progress UI is visible
      _ensureSSE();
      if (!S._m365ScanRunning && !S._googleScanRunning && !S._fileScanRunning) {
        document.getElementById('scanBtn').disabled = true;
        document.getElementById('stopBtn').style.display = 'inline-block';
        // /api/scan/status checks the M365 lock — if running=true it's an M365 scan
        S._m365ScanRunning = true; _renderProgressSegments();
        document.getElementById('progressFile').textContent = t('m365_sse_reconnecting', 'Reconnecting to running scan…');
        log(t('m365_sse_reconnecting', 'Reconnecting to running scan…'));
      }
    }
    if (!_initialStatusChecked) {
      _initialStatusChecked = true;
      if (!status.running) loadLastScanSummary();
    }
    // When no scan is running, we still keep polling — the SSE connection
    // may have died and we need to detect the *next* scheduled scan.
    // The SSE itself is only opened/reopened when a scan is detected.
  }).catch(function(err) {
    // Status endpoint unavailable — server might be restarting
    console.warn('[SSE] status poll failed:', err);
  });
}

function _autoConnectSSEIfRunning() {
  // Open initial SSE connection
  _ensureSSE();
  // Check if a scan is already running (e.g. scheduled scan started before page load)
  _sseWatchdog();
  // Start polling watchdog — catches scheduled scans that start later
  if (!_sseWatchdogTimer) {
    _sseWatchdogTimer = setInterval(_sseWatchdog, _SSE_POLL_INTERVAL);
  }
}

// ── Viewer mode result loader ─────────────────────────────────────────────────
async function _loadViewerResults() {
  try {
    const r = await fetch('/api/db/flagged');
    const items = await r.json();
    if (!Array.isArray(items) || items.length === 0) {
      // Show last-scan summary card (stats only, no items yet)
      const panel = document.getElementById('lastScanSummary');
      const empty = document.getElementById('emptyState');
      const r2 = await fetch('/api/db/stats');
      const stats = await r2.json();
      if (stats.scan_id && panel && empty) {
        const dateStr = stats.finished_at
          ? new Date(stats.finished_at * 1000).toLocaleDateString('da-DK', {day:'numeric', month:'short', year:'numeric'})
          : '—';
        const srcLabels = {email:'Outlook',onedrive:'OneDrive',sharepoint:'SharePoint',teams:'Teams',
                          gmail:'Gmail',gdrive:'Drive',local:'Lokale filer',smb:'SMB'};
        const srcStr = Object.keys(stats.by_source || {}).map(s => srcLabels[s] || s).join(' · ') || '—';
        panel.innerHTML =
          '<div class="last-scan-card">' +
            '<h3>' + t('last_scan_title', 'Seneste scanning') + '</h3>' +
            '<div class="last-scan-stats">' +
              '<div class="last-scan-stat"><span class="val">' + (stats.flagged_count || 0) + '</span><span class="lbl">' + t('last_scan_hits', 'Fund') + '</span></div>' +
              '<div class="last-scan-stat"><span class="val">' + (stats.unique_subjects || 0) + '</span><span class="lbl">' + t('last_scan_subjects', 'Unikke CPR') + '</span></div>' +
              '<div class="last-scan-stat"><span class="val">' + (stats.total_scanned || 0) + '</span><span class="lbl">' + t('last_scan_scanned', 'Scannet') + '</span></div>' +
            '</div>' +
            '<div style="margin-top:12px;font-size:11px;color:var(--muted)">' + dateStr + ' &nbsp;·&nbsp; ' + srcStr + '</div>' +
          '</div>';
        empty.style.display = 'none';
        panel.style.display = 'flex';
      }
      return;
    }
    S.flaggedData = items;
    S.filteredData = [];
    const grid = document.getElementById('grid');
    const emptyState = document.getElementById('emptyState');
    const lastScan   = document.getElementById('lastScanSummary');
    if (emptyState) emptyState.style.display = 'none';
    if (lastScan)   lastScan.style.display   = 'none';
    if (grid)       grid.style.display       = 'grid';
    renderGrid(items);
    try { loadTrend(); } catch(_) {}
  } catch(e) {
    console.error('[viewer] failed to load results:', e);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  _restoreLog();
  _initLogResize();
  _initPreviewResize();
  _initSourcesResize();
  restoreSectionStates();
  if (window.VIEWER_MODE) {
    _loadViewerResults();
    return;
  }
  _loadFileSources();
  _autoConnectSSEIfRunning();  // populates S._fileSources then calls renderSourcesPanel()
  smGoogleRefreshStatus();    // sets _googleConnected and re-renders sources panel
  // Restore all source toggle states
  fetch('/api/src_toggles').then(function(r){ return r.json(); }).then(function(d) {
    _restoreM365SourceToggles(d);
    var gm = document.getElementById('smGoogleSrcGmail');
    var gd = document.getElementById('smGoogleSrcDrive');
    if (gm && d.src_gmail !== undefined) { gm.checked = !!d.src_gmail; }
    if (gd && d.src_drive !== undefined) { gd.checked = !!d.src_drive; }
  }).catch(function(){});

  // ── macOS pywebview: push content below traffic-light buttons ─────────────
  // In frameless pywebview windows on macOS the content starts at y=0, behind
  // the system close/minimise/maximise buttons (~28px). Apply a padding only
  // when running inside pywebview AND on macOS (navigator.platform contains Mac).
  if (window.pywebview && navigator.platform.toLowerCase().includes('mac')) {
    document.body.style.paddingTop = '30px';
  }

  ['bdSource','bdMinCpr','bdOlderThan'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateBdPreview);
  });
  ['optRetentionYears','optFiscalYearEnd'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', updateRetentionCutoffHint);
  });
  window.addEventListener('resize', () => {
    const tp = document.getElementById('trendPanel');
    if (tp && tp.style.display !== 'none') loadTrend();
  });
  const deltaCb = document.getElementById('optDelta');
  if (deltaCb) {
    deltaCb.addEventListener('change', () => {
      if (deltaCb.checked) checkDeltaStatus();
      else document.getElementById('deltaStatusRow').style.display = 'none';
    });
  }
});

async function executeBulkDelete() {
  const matches = _bdMatches();
  if (!matches.length) return;
  const confirmMsg = matches.length + ' ' + t('m365_bulk_confirm_q', 'item(s) will be permanently deleted. Continue?');
  if (!confirm(confirmMsg)) return;

  const btn = document.getElementById('bdConfirmBtn');
  const prog = document.getElementById('bdProgress');
  btn.disabled = true;
  prog.textContent = t('m365_bulk_deleting', 'Deleting…');

  try {
    const r = await fetch('/api/delete_bulk', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ ids: matches.map(x => x.id), filters: {} })
    });
    const d = await r.json();
    if (d.ok) {
      const deletedSet = new Set(matches.map(x => x.id));
      S.flaggedData  = S.flaggedData.filter(x => !deletedSet.has(x.id));
      S.filteredData = S.filteredData.filter(x => !deletedSet.has(x.id));
      renderGrid(S.filteredData.length ? S.filteredData : S.flaggedData);
      updateStats();
      prog.innerHTML = `<span style="color:var(--ok,#4c4)">✓ ${d.deleted} ${t('m365_bulk_deleted', 'deleted')}</span>` +
        (d.failed ? ` · <span style="color:var(--danger)">${d.failed} ${t('m365_bulk_failed', 'failed')}</span>` : '');
      if (d.errors && d.errors.length) {
        d.errors.forEach(err => log('✗ ' + err.name + ': ' + err.error, 'err'));
      }
      log(t('m365_log_bulk_done', 'Bulk delete:') + ' ' + d.deleted + ' deleted, ' + d.failed + ' failed', d.failed ? 'err' : 'ok');
      if (d.failed === 0) setTimeout(closeBulkDelete, 1800);
    } else {
      prog.textContent = d.error || 'Error';
    }
  } catch(e) {
    prog.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

function applyFilters() {
  const search  = document.getElementById('filterSearch').value.trim().toLowerCase();
  const srcVal  = document.getElementById('filterSource').value;
  const dispVal     = document.getElementById('filterDisposition')?.value || '';
  const transferVal = document.getElementById('filterTransfer')?.value || '';
  const specialVal  = document.getElementById('filterSpecial')?.value || '';
  const roleVal     = document.getElementById('filterRole')?.value || '';
  S.filteredData = S.flaggedData.filter(f => {
    if (search && !f.name.toLowerCase().includes(search)) return false;
    if (srcVal       && f.source_type !== srcVal) return false;
    if (dispVal      && (f.disposition || 'unreviewed') !== dispVal) return false;
    if (transferVal  && (f.transfer_risk || '') !== transferVal) return false;
    if (specialVal === '1' && !(f.special_category && f.special_category.length)) return false;
    if (specialVal === 'photo' && !(f.face_count > 0)) return false;
    if (roleVal === 'student' && f.user_role !== 'student') return false;
    if (roleVal === 'staff'   && f.user_role === 'student') return false;
    return true;
  });
  const grid = document.getElementById('grid');
  if (S.filteredData.length === 0 && S.flaggedData.length > 0) {
    grid.style.display = 'none';
    document.getElementById('emptyState').innerHTML =
      `<div class="empty-icon">🔍</div><div class="empty-text">${t('m365_no_matches','No matches')}</div>`;
    document.getElementById('emptyState').style.display = 'flex';
  } else {
    document.getElementById('emptyState').style.display = 'none';
    grid.style.display = S.isListView ? 'block' : 'grid';
    renderGrid(S.filteredData);
  }
}

async function exportExcel() {
  if (!S.flaggedData || S.flaggedData.length === 0) {
    log(t('m365_export_no_data', 'No results to export.'));
    return;
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_excel) {
    try {
      const r = await window.pywebview.api.save_excel();
      if (r && r.ok) { log('Excel exported: ' + r.path); }
      else if (r && r.error && r.error !== 'cancelled') { alert('Export failed: ' + r.error); }
    } catch(e) { alert('Export failed: ' + e.message); }
    return;
  }
  const btn = document.getElementById('exportBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    // In pywebview (macOS/Windows app), blob URL downloads don't work —
    // use the native save dialog exposed via the JS API instead.
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_excel) {
      const result = await window.pywebview.api.save_excel();
      if (result && result.ok) {
        log(t('m365_export_done', 'Excel export ready.'), 'ok');
      } else {
        if (result && result.error && result.error !== 'cancelled') {
          log('Export error: ' + result.error, 'err');
        }
      }
      return;
    }
    // Browser / localhost fallback: fetch as blob and trigger download
    const _roleParam = document.getElementById('filterRole')?.value || '';
    const r = await fetch('/api/export_excel' + (_roleParam ? '?role=' + encodeURIComponent(_roleParam) : ''));
    if (!r.ok) {
      const err = await r.json().catch(() => ({error: 'Export failed'}));
      log('Export error: ' + (err.error || r.status), 'err');
      return;
    }
    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    const disp = r.headers.get('Content-Disposition') || '';
    const match = disp.match(/filename=([^\s;]+)/);
    a.href     = url;
    a.download = match ? match[1] : 'export.xlsx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    log(t('m365_export_done', 'Excel export ready.'), 'ok');
  } catch(e) {
    log('Export error: ' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '⬇ Excel'; }
  }
}

async function exportArticle30() {
  if (!S.flaggedData || S.flaggedData.length === 0) {
    log(t('m365_export_no_data', 'No results to export.'));
    return;
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_article30) {
    try {
      const r = await window.pywebview.api.save_article30();
      if (r && r.ok) { log('Article 30 exported: ' + r.path); }
      else if (r && r.error && r.error !== 'cancelled') { alert('Export failed: ' + r.error); }
    } catch(e) { alert('Export failed: ' + e.message); }
    return;
  }
  const btn = document.getElementById('exportA30Btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const _roleParam30 = document.getElementById('filterRole')?.value || '';
    const r = await fetch('/api/export_article30' + (_roleParam30 ? '?role=' + encodeURIComponent(_roleParam30) : ''));
    if (!r.ok) {
      const err = await r.json().catch(() => ({error: 'Export failed'}));
      log('Article 30 export error: ' + (err.error || r.status), 'err');
      return;
    }
    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    const disp = r.headers.get('Content-Disposition') || '';
    const match = disp.match(/filename=([^\s;]+)/);
    a.href     = url;
    a.download = match ? match[1] : 'article30.docx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    log(t('m365_article30_done', 'Article 30 report ready.'), 'ok');
  } catch(e) {
    log('Article 30 export error: ' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '📋 Art.30'; }
  }
}

function clearFilters() {
  document.getElementById('filterSearch').value = '';
  document.getElementById('filterSource').value = '';
  const fd = document.getElementById('filterDisposition');
  if (fd) fd.value = '';
  const ft = document.getElementById('filterTransfer');
  if (ft) ft.value = '';
  const fs = document.getElementById('filterSpecial');
  if (fs) fs.value = '';
  const fr = document.getElementById('filterRole');
  if (fr) fr.value = '';
  applyFilters();
}

function toggleView() {
  S.isListView = !S.isListView;
  document.getElementById('listViewBtn').textContent = S.isListView ? t('m365_btn_grid_view', '⊞ Grid') : t('m365_btn_list_view', '☰ List');
  document.getElementById('grid').className = S.isListView ? '' : 'grid';
  document.getElementById('grid').style.display = S.isListView ? 'block' : 'grid';
  renderGrid(S.filteredData.length ? S.filteredData : S.flaggedData);
}

// ── Hint tooltips ─────────────────────────────────────────────────────────────

function toggleHint(icon) {
  const isActive = icon.classList.contains('active');
  // Close all open hints first
  document.querySelectorAll('.hint-icon.active').forEach(function(el) {
    el.classList.remove('active');
    const b = el.nextElementSibling;
    if (b && b.classList.contains('hint-bubble')) b.style.display = '';
  });
  if (!isActive) {
    icon.classList.add('active');
    // Position bubble using fixed coords so it escapes sidebar stacking context
    const bubble = icon.nextElementSibling;
    if (bubble && bubble.classList.contains('hint-bubble')) {
      bubble.style.display = 'block';
      const rect = icon.getBoundingClientRect();
      bubble.style.top  = Math.round(rect.top + rect.height / 2 - bubble.offsetHeight / 2) + 'px';
      bubble.style.left = Math.round(rect.right + 8) + 'px';
    }
    // Close when clicking anywhere else
    setTimeout(function() {
      document.addEventListener('click', function closeHint(e) {
        if (!e.target.classList.contains('hint-icon')) {
          document.querySelectorAll('.hint-icon.active').forEach(function(el) {
            el.classList.remove('active');
          });
          document.querySelectorAll('.hint-bubble').forEach(function(el) {
            el.style.display = '';
          });
          document.removeEventListener('click', closeHint);
        }
      });
    }, 0);
  }
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.appendCard = appendCard;
window.renderGrid = renderGrid;
window.openPreview = openPreview;
window.toggleRetentionPanel = toggleRetentionPanel;
window.updateRetentionCutoffHint = updateRetentionCutoffHint;
window.markOverdueCards = markOverdueCards;
window.preFilterOverdue = preFilterOverdue;
window.clearBdFilters = clearBdFilters;
window.openSubjectModal = openSubjectModal;
window.closeDsubModal = closeDsubModal;
window.runSubjectLookup = runSubjectLookup;
window.deleteSubjectItems = deleteSubjectItems;
window.loadDisposition = loadDisposition;
window.saveDisposition = saveDisposition;
window.closePreview = closePreview;
window.deleteItem = deleteItem;
window.openBulkDelete = openBulkDelete;
window.closeBulkDelete = closeBulkDelete;
window._bdFilters = _bdFilters;
window._bdMatches = _bdMatches;
window.updateBdPreview = updateBdPreview;
window._ensureSSE = _ensureSSE;
window._sseWatchdog = _sseWatchdog;
window._autoConnectSSEIfRunning = _autoConnectSSEIfRunning;
window._loadViewerResults = _loadViewerResults;
window.executeBulkDelete = executeBulkDelete;
window.applyFilters = applyFilters;
window.exportExcel = exportExcel;
window.exportArticle30 = exportArticle30;
window.clearFilters = clearFilters;
window.toggleView = toggleView;
window.toggleHint = toggleHint;
window.SOURCE_BADGES = SOURCE_BADGES;
window._previewItemId = _previewItemId;
window._dsubItems = _dsubItems;
window._dispositionItemId = _dispositionItemId;
window._sseWatchdogTimer = _sseWatchdogTimer;
window._initialStatusChecked = _initialStatusChecked;
window._SSE_POLL_INTERVAL = _SSE_POLL_INTERVAL;
