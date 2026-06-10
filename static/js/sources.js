import { S } from './state.js';
// ── Dynamic sources panel ─────────────────────────────────────────────────────

// Fixed M365 sources — always present when authenticated
const _M365_SOURCES = [
  { id: 'email',      icon: '\uD83D\uDCE7', labelKey: 'm365_src_email',      labelDefault: 'Exchange / Outlook', toggleId: 'smSrcEmail' },
  { id: 'onedrive',   icon: '\uD83D\uDCBE', labelKey: 'm365_src_onedrive',   labelDefault: 'OneDrive',           toggleId: 'smSrcOneDrive' },
  { id: 'sharepoint', icon: '\uD83C\uDF10', labelKey: 'm365_src_sharepoint', labelDefault: 'SharePoint',         toggleId: 'smSrcSharePoint' },
  { id: 'teams',      icon: '\uD83D\uDCAC', labelKey: 'm365_src_teams',      labelDefault: 'Teams',              toggleId: 'smSrcTeams' },
];

// Future connector stubs — uncomment when implemented
// const _GMAIL_SOURCE  = { id: 'gmail',        icon: '\uD83D\uDCE7', labelKey: 'm365_src_gmail',       labelDefault: 'Gmail',        type: 'm365' };
// const _GDRIVE_SOURCE = { id: 'googledrive',  icon: '\uD83D\uDCC1', labelKey: 'm365_src_googledrive', labelDefault: 'Google Drive', type: 'm365' };

function renderSourcesPanel() {
  const panel = document.getElementById('sourcesPanel');
  if (!panel) return;

  // Remember currently checked state before re-render
  const checked = {};
  panel.querySelectorAll('input[data-source-id]').forEach(function(cb) {
    checked[cb.dataset.sourceId] = cb.checked;
  });

  let html = '';

  // M365 fixed sources — only show if their toggle in Source Management is on
  _M365_SOURCES.forEach(function(s) {
    const toggle = s.toggleId ? document.getElementById(s.toggleId) : null;
    if (toggle && !toggle.checked) return;  // hidden by user in Source Management
    const isChecked = (s.id in checked) ? checked[s.id] : true;
    html += '<label class="source-check">'
      + '<input type="checkbox" data-source-id="' + s.id + '" data-source-type="m365"' + (isChecked ? ' checked' : '') + ' onchange="_onSourceChange()">'
      + '<span class="source-icon">' + s.icon + '</span>'
      + '<span class="source-label" data-i18n="' + s.labelKey + '">' + t(s.labelKey, s.labelDefault) + '</span>'
      + '</label>';
  });

  // Google Workspace sources — only show if connected
  if (window._googleConnected) {
    var gmailToggle = document.getElementById('smGoogleSrcGmail');
    var driveToggle = document.getElementById('smGoogleSrcDrive');
    var showGmail = !gmailToggle || gmailToggle.checked;
    var showDrive = !driveToggle || driveToggle.checked;
    if (showGmail || showDrive) {
      html += '<div style="margin:6px 0 2px"><hr style="border:none;border-top:1px solid var(--border);margin:1px 0 2px"></div>';
    }
    if (showGmail) {
      var isCheckedG = ('gmail' in checked) ? checked['gmail']
        : S._pendingGoogleSources !== null ? S._pendingGoogleSources.includes('gmail')
        : true;
      html += '<label class="source-check"><input type="checkbox" data-source-id="gmail" data-source-type="google"' + (isCheckedG ? ' checked' : '') + ' onchange="_onSourceChange()"><span class="source-icon">📧</span><span class="source-label">Gmail</span></label>';
    }
    if (showDrive) {
      var isCheckedD = ('gdrive' in checked) ? checked['gdrive']
        : S._pendingGoogleSources !== null ? S._pendingGoogleSources.includes('gdrive')
        : true;
      html += '<label class="source-check"><input type="checkbox" data-source-id="gdrive" data-source-type="google"' + (isCheckedD ? ' checked' : '') + ' onchange="_onSourceChange()"><span class="source-icon">📁</span><span class="source-label">Google Drive</span></label>';
    }
    // Pending has been applied — clear it
    S._pendingGoogleSources = null;
  }

  // File sources (local / SMB / SFTP) — one entry per saved source
  if (S._fileSources.length > 0) {
    html += '<div style="margin:6px 0 2px;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em">'
      + '<hr style="border:none;border-top:1px solid var(--border);margin:1px 0 2px">';
    S._fileSources.forEach(function(s) {
      const isSftp = s.source_type === 'sftp';
      const isSmb  = !isSftp && s.path && (s.path.startsWith('//') || s.path.startsWith('\\\\'));
      const icon   = isSftp ? '\uD83D\uDD12' : (isSmb ? '\uD83C\uDF10' : '\uD83D\uDCC1');
      const label  = s.label || s.path || s.id;
      const isChecked = (s.id in checked) ? checked[s.id] : true;
      html += '<label class="source-check">'
        + '<input type="checkbox" data-source-id="' + _esc(s.id) + '" data-source-type="file"' + (isChecked ? ' checked' : '') + '>'
        + '<span class="source-icon">' + icon + '</span>'
        + '<span class="source-label" title="' + _esc(s.path || '') + '">' + _esc(label) + '</span>'
        + '</label>';
    });
  }

  panel.innerHTML = html;

  // Resize panel to fit all rendered sources (respects user's saved smaller preference)
  if (typeof _fitSourcesPanel === 'function') _fitSourcesPanel();

  // Grey out the accounts section when no M365 sources are selected
  _updateAccountsVisibility();
}

function _onSourceChange() {
  _updateAccountsVisibility();
  renderAccountList();
}

function _onGoogleSourceToggle() {
  // Re-render sources panel (hides/shows Gmail+Drive checkboxes in KILDER)
  renderSourcesPanel();
  // Re-render accounts — 'both' users show as M365-only when Google sources disabled
  renderAccountList();
  // Persist toggle state
  var gm = document.getElementById('smGoogleSrcGmail');
  var gd = document.getElementById('smGoogleSrcDrive');
  fetch('/api/src_toggles', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      src_gmail: gm ? gm.checked : true,
      src_drive: gd ? gd.checked : true
    })
  }).catch(function(){});
}
function _saveM365SourceToggles() {
  var state = {};
  _M365_SOURCES.forEach(function(s) {
    var el = s.toggleId ? document.getElementById(s.toggleId) : null;
    if (el) state['src_toggle_' + s.id] = el.checked;
  });
  fetch('/api/src_toggles', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(state)
  }).catch(function(){});
}

function _restoreM365SourceToggles(settings) {
  _M365_SOURCES.forEach(function(s) {
    var el = s.toggleId ? document.getElementById(s.toggleId) : null;
    var key = 'src_toggle_' + s.id;
    if (el && settings[key] !== undefined) el.checked = !!settings[key];
  });
  renderSourcesPanel();
}

function _googleSourcesEnabled() {
  return !!(document.getElementById('smGoogleSrcGmail') && document.getElementById('smGoogleSrcGmail').checked)
      || !!(document.getElementById('smGoogleSrcDrive') && document.getElementById('smGoogleSrcDrive').checked);
}


function _updateAccountsVisibility() {
  const panel = document.getElementById('sourcesPanel');
  const anyActive = panel
    ? Array.from(panel.querySelectorAll('input[data-source-type]')).some(cb => cb.checked)
    : false;
  const sec = document.getElementById('accountsSection');
  if (!sec) return;
  sec.style.opacity       = anyActive ? '1' : '0.35';
  sec.style.pointerEvents = anyActive ? '' : 'none';
  sec.title               = anyActive ? '' : t('m365_accounts_disabled_tip', 'Select a source to enable account selection');
}

// ── Admin PIN ─────────────────────────────────────────────────────────────────

let _pinCallback = null;

async function stLoadPinStatus() {
  const r = await fetch('/api/admin/pin');
  const d = await r.json();
  const statusEl = document.getElementById('stPinStatus');
  const currentRow = document.getElementById('stCurrentPinRow');
  if (d.pin_set) {
    if (statusEl) statusEl.textContent = '\u2714 ' + t('m365_settings_pin_set', 'Admin PIN is set');
    if (currentRow) currentRow.style.display = '';
  } else {
    if (statusEl) statusEl.textContent = t('m365_settings_pin_not_set', 'No PIN set \u2014 Reset DB is unprotected');
    if (currentRow) currentRow.style.display = 'none';
  }
}

async function stSavePin() {
  const newPin     = document.getElementById('stNewPin').value;
  const confirmPin = document.getElementById('stConfirmPin').value;
  const currentPin = document.getElementById('stCurrentPin')?.value || '';
  const st         = document.getElementById('stPinSaveStatus');
  if (!newPin) { st.style.color='var(--danger)'; st.textContent=t('m365_settings_pin_required','New PIN is required.'); return; }
  if (newPin !== confirmPin) { st.style.color='var(--danger)'; st.textContent=t('m365_settings_pin_mismatch','PINs do not match.'); return; }
  st.style.color='var(--muted)'; st.textContent=t('m365_fsrc_saving','Saving...');
  try {
    const r = await fetch('/api/admin/pin', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({current_pin: currentPin, new_pin: newPin})});
    const d = await r.json();
    if (d.error === 'incorrect_pin') { st.style.color='var(--danger)'; st.textContent=t('m365_settings_pin_wrong','Current PIN is incorrect.'); return; }
    if (d.error) { st.style.color='var(--danger)'; st.textContent=d.error; return; }
    st.style.color='var(--accent)'; st.textContent='\u2714 '+t('m365_settings_pin_saved','PIN saved');
    ['stNewPin','stConfirmPin','stCurrentPin'].forEach(function(id){const el=document.getElementById(id);if(el)el.value='';});
    stLoadPinStatus();
  } catch(e){ st.style.color='var(--danger)'; st.textContent=e.message; }
}

// PIN prompt — used for destructive actions
function requirePin(message, callback) {
  fetch('/api/admin/pin').then(function(r){return r.json();}).then(function(d) {
    if (!d.pin_set) {
      // No PIN set — proceed directly
      callback('');
      return;
    }
    _pinCallback = callback;
    const msg = document.getElementById('pinPromptMsg');
    const inp = document.getElementById('pinPromptInput');
    const err = document.getElementById('pinPromptError');
    if (msg) msg.textContent = message || t('m365_settings_enter_pin','Enter admin PIN to continue.');
    if (inp) inp.value = '';
    if (err) err.textContent = '';
    document.getElementById('pinPromptBackdrop').classList.add('open');
    setTimeout(function(){ if(inp) inp.focus(); }, 100);
  });
}

function closePinPrompt() {
  document.getElementById('pinPromptBackdrop').classList.remove('open');
  _pinCallback = null;
}

function confirmPinPrompt() {
  const pin = document.getElementById('pinPromptInput').value;
  const err = document.getElementById('pinPromptError');
  if (!pin) { if(err) err.textContent = t('m365_settings_pin_required','PIN is required.'); return; }
  const cb = _pinCallback;   // save before closePinPrompt nulls it
  closePinPrompt();
  if (cb) cb(pin);
}

// ── Settings modal ────────────────────────────────────────────────────────────

function openSettings(tab) {
  document.getElementById('settingsBackdrop').classList.add('open');
  switchSettingsTab(tab || 'general');
  stPopulateGeneral();
  if (tab === 'email')    stLoadSmtp();
  if (tab === 'database') stLoadDbStats();
  if (tab === 'scheduler') schedLoad();
}

function closeSettings() {
  document.getElementById('settingsBackdrop').classList.remove('open');
}

function switchSettingsTab(tab) {
  ['general','security','scheduler','email','database','auditlog','ai'].forEach(function(t) {
    var cap = t.charAt(0).toUpperCase() + t.slice(1);
    var pane = document.getElementById('stPane' + cap);
    var btn  = document.getElementById('stTab'  + cap);
    if (pane) pane.classList.toggle('active', t === tab);
    if (btn)  btn.classList.toggle('active', t === tab);
  });
  if (tab === 'general')   stLoadUpdateSettings();
  if (tab === 'security')  { stLoadPinStatus(); if (typeof stLoadViewerPinStatus === 'function') stLoadViewerPinStatus(); if (typeof stLoadInterfacePinStatus === 'function') stLoadInterfacePinStatus(); }
  if (tab === 'email')     stLoadSmtp();
  if (tab === 'database')  stLoadDbStats();
  if (tab === 'scheduler') schedLoad();
  if (tab === 'auditlog')  stLoadAuditLog();
  if (tab === 'ai')        stLoadAiSettings();
}

async function stLoadAuditLog() {
  const tbody = document.getElementById('stAuditTableBody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:8px;color:var(--muted)">${t('m365_audit_loading')}</td></tr>`;
  try {
    const rows = await fetch('/api/audit_log?limit=200').then(r => r.json());
    if (!Array.isArray(rows) || !rows.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="padding:8px;color:var(--muted)">${t('m365_audit_empty')}</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(function(r) {
      const d  = new Date(r.ts * 1000);
      const ts = d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
      return '<tr style="border-bottom:1px solid var(--border)">'
        + '<td style="padding:4px 8px;white-space:nowrap;color:var(--muted);font-size:11px">' + window._escHtml(ts) + '</td>'
        + '<td style="padding:4px 8px"><span style="font-family:monospace;background:var(--bg);border:1px solid var(--border);border-radius:3px;padding:1px 4px;font-size:11px">' + window._escHtml(r.action) + '</span></td>'
        + '<td style="padding:4px 8px;color:var(--text);font-size:12px">' + window._escHtml(r.detail) + '</td>'
        + '<td style="padding:4px 8px;color:var(--muted);font-size:11px">' + window._escHtml(r.ip) + '</td>'
        + '</tr>';
    }).join('');
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="4" style="padding:8px;color:var(--danger)">' + window._escHtml(String(e)) + '</td></tr>';
  }
}

// ── AI / Claude NER settings ─────────────────────────────────────────────────

async function stLoadAiSettings() {
  try {
    const cfg = await fetch('/api/settings/claude').then(r => r.json());
    const cb = document.getElementById('aiEnabled');
    if (cb) cb.checked = !!cfg.enabled;
    const ks = document.getElementById('aiKeyStatus');
    if (ks) ks.textContent = cfg.api_key_set
      ? t('m365_ai_key_set', 'API key saved')
      : t('m365_ai_key_not_set', 'No API key saved');
  } catch(e) { /* ignore */ }
}

async function stAiSave() {
  const enabled = !!(document.getElementById('aiEnabled') || {}).checked;
  const keyVal  = (document.getElementById('aiApiKey') || {}).value || '';
  const status  = document.getElementById('aiStatus');
  const payload = { enabled };
  if (keyVal) payload.api_key = keyVal;
  try {
    await fetch('/api/settings/claude', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (status) { status.textContent = t('m365_ai_saved', 'Saved'); status.style.color = 'var(--success)'; }
    if (keyVal) {
      const inp = document.getElementById('aiApiKey');
      if (inp) inp.value = '';
      const ks = document.getElementById('aiKeyStatus');
      if (ks) ks.textContent = t('m365_ai_key_set', 'API key saved');
    }
    setTimeout(function() { if (status) status.textContent = ''; }, 2000);
  } catch(e) {
    if (status) { status.textContent = String(e); status.style.color = 'var(--danger)'; }
  }
}

async function stAiTest() {
  const status = document.getElementById('aiStatus');
  if (status) { status.textContent = t('m365_ai_testing', 'Testing…'); status.style.color = 'var(--muted)'; }
  try {
    const res = await fetch('/api/settings/claude/test', { method: 'POST' }).then(r => r.json());
    if (status) {
      status.textContent = res.ok
        ? t('m365_ai_test_ok', 'API key valid')
        : (t('m365_ai_test_fail', 'Test failed') + ': ' + (res.error || ''));
      status.style.color = res.ok ? 'var(--success)' : 'var(--danger)';
    }
  } catch(e) {
    if (status) { status.textContent = String(e); status.style.color = 'var(--danger)'; }
  }
}

// ── Software updates ─────────────────────────────────────────────────────────

async function stLoadUpdateSettings() {
  try {
    const cfg = await fetch('/api/update/settings').then(r => r.json());
    const grp = document.getElementById('stUpdateGroup');
    if (grp) grp.style.display = cfg.supported ? '' : 'none';
    const cb = document.getElementById('stAutoUpdate');
    if (cb) cb.checked = !!cfg.auto_update;
  } catch(e) { /* ignore */ }
}

async function stSaveAutoUpdate() {
  const cb = document.getElementById('stAutoUpdate');
  try {
    await fetch('/api/update/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ auto_update: !!(cb && cb.checked) }),
    });
  } catch(e) { /* ignore */ }
}

async function stCheckUpdate() {
  const status  = document.getElementById('stUpdateStatus');
  const commits = document.getElementById('stUpdateCommits');
  const applyBtn = document.getElementById('stApplyUpdateBtn');
  if (status) { status.textContent = t('m365_update_checking', 'Checking…'); status.style.color = 'var(--muted)'; }
  if (commits) commits.style.display = 'none';
  if (applyBtn) applyBtn.style.display = 'none';
  try {
    const res = await fetch('/api/update/check').then(r => r.json());
    if (!status) return;
    if (res.error) {
      status.textContent = t('m365_update_failed', 'Update check failed') + ': ' + res.error;
      status.style.color = 'var(--danger)';
    } else if (res.up_to_date) {
      status.textContent = t('m365_update_uptodate', 'You are running the latest version.') + ' (' + res.current + ')';
      status.style.color = 'var(--success)';
    } else {
      status.textContent = t('m365_update_available', 'Update available') + ': ' + res.current + ' → ' + res.latest;
      status.style.color = 'var(--accent)';
      if (commits && res.commits && res.commits.length) {
        commits.innerHTML = res.commits.map(function(c) { return window._escHtml(c); }).join('<br>');
        commits.style.display = '';
      }
      if (applyBtn) applyBtn.style.display = '';
    }
  } catch(e) {
    if (status) { status.textContent = String(e); status.style.color = 'var(--danger)'; }
  }
}

async function stApplyUpdate() {
  const status   = document.getElementById('stUpdateStatus');
  const applyBtn = document.getElementById('stApplyUpdateBtn');
  const checkBtn = document.getElementById('stCheckUpdateBtn');
  if (applyBtn) applyBtn.disabled = true;
  if (checkBtn) checkBtn.disabled = true;
  if (status) { status.textContent = t('m365_update_installing', 'Installing update — the app will restart…'); status.style.color = 'var(--muted)'; }
  try {
    const res = await fetch('/api/update/apply', { method: 'POST' }).then(r => r.json());
    if (!res.ok) {
      const msg = res.code === 'scan_running'
        ? t('m365_update_scan_running', 'Cannot update while a scan is running.')
        : (res.error || 'Update failed');
      if (status) { status.textContent = msg; status.style.color = 'var(--danger)'; }
      if (applyBtn) applyBtn.disabled = false;
      if (checkBtn) checkBtn.disabled = false;
      return;
    }
    if (!res.updated) {   // already up to date
      if (status) { status.textContent = t('m365_update_uptodate', 'You are running the latest version.'); status.style.color = 'var(--success)'; }
      if (applyBtn) { applyBtn.disabled = false; applyBtn.style.display = 'none'; }
      if (checkBtn) checkBtn.disabled = false;
      return;
    }
    _stWaitForRestart();
  } catch(e) {
    if (status) { status.textContent = String(e); status.style.color = 'var(--danger)'; }
    if (applyBtn) applyBtn.disabled = false;
    if (checkBtn) checkBtn.disabled = false;
  }
}

// Poll until the server has gone down and come back, then reload the page.
function _stWaitForRestart() {
  let tries = 0, sawDown = false;
  const iv = setInterval(async function() {
    tries++;
    try {
      await fetch('/api/about', { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(); });
      if (sawDown || tries >= 5) { clearInterval(iv); location.reload(); }
    } catch(e) {
      sawDown = true;
    }
    if (tries > 90) clearInterval(iv);   // give up after ~3 minutes
  }, 2000);
}

function stAiToggleKey() {
  const inp = document.getElementById('aiApiKey');
  const btn = document.getElementById('aiShowKeyBtn');
  if (!inp) return;
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  if (btn) btn.textContent = show ? t('m365_ai_hide_key', 'Hide') : t('m365_ai_show_key', 'Show');
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.renderSourcesPanel = renderSourcesPanel;
window._onSourceChange = _onSourceChange;
window._onGoogleSourceToggle = _onGoogleSourceToggle;
window._saveM365SourceToggles = _saveM365SourceToggles;
window._restoreM365SourceToggles = _restoreM365SourceToggles;
window._googleSourcesEnabled = _googleSourcesEnabled;
window._updateAccountsVisibility = _updateAccountsVisibility;
window.stLoadPinStatus = stLoadPinStatus;
window.stSavePin = stSavePin;
window.requirePin = requirePin;
window.closePinPrompt = closePinPrompt;
window.confirmPinPrompt = confirmPinPrompt;
window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.switchSettingsTab = switchSettingsTab;
window.stLoadAuditLog = stLoadAuditLog;
window.stLoadAiSettings = stLoadAiSettings;
window.stAiSave = stAiSave;
window.stAiTest = stAiTest;
window.stAiToggleKey = stAiToggleKey;
window.stLoadUpdateSettings = stLoadUpdateSettings;
window.stSaveAutoUpdate = stSaveAutoUpdate;
window.stCheckUpdate = stCheckUpdate;
window.stApplyUpdate = stApplyUpdate;
window._M365_SOURCES = _M365_SOURCES;
window._pinCallback = _pinCallback;
