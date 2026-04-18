// ── Scan history browser ──────────────────────────────────────────────────────
// Lets the user load and browse results from any past scan session without
// running a new scan.  Sessions are groups of concurrent M365 + Google + File
// scans (same 300-second window used by get_session_items on the server).
import { S } from './state.js';

const _SRC_LABELS = {
  email:      'Outlook',
  onedrive:   'OneDrive',
  sharepoint: 'SharePoint',
  teams:      'Teams',
  gmail:      'Gmail',
  gdrive:     'Google Drive',
  local:      'Lokal',
  smb:        'SMB',
};

let _sessions        = null;  // cached list; null = stale
let _latestRefScanId = null;  // ref_scan_id of the newest session

// ── Session cache ─────────────────────────────────────────────────────────────

async function _fetchSessions() {
  try {
    const r = await fetch('/api/db/sessions');
    _sessions = await r.json();
  } catch(e) {
    _sessions = [];
  }
  _latestRefScanId = _sessions.length ? _sessions[0].ref_scan_id : null;
  return _sessions;
}

function invalidateHistoryCache() {
  _sessions        = null;
  _latestRefScanId = null;
}

// ── Load a session into the results grid ──────────────────────────────────────

async function loadHistorySession(refScanId) {
  // refScanId: null → latest session, positive int → specific session
  let resolvedRef = refScanId;
  if (resolvedRef === null) {
    const sessions = _sessions !== null ? _sessions : await _fetchSessions();
    if (!sessions.length) {
      // No scans in DB — nothing to show
      window.loadLastScanSummary?.();
      return;
    }
    resolvedRef = sessions[0].ref_scan_id;
  }

  try {
    const r     = await fetch('/api/db/flagged?ref=' + resolvedRef);
    const items = await r.json();
    closeHistoryPicker();

    if (!Array.isArray(items) || items.length === 0) {
      S._historyRefScanId = null;
      _setHistoryBanner(false);
      window.loadLastScanSummary?.();
      return;
    }

    S._historyRefScanId = resolvedRef;
    S.flaggedData  = items;
    S.filteredData = [];

    const grid      = document.getElementById('grid');
    const emptyState = document.getElementById('emptyState');
    const lastScan  = document.getElementById('lastScanSummary');
    if (emptyState) emptyState.style.display = 'none';
    if (lastScan)   lastScan.style.display   = 'none';
    if (grid) { grid.innerHTML = ''; grid.style.display = 'grid'; }

    window.renderGrid(items);
    try { window.markOverdueCards(); } catch(_) {}
    try { window.loadTrend();        } catch(_) {}
    _setHistoryBanner(true, resolvedRef);
  } catch(e) {
    console.error('[history] failed to load session:', e);
  }
}

// ── Banner ────────────────────────────────────────────────────────────────────

function _setHistoryBanner(visible, resolvedRef) {
  const banner    = document.getElementById('historyBanner');
  const bannerTxt = document.getElementById('historyBannerText');
  const latestBtn = document.getElementById('historyLatestBtn');
  if (!banner) return;
  if (!visible) { banner.style.display = 'none'; return; }

  const sess = (_sessions || []).find(s => s.ref_scan_id === resolvedRef);
  let label = '';
  if (sess) {
    const date   = new Date(sess.started_at * 1000).toLocaleDateString(undefined,
      {day: 'numeric', month: 'short', year: 'numeric'});
    const time   = new Date(sess.started_at * 1000).toLocaleTimeString(undefined,
      {hour: '2-digit', minute: '2-digit'});
    const srcStr = (sess.sources || []).map(s => _SRC_LABELS[s] || s).join(' · ');
    label = date + ' ' + time
      + (srcStr ? ' · ' + srcStr : '')
      + ' · ' + sess.flagged_count + ' ' + t('history_items', 'items');
  } else {
    label = S.flaggedData.length + ' ' + t('history_items', 'items');
  }

  if (bannerTxt) bannerTxt.textContent = label;
  if (latestBtn) latestBtn.style.display = (resolvedRef !== _latestRefScanId) ? '' : 'none';
  banner.style.display = 'flex';
}

function exitHistoryMode() {
  S._historyRefScanId = null;
  const banner = document.getElementById('historyBanner');
  if (banner) banner.style.display = 'none';
  closeHistoryPicker();
}

// ── Session picker dropdown ───────────────────────────────────────────────────

async function openHistoryPicker() {
  const drop = document.getElementById('historyDropdown');
  if (!drop) return;
  // Toggle
  if (drop.style.display !== 'none') { drop.style.display = 'none'; return; }

  drop.innerHTML = '<div style="padding:10px 12px;font-size:12px;color:var(--muted)">'
    + t('lbl_loading', 'Loading\u2026') + '</div>';
  drop.style.display = '';

  const sessions = _sessions !== null ? _sessions : await _fetchSessions();

  if (!sessions.length) {
    drop.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--muted);text-align:center">'
      + t('history_picker_empty', 'No past scans') + '</div>';
    return;
  }

  drop.innerHTML = '';
  sessions.forEach((sess, i) => {
    const date    = new Date(sess.started_at * 1000).toLocaleDateString(undefined,
      {day: 'numeric', month: 'short', year: 'numeric'});
    const time    = new Date(sess.started_at * 1000).toLocaleTimeString(undefined,
      {hour: '2-digit', minute: '2-digit'});
    const srcStr  = (sess.sources || []).map(s => _SRC_LABELS[s] || s).join(' · ');
    const isActive = sess.ref_scan_id === S._historyRefScanId;

    const row = document.createElement('div');
    row.style.cssText = 'padding:8px 12px;cursor:pointer'
      + (i < sessions.length - 1 ? ';border-bottom:1px solid var(--border)' : '')
      + (isActive ? ';background:var(--bg)' : '');
    row.innerHTML =
      '<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">' +
        '<span style="font-size:12px;font-weight:500;color:var(--text)">' + date + '</span>' +
        '<span style="font-size:10px;color:var(--muted)">' + time + '</span>' +
        (sess.delta
          ? '<span style="font-size:9px;padding:1px 5px;border-radius:10px;background:var(--muted);color:#fff;font-weight:600">'
            + t('history_delta_badge', 'Delta') + '</span>'
          : '') +
        (i === 0
          ? '<span style="font-size:9px;padding:1px 5px;border-radius:10px;background:var(--accent);color:#fff;font-weight:600">'
            + t('history_latest_badge', 'Latest') + '</span>'
          : '') +
      '</div>' +
      '<div style="font-size:10px;color:var(--muted)">' +
        srcStr + ' &nbsp;\u00b7&nbsp; ' + sess.flagged_count + ' ' + t('history_items', 'items') +
      '</div>';

    row.addEventListener('mouseenter', () => { if (!isActive) row.style.background = 'var(--surface)'; });
    row.addEventListener('mouseleave', () => { row.style.background = isActive ? 'var(--bg)' : ''; });
    row.addEventListener('click', () => loadHistorySession(sess.ref_scan_id));
    drop.appendChild(row);
  });
}

function closeHistoryPicker() {
  const drop = document.getElementById('historyDropdown');
  if (drop) drop.style.display = 'none';
}

// Close picker when clicking outside its container
document.addEventListener('click', e => {
  const wrap = document.getElementById('historyPickerBtn')?.closest('[data-history-wrap]');
  if (wrap && !wrap.contains(e.target)) closeHistoryPicker();
}, true);

// ── Window exports ────────────────────────────────────────────────────────────
window.loadHistorySession   = loadHistorySession;
window.openHistoryPicker    = openHistoryPicker;
window.closeHistoryPicker   = closeHistoryPicker;
window.exitHistoryMode      = exitHistoryMode;
window.invalidateHistoryCache = invalidateHistoryCache;
