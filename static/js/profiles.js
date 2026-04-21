import { S } from './state.js';
// ── Profiles (15c) ───────────────────────────────────────────────────────────


async function loadProfiles() {
  try {
    const r = await fetch('/api/profiles');
    if (!r.ok) return;
    const d = await r.json();
    S._profiles = d.profiles || [];
    _renderProfileSelect();
  } catch(e) { /* profiles not critical */ }
}

function _renderProfileSelect() {
  const sel = document.getElementById('profileSelect');
  if (!sel) return;
  const prev = sel.value;
  // Clear all except the placeholder option (first)
  while (sel.options.length > 1) sel.remove(1);
  for (const p of S._profiles) {
    const opt = document.createElement('option');
    opt.value = p.id;
    const last = p.last_run ? ' — ' + p.last_run.slice(0, 10) : '';
    opt.textContent = p.name + last;
    opt.title = p.description || '';
    sel.appendChild(opt);
  }
  // Restore selection if the profile still exists; else fall back to placeholder
  if (prev && [...sel.options].some(o => o.value === prev)) {
    sel.value = prev;
  } else {
    sel.value = '';
    S._activeProfileId = null;
    const clrBtn = document.getElementById('profileClearBtn');
    if (clrBtn) clrBtn.style.display = 'none';
  }
}

function _setProfileClearBtn(visible) {
  const btn = document.getElementById('profileClearBtn');
  if (btn) btn.style.display = visible ? 'inline-block' : 'none';
}

function onProfileChange() {
  const sel = document.getElementById('profileSelect');
  const id  = sel.value;
  if (!id) return;  // placeholder can't be selected (disabled), guard anyway
  const profile = S._profiles.find(p => p.id === id);
  if (!profile) return;
  S._activeProfileId = id;
  _setProfileClearBtn(true);
  _applyProfile(profile);
}

// Clear the active profile label without touching sidebar settings.
// The sidebar already reflects the loaded (or manually adjusted) state.
function clearActiveProfile() {
  S._activeProfileId = null;
  const sel = document.getElementById('profileSelect');
  if (sel) sel.value = '';
  _setProfileClearBtn(false);
}


function _applyProfile(profile) {
  // ── Sources ──────────────────────────────────────────────────────────────
  // Restore source selections from profile — works for both M365 and file sources.
  // File sources may not be rendered yet (they load async), so store their IDs
  // in S._pendingProfileSources for renderSourcesPanel() to apply after re-render.
  const profileSources = profile.sources || [];
  // Ensure at least M365 source checkboxes are present before reading the DOM.
  // renderSourcesPanel() is idempotent and fast — safe to call here.
  if (!document.querySelector('#sourcesPanel input[data-source-id]') && typeof renderSourcesPanel === 'function') {
    renderSourcesPanel();
  }
  document.querySelectorAll('#sourcesPanel input[data-source-id]').forEach(function(cb) {
    cb.checked = profileSources.includes(cb.dataset.sourceId);
  });
  _updateAccountsVisibility();
  // Deferred file sources — store IDs now, apply when _loadFileSources() resolves.
  // Don't filter against S._fileSources here — it may be empty at this point.
  const _knownSourceIds = new Set(['email', 'onedrive', 'sharepoint', 'teams', 'gmail', 'gdrive']);
  S._pendingProfileSources = (profile.file_sources && profile.file_sources.length)
    ? profile.file_sources.slice()
    : profileSources.filter(function(id) { return !_knownSourceIds.has(id); });
  // Deferred Google sources — store IDs now, apply when smGoogleRefreshStatus() resolves.
  const googleIds = profile.google_sources
    || profileSources.filter(function(id) { return id === 'gmail' || id === 'gdrive'; });
  S._pendingGoogleSources = googleIds.slice();

  // ── Options ───────────────────────────────────────────────────────────────
  const opts = profile.options || {};

  if (opts.email_body !== undefined) {
    const el = document.getElementById('optEmailBody');
    if (el) el.checked = opts.email_body;
  }

  if (opts.attachments !== undefined) {
    const el = document.getElementById('optAttachments');
    if (el) {
      el.checked = opts.attachments;
      // Update the size row opacity directly
      const sizeRow = document.getElementById('attachSizeRow');
      if (sizeRow) sizeRow.style.opacity = opts.attachments ? '1' : '0.4';
    }
  }

  if (opts.max_attach_mb !== undefined) {
    const el = document.getElementById('optMaxAttachMB');
    if (el) el.value = opts.max_attach_mb;
  }

  if (opts.max_emails !== undefined) {
    const el = document.getElementById('optMaxEmails');
    if (el) el.value = opts.max_emails;
  }

  if (opts.delta !== undefined) {
    const el = document.getElementById('optDelta');
    if (el) el.checked = opts.delta;
  }

  if (opts.scan_photos !== undefined) {
    const el = document.getElementById('optScanPhotos');
    if (el) el.checked = opts.scan_photos;
  }

  if (opts.skip_gps_images !== undefined) {
    const el = document.getElementById('optSkipGps');
    if (el) el.checked = opts.skip_gps_images;
  }

  if (opts.min_cpr_count !== undefined) {
    const el = document.getElementById('optMinCpr');
    if (el) el.value = opts.min_cpr_count;
  }

  // ── Date filter ───────────────────────────────────────────────────────────
  const days = opts.older_than_days;
  if (days !== undefined) {
    const hidden  = document.getElementById('olderThan');
    const dateIn  = document.getElementById('olderThanDate');
    const presets = document.querySelectorAll('.date-preset');
    if (hidden) hidden.value = days;
    if (dateIn) {
      if (!days) {
        dateIn.value = '';
      } else {
        const d = new Date();
        d.setDate(d.getDate() - days);
        dateIn.value = d.toISOString().slice(0, 10);
      }
    }
    // Highlight matching preset button
    presets.forEach(p => {
      const y = parseInt(p.dataset.years || '0');
      const presetDays = y === 0 ? 0 : y * 365;
      if (y === 0) {
        p.classList.toggle('selected', !days);
      } else {
        p.classList.toggle('selected', days > 0 && presetDays === days);
      }
    });
  }

  // ── Retention ─────────────────────────────────────────────────────────────
  const retEnabled = !!(opts.retention_enabled || profile.retention_years);
  const retEl = document.getElementById('optRetention');
  if (retEl) {
    retEl.checked = retEnabled;
    // Show/hide panel directly
    const panel = document.getElementById('retentionPanel');
    if (panel) panel.style.display = retEnabled ? 'block' : 'none';
  }
  if (profile.retention_years) {
    const el = document.getElementById('optRetentionYears');
    if (el) el.value = profile.retention_years;
  }
  if (profile.fiscal_year_end) {
    const el = document.getElementById('optFiscalYearEnd');
    if (el) el.value = profile.fiscal_year_end;
  }
  updateRetentionCutoffHint && updateRetentionCutoffHint();

  // ── User selection ────────────────────────────────────────────────────────
  if (profile.user_ids === 'all') {
    if (S._allUsers.length) {
      S._allUsers.forEach(u => { u.selected = true; });
      renderAccountList();
    } else {
      // Users not loaded yet — defer until loadUsers() resolves
      window._pendingProfileAllUsers = true;
    }
  } else if (Array.isArray(profile.user_ids) && profile.user_ids.length) {
    window._pendingProfileUserIds = profile.user_ids.map(u => u.id || u);
    _applyPendingProfileUsers();
  } else if (Array.isArray(profile.user_ids) && profile.user_ids.length === 0) {
    // Explicitly empty list — deselect everyone so previous sidebar state doesn't persist
    S._allUsers.forEach(u => { u.selected = false; });
    if (S._allUsers.length) renderAccountList();
  }

  log(t('m365_profile_applied', 'Profile loaded') + ': ' + profile.name);
}

function _applyPendingProfileUsers() {
  const ids = window._pendingProfileUserIds;
  if (!ids || !ids.length || !S._allUsers.length) return;
  // Select only the users listed in the profile
  S._allUsers.forEach(u => { u.selected = ids.includes(u.id); });
  renderAccountList();
  window._pendingProfileUserIds = null;
}

async function saveCurrentAsProfile() {
  const name = prompt(t('m365_profile_save_prompt', 'Profile name:'),
                      S._activeProfileId
                        ? (S._profiles.find(p => p.id === S._activeProfileId) || {}).name || ''
                        : '');
  if (!name) return;
  const { sources, fileSources, googleSources, allSources, user_ids, options } = buildScanPayload();
  const existing = S._profiles.find(p => p.name.toLowerCase() === name.toLowerCase());
  const profile = {
    id:               existing?.id || '',
    name,
    description:      existing?.description || '',
    sources:          allSources,
    google_sources:   googleSources,
    user_ids,
    options,
    retention_years:  parseInt(document.getElementById('optRetentionYears')?.value) || null,
    fiscal_year_end:  document.getElementById('optFiscalYearEnd')?.value || '',
    email_to:         '',
    file_sources:     fileSources,
  };
  try {
    const r = await fetch('/api/profiles/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(profile)
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    await loadProfiles();
    // Select the newly saved profile
    const sel = document.getElementById('profileSelect');
    if (sel) { sel.value = d.profile.id; S._activeProfileId = d.profile.id; _setProfileClearBtn(true); }
    log(t('m365_profile_saved', 'Profile saved') + ': ' + name);
  } catch(e) {
    alert('Save failed: ' + e.message);
  }
}

// ── Profile management modal (#15d) ──────────────────────────────────────────

function openProfileMgmtModal() {
  try { _renderProfileMgmt(); } catch(e) { console.error('[profiles] _renderProfileMgmt threw:', e); }
  document.getElementById('pmgmtBackdrop').classList.add('open');
  // Auto-open editor for the first profile
  if (S._profiles.length > 0) {
    try { _pmgmtOpenEditor(S._profiles[0].id); } catch(e) { console.error('[profiles] _pmgmtOpenEditor threw:', e); }
  }
}

function closeProfileMgmt() {
  document.getElementById('pmgmtBackdrop').classList.remove('open');
}

function _sourceLabel(id) {
  const known = {email:'Outlook', onedrive:'OneDrive', sharepoint:'SharePoint', teams:'Teams', gmail:'Gmail', gdrive:'Google Drive'};
  if (known[id]) return known[id];
  const fs = S._fileSources.find(s => s.id === id);
  return fs ? (fs.label || fs.path || id) : id;
}

function _renderProfileMgmt() {
  const list = document.getElementById('pmgmtList');
  if (!list) return;
  const saved = S._profiles.filter(p => p.name !== 'Default' || S._profiles.length === 1);
  if (!saved.length) {
    list.innerHTML = `<div class="pmgmt-empty">${t('m365_profile_no_profiles','No saved profiles yet. Use 💾 to save the current sidebar settings as a profile.')}</div>`;
    return;
  }
  list.innerHTML = '';
  for (const p of S._profiles) {
    const sources   = (p.sources || []).map(_sourceLabel).join(', ') || '—';
    const lastRun   = p.last_run ? p.last_run.slice(0,16).replace('T',' ') : t('m365_profile_never','never');
    const isActive  = p.id === S._activeProfileId;
    const row = document.createElement('div');
    row.className = 'pmgmt-row';
    row.dataset.id = p.id;
    row.onclick = function() { _pmgmtOpenEditor(p.id); };
    row.innerHTML = `
      <div class="pmgmt-row-head">
        <span class="pmgmt-name">${_esc(p.name)}${isActive ? ' <span style="color:var(--accent);font-weight:400;font-size:10px">● activ</span>' : ''}</span>
        <div class="pmgmt-actions">
          <div style="display:flex;border:1px solid var(--border);border-radius:5px;overflow:hidden">
            <button class="btn-use" onclick="event.stopPropagation();_pmgmtUse('${p.id}')" style="border-radius:0;border:none;border-right:1px solid var(--border)" data-i18n="m365_profile_use">Brug</button>
            <button onclick="event.stopPropagation();_pmgmtDuplicate('${p.id}')" style="border-radius:0;border:none" data-i18n="m365_profile_duplicate">Kopier</button>
          </div>
          <button class="btn-del" onclick="event.stopPropagation();_pmgmtDelete('${p.id}','${_esc(p.name)}')" data-i18n="m365_profile_delete">Slet</button>
        </div>
      </div>
      <div class="pmgmt-sources">${_esc(sources)}</div>
      ${p.description ? `<div class="pmgmt-desc">${_esc(p.description)}</div>` : ''}
      <div class="pmgmt-meta">${t('m365_profile_last_run','Last run')}: ${lastRun}</div>
    `;
    list.appendChild(row);
  }
}

function _esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _pmgmtUse(id) {
  const profile = S._profiles.find(p => p.id === id);
  if (!profile) return;
  S._activeProfileId = id;
  _setProfileClearBtn(true);
  _applyProfile(profile);
  // Sync the topbar dropdown
  const sel = document.getElementById('profileSelect');
  if (sel) sel.value = id;
  closeProfileMgmt();
}

function _pmgmtOpenEditor(id) {
  const profile = S._profiles.find(p => p.id === id);
  if (!profile) return;
  _openEditorForProfile(profile);
}

function _openEditorForProfile(profile) {
  const id = profile.id || '';
  window._pmgmtEditId = id;
  _pmgmtRoleActive = '';
  // Highlight active row
  document.querySelectorAll('.pmgmt-row').forEach(r => r.classList.toggle('active', id && r.dataset.id === id));
  document.getElementById('pmgmtEditorTitle').textContent = profile.name;
  const body = document.getElementById('pmgmtEditorBody');
  const allSources = profile.sources || [];
  const opts = profile.options || {};
  const srcCheck = (id) => allSources.includes(id) ? 'checked' : '';

  // Build account list from S._allUsers
  const savedIds = new Set((profile.user_ids || []).map(u => u.id || u));
  // If no saved IDs match current users, treat as all-selected (new profile or users changed)
  const anyMatch = savedIds.size > 0 && S._allUsers.some(u => savedIds.has(u.id));
  const accountRows = S._allUsers.map(u => {
    // Only check if the user was explicitly saved — default to unchecked like the main window
    const checked = anyMatch && savedIds.has(u.id) ? 'checked' : '';
    const platBadge = u.platform === 'both' ? '<span style="font-size:9px;padding:1px 5px;border-radius:10px;background:linear-gradient(90deg,#E6F1FB 50%,#EAF3DE 50%);color:#1a4a1a;font-weight:500;border:0.5px solid #b5d4b5">M365+GWS</span>'
      : (u.platform || 'm365') === 'google' ? '<span style="font-size:9px;padding:1px 5px;border-radius:10px;background:#EAF3DE;color:#3B6D11;font-weight:500">GWS</span>'
      : '<span style="font-size:9px;padding:1px 5px;border-radius:10px;background:#E6F1FB;color:#185FA5;font-weight:500">M365</span>';
    const roleBadge = u.userRole === 'student' ? t('role_student','Elev') : u.userRole === 'staff' ? t('role_staff','Ansat') : t('role_other','Anden');
    const roleOverrideStyle = u.roleOverride ? 'color:var(--color-text-info);outline:1px solid var(--color-border-info);' : '';
    return `<label class="pmgmt-acct-row" data-uid="${_esc(u.id)}" data-role="${_esc(u.userRole || 'other')}"><input type="checkbox" ${checked} data-uid="${_esc(u.id)}"><span style="flex:1;color:var(--color-text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(u.displayName)}</span>${platBadge}<button type="button" class="pmgmt-role-badge" data-uid="${_esc(u.id)}" onclick="_pmgmtCycleRole(this.getAttribute('data-uid'),event)" style="font-size:9px;padding:1px 5px;border-radius:10px;background:#D3D1C7;border:none;cursor:pointer;${roleOverrideStyle}">${roleBadge}</button></label>`;
  }).join('');

  body.innerHTML = `
    <div>
      <div class="pmgmt-editor-section-title">Navn</div>
      <input id="pmgmtEditName" type="text" value="${_esc(profile.name)}" style="width:100%;margin-bottom:6px">
      <textarea id="pmgmtEditDesc" style="width:100%;font-size:12px;height:44px;resize:none" placeholder="Beskrivelse (valgfri)">${_esc(profile.description || '')}</textarea>
    </div>
    <div style="display:flex;gap:0;flex:1;min-height:0">
      <div style="flex:1;display:flex;flex-direction:column;gap:14px;overflow-y:auto;padding-right:16px">
        <div>
          <div class="pmgmt-editor-section-title">Kilder</div>
          <div id="peSourcesPanel"></div>
        </div>
        <div>
          <div class="pmgmt-editor-section-title">
            <span>Konti</span>
            <div style="display:flex;gap:4px;align-items:center">
              <div style="display:flex;background:var(--bg);border:1px solid var(--border);border-radius:6px;overflow:hidden">
                <button type="button" id="peRoleAll" onclick="_pmgmtRoleFilter('')" style="font-size:10px;height:22px;padding:0 7px;border:none;border-right:1px solid var(--border);background:var(--accent);color:#fff;cursor:pointer;box-sizing:border-box">${t('m365_filter_all','Alle')}</button>
                <button type="button" id="peRoleStaff" onclick="_pmgmtRoleFilter('staff')" style="font-size:10px;height:22px;padding:0 7px;border:none;border-right:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;box-sizing:border-box">${t('role_staff','Ansat')}</button>
                <button type="button" id="peRoleStudent" onclick="_pmgmtRoleFilter('student')" style="font-size:10px;height:22px;padding:0 7px;border:none;background:none;color:var(--muted);cursor:pointer;box-sizing:border-box">${t('role_student','Elev')}</button>
              </div>
              <div style="display:flex;background:var(--bg);border:1px solid var(--border);border-radius:6px;overflow:hidden">
                <button type="button" onclick="_pmgmtSelectAllAccounts(true)" style="font-size:10px;height:22px;padding:0 7px;border:none;border-right:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;box-sizing:border-box">${t('btn_all','Alle')}</button>
                <button type="button" onclick="_pmgmtSelectAllAccounts(false)" style="font-size:10px;height:22px;padding:0 7px;border:none;background:none;color:var(--muted);cursor:pointer;box-sizing:border-box">${t('btn_none','Ingen')}</button>
              </div>
            </div>
          </div>
          <div style="display:flex;gap:6px;margin-bottom:4px">
            <input type="text" id="pmgmtAcctSearch" placeholder="Søg konti…" style="flex:1;font-size:12px" oninput="_pmgmtFilterAccounts(this.value)">
            <button type="button" onclick="_pmgmtAddManual()" style="font-size:11px;padding:3px 10px;border-radius:5px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;white-space:nowrap">+ Tilføj konto</button>
          </div>
          <div class="pmgmt-account-list" id="pmgmtAcctList">${accountRows}</div>
        </div>
      </div>
      <div class="pmgmt-settings-col" style="overflow-y:auto">
        <div class="pmgmt-editor-section-title">Indstillinger</div>
        <div style="display:flex;flex-direction:column;gap:6px;font-size:12px">
          <label style="font-size:11px;color:var(--muted)">${t('m365_opt_date_from','Scan e-mails/filer fra')}</label>
          <div class="datepicker-wrap">
            <input type="date" id="peOptDate" autocomplete="off" value="${(function(){ if(!opts.older_than_days) return ''; var d=new Date(); d.setDate(d.getDate()-opts.older_than_days); return d.toISOString().slice(0,10); }())}" onchange="_peSetDate(this.value)">
          <div class="date-presets">
            <button type="button" class="date-preset peYearBtn ${(opts.older_than_days||0)===365   ? 'selected' : ''}" data-years="1"  onclick="_peSetYear(1)">${t('m365_preset_1yr','1 år')}</button>
            <button type="button" class="date-preset peYearBtn ${(opts.older_than_days||0)===730   ? 'selected' : ''}" data-years="2"  onclick="_peSetYear(2)">${t('m365_preset_2yr','2 år')}</button>
            <button type="button" class="date-preset peYearBtn ${(opts.older_than_days||0)===1825  ? 'selected' : ''}" data-years="5"  onclick="_peSetYear(5)">${t('m365_preset_5yr','5 år')}</button>
            <button type="button" class="date-preset peYearBtn ${(opts.older_than_days||0)===3650  ? 'selected' : ''}" data-years="10" onclick="_peSetYear(10)">${t('m365_preset_10yr','10 år')}</button>
            <button type="button" class="date-preset peYearBtn ${!(opts.older_than_days)           ? 'selected' : ''}" data-years="0"  onclick="_peSetYear(0)">${t('m365_preset_any','Alle')}</button>
          </div>
          </div>
          <input type="hidden" id="peOptDays" value="${opts.older_than_days || 0}">
          <hr style="border:none;border-top:1px solid var(--pmgmt-divider);margin:2px 0">
          <div class="pmgmt-opt-row"><span>${t('m365_opt_email_body','Scan e-mailindhold')}</span><label class="toggle"><input type="checkbox" id="peOptBody" ${opts.email_body !== false ? 'checked' : ''}><span class="toggle-slider"></span></label></div>
          <div class="pmgmt-opt-row"><span>${t('m365_opt_attachments','Scan vedhæftede filer')}</span><label class="toggle"><input type="checkbox" id="peOptAtt" ${opts.attachments !== false ? 'checked' : ''}><span class="toggle-slider"></span></label></div>
          <div class="pmgmt-opt-row"><span style="color:var(--muted)">${t('m365_opt_max_attach','Maks. vedhæftet filstørrelse (MB)')}</span><input type="number" id="peOptMaxAttach" value="${opts.max_attach_mb || 20}" min="1" max="100" style="width:46px;padding:3px 6px;font-size:11px;text-align:right"></div>
          <div class="pmgmt-opt-row"><span>${t('m365_opt_max_emails','Maks. e-mails pr. bruger')}</span><input type="number" id="peOptMaxEmails" value="${opts.max_emails || 2000}" min="10" max="50000" style="width:56px;padding:3px 6px;font-size:11px;text-align:right"></div>
          <div class="pmgmt-opt-row"><span>${t('m365_opt_delta','Delta-scanning')}</span><label class="toggle"><input type="checkbox" id="peOptDelta" ${opts.delta ? 'checked' : ''}><span class="toggle-slider"></span></label></div>
          <div class="pmgmt-opt-row"><span>${t('m365_opt_scan_photos','Søg efter ansigter i billeder')}</span><label class="toggle"><input type="checkbox" id="peOptPhotos" ${opts.scan_photos ? 'checked' : ''}><span class="toggle-slider"></span></label></div>
          <div class="pmgmt-opt-row"><span>${t('m365_opt_skip_gps','Ignorer GPS i billeder')}</span><label class="toggle"><input type="checkbox" id="peOptSkipGps" ${opts.skip_gps_images ? 'checked' : ''}><span class="toggle-slider"></span></label></div>
          <div class="pmgmt-opt-row"><span style="color:var(--muted)">${t('m365_opt_min_cpr','Min. CPR-antal pr. fil')}</span><input type="number" id="peOptMinCpr" value="${opts.min_cpr_count || 1}" min="1" max="50" style="width:46px;padding:3px 6px;font-size:11px;text-align:right"></div>
          <hr style="border:none;border-top:1px solid var(--pmgmt-divider);margin:2px 0">
          <div class="pmgmt-opt-row"><span>${t('m365_opt_retention','Opbevaringspolitik')}</span><label class="toggle"><input type="checkbox" id="peOptRetention" ${profile.retention_years ? 'checked' : ''}><span class="toggle-slider"></span></label></div>
          <div style="padding:7px 8px;background:var(--bg);border-radius:6px">
            <div class="pmgmt-opt-row" style="margin-bottom:5px"><span style="color:var(--muted)">${t('m365_ret_years','Opbevaringsår')}</span><input type="number" id="peOptRetYears" value="${profile.retention_years || 5}" min="1" max="30" style="width:46px;padding:3px 6px;font-size:11px;text-align:right"></div>
            <div style="display:flex;flex-direction:column;gap:3px">
              <label style="font-size:11px;color:var(--muted)">${t('m365_ret_fy_end','Regnskabsår slut')}</label>
              <select id="peOptFiscalYearEnd" style="font-size:11px;padding:3px 6px;width:100%">
                <option value="" ${!profile.fiscal_year_end ? 'selected' : ''}>${t('m365_ret_fy_rolling','Rullende (i dag)')}</option>
                <option value="12-31" ${profile.fiscal_year_end==='12-31' ? 'selected' : ''}>${t('m365_ret_fy_dec','31 dec (Bogføringsloven)')}</option>
                <option value="06-30" ${profile.fiscal_year_end==='06-30' ? 'selected' : ''}>${t('m365_ret_fy_jun','30 jun')}</option>
                <option value="03-31" ${profile.fiscal_year_end==='03-31' ? 'selected' : ''}>${t('m365_ret_fy_mar','31 mar')}</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;;
  document.getElementById('pmgmtEditorPlaceholder')?.remove();
  document.getElementById('pmgmtEditor').classList.add('open');
  _renderEditorSources((profile.sources || []).concat(profile.google_sources || []).concat(profile.file_sources || []));
}

function _peSetDate(val) {
  if (!val) return;
  const ms   = new Date() - new Date(val);
  const days = Math.round(ms / 86400000);
  const hidden = document.getElementById('peOptDays');
  if (hidden) hidden.value = days;
  // Clear selected year buttons since user picked a custom date
  document.querySelectorAll('.peYearBtn').forEach(b => b.classList.remove('selected'));
}

function _peSetYear(years) {
  const days = years === 0 ? 0 : years * 365;
  const hidden = document.getElementById('peOptDays');
  if (hidden) hidden.value = days;
  document.querySelectorAll('.peYearBtn').forEach(function(btn) {
    const y = parseInt(btn.dataset.years);
    const active = (years === 0 && y === 0) || (years > 0 && y === years);
    btn.classList.toggle('selected', active);
  });
  // Sync the date input
  var dateInput = document.getElementById('peOptDate');
  if (dateInput) {
    if (days === 0) { dateInput.value = ''; }
    else { var d = new Date(); d.setDate(d.getDate()-days); dateInput.value = d.toISOString().slice(0,10); }
  }
}

function _renderEditorSources(checkedIds) {
  const panel = document.getElementById('peSourcesPanel');
  if (!panel) return;
  let html = '';
  _M365_SOURCES.forEach(function(s) {
    const toggle = s.toggleId ? document.getElementById(s.toggleId) : null;
    if (toggle && !toggle.checked) return;
    const isChecked = checkedIds.includes(s.id);
    html += '<label class="source-check">'
      + '<input type="checkbox" data-source-id="' + s.id + '" data-source-type="m365"' + (isChecked ? ' checked' : '') + '>'
      + '<span class="source-icon">' + s.icon + '</span>'
      + '<span class="source-label">' + t(s.labelKey, s.labelDefault) + '</span>'
      + '</label>';
  });
  if (window._googleConnected) {
    var gmailOn = !document.getElementById('smGoogleSrcGmail') || document.getElementById('smGoogleSrcGmail').checked;
    var driveOn = !document.getElementById('smGoogleSrcDrive') || document.getElementById('smGoogleSrcDrive').checked;
    if (gmailOn || driveOn) html += '<hr style="border:none;border-top:1px solid var(--border);margin:4px 0">';
    if (gmailOn) {
      html += '<label class="source-check"><input type="checkbox" data-source-id="gmail" data-source-type="google"' + (checkedIds.includes('gmail') ? ' checked' : '') + '><span class="source-icon">📧</span><span class="source-label">Gmail</span></label>';
    }
    if (driveOn) {
      html += '<label class="source-check"><input type="checkbox" data-source-id="gdrive" data-source-type="google"' + (checkedIds.includes('gdrive') ? ' checked' : '') + '><span class="source-icon">📁</span><span class="source-label">Google Drive</span></label>';
    }
  }
  if (S._fileSources.length > 0) {
    html += '<hr style="border:none;border-top:1px solid var(--border);margin:4px 0">';
    S._fileSources.forEach(function(s) {
      const isSmb = s.path && (s.path.startsWith('//') || s.path.startsWith('\\\\'));
      html += '<label class="source-check"><input type="checkbox" data-source-id="' + _esc(s.id) + '" data-source-type="file"' + (checkedIds.includes(s.id) ? ' checked' : '') + '><span class="source-icon">' + (isSmb ? '🌐' : '📁') + '</span><span class="source-label" title="' + _esc(s.path||'') + '">' + _esc(s.label||s.path||s.id) + '</span></label>';
    });
  }
  panel.innerHTML = html;
}

function _pmgmtNewProfile() {
  // Create a blank profile shell and open the editor
  const blank = {
    id:          '',
    name:        '',
    description: '',
    sources:     [],
    google_sources: [],
    user_ids:    [],
    options:     {},
    file_sources: [],
  };
  // Temporarily add to S._profiles so the editor can find it
  window._pmgmtNewDraft = blank;
  _openEditorForProfile(blank);
}

function _pmgmtCloseEditor() {
  document.getElementById('pmgmtEditor').classList.remove('open');
  document.querySelectorAll('.pmgmt-row').forEach(r => r.classList.remove('active'));
  window._pmgmtEditId = null;
  closeProfileMgmt();
}

async function _pmgmtCycleRole(uid, event) {
  event.stopPropagation();
  if (typeof cycleUserRole !== 'function') return;
  await cycleUserRole(uid);
  // Refresh the badge inside the profile modal to reflect the new role
  const u = S._allUsers.find(function(u){ return u.id === uid; });
  if (!u) return;
  const lbl = document.querySelector('#pmgmtAcctList label[data-uid="' + uid.replace(/"/g, '\\"') + '"]');
  if (!lbl) return;
  const badge = lbl.querySelector('.pmgmt-role-badge');
  if (!badge) return;
  const roleText = u.userRole === 'student' ? t('role_student','Elev')
                 : u.userRole === 'staff'   ? t('role_staff','Ansat')
                 : t('role_other','Anden');
  badge.textContent = roleText;
  lbl.dataset.role  = u.userRole || 'other';
  badge.style.color   = u.roleOverride ? 'var(--color-text-info)' : '';
  badge.style.outline = u.roleOverride ? '1px solid var(--color-border-info)' : '';
}

function _pmgmtSelectAllAccounts(checked) {
  document.querySelectorAll('#pmgmtAcctList label input[type=checkbox]').forEach(function(cb) {
    if (cb.closest('label').style.display !== 'none') cb.checked = checked;
  });
}

let _pmgmtRoleActive = '';
function _pmgmtRoleFilter(role) {
  _pmgmtRoleActive = role;
  // Update button styles
  ['peRoleAll','peRoleStaff','peRoleStudent'].forEach(function(id) {
    const btn = document.getElementById(id);
    if (!btn) return;
    const isActive = (id === 'peRoleAll' && role === '') || (id === 'peRoleStaff' && role === 'staff') || (id === 'peRoleStudent' && role === 'student');
    btn.style.background = isActive ? 'var(--accent)' : 'none';
    btn.style.color      = isActive ? '#fff' : 'var(--muted)';
    btn.style.border     = isActive ? '1px solid var(--accent)' : '1px solid var(--border)';
  });
  // Apply filter combined with any active text search
  _pmgmtFilterAccounts(document.getElementById('pmgmtAcctSearch')?.value || '');
}

function _pmgmtAddManual() {
  const email = prompt('E-mail adresse:');
  if (!email || !email.trim()) return;
  const list = document.getElementById('pmgmtAcctList');
  if (!list) return;
  const id = 'manual:' + email.trim().toLowerCase();
  if (list.querySelector(`input[data-uid="${id}"]`)) return;  // already exists
  const lbl = document.createElement('label');
  lbl.className = 'pmgmt-acct-row';
  lbl.innerHTML = `<input type="checkbox" checked data-uid="${_esc(id)}"><span style="flex:1;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(email.trim())}</span><span style="font-size:9px;padding:1px 5px;border-radius:10px;background:#D3D1C7;color:#444441">Manuel</span>`;
  list.appendChild(lbl);
}

function _pmgmtFilterAccounts(q) {
  q = (q || '').toLowerCase();
  document.querySelectorAll('#pmgmtAcctList label').forEach(function(lbl) {
    var name   = (lbl.querySelector('span') || {}).textContent || '';
    var role   = lbl.dataset.role || 'other';
    var roleOk = !_pmgmtRoleActive || role === _pmgmtRoleActive;
    var nameOk = !q || name.toLowerCase().includes(q);
    lbl.style.display = (roleOk && nameOk) ? '' : 'none';
  });
}

async function _pmgmtSaveFullEdit() {
  const id = window._pmgmtEditId;
  const profile = (id ? S._profiles.find(p => p.id === id) : null) || window._pmgmtNewDraft || {};
  const name = document.getElementById('pmgmtEditName')?.value?.trim();
  if (!name) { alert(t('m365_profile_name_required','Profile name is required.')); return; }
  const peSources     = Array.from(document.querySelectorAll('#peSourcesPanel input[type=checkbox]:checked'));
  const m365Sources   = peSources.filter(cb => cb.dataset.sourceType === 'm365').map(cb => cb.dataset.sourceId);
  const googleSources = peSources.filter(cb => cb.dataset.sourceType === 'google').map(cb => cb.dataset.sourceId);
  const fileSources   = peSources.filter(cb => cb.dataset.sourceType === 'file').map(cb => cb.dataset.sourceId);
  // Check whether the checkboxes were actually rendered in the editor DOM —
  // NOT whether Google is connected or file sources are loaded. Those are async
  // and may not have resolved when the editor first opened, leaving the panel
  // without checkboxes even though the connection exists. Using the DOM as the
  // source of truth avoids a race-condition that silently cleared google/file sources.
  const googleRendered = !!document.querySelector('#peSourcesPanel input[data-source-type="google"]');
  const fileRendered   = !!document.querySelector('#peSourcesPanel input[data-source-type="file"]');
  const effectiveGoogleSources = googleRendered ? googleSources : (profile.google_sources || []);
  const effectiveFileSources   = fileRendered   ? fileSources   : (profile.file_sources   || []);
  const allSources    = m365Sources.concat(effectiveGoogleSources).concat(effectiveFileSources);
  const user_ids = Array.from(document.querySelectorAll('#pmgmtAcctList input[type=checkbox]:checked'))
    .map(cb => cb.dataset.uid)
    .filter(Boolean);
  const updated = {
    ...profile,
    name,
    description: document.getElementById('pmgmtEditDesc')?.value?.trim() || '',
    sources:        allSources,
    google_sources: effectiveGoogleSources,
    file_sources:   effectiveFileSources,
    user_ids,
    options: {
      ...(profile.options || {}),
      older_than_days: parseInt(document.getElementById('peOptDays')?.value) || 0,
      email_body:      document.getElementById('peOptBody')?.checked ?? true,
      attachments:     document.getElementById('peOptAtt')?.checked ?? true,
      max_attach_mb:   parseInt(document.getElementById('peOptMaxAttach')?.value) || 20,
      max_emails:      parseInt(document.getElementById('peOptMaxEmails')?.value) || 2000,
      delta:           document.getElementById('peOptDelta')?.checked ?? false,
      scan_photos:     document.getElementById('peOptPhotos')?.checked ?? false,
      skip_gps_images: document.getElementById('peOptSkipGps')?.checked ?? false,
      min_cpr_count:   parseInt(document.getElementById('peOptMinCpr')?.value) || 1,
    },
    retention_years:  document.getElementById('peOptRetention')?.checked ? (parseInt(document.getElementById('peOptRetYears')?.value) || 5) : null,
    fiscal_year_end:  document.getElementById('peOptRetention')?.checked ? (document.getElementById('peOptFiscalYearEnd')?.value || '') : '',
  };
  try {
    const r = await fetch('/api/profiles/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(updated)
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    await loadProfiles();
    _renderProfileMgmt();
    window._pmgmtNewDraft = null;
    log(t('m365_profile_saved','Profile saved') + ': ' + name);
    // Show inline saved feedback without closing the modal
    const footer = document.querySelector('#pmgmtEditor > div:last-child');
    if (footer) {
      const fb = document.createElement('span');
      fb.textContent = '✓ ' + t('m365_profile_saved', 'Saved');
      fb.style.cssText = 'font-size:11px;color:var(--success);margin-right:auto';
      footer.prepend(fb);
      setTimeout(function() { fb.remove(); }, 2000);
    }
    // Re-open the editor for the saved profile so it reflects the saved state
    const saved = S._profiles.find(function(p) { return p.name === name; });
    if (saved) {
      window._pmgmtEditId = saved.id;
      document.querySelectorAll('.pmgmt-row').forEach(r => r.classList.toggle('active', r.dataset.id === saved.id));
    }
  } catch(e) { alert('Save failed: ' + e.message); }
}


async function _pmgmtSaveEdit(id) {
  const name = document.getElementById(`pmgmt-edit-name-${id}`)?.value?.trim();
  const desc = document.getElementById(`pmgmt-edit-desc-${id}`)?.value?.trim();
  if (!name) { alert(t('m365_profile_name_required','Profile name is required.')); return; }
  const profile = S._profiles.find(p => p.id === id);
  if (!profile) return;
  const updated = { ...profile, name, description: desc || '' };
  try {
    const r = await fetch('/api/profiles/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(updated)
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    await loadProfiles();
    _renderProfileMgmt();
    log(t('m365_profile_saved','Profile saved') + ': ' + name);
  } catch(e) { alert('Save failed: ' + e.message); }
}

async function _pmgmtDuplicate(id) {
  const profile = S._profiles.find(p => p.id === id);
  if (!profile) return;
  const base = profile.name.replace(/ \(copy( \d+)?\)$/, '');
  // Find a unique name
  let n = 1, name = base + ' (copy)';
  while (S._profiles.some(p => p.name === name)) { n++; name = `${base} (copy ${n})`; }
  const copy = { ...profile, id: '', name, last_run: null, last_scan_id: null };
  try {
    const r = await fetch('/api/profiles/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(copy)
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    await loadProfiles();
    _renderProfileMgmt();
    log(t('m365_profile_duplicated','Profile duplicated') + ': ' + name);
  } catch(e) { alert('Duplicate failed: ' + e.message); }
}

async function _pmgmtDelete(id, name) {
  if (!confirm(t('m365_profile_delete_confirm','Delete profile') + ' "' + name + '"?')) return;
  try {
    const r = await fetch('/api/profiles/delete', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ id })
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    if (S._activeProfileId === id) { S._activeProfileId = null; _setProfileClearBtn(false); }
    await loadProfiles();
    _renderProfileMgmt();
    log(t('m365_profile_deleted','Profile deleted') + ': ' + name);
  } catch(e) { alert('Delete failed: ' + e.message); }
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.loadProfiles = loadProfiles;
window._renderProfileSelect = _renderProfileSelect;
window._setProfileClearBtn = _setProfileClearBtn;
window.onProfileChange = onProfileChange;
window.clearActiveProfile = clearActiveProfile;
window._applyProfile = _applyProfile;
window._applyPendingProfileUsers = _applyPendingProfileUsers;
window.saveCurrentAsProfile = saveCurrentAsProfile;
window.openProfileMgmtModal = openProfileMgmtModal;
window.closeProfileMgmt = closeProfileMgmt;
window._sourceLabel = _sourceLabel;
window._renderProfileMgmt = _renderProfileMgmt;
window._esc = _esc;
window._pmgmtUse = _pmgmtUse;
window._pmgmtOpenEditor = _pmgmtOpenEditor;
window._openEditorForProfile = _openEditorForProfile;
window._peSetDate = _peSetDate;
window._peSetYear = _peSetYear;
window._renderEditorSources = _renderEditorSources;
window._pmgmtNewProfile = _pmgmtNewProfile;
window._pmgmtCloseEditor = _pmgmtCloseEditor;
window._pmgmtCycleRole = _pmgmtCycleRole;
window._pmgmtSelectAllAccounts = _pmgmtSelectAllAccounts;
window._pmgmtRoleFilter = _pmgmtRoleFilter;
window._pmgmtAddManual = _pmgmtAddManual;
window._pmgmtFilterAccounts = _pmgmtFilterAccounts;
window._pmgmtSaveFullEdit = _pmgmtSaveFullEdit;
window._pmgmtSaveEdit = _pmgmtSaveEdit;
window._pmgmtDuplicate = _pmgmtDuplicate;
window._pmgmtDelete = _pmgmtDelete;
window._pmgmtRoleActive = _pmgmtRoleActive;
