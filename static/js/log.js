import { S } from './state.js';
// ── Log ──────────────────────────────────────────────────────────────────────
const _LOG_SESSION_KEY = 'gdpr_log_session';
const _LOG_MAX_LINES = 300;
let _logFilter = 'all'; // 'all' | 'err'

// Maps keywords found in phase strings → {label, pillClass}
// Emoji patterns cover phases that have no source keyword in text
// (e.g. "📂 skolehaver: 1 msg(s)" — 📂 is only used for mail folders)
const _PHASE_SOURCE_MAP = [
  { re: /OneDrive/i,                       label: 'OneDrive',   cls: 'progress-src-m365'   },
  { re: /SharePoint/i,                     label: 'SharePoint', cls: 'progress-src-m365'   },
  { re: /\bTeams\b/i,                      label: 'Teams',      cls: 'progress-src-m365'   },
  { re: /E-?mail|emails?|msg\(s\)|\uD83D\uDCC2/iu, label: 'Outlook',  cls: 'progress-src-m365' },
  { re: /Google Workspace/i,               label: 'Gmail',      cls: 'progress-src-google' },
  { re: /Google Drive/i,                   label: 'GDrive',     cls: 'progress-src-google' },
  { re: /Gmail/i,                          label: 'Gmail',      cls: 'progress-src-google' },
  { re: /\bfil(er|S.es)?\b/i,               label: 'Local',      cls: 'progress-src-file'   },
];

function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Resolve an email address to a display name using S._allUsers, and strip
// trailing count suffixes like ": 3 file(s)" or ": 5 msg(s)".
function _resolveDisplayName(text) {
  if (!text) return text;
  const stripped = text.replace(/:\s*\d+\s*(file\(s\)|files?|filer|msg\(s\)|folders?)[\u2026\.]*\s*$/iu, '').trim();
  const check = stripped || text;
  if (check.includes('@')) {
    const email = check.toLowerCase();
    const user = S._allUsers.find(function(u) {
      return (u.email || '').toLowerCase() === email ||
             (u.googleEmail || '').toLowerCase() === email;
    });
    if (user) return user.displayName;
  }
  return stripped || text;
}

// Tracks the most recent user name shown — used for sub-phases (e.g. mail folder counts)
// that don't repeat the username in their phase string.

function _setProgressPhase(phase) {
  const who = document.getElementById('progressWho');
  if (!who) return;

  // Find source from the full phase string first
  let srcEntry = null;
  for (const s of _PHASE_SOURCE_MAP) {
    if (s.re.test(phase)) { srcEntry = s; break; }
  }

  // Try "Left — Right" split (em-dash / en-dash only — plain hyphens cause false splits)
  const dashMatch = phase.match(/^(.+?)\s+[\u2014\u2013]\s+(.+?)[\u2026\.]*\s*$/u);

  if (srcEntry && dashMatch) {
    const left  = dashMatch[1].trim();
    const right = dashMatch[2].trim();
    // Full name is whichever side doesn't contain the source keyword
    const raw = srcEntry.re.test(left) ? right : left;
    const displayName = _resolveDisplayName(raw);
    S._progressCurrentUser = displayName;
    who.innerHTML =
      '<span class="progress-src-pill ' + srcEntry.cls + '">' + srcEntry.label + '</span>' +
      '<span class="progress-user">' + _escHtml(displayName) + '</span>';
    return;
  }

  if (srcEntry) {
    // Source identified but no dash split (e.g. "📂 Indbakke: 3 msg(s)").
    // Re-use last known user rather than showing a folder path.
    const displayName = S._progressCurrentUser ||
      phase.replace(/^[\u{1F000}-\u{1FFFF}\u{2600}-\u{27FF}\s]+/u, '').trim();
    who.innerHTML =
      '<span class="progress-src-pill ' + srcEntry.cls + '">' + srcEntry.label + '</span>' +
      '<span class="progress-user">' + _escHtml(displayName) + '</span>';
    return;
  }

  // Informational phase (Auth mode, Delta mode, Resuming, …) — keep pill cleared
  who.innerHTML = '<span class="progress-phase">' + _escHtml(phase) + '</span>';
}

function _clearProgressBar() {
  _setProgressPhase('');
  document.getElementById('progressStats').textContent = '';
  document.getElementById('progressEta').textContent   = '';
  document.getElementById('progressFile').textContent  = '';
}

function _renderProgressSegments() {
  const track = document.getElementById('progressTrack');
  if (!track) return;
  const sources = [
    { key: 'm365',   active: S._m365ScanRunning,   color: 'var(--accent)', label: 'M365'  },
    { key: 'google', active: S._googleScanRunning,  color: '#3a7d44',       label: 'GWS'   },
    { key: 'file',   active: S._fileScanRunning,    color: '#7a6a9e',       label: 'Files' },
  ].filter(function(s) { return s.active; });
  if (!sources.length) { track.innerHTML = ''; return; }
  track.innerHTML = sources.map(function(s, i) {
    return '<div class="progress-seg"' + (i < sources.length - 1 ? '' : '') + '>' +
           '<div class="progress-seg-fill" id="progressFill_' + s.key + '" style="background:' + s.color + ';width:' + (S._srcPct[s.key] || 0) + '%"></div>' +
           '</div>';
  }).join('');
}

function _logAtBottom(p) {
  return p.scrollHeight - p.scrollTop - p.clientHeight < 24;
}

function log(msg, cls='') {
  const p = document.getElementById('logPanel');
  const live = document.getElementById('logLive');
  const atBottom = _logAtBottom(p);
  const d = document.createElement('div');
  const timestamp = new Date().toLocaleTimeString();
  d.className = 'log-line' + (cls ? ' log-' + cls : '');
  d.textContent = timestamp + '  ' + msg;
  // Insert before live indicator (always last)
  if (live) p.insertBefore(d, live); else p.appendChild(d);
  // Apply filter
  if (_logFilter === 'err' && !cls) d.classList.add('log-err-hidden');
  if (atBottom) p.scrollTop = p.scrollHeight;
  // Persist to sessionStorage
  try {
    const lines = JSON.parse(sessionStorage.getItem(_LOG_SESSION_KEY) || '[]');
    lines.push({ t: timestamp, msg, cls });
    if (lines.length > _LOG_MAX_LINES) lines.splice(0, lines.length - _LOG_MAX_LINES);
    sessionStorage.setItem(_LOG_SESSION_KEY, JSON.stringify(lines));
  } catch(e) {}
}

function setLogLive(msg) {
  const live = document.getElementById('logLive');
  if (!live) return;
  if (msg) {
    live.style.display = 'block';
    live.textContent = '▶ ' + msg;
    const p = document.getElementById('logPanel');
    if (_logAtBottom(p)) p.scrollTop = p.scrollHeight;
  } else {
    live.style.display = 'none';
    live.textContent = '';
  }
}

function setLogFilter(filter) {
  _logFilter = filter;
  document.getElementById('logFilterAll').classList.toggle('active', filter === 'all');
  document.getElementById('logFilterErr').classList.toggle('active', filter === 'err');
  document.querySelectorAll('#logPanel .log-line:not(#logLive)').forEach(function(d) {
    const isErr = d.classList.contains('log-err') || d.classList.contains('log-warn');
    d.classList.toggle('log-err-hidden', filter === 'err' && !isErr);
  });
}

function copyLog() {
  const lines = [];
  document.querySelectorAll('#logPanel .log-line:not(#logLive)').forEach(function(d) {
    lines.push(d.textContent);
  });
  navigator.clipboard.writeText(lines.join('\n')).then(function() {
    const btn = document.querySelector('.log-copy-btn');
    if (btn) { btn.textContent = '✓ Copied'; setTimeout(function(){ btn.textContent = '⎘ Copy'; }, 1500); }
  }).catch(function() {});
}

function _restoreLog() {
  try {
    const lines = JSON.parse(sessionStorage.getItem(_LOG_SESSION_KEY) || '[]');
    if (!lines.length) return;
    const p = document.getElementById('logPanel');
    const live = document.getElementById('logLive');
    lines.forEach(function(entry) {
      const d = document.createElement('div');
      d.className = 'log-line' + (entry.cls ? ' log-' + entry.cls : '');
      d.textContent = entry.t + '  ' + entry.msg;
      if (live) p.insertBefore(d, live); else p.appendChild(d);
    });
    p.scrollTop = p.scrollHeight;
  } catch(e) {}
}

function _initLogResize() {
  const handle = document.getElementById('logResizeHandle');
  const wrap   = document.getElementById('logWrap');
  const panel  = document.getElementById('logPanel');
  if (!handle || !wrap || !panel) return;
  let startY, startH;
  handle.addEventListener('pointerdown', function(e) {
    startY = e.clientY;
    startH = panel.getBoundingClientRect().height;
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
    handle.setPointerCapture(e.pointerId);
    handle.addEventListener('pointermove', onDrag);
    handle.addEventListener('pointerup',   onUp);
    handle.addEventListener('pointercancel', onUp);
    e.preventDefault();
  });
  function onDrag(e) {
    const ROW = 18; // 16px line-height + 2px margin-bottom
    const PAD = 10; // 6px padding-top + 6px padding-bottom - 2px (no margin on last line)
    const MIN_ROWS = 2;
    const MAX_ROWS = 30;
    const delta = startY - e.clientY; // drag up = taller
    const rawH = Math.max(60, Math.min(600, startH + delta));
    const rows = Math.round((rawH - PAD) / ROW);
    const snapped = Math.max(MIN_ROWS, Math.min(MAX_ROWS, rows)) * ROW + PAD;
    panel.style.height = snapped + 'px';
  }
  function onUp(e) {
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    handle.releasePointerCapture(e.pointerId);
    handle.removeEventListener('pointermove', onDrag);
    handle.removeEventListener('pointerup',   onUp);
    handle.removeEventListener('pointercancel', onUp);
  }
}

function _initPreviewResize() {
  const handle = document.getElementById('previewResizeHandle');
  const panel  = document.getElementById('previewPanel');
  if (!handle || !panel) return;
  const MIN_W = 280;
  const MAX_W = Math.round(window.innerWidth * 0.7);
  let startX, startW;
  handle.addEventListener('pointerdown', function(e) {
    if (panel.classList.contains('hidden')) return;
    startX = e.clientX;
    startW = panel.getBoundingClientRect().width;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    handle.setPointerCapture(e.pointerId);
    handle.addEventListener('pointermove', onDrag);
    handle.addEventListener('pointerup',   onUp);
    handle.addEventListener('pointercancel', onUp);
    e.preventDefault();
  });
  function onDrag(e) {
    const delta = startX - e.clientX; // drag left = wider
    const w = Math.max(MIN_W, Math.min(MAX_W, startW + delta));
    panel.style.width = w + 'px';
  }
  function onUp(e) {
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    handle.releasePointerCapture(e.pointerId);
    handle.removeEventListener('pointermove', onDrag);
    handle.removeEventListener('pointerup',   onUp);
    handle.removeEventListener('pointercancel', onUp);
    sessionStorage.setItem('gdpr_preview_width', parseInt(panel.style.width));
  }
}

// Called by renderSourcesPanel() after every re-render.
// Pins the panel to its natural scroll height (all sources visible) unless the
// user has previously dragged it smaller, in which case that saved height is
// restored — but only if it's still smaller than the new content height.
function _fitSourcesPanel() {
  const panel = document.getElementById('sourcesPanel');
  if (!panel) return;
  panel.style.height = '';               // clear to measure natural content height
  const natural = panel.scrollHeight;
  try {
    const saved = parseInt(localStorage.getItem('gdpr_sources_h'));
    if (saved && saved < natural) {
      panel.style.height = saved + 'px'; // honour user's smaller preference
      return;
    }
  } catch(e) {}
  panel.style.height = natural + 'px';  // default: show everything
}

function _initSourcesResize() {
  const handle = document.getElementById('sourcesResizeHandle');
  const panel  = document.getElementById('sourcesPanel');
  if (!handle || !panel) return;

  let startY, startH, maxH;
  handle.addEventListener('pointerdown', function(e) {
    startY = e.clientY;
    startH = panel.getBoundingClientRect().height;
    // Max = natural scroll height (enough to show all sources — no more)
    panel.style.height = '';
    maxH = panel.scrollHeight;
    panel.style.height = startH + 'px';
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
    handle.setPointerCapture(e.pointerId);
    handle.addEventListener('pointermove', onDrag);
    handle.addEventListener('pointerup',   onUp);
    handle.addEventListener('pointercancel', onUp);
    e.preventDefault();
  });
  function onDrag(e) {
    const ROW     = 22;   // ~21px per .source-check row (padding:3px 0 + ~15px content)
    const MIN_H   = ROW * 2;
    const delta   = e.clientY - startY;  // drag down = taller, drag up = shorter
    const rawH    = Math.max(MIN_H, Math.min(maxH, startH + delta));
    const snapped = Math.round(rawH / ROW) * ROW;
    panel.style.height = Math.max(MIN_H, Math.min(maxH, snapped)) + 'px';
  }
  function onUp(e) {
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    handle.releasePointerCapture(e.pointerId);
    handle.removeEventListener('pointermove', onDrag);
    handle.removeEventListener('pointerup',   onUp);
    handle.removeEventListener('pointercancel', onUp);
    const h = parseInt(panel.style.height);
    try {
      if (h >= maxH) localStorage.removeItem('gdpr_sources_h'); // back to full — forget preference
      else           localStorage.setItem('gdpr_sources_h', h);
    } catch(e) {}
  }
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window._escHtml = _escHtml;
window._resolveDisplayName = _resolveDisplayName;
window._setProgressPhase = _setProgressPhase;
window._clearProgressBar = _clearProgressBar;
window._renderProgressSegments = _renderProgressSegments;
window._logAtBottom = _logAtBottom;
window.log = log;
window.setLogLive = setLogLive;
window.setLogFilter = setLogFilter;
window.copyLog = copyLog;
window._restoreLog = _restoreLog;
window._initLogResize = _initLogResize;
window._initPreviewResize = _initPreviewResize;
window._initSourcesResize = _initSourcesResize;
window._fitSourcesPanel   = _fitSourcesPanel;
window._LOG_SESSION_KEY = _LOG_SESSION_KEY;
window._LOG_MAX_LINES = _LOG_MAX_LINES;
window._logFilter = _logFilter;
window._PHASE_SOURCE_MAP = _PHASE_SOURCE_MAP;
