import { S } from './state.js';
// ── Unified Source Management (#17) ──────────────────────────────────────────

function openSourcesMgmt(tab) {
  document.getElementById('srcMgmtBackdrop').classList.add('open');
  switchSrcTab(tab || 'm365');
  smRefreshStatus();
  smGoogleRefreshStatus();
  srcFileRenderList();
}

function closeSourcesMgmt() {
  document.getElementById('srcMgmtBackdrop').classList.remove('open');
}

function switchSrcTab(tab) {
  ['m365','google','files'].forEach(function(t) {
    document.getElementById('srcPane'  + t.charAt(0).toUpperCase() + t.slice(1))
             .classList.toggle('active', t === tab);
    const btn = document.getElementById('srcTab' + t.charAt(0).toUpperCase() + t.slice(1));
    if (btn) btn.classList.toggle('active', t === tab);
  });
  // Capitalise pane ids correctly: srcPaneM365, srcPaneGoogle, srcPaneFiles
  const paneMap = {m365:'M365', google:'Google', files:'Files'};
  ['m365','google','files'].forEach(function(t) {
    const pane = document.getElementById('srcPane' + paneMap[t]);
    if (pane) pane.classList.toggle('active', t === tab);
    const btn  = document.getElementById('srcTab'  + paneMap[t]);
    if (btn)  btn.classList.toggle('active', t === tab);
  });
}

// ── M365 pane ─────────────────────────────────────────────────────────────────

function smRefreshStatus() {
  const dot   = document.getElementById('srcM365StatusDot');
  const label = document.getElementById('srcM365StatusLabel');
  const sub   = document.getElementById('srcM365StatusSub');
  const disc  = document.getElementById('smDisconnectBtn');
  const st    = document.getElementById('smConnStatus');
  if (!dot) return;

  // Load saved credentials and auth status from the correct endpoints
  fetch('/api/auth/status').then(function(r){ return r.json(); }).then(function(d) {
    // Pre-fill credential fields
    const cidEl = document.getElementById('smClientId');
    const tidEl = document.getElementById('smTenantId');
    const secEl = document.getElementById('smClientSecret');
    if (cidEl && d.client_id)  cidEl.value = d.client_id;
    if (tidEl && d.tenant_id)  tidEl.value = d.tenant_id;
    if (secEl && d.client_secret) secEl.value = d.client_secret.length > 4 ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' : '';

    if (d.authenticated) {
      dot.className = 'srcmgmt-status green';
      const who = d.display_name || d.email || '';
      const mode = d.app_mode ? t('m365_mode_app_short','App mode') : t('m365_mode_delegated_short','Delegated');
      label.textContent = who || t('m365_srcmgmt_connected','Connected');
      sub.textContent = mode + (d.email && d.display_name ? '  \u00b7  ' + d.email : '');
      if (disc) disc.style.display = '';
      if (st)   st.textContent = '';
    } else {
      dot.className = 'srcmgmt-status grey';
      label.textContent = t('m365_srcmgmt_not_connected','Not connected');
      sub.textContent = '';
      if (disc) disc.style.display = 'none';
      if (st)   st.textContent = '';
    }
  }).catch(function(){
    if (dot) dot.className = 'srcmgmt-status grey';
  });
}

async function smConnect() {
  const cid = document.getElementById('smClientId').value.trim();
  const tid = document.getElementById('smTenantId').value.trim();
  const rawSec = document.getElementById('smClientSecret').value;
  // If field shows placeholder dots and user hasn't changed it, use saved secret (send empty to keep it)
  const sec = (rawSec === '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022') ? '' : rawSec.trim();
  const st  = document.getElementById('smConnStatus');
  if (!cid || !tid) { st.style.color='var(--danger)'; st.textContent=t('m365_err_creds_required','Client ID and Tenant ID required'); return; }
  st.style.color='var(--muted)'; st.textContent=t('m365_connecting','Connecting...');

  // Persist credentials
  await fetch('/api/auth/config', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({client_id:cid, tenant_id:tid, client_secret:sec})
  });

  // Start auth — same as the auth screen flow
  try {
    const r = await fetch('/api/auth/start', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({client_id:cid, tenant_id:tid, client_secret:sec})
    });
    const d = await r.json();
    if (d.error) { st.style.color='var(--danger)'; st.textContent=d.error; return; }

    if (d.mode === 'application') {
      // App mode — no device code needed
      st.style.color='var(--accent)'; st.textContent='\u2714 '+t('m365_connected','Connected');
      closeSourcesMgmt();
      setTimeout(onAuthenticated, 400);
    } else {
      // Delegated — show device code flow, close modal
      closeSourcesMgmt();
      document.getElementById('clientId').value = cid;
      document.getElementById('tenantId').value = tid;
      document.getElementById('clientSecret').value = sec;
      document.getElementById('configForm').style.display = 'none';
      document.getElementById('authScreen').style.display = 'flex';
      document.getElementById('deviceCodeBackdrop').classList.add('open');
      document.getElementById('deviceCode').textContent = d.user_code || '\u2014';
      pollAuth();
    }
  } catch(e) { st.style.color='var(--danger)'; st.textContent=e.message; }
}

function smDisconnect() {
  if (!confirm(t('m365_signout_confirm','Disconnect and clear credentials?'))) return;
  fetch('/api/auth/signout', {method:'POST'}).then(function(){
    closeSourcesMgmt();
    signOut();
  });
}

// ── Google Workspace pane ─────────────────────────────────────────────────────

// Parsed key dict held in memory while the pane is open — cleared on disconnect
var _googleKeyDict  = null;
var _googleAuthMode = 'workspace';

function smGoogleSetMode(mode) {
  _googleAuthMode = mode;
  var saSection       = document.getElementById('smGoogleSaSection');
  var personalSection = document.getElementById('smGooglePersonalSection');
  var wsSetup         = document.getElementById('smGoogleWorkspaceSetup');
  var btnWs           = document.getElementById('smGoogleModeWorkspace');
  var btnPl           = document.getElementById('smGoogleModePersonal');
  var isPersonal      = (mode === 'personal');
  if (saSection)       saSection.style.display       = isPersonal ? 'none' : '';
  if (personalSection) personalSection.style.display  = isPersonal ? '' : 'none';
  if (wsSetup)         wsSetup.style.display          = isPersonal ? 'none' : '';
  if (btnWs) { btnWs.style.background = isPersonal ? 'var(--surface)' : 'var(--accent)'; btnWs.style.color = isPersonal ? 'var(--text)' : '#fff'; }
  if (btnPl) { btnPl.style.background = isPersonal ? 'var(--accent)' : 'var(--surface)'; btnPl.style.color = isPersonal ? '#fff' : 'var(--text)'; }
}

function smGoogleRefreshStatus() {
  var wsPromise = fetch('/api/google/auth/status').then(function(r){ return r.json(); }).catch(function(){ return {}; });
  var personalPromise = fetch('/api/google/personal/status').then(function(r){ return r.json(); }).catch(function(){ return {connected: false}; });

  Promise.all([wsPromise, personalPromise]).then(function(results) {
    var ws = results[0];
    var personal = results[1];
    var dot        = document.getElementById('srcGoogleStatusDot');
    var label      = document.getElementById('srcGoogleStatusLabel');
    var sub        = document.getElementById('srcGoogleStatusSub');
    var disc       = document.getElementById('smGoogleDisconnectBtn');
    var srcs       = document.getElementById('smGoogleSourcesGroup');
    var signOutBtn = document.getElementById('smGooglePersonalSignOutBtn');
    var signInBtn  = document.getElementById('smGooglePersonalSignInBtn');
    if (!dot) return;

    if (ws.libs_ok === false) {
      dot.className = 'srcmgmt-status amber';
      label.textContent = t('m365_google_libs_missing', 'Libraries not installed');
      sub.textContent   = 'pip install google-auth google-auth-httplib2 google-api-python-client';
      if (disc) disc.style.display = 'none';
      if (srcs) srcs.style.display = 'none';
      return;
    }

    if (personal.connected) {
      smGoogleSetMode('personal');
      window._googleConnected = true;
      dot.className = 'srcmgmt-status green';
      label.textContent = personal.email || personal.displayName || t('m365_srcmgmt_connected', 'Connected');
      sub.textContent   = t('m365_google_mode_personal', 'Personal account');
      if (disc)       disc.style.display       = 'none';
      if (srcs)       srcs.style.display       = '';
      if (signOutBtn) signOutBtn.style.display  = '';
      if (signInBtn)  signInBtn.style.display   = 'none';
    } else if (ws.connected) {
      smGoogleSetMode('workspace');
      window._googleConnected = true;
      dot.className = 'srcmgmt-status green';
      label.textContent = ws.sa_email || t('m365_srcmgmt_connected', 'Connected');
      sub.textContent   = (ws.project_id ? ws.project_id + '  ·  ' : '') + (ws.admin_email || '');
      if (disc)       disc.style.display       = '';
      if (srcs)       srcs.style.display       = '';
      if (signOutBtn) signOutBtn.style.display  = 'none';
      if (signInBtn)  signInBtn.style.display   = '';
      var ae = document.getElementById('smGoogleAdminEmail');
      if (ae && ws.admin_email && !ae.value) ae.value = ws.admin_email;
      var gm = document.getElementById('smGoogleSrcGmail');
      var gd = document.getElementById('smGoogleSrcDrive');
      if (gm && ws.src_gmail !== undefined) gm.checked = !!ws.src_gmail;
      if (gd && ws.src_drive !== undefined) gd.checked = !!ws.src_drive;
    } else {
      window._googleConnected = false;
      dot.className = 'srcmgmt-status grey';
      label.textContent = t('m365_srcmgmt_not_connected', 'Not connected');
      sub.textContent   = ws.error || personal.error || '';
      if (disc)       disc.style.display       = 'none';
      if (srcs)       srcs.style.display       = 'none';
      if (signOutBtn) signOutBtn.style.display  = 'none';
      if (signInBtn)  signInBtn.style.display   = '';
    }
    renderSourcesPanel();
    // If the profile editor is open and its source panel has no Google checkboxes yet,
    // re-render it now that connection status is known.
    if (document.getElementById('pmgmtEditor')?.classList.contains('open') &&
        !document.querySelector('#peSourcesPanel input[data-source-type="google"]')) {
      var _peCheckedIds = Array.from(document.querySelectorAll('#peSourcesPanel input[type=checkbox]'))
        .filter(function(cb) { return cb.checked; }).map(function(cb) { return cb.dataset.sourceId; });
      var _peProfile = window._pmgmtEditId ? (S._profiles.find(function(p) { return p.id === window._pmgmtEditId; }) || window._pmgmtNewDraft) : window._pmgmtNewDraft;
      if (_peProfile) {
        var _peSavedIds = (_peProfile.sources||[]).concat(_peProfile.google_sources||[]).concat(_peProfile.file_sources||[]);
        _renderEditorSources(_peCheckedIds.concat(_peSavedIds));
      }
    }
    if (window._googleConnected) {
      _mergeGoogleUsers();
    } else {
      // Remove standalone Google users; reset merged 'both' users back to M365
      S._allUsers = S._allUsers.filter(function(u){ return (u.platform||'m365') !== 'google'; });
      S._allUsers.forEach(function(u) {
        if (u.platform === 'both') { u.platform = 'm365'; delete u.googleEmail; }
      });
      renderAccountList();
    }
  }).catch(function() {
    var dot = document.getElementById('srcGoogleStatusDot');
    if (dot) dot.className = 'srcmgmt-status grey';
  });
}

// Wire up file input to read + validate JSON immediately
(function() {
  document.addEventListener('DOMContentLoaded', function() {
    var fi = document.getElementById('smGoogleKeyFile');
    if (!fi) return;
    fi.addEventListener('change', function() {
      var f = fi.files && fi.files[0];
      if (!f) { _googleKeyDict = null; return; }
      var reader = new FileReader();
      reader.onload = function(e) {
        try {
          _googleKeyDict = JSON.parse(e.target.result);
          var nameEl = document.getElementById('smGoogleKeyName');
          if (nameEl) nameEl.textContent = _googleKeyDict.client_email ? '✔ ' + _googleKeyDict.client_email.split('@')[0] : '✔ loaded';
        } catch(err) {
          _googleKeyDict = null;
          var st = document.getElementById('smGoogleConnStatus');
          if (st) { st.style.color='var(--danger)'; st.textContent = t('m365_google_invalid_json','Invalid JSON file'); }
        }
      };
      reader.readAsText(f);
    });
  });
})();

async function smGoogleConnect() {
  var st = document.getElementById('smGoogleConnStatus');
  var adminEmail = (document.getElementById('smGoogleAdminEmail') || {}).value || '';

  if (!_googleKeyDict) {
    if (st) { st.style.color='var(--danger)'; st.textContent = t('m365_google_key_required','Select a service account JSON key file'); }
    return;
  }
  if (st) { st.style.color='var(--muted)'; st.textContent = t('m365_connecting','Connecting...'); }

  try {
    var r = await fetch('/api/google/auth/connect', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({key_json: _googleKeyDict, admin_email: adminEmail})
    });
    var d = await r.json();
    if (d.error) {
      if (st) { st.style.color='var(--danger)'; st.textContent = d.error; }
      return;
    }
    if (st) { st.style.color='var(--accent)'; st.textContent = '✔ ' + t('m365_connected','Connected'); }
    smGoogleRefreshStatus();
  } catch(e) {
    if (st) { st.style.color='var(--danger)'; st.textContent = e.message; }
  }
}

function smGoogleDisconnect() {
  if (!confirm(t('m365_signout_confirm','Disconnect and clear credentials?'))) return;
  fetch('/api/google/auth/disconnect', {method:'POST'}).then(function() {
    _googleKeyDict = null;
    var fi = document.getElementById('smGoogleKeyFile');
    if (fi) fi.value = '';
    var nameEl = document.getElementById('smGoogleKeyName');
    if (nameEl) nameEl.textContent = '';
    var st = document.getElementById('smGoogleConnStatus');
    if (st) st.textContent = '';
    smGoogleRefreshStatus();
  });
}

async function smGooglePersonalStart() {
  var clientId     = (document.getElementById('smGooglePersonalClientId')     || {}).value || '';
  var clientSecret = (document.getElementById('smGooglePersonalClientSecret') || {}).value || '';
  var st = document.getElementById('smGooglePersonalConnStatus');
  if (!clientId || !clientSecret) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = t('m365_google_personal_creds_required', 'Client ID and secret required'); }
    return;
  }
  if (st) { st.style.color = 'var(--muted)'; st.textContent = t('m365_connecting', 'Connecting...'); }
  try {
    var r = await fetch('/api/google/personal/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({client_id: clientId, client_secret: clientSecret})
    });
    var d = await r.json();
    if (d.error) {
      if (st) { st.style.color = 'var(--danger)'; st.textContent = d.error; }
      return;
    }
    var box    = document.getElementById('smGoogleDeviceBox');
    var codeEl = document.getElementById('smGoogleDeviceCode');
    var urlEl  = document.getElementById('smGoogleDeviceUrl');
    var pollSt = document.getElementById('smGooglePollStatus');
    if (box)    box.style.display  = '';
    if (codeEl) codeEl.textContent = d.user_code || '—';
    if (urlEl)  { urlEl.href = d.verification_url || 'https://google.com/device'; urlEl.textContent = (d.verification_url || 'https://google.com/device').replace('https://', ''); }
    if (pollSt) { pollSt.style.color = 'var(--muted)'; pollSt.textContent = '⏳ ' + t('m365_auth_waiting', 'Waiting for sign-in…'); }
    if (st)     st.textContent = '';
    smGooglePersonalPoll();
  } catch(e) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = e.message; }
  }
}

function smGooglePersonalPoll() {
  fetch('/api/google/personal/poll', {method: 'POST'})
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var pollSt = document.getElementById('smGooglePollStatus');
      if (d.status === 'pending') {
        setTimeout(smGooglePersonalPoll, 3000);
      } else if (d.status === 'ok') {
        if (pollSt) { pollSt.style.color = 'var(--success)'; pollSt.textContent = '✓ ' + t('m365_connected', 'Connected'); }
        setTimeout(function() {
          var box = document.getElementById('smGoogleDeviceBox');
          if (box) box.style.display = 'none';
          smGoogleRefreshStatus();
        }, 1000);
      } else {
        if (pollSt) { pollSt.style.color = 'var(--danger)'; pollSt.textContent = '✗ ' + (d.error || 'Sign-in failed'); }
        setTimeout(function() {
          var box = document.getElementById('smGoogleDeviceBox');
          if (box) box.style.display = 'none';
        }, 3000);
      }
    })
    .catch(function() { setTimeout(smGooglePersonalPoll, 5000); });
}

function smGooglePersonalSignOut() {
  if (!confirm(t('m365_signout_confirm', 'Disconnect and clear credentials?'))) return;
  fetch('/api/google/personal/signout', {method: 'POST'}).then(function() {
    smGoogleRefreshStatus();
  });
}

// Returns {sources, options} reflecting current Google pane state — used by scan launcher
function getGoogleScanOptions() {
  var sources = [];
  if (document.getElementById('smGoogleSrcGmail') && document.getElementById('smGoogleSrcGmail').checked) sources.push('gmail');
  if (document.getElementById('smGoogleSrcDrive') && document.getElementById('smGoogleSrcDrive').checked) sources.push('gdrive');
  return {sources: sources, options: {}};
}

// ── File sources pane ─────────────────────────────────────────────────────────

function srcFileRenderList() {
  const list = document.getElementById('srcFileList');
  if (!list) return;
  if (!S._fileSources.length) {
    list.innerHTML = '<div class="fsrc-empty">'+t('m365_file_sources_empty','No file sources yet.')+'</div>';
    return;
  }
  list.innerHTML = S._fileSources.map(function(s) {
    const isSmb = s.path && (s.path.startsWith('//') || s.path.startsWith('\\\\'));
    const icon  = isSmb ? '\uD83C\uDF10' : '\uD83D\uDCC1';
    const sid   = _esc(s.id||'');
    const slabel = _esc(s.label||s.path||'');
    return '<div class="fsrc-row">'
      +'<div class="fsrc-row-head">'
      +'<span class="fsrc-row-label">'+icon+' '+slabel+'</span>'
      +'<div class="fsrc-actions">'
      +'<button class="btn-scan" onclick="srcFileScan(\''+sid+'\')">&#9654; '+t('m365_fsrc_scan_btn','Scan')+'</button>'
      +'<button class="btn-edit" onclick="srcFileEdit(\''+sid+'\')" style="background:none;border:1px solid var(--border);color:var(--muted);padding:2px 7px;border-radius:4px;font-size:10px;cursor:pointer">'+t('m365_fsrc_edit_btn','Edit')+'</button>'
      +'<button class="btn-del" onclick="srcFileDelete(\''+sid+'\',\''+slabel+'\')">'+t('m365_profile_delete','Delete')+'</button>'
      +'</div></div>'
      +'<div class="fsrc-row-path">'+_esc(s.path||'')+(s.smb_user?'  \u00b7  \uD83D\uDC64 '+_esc(s.smb_user):'')+'</div>'
      +'</div>';
  }).join('');
}

function srcFileDetectSmb() {
  const p = document.getElementById('srcFilePath').value;
  const isSmb = p.startsWith('//') || p.startsWith('\\\\');
  document.getElementById('srcFileSmbFields').style.display = isSmb ? 'flex' : 'none';
  if (isSmb && !document.getElementById('srcFileSmbHost').value) {
    document.getElementById('srcFileSmbHost').value = p.replace(/^[\/\\]+/,'').split(/[\/\\]/)[0];
  }
}

function srcFileAutoName() {
  const labelEl = document.getElementById('srcFileLabel');
  if (labelEl._userEdited) return;
  const p = document.getElementById('srcFilePath').value.trim();
  if (!p) { labelEl.value=''; return; }
  const parts = p.replace(/[\/\\]+$/,'').split(/[\/\\]/);
  if ((p.startsWith('//')||p.startsWith('\\\\')) && parts.filter(function(x){return x;}).length>=2) {
    const segs = parts.filter(function(x){return x;});
    labelEl.value = segs[0]+(segs[1]?' / '+segs[1]:'');
  } else {
    labelEl.value = parts[parts.length-1]||p;
  }
}

async function srcFileAdd() {
  const label   = document.getElementById('srcFileLabel').value.trim();
  const path    = document.getElementById('srcFilePath').value.trim();
  const smbHost = document.getElementById('srcFileSmbHost').value.trim();
  const smbUser = document.getElementById('srcFileSmbUser').value.trim();
  const smbPw   = document.getElementById('srcFileSmbPw').value;
  const stat    = document.getElementById('srcFileStatus');
  if (!label) { stat.style.color='var(--danger)'; stat.textContent=t('m365_fsrc_name_required','Name is required.'); document.getElementById('srcFileLabel').focus(); return; }
  if (!path)  { stat.style.color='var(--danger)'; stat.textContent=t('m365_fsrc_path_required','Path is required.'); return; }
  stat.style.color='var(--muted)'; stat.textContent=t('m365_fsrc_saving','Saving...');
  if (smbPw && smbUser) {
    try { await fetch('/api/file_sources/store_creds',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({smb_host:smbHost,smb_user:smbUser,password:smbPw})}); } catch(e){}
  }
  try {
    const editId = document.getElementById('srcFileEditId');
    const existingId = editId ? editId.value : '';
    const body = {label, path, smb_host:smbHost, smb_user:smbUser};
    if (existingId) body.id = existingId;
    const r = await fetch('/api/file_sources/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d = await r.json();
    if (d.error) { stat.style.color='var(--danger)'; stat.textContent=d.error; return; }
    ['srcFileLabel','srcFilePath','srcFileSmbHost','srcFileSmbUser','srcFileSmbPw'].forEach(function(id){const el=document.getElementById(id);if(el){el.value='';el._userEdited=false;}});
    if (editId) editId.value='';
    const addBtn=document.getElementById('srcFileAddBtn'); if(addBtn) addBtn.textContent=t('m365_fsrc_add_btn','Add');
    document.getElementById('srcFileSmbFields').style.display='none';
    stat.style.color='var(--accent)'; stat.textContent='\u2714 '+t('m365_fsrc_saved','Source saved');
    await _loadFileSources();
    srcFileRenderList();
    log(t('m365_fsrc_saved','Source saved')+': '+label);
  } catch(e){ stat.style.color='var(--danger)'; stat.textContent=e.message; }
}

function srcFileEdit(id) {
  const s = S._fileSources.find(function(x){return x.id===id;});
  if (!s) return;
  const labelEl = document.getElementById('srcFileLabel');
  const pathEl  = document.getElementById('srcFilePath');
  const hostEl  = document.getElementById('srcFileSmbHost');
  const userEl  = document.getElementById('srcFileSmbUser');
  const pwEl    = document.getElementById('srcFileSmbPw');
  const editId  = document.getElementById('srcFileEditId');
  if (labelEl) { labelEl.value = s.label||''; labelEl._userEdited = true; }
  if (pathEl)  pathEl.value  = s.path||'';
  if (hostEl)  hostEl.value  = s.smb_host||'';
  if (userEl)  userEl.value  = s.smb_user||'';
  if (pwEl)    pwEl.value    = s.smb_user ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' : '';
  if (editId)  editId.value  = id;
  const isSmb = (s.path||'').startsWith('//') || (s.path||'').startsWith('\\\\');
  const smbFields = document.getElementById('srcFileSmbFields');
  if (smbFields) smbFields.style.display = isSmb ? 'flex' : 'none';
  const btn = document.getElementById('srcFileAddBtn');
  if (btn) btn.textContent = t('m365_fsrc_save_changes','Save changes');
  const stat = document.getElementById('srcFileStatus');
  if (stat) { stat.style.color='var(--muted)'; stat.textContent='Editing: '+_esc(s.label||s.path||''); }
}

async function srcFileDelete(id, label) {
  if (!confirm(t('m365_profile_delete_confirm','Delete')+' "'+label+'"?')) return;
  await fetch('/api/file_sources/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  await _loadFileSources();
  srcFileRenderList();
}

async function srcFileScan(id) {
  const source = S._fileSources.find(function(s){ return s.id===id; });
  if (!source) return;
  closeSourcesMgmt();
  log(t('m365_fsrc_scan_start','Starting file scan')+': '+(source.label||source.path));
  try {
    const r = await fetch('/api/file_scan/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(source)});
    const d = await r.json();
    if (d.error) log('File scan error: '+d.error,'err');
  } catch(e){ log('File scan error: '+e.message,'err'); }
}

// Redirect old openFileSourcesModal() to the new unified modal
function openFileSourcesModal() { openSourcesMgmt('files'); }
function closeFileSourcesModal() { closeSourcesMgmt(); }

// ── File Sources (#8) ─────────────────────────────────────────────────────────

async function _loadFileSources() {
  try {
    const r = await fetch('/api/file_sources');
    const d = await r.json();
    S._fileSources = d.sources || [];
    _renderFileSources(d.smb_available);
    renderSourcesPanel();
    // Re-apply any pending profile source selection (file sources render after load)
    if (S._pendingProfileSources.length) {
      document.querySelectorAll('#sourcesPanel input[data-source-type="file"]').forEach(function(cb) {
        cb.checked = S._pendingProfileSources.includes(cb.dataset.sourceId);
      });
      S._pendingProfileSources = [];
    }
    // If the profile editor is open and has no file checkboxes yet, re-render it now.
    if (document.getElementById('pmgmtEditor')?.classList.contains('open') &&
        !document.querySelector('#peSourcesPanel input[data-source-type="file"]') &&
        S._fileSources.length > 0) {
      var _peCheckedIds = Array.from(document.querySelectorAll('#peSourcesPanel input[type=checkbox]'))
        .filter(function(cb) { return cb.checked; }).map(function(cb) { return cb.dataset.sourceId; });
      var _peProfile = window._pmgmtEditId ? (S._profiles.find(function(p) { return p.id === window._pmgmtEditId; }) || window._pmgmtNewDraft) : window._pmgmtNewDraft;
      if (_peProfile) {
        var _peSavedIds = (_peProfile.sources||[]).concat(_peProfile.google_sources||[]).concat(_peProfile.file_sources||[]);
        _renderEditorSources(_peCheckedIds.concat(_peSavedIds));
      }
    }
  } catch(e) {
    const s = document.getElementById('fsrcStatus');
    if (s) { s.style.color = 'var(--danger)'; s.textContent = 'Error: ' + e.message; }
  }
}

function _renderFileSources() {
  const list = document.getElementById('fsrcList');
  if (!list) return;
  if (!S._fileSources.length) {
    list.innerHTML = '<div class="fsrc-empty">' + t('m365_file_sources_empty','No file sources yet.') + '</div>';
    return;
  }
  list.innerHTML = S._fileSources.map(function(s) {
    const isSmb = s.path && (s.path.startsWith('//') || s.path.startsWith('\\\\'));
    const icon  = isSmb ? '\uD83C\uDF10' : '\uD83D\uDCC1';
    const userPart = s.smb_user ? '  \u00b7  \uD83D\uDC64 ' + _esc(s.smb_user) : '';
    const sid    = _esc(s.id || '');
    const slabel = _esc(s.label || s.path || '');
    return '<div class="fsrc-row">'
      + '<div class="fsrc-row-head">'
      + '<span class="fsrc-row-label">' + icon + ' ' + slabel + '</span>'
      + '<div class="fsrc-actions">'
      + '<button class="btn-scan" onclick="fsrcScan(\'' + sid + '\')">&#9654; ' + t('m365_fsrc_scan_btn','Scan') + '</button>'
      + '<button class="btn-del"  onclick="fsrcDelete(\'' + sid + '\',\'' + slabel + '\')">' + t('m365_profile_delete','Delete') + '</button>'
      + '</div></div>'
      + '<div class="fsrc-row-path">' + _esc(s.path || '') + userPart + '</div>'
      + '</div>';
  }).join('');
}

function fsrcDetectSmb() {
  const p = document.getElementById('fsrcPath').value;
  const isSmb = p.startsWith('//') || p.startsWith('\\\\');
  document.getElementById('fsrcSmbFields').style.display = isSmb ? 'flex' : 'none';
  if (isSmb && !document.getElementById('fsrcSmbHost').value) {
    document.getElementById('fsrcSmbHost').value = p.replace(/^[\/\\]+/,'').split(/[\/\\]/)[0];
  }
}

function fsrcAutoName() {
  // Suggest a name from the path only if the user hasn't typed one yet
  const labelEl = document.getElementById('fsrcLabel');
  if (labelEl._userEdited) return;
  const p = document.getElementById('fsrcPath').value.trim();
  if (!p) { labelEl.value = ''; return; }
  // Extract last meaningful path segment
  const parts = p.replace(/[/\\]+$/, '').split(/[/\\]/);
  const last = parts[parts.length - 1] || parts[parts.length - 2] || p;
  // For SMB paths like //nas/share use "nas / share"
  if ((p.startsWith('//') || p.startsWith('\\\\')) && parts.length >= 3) {
    const host  = parts.find(function(x){ return x.length > 0; }) || '';
    const share = parts.filter(function(x){ return x.length > 0; })[1] || '';
    labelEl.value = share ? host + ' / ' + share : host;
  } else {
    labelEl.value = last;
  }
}

document.addEventListener('DOMContentLoaded', function() {
  const labelEl = document.getElementById('fsrcLabel');
  if (labelEl) {
    labelEl.addEventListener('input', function() { labelEl._userEdited = !!labelEl.value; });
  }
  const srcFileLabelEl = document.getElementById('srcFileLabel');
  if (srcFileLabelEl) {
    srcFileLabelEl.addEventListener('input', function() { srcFileLabelEl._userEdited = !!srcFileLabelEl.value; });
  }
});

async function fsrcAddSource() {
  const path    = document.getElementById('fsrcPath').value.trim();
  const label   = document.getElementById('fsrcLabel').value.trim() || path;
  const smbHost = document.getElementById('fsrcSmbHost').value.trim();
  const smbUser = document.getElementById('fsrcSmbUser').value.trim();
  const smbPw   = document.getElementById('fsrcSmbPw').value;
  const stat    = document.getElementById('fsrcStatus');
  if (!label) { stat.style.color='var(--danger)'; stat.textContent=t('m365_fsrc_name_required','Name is required.'); document.getElementById('fsrcLabel').focus(); return; }
  if (!path) { stat.style.color='var(--danger)'; stat.textContent=t('m365_fsrc_path_required','Path is required.'); return; }
  stat.style.color='var(--muted)'; stat.textContent=t('m365_fsrc_saving','Saving...');
  if (smbPw && smbUser) {
    try { await fetch('/api/file_sources/store_creds',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({smb_host:smbHost,smb_user:smbUser,password:smbPw})}); } catch(e){}
  }
  try {
    const r = await fetch('/api/file_sources/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label,path,smb_host:smbHost,smb_user:smbUser})});
    const d = await r.json();
    if (d.error) { stat.style.color='var(--danger)'; stat.textContent=d.error; return; }
    ['fsrcLabel','fsrcPath','fsrcSmbHost','fsrcSmbUser','fsrcSmbPw'].forEach(function(id){const el=document.getElementById(id);if(el){el.value='';el._userEdited=false;}});
    document.getElementById('fsrcSmbFields').style.display='none';
    stat.style.color='var(--accent)'; stat.textContent='\u2714 '+t('m365_fsrc_saved','Source saved');
    await _loadFileSources();
    log(t('m365_fsrc_saved','Source saved')+': '+label);
  } catch(e){ stat.style.color='var(--danger)'; stat.textContent=e.message; }
}

async function fsrcDelete(id, label) {
  if (!confirm(t('m365_profile_delete_confirm','Delete')+' "'+label+'"?')) return;
  try {
    await fetch('/api/file_sources/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
    await _loadFileSources();
    log(t('m365_profile_deleted','Deleted')+': '+label);
  } catch(e){ const s=document.getElementById('fsrcStatus'); if(s) s.textContent=e.message; }
}

async function fsrcScan(id) {
  const source = S._fileSources.find(function(s){ return s.id===id; });
  if (!source) return;
  closeFileSourcesModal();
  log(t('m365_fsrc_scan_start','Starting file scan')+': '+(source.label||source.path));
  try {
    const r = await fetch('/api/file_scan/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(source)});
    const d = await r.json();
    if (d.error) log('File scan error: '+d.error,'err');
  } catch(e){ log('File scan error: '+e.message,'err'); }
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.openSourcesMgmt = openSourcesMgmt;
window.closeSourcesMgmt = closeSourcesMgmt;
window.switchSrcTab = switchSrcTab;
window.smRefreshStatus = smRefreshStatus;
window.smConnect = smConnect;
window.smDisconnect = smDisconnect;
window.smGoogleSetMode = smGoogleSetMode;
window.smGoogleRefreshStatus = smGoogleRefreshStatus;
window.smGoogleConnect = smGoogleConnect;
window.smGoogleDisconnect = smGoogleDisconnect;
window.smGooglePersonalStart = smGooglePersonalStart;
window.smGooglePersonalPoll = smGooglePersonalPoll;
window.smGooglePersonalSignOut = smGooglePersonalSignOut;
window.getGoogleScanOptions = getGoogleScanOptions;
window.srcFileRenderList = srcFileRenderList;
window.srcFileDetectSmb = srcFileDetectSmb;
window.srcFileAutoName = srcFileAutoName;
window.srcFileAdd = srcFileAdd;
window.srcFileEdit = srcFileEdit;
window.srcFileDelete = srcFileDelete;
window.srcFileScan = srcFileScan;
window.openFileSourcesModal = openFileSourcesModal;
window.closeFileSourcesModal = closeFileSourcesModal;
window._loadFileSources = _loadFileSources;
window._renderFileSources = _renderFileSources;
window.fsrcDetectSmb = fsrcDetectSmb;
window.fsrcAutoName = fsrcAutoName;
window.fsrcAddSource = fsrcAddSource;
window.fsrcDelete = fsrcDelete;
window.fsrcScan = fsrcScan;
window._googleKeyDict = _googleKeyDict;
window._googleAuthMode = _googleAuthMode;
