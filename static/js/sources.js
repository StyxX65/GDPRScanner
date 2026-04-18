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

  // File sources (local / SMB) — one entry per saved source
  if (S._fileSources.length > 0) {
    html += '<div style="margin:6px 0 2px;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em">'
      + '<hr style="border:none;border-top:1px solid var(--border);margin:1px 0 2px">';
    S._fileSources.forEach(function(s) {
      const isSmb = s.path && (s.path.startsWith('//') || s.path.startsWith('\\\\'));
      const icon  = isSmb ? '\uD83C\uDF10' : '\uD83D\uDCC1';
      const label = s.label || s.path || s.id;
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
  ['general','security','scheduler','email','database'].forEach(function(t) {
    var cap = t.charAt(0).toUpperCase() + t.slice(1);
    var pane = document.getElementById('stPane' + cap);
    var btn  = document.getElementById('stTab'  + cap);
    if (pane) pane.classList.toggle('active', t === tab);
    if (btn)  btn.classList.toggle('active', t === tab);
  });
  if (tab === 'security')  { stLoadPinStatus(); if (typeof stLoadViewerPinStatus === 'function') stLoadViewerPinStatus(); if (typeof stLoadInterfacePinStatus === 'function') stLoadInterfacePinStatus(); }
  if (tab === 'email')     stLoadSmtp();
  if (tab === 'database')  stLoadDbStats();
  if (tab === 'scheduler') schedLoad();
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
window._M365_SOURCES = _M365_SOURCES;
window._pinCallback = _pinCallback;
