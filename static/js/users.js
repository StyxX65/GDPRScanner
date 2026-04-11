import { S } from './state.js';
// ── Accounts ──────────────────────────────────────────────────────────────────

async function loadUsers() {
  const list    = document.getElementById('accountsList');
  const loading = document.getElementById('accountsLoading');
  if (!list) return;
  if (loading) loading.textContent = t('lbl_loading', 'Loading…');
  // Ensure source panel checkboxes exist before we render the account list
  if (!document.querySelector('#sourcesPanel input') && typeof renderSourcesPanel === 'function') {
    renderSourcesPanel();
  }
  try {
    const r = await fetch('/api/users');
    if (!r.ok) { if (loading) loading.textContent = 'Could not load users'; return; }
    const d = await r.json();
    if (d.error) { if (loading) loading.textContent = d.error; return; }
    // Merge with any manually-added users, preserving them
    const fetched = d.users || [];
    fetched.forEach(u => { u.platform = 'm365'; });
    const existingManual = S._allUsers.filter(u => u.manual);
    const fetchedIds = new Set(fetched.map(u => u.id));
    const toAdd = existingManual.filter(u => !fetchedIds.has(u.id));
    // Preserve existing selected state for users already in S._allUsers;
    // new users default to selected=true
    const prevSelected = new Map(S._allUsers.map(u => [u.id, u.selected]));
    fetched.forEach(u => {
      u.selected = prevSelected.has(u.id) ? prevSelected.get(u.id) : false;
    });
    S._allUsers = [...fetched, ...toAdd];
    renderAccountList(fetched.length <= 1);
    // Merge Google users separately so they're not blocked by M365 auth timing
    _mergeGoogleUsers();
    checkCheckpoint();
    checkDeltaStatus();
    _applyPendingProfileUsers();

    // Show warning banner when no users could be classified
    const warn = document.getElementById('skuWarnBanner');
    if (warn) {
      const allOther = fetched.length > 0 && fetched.every(u => u.userRole === 'other');
      warn.style.display = allOther ? 'block' : 'none';
    }
  } catch(e) {
    if (loading) loading.textContent = 'Could not load users';
  }
}

async function _mergeGoogleUsers() {
  if (!window._googleConnected) return;
  try {
    var gr = await fetch('/api/google/scan/users');
    if (!gr.ok) return;
    var gd = await gr.json();
    if (gd.error) return;
    var prevSelected = new Map(S._allUsers.map(function(u){ return [u.id, u.selected]; }));

    // Build displayName → Google user map for cross-platform matching
    // Both M365 and GWS are maintained from AD — full name is identical
    var googleByName = {};
    (gd.users || []).forEach(function(gu) {
      var name = (gu.displayName || '').trim().toLowerCase();
      if (name) googleByName[name] = gu;
    });

    // Merge onto M365 users where display name matches
    var matchedNames = new Set();
    S._allUsers.forEach(function(u) {
      if ((u.platform || 'm365') !== 'm365') return;
      var name = (u.displayName || '').trim().toLowerCase();
      var gu = googleByName[name];
      if (gu) {
        u.platform    = 'both';
        u.googleEmail = gu.email;
        // Keep M365 displayName (from AD, authoritative)
        matchedNames.add(name);
      } else {
        // Clear previous merge if Google disconnected
        delete u.googleEmail;
        u.platform = 'm365';
      }
    });

    // Add unmatched Google users as standalone entries
    var googleUsers = [];
    (gd.users || []).forEach(function(gu) {
      var name = (gu.displayName || '').trim().toLowerCase();
      if (matchedNames.has(name)) return;  // already merged
      var uid = 'google:' + gu.email;
      googleUsers.push({
        id:          uid,
        displayName: gu.displayName || gu.email,
        email:       gu.email,
        userRole:    gu.userRole || 'other',
        platform:    'google',
        selected:    prevSelected.has(uid) ? prevSelected.get(uid) : false,
      });
    });

    // Remove stale standalone Google users, add fresh unmatched ones
    S._allUsers = S._allUsers.filter(function(u){ return (u.platform||'m365') !== 'google'; });
    S._allUsers = S._allUsers.concat(googleUsers);
    renderAccountList();
  } catch(e) { /* Google users unavailable */ }
}

let _activeRoleFilter = '';  // '' = all, 'staff', 'student'

// ── Sidebar section collapse ──────────────────────────────────────────────────
const _COLLAPSE_SECTIONS = ['sourcesPanelSection', 'optionsSection', 'accountsSection', 'logSection'];

function toggleSection(id) {
  const body = document.getElementById(id + 'Body');
  if (!body) return;
  const collapsing = body.style.display !== 'none';
  body.style.display = collapsing ? 'none' : '';
  const btn = document.getElementById(id + '-btn');
  if (btn) btn.textContent = collapsing ? '▸' : '▾';
  if (id === 'accountsSection') {
    const sec = document.getElementById('accountsSection');
    if (sec) sec.style.flex = collapsing ? '0 0 auto' : '1';
  }
  try { localStorage.setItem('sc_' + id, collapsing ? '1' : '0'); } catch(e) {}
}

function restoreSectionStates() {
  _COLLAPSE_SECTIONS.forEach(function(id) {
    try {
      if (localStorage.getItem('sc_' + id) === '1') {
        const body = document.getElementById(id + 'Body');
        if (body) body.style.display = 'none';
        const btn = document.getElementById(id + '-btn');
        if (btn) btn.textContent = '▸';
        if (id === 'accountsSection') {
          const sec = document.getElementById('accountsSection');
          if (sec) sec.style.flex = '0 0 auto';
        }
      }
    } catch(e) {}
  });
}

// ── Role filter with counts ───────────────────────────────────────────────────
function updateRoleFilterCounts() {
  const total   = S._allUsers.filter(function(u){ return !u.manual; }).length;
  const staff   = S._allUsers.filter(function(u){ return !u.manual && u.userRole === 'staff'; }).length;
  const student = S._allUsers.filter(function(u){ return !u.manual && u.userRole === 'student'; }).length;
  const btnAll  = document.getElementById('rfAll');
  const btnStaff   = document.getElementById('rfStaff');
  const btnStudent = document.getElementById('rfStudent');
  if (btnAll)     btnAll.textContent     = t('m365_role_all','All') + (total   ? ' (' + total   + ')' : '');
  if (btnStaff)   btnStaff.textContent   = t('role_staff','Ansat') + (staff   ? ' (' + staff   + ')' : '');
  if (btnStudent) btnStudent.textContent = t('role_student','Elev') + (student ? ' (' + student + ')' : '');
}

function setRoleFilter(role) {
  _activeRoleFilter = role;
  [['rfAll',''],['rfStaff','staff'],['rfStudent','student']].forEach(function(pair) {
    const btn = document.getElementById(pair[0]);
    if (!btn) return;
    const active = role === pair[1];
    btn.style.background = active ? 'var(--accent)' : 'none';
    btn.style.color      = active ? '#fff' : 'var(--muted)';
  });
  updateRoleFilterCounts();
  filterUsers();
}

// ── Last scan summary (empty state) ──────────────────────────────────────────
async function loadLastScanSummary() {
  try {
    const r = await fetch('/api/db/stats');
    const d = await r.json();
    if (!d.scan_id || S.flaggedData.length > 0) return;
    const panel = document.getElementById('lastScanSummary');
    const empty = document.getElementById('emptyState');
    if (!panel || !empty) return;

    const dateStr = d.finished_at
      ? new Date(d.finished_at * 1000).toLocaleDateString('da-DK', {day:'numeric', month:'short', year:'numeric'})
      : '—';
    const sources = Object.keys(d.by_source || {});
    const srcLabels = {'email':'Outlook','onedrive':'OneDrive','sharepoint':'SharePoint','teams':'Teams',
                       'gmail':'Gmail','gdrive':'Drive','local':'Lokale filer','smb':'SMB'};
    const srcStr = sources.map(function(s){ return srcLabels[s] || s; }).join(' · ') || '—';

    panel.innerHTML =
      '<div class="last-scan-card">' +
        '<h3>' + t('last_scan_title', 'Seneste scanning') + '</h3>' +
        '<div class="last-scan-stats">' +
          '<div class="last-scan-stat"><span class="val">' + (d.flagged_count || 0) + '</span><span class="lbl">' + t('last_scan_hits', 'Fund') + '</span></div>' +
          '<div class="last-scan-stat"><span class="val">' + (d.unique_subjects || 0) + '</span><span class="lbl">' + t('last_scan_subjects', 'Unikke CPR') + '</span></div>' +
          '<div class="last-scan-stat"><span class="val">' + (d.total_scanned || 0) + '</span><span class="lbl">' + t('last_scan_scanned', 'Scannet') + '</span></div>' +
        '</div>' +
        '<div style="margin-top:12px;font-size:11px;color:var(--muted)">' + dateStr + ' &nbsp;·&nbsp; ' + srcStr + '</div>' +
      '</div>' +
      '<div class="empty-text" style="font-size:12px">' + t('m365_empty_hint', 'Vælg kilder og klik på <strong>Scan</strong><br>for at starte en ny scanning') + '</div>';

    empty.style.display = 'none';
    panel.style.display = 'flex';
  } catch(e) {}
}

function renderAccountList(showAdminNote = false) {
  updateRoleFilterCounts();
  const list = document.getElementById('accountsList');
  if (!list) return;
  const q = (document.getElementById('userSearch')?.value || '').toLowerCase().trim();

  let visible = S._allUsers;

  // Filter by platform: only show accounts relevant to checked sources
  // If the sources panel hasn't been rendered yet (no checkboxes at all), treat M365 as active
  var panelHasAny = !!document.querySelector('#sourcesPanel input[data-source-type]');
  var hasM365Src   = panelHasAny
    ? !!document.querySelector('#sourcesPanel input[data-source-type="m365"]:checked')
    : S._allUsers.some(function(u){ return !u.platform || u.platform === 'm365' || u.platform === 'both'; });
  var hasGoogleSrc = !!document.querySelector('#sourcesPanel input[data-source-type="google"]:checked');
  // Always filter — if neither is active, show nothing
  // Check if Google is enabled in Source Management (not just selected in KILDER)
  var googleEnabled = !!(document.getElementById('smGoogleSrcGmail') && document.getElementById('smGoogleSrcGmail').checked)
                   || !!(document.getElementById('smGoogleSrcDrive') && document.getElementById('smGoogleSrcDrive').checked);
  var effectiveGws = hasGoogleSrc && googleEnabled;
  visible = visible.filter(function(u) {
    var plat = u.platform || 'm365';
    if (plat === 'both') return hasM365Src || effectiveGws;
    return (plat === 'm365' && hasM365Src) || (plat === 'google' && effectiveGws);
  });

  // Apply role filter first
  if (_activeRoleFilter) {
    visible = visible.filter(u => (u.userRole || 'other') === _activeRoleFilter);
  }

  // Then apply text search
  if (q) {
    visible = visible.filter(u =>
      (u.displayName || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q));
  }

  _updateUserCountBadge(visible.length, S._allUsers.length);

  const note = (!q && !_activeRoleFilter && showAdminNote)
    ? `<div style="font-size:10px;color:var(--muted);padding:4px 0 6px;line-height:1.4">${t('m365_admin_note','Only showing your account. To list all users, an admin must grant <strong>User.Read.All</strong> consent.')}</div>`
    : '';

  const noMatch = (q || _activeRoleFilter) && !visible.length
    ? `<div style="padding:4px 0;color:var(--muted);font-size:11px">${t('m365_no_users_match','No users match')} "${q || _activeRoleFilter}"</div>`
    : '';

  list.innerHTML = note + noMatch + visible.map(u => `
    <label style="display:flex;align-items:center;gap:7px;padding:2px 0;cursor:pointer">
      <input type="checkbox" class="account-check" data-id="${u.id}" data-name="${u.displayName}" data-role="${u.userRole || 'other'}"
             ${u.selected !== false ? 'checked' : ''}
             onchange="onAccountCheckChange('${u.id}', this.checked)">
      <span style="flex:1;overflow:hidden">
        <span style="display:block;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${u.displayName}${u.isMe ? ' <span style=\'color:var(--accent);font-size:10px\'>(you)</span>' : ''}${u.manual ? ' <span style=\'color:var(--muted);font-size:10px\'>(manual)</span>' : ''}</span>
        <span style="color:var(--muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block">${u.email}</span>
      </span>
      <span style="font-size:9px;padding:1px 5px;border-radius:10px;flex-shrink:0;"
            class="${u.platform==='both' ? (hasM365Src && effectiveGws ? 'plat-badge-both' : effectiveGws ? 'plat-badge-google' : 'plat-badge-m365') : (u.platform||'m365')==='google' ? 'plat-badge-google' : 'plat-badge-m365'}">
        ${u.platform==='both' ? (hasM365Src && effectiveGws ? 'M365 + GWS' : effectiveGws ? 'GWS' : 'M365') : (u.platform||'m365')==='google' ? 'GWS' : 'M365'}
      </span>
      <button type="button" onclick="cycleUserRole(this.getAttribute('data-uid'))"
              data-uid="${u.id.replace(/&/g,'&amp;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}"
              title="${t('m365_role_cycle_tip','Click to change role')}"
              class="role-badge" style="font-size:9px;padding:1px 5px;cursor:pointer;flex-shrink:0;white-space:nowrap;border:none;${u.roleOverride ? 'color:var(--color-text-info);outline:1px solid var(--color-border-info)' : ''}">
        ${u.userRole === 'student' ? t('role_student','Elev') : u.userRole === 'staff' ? t('role_staff','Ansat') : t('role_other','Anden')}${u.roleOverride ? ' ✎' : ''}
      </button>
      ${u.manual ? `<button onclick="removeUser(this.getAttribute('data-uid'))" data-uid="${u.id.replace(/&/g,'&amp;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:13px;padding:0;flex-shrink:0" title="Remove">×</button>` : ''}
    </label>`).join('');
}

function _updateUserCountBadge(visible, total) {
  const badge = document.getElementById('userCountBadge');
  if (!badge) return;
  if (total === 0) { badge.textContent = ''; return; }
  badge.textContent = visible < total ? `(${visible} / ${total})` : `(${total})`;
}

// ── SKU debug — surface unknown tenant SKU IDs so they can be added to m365_skus.json ──
async function showSkuDebug() {
  let modal = document.getElementById('skuDebugModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'skuDebugModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:1000;display:flex;align-items:center;justify-content:center';
    modal.onclick = e => { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);
  }
  modal.innerHTML = `<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:22px 26px;width:min(520px,95vw);max-height:80vh;display:flex;flex-direction:column;gap:12px;font-size:12px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <strong style="font-size:13px">${t('m365_sku_debug_title','🔍 Tenant SKU IDs')}</strong>
      <button onclick="document.getElementById('skuDebugModal').remove()" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px">×</button>
    </div>
    <div style="color:var(--muted);font-size:11px;line-height:1.5">${t('m365_sku_debug_desc','These are the raw SKU IDs assigned to your users. Any marked <b>❓ unknown</b> are not in <code>classification/m365_skus.json</code> — copy them in under <code>student_ids</code> or <code>staff_ids</code> and restart.')}</div>
    <div id="skuDebugList" style="overflow-y:auto;flex:1;font-family:var(--mono);font-size:11px">Loading…</div>
    <div style="display:flex;justify-content:flex-end;gap:8px;padding-top:4px;border-top:1px solid var(--border)">
      <button onclick="document.getElementById('skuDebugModal').remove()" style="background:none;border:1px solid var(--border);color:var(--muted);padding:4px 14px;border-radius:6px;cursor:pointer">${t('btn_close','Close')}</button>
    </div>
  </div>`;

  const listEl = document.getElementById('skuDebugList');
  try {
    const r = await fetch('/api/users/license_debug');
    const d = await r.json();
    if (d.error) { listEl.textContent = 'Error: ' + d.error; return; }

    // Collect unique SKUs across all users
    const skuSeen = {};  // skuId → {name, role, count, known}
    for (const u of (d.users || [])) {
      for (let i = 0; i < (u.skuIds || []).length; i++) {
        const id  = u.skuIds[i];
        const nm  = (u.skuNames || [])[i] || '';
        if (!skuSeen[id]) skuSeen[id] = { name: nm, role: u.role, count: 0 };
        skuSeen[id].count++;
      }
    }

    const rows = Object.entries(skuSeen).sort((a,b) => b[1].count - a[1].count);
    if (!rows.length) { listEl.textContent = t('m365_sku_debug_none','No license data returned — check that the app has User.Read.All permission.'); return; }

    const knownStudent = new Set((d.student_ids || []));
    const knownStaff   = new Set((d.staff_ids   || []));

    listEl.innerHTML = rows.map(([id, info]) => {
      const known = knownStudent.has(id) ? '🎓 student'
                  : knownStaff.has(id)   ? '👔 staff'
                  : '❓ unknown';
      const color = known.startsWith('❓') ? 'var(--danger)' : 'var(--accent)';
      return `<div style="display:flex;align-items:baseline;gap:8px;padding:3px 0;border-bottom:1px solid var(--border)">
        <code style="flex:1;color:var(--text);user-select:all">${id}</code>
        <span style="color:var(--muted);font-size:10px;white-space:nowrap">${info.name || '—'}</span>
        <span style="color:${color};font-size:10px;white-space:nowrap;flex-shrink:0">${known} (${info.count})</span>
      </div>`;
    }).join('');
  } catch(e) {
    listEl.textContent = 'Error: ' + e.message;
  }
}

function filterUsers() {
  const showAdminNote = S._allUsers.filter(u => !u.manual).length <= 1;
  renderAccountList(showAdminNote);
}

async function cycleUserRole(id) {
  // Cycle: student → staff → other → (clear override, back to auto)
  if (!id) { console.warn('cycleUserRole: no id'); return; }
  const u = S._allUsers.find(u => u.id === id);
  if (!u) { console.warn('cycleUserRole: user not found for id', id); return; }
  const cycle = ['student', 'staff', 'other'];
  let next;
  if (!u.roleOverride) {
    // First click: remember auto role, pin to next in cycle
    u._autoRole   = u.userRole;
    u._cycleSteps = 0;
    const cur = cycle.indexOf(u.userRole);
    next = cycle[(cur + 1) % cycle.length];
  } else {
    u._cycleSteps = (u._cycleSteps || 0) + 1;
    if (u._cycleSteps >= cycle.length) {
      next = '';  // full cycle completed — clear override
    } else {
      const cur = cycle.indexOf(u.userRole);
      next = cycle[(cur + 1) % cycle.length];
    }
  }
  try {
    const r = await fetch('/api/users/role_override', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: id, role: next})
    });
    const d = await r.json();
    if (d.error) { log('Role override failed: ' + d.error, 'err'); return; }
    // Update local state
    if (next) {
      if (!u.roleOverride) u._autoRole = u.userRole;  // remember original for clear
      u.userRole = next;
      u.roleOverride = true;
    } else {
      u.userRole = u._autoRole || u.userRole;
      u.roleOverride = false;
      u._autoRole = undefined;
    }
    // Update the role filter count badges and re-render
    renderAccountList(S._allUsers.filter(u => !u.manual).length <= 1);
    log((next ? t('m365_role_set', 'Role set') + ': ' + next : t('m365_role_cleared', 'Role override cleared')) + ' — ' + (u.displayName || id));
  } catch(e) {
    log('Role override error: ' + e.message, 'err');
  }
}

function removeUser(id) {
  S._allUsers = S._allUsers.filter(u => u.id !== id);
  renderAccountList(S._allUsers.filter(u => !u.manual).length <= 1);
}

async function addUserManually() {
  const input = document.getElementById('addUserInput');
  const upn = input.value.trim();
  if (!upn) return;
  // Look up the user via server
  const btn = input.nextElementSibling;
  btn.disabled = true; btn.textContent = '…';
  try {
    const r = await fetch('/api/users/lookup?upn=' + encodeURIComponent(upn));
    const d = await r.json();
    if (d.error) { alert('User not found: ' + d.error); return; }
    if (S._allUsers.find(u => u.id === d.id)) { alert('User already in list.'); return; }
    S._allUsers.push({...d, manual: true});
    input.value = '';
    renderAccountList(S._allUsers.filter(u => !u.manual).length <= 1);
  } catch(e) {
    alert('Lookup failed: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '+';
  }
}

function onAccountCheckChange(id, checked) {
  const user = S._allUsers.find(u => u.id === id);
  if (user) user.selected = checked;
}

function selectAllAccounts(checked) {
  // Toggle all visible users (respects search + role filter)
  const visible = new Set(
    Array.from(document.querySelectorAll('#accountsList .account-check')).map(cb => cb.dataset.id)
  );
  S._allUsers.forEach(u => { if (visible.has(u.id)) u.selected = checked; });
  document.querySelectorAll('#accountsList .account-check').forEach(cb => cb.checked = checked);
}

function getSelectedUsers() {
  // Only return M365 users — Google users are handled separately via selectedGoogleEmails
  let selected = S._allUsers.filter(u => u.selected !== false && (u.platform === 'm365' || u.platform === 'both'));
  // Respect the active role filter — hidden users must not sneak into the scan
  // even if they were checked before the filter was applied.
  if (_activeRoleFilter) {
    selected = selected.filter(u => (u.userRole || 'other') === _activeRoleFilter);
  }
  if (selected.length) {
    return selected.map(u => ({
      id: u.id, displayName: u.displayName, userRole: u.userRole || 'other'
    }));
  }
  // Fallback to DOM if S._allUsers not yet populated
  return Array.from(document.querySelectorAll('.account-check:checked')).map(cb => ({
    id: cb.dataset.id, displayName: cb.dataset.name, userRole: cb.dataset.role || 'other'
  }));
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.loadUsers = loadUsers;
window._mergeGoogleUsers = _mergeGoogleUsers;
window.toggleSection = toggleSection;
window.restoreSectionStates = restoreSectionStates;
window.updateRoleFilterCounts = updateRoleFilterCounts;
window.setRoleFilter = setRoleFilter;
window.loadLastScanSummary = loadLastScanSummary;
window.renderAccountList = renderAccountList;
window._updateUserCountBadge = _updateUserCountBadge;
window.showSkuDebug = showSkuDebug;
window.filterUsers = filterUsers;
window.cycleUserRole = cycleUserRole;
window.removeUser = removeUser;
window.addUserManually = addUserManually;
window.onAccountCheckChange = onAccountCheckChange;
window.selectAllAccounts = selectAllAccounts;
window.getSelectedUsers = getSelectedUsers;
window._activeRoleFilter = _activeRoleFilter;
window._COLLAPSE_SECTIONS = _COLLAPSE_SECTIONS;
