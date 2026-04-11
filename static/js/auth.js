import { S } from './state.js';
// ── Auth ─────────────────────────────────────────────────────────────────────
function handleSignIn() {
  try {
    startAuth().catch(function(e) {
      alert('Sign-in error: ' + (e.message || String(e)));
    });
  } catch(e) {
    alert('Sign-in error: ' + (e.message || String(e)));
  }
}

async function startAuth() {
  const clientId     = document.getElementById('clientId').value.trim();
  const tenantId     = document.getElementById('tenantId').value.trim();
  const clientSecret = document.getElementById('clientSecret').value.trim();
  if (!clientId || !tenantId) { alert('Enter Client ID and Tenant ID'); return; }

  // Persist credentials first so they survive restarts regardless of auth outcome
  await fetch('/api/auth/config', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({client_id: clientId, tenant_id: tenantId, client_secret: clientSecret})
  });

  const r = await fetch('/api/auth/start', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({client_id: clientId, tenant_id: tenantId, client_secret: clientSecret})
  });
  const d = await r.json();
  if (d.error) { alert(d.error); return; }

  if (d.mode === 'application') {
    // App mode — token acquired immediately, no device code step needed
    document.getElementById('configForm').style.display = 'none';
    document.getElementById('deviceCodeBackdrop').classList.add('open');
    document.getElementById('deviceCode').textContent = '—';
    document.getElementById('authStatus').className = 'auth-status success';
    document.getElementById('authStatus').textContent = '✓ Connected (Application mode — org-wide access)';
    setTimeout(onAuthenticated, 900);
    return;
  }

  document.getElementById('configForm').style.display = 'none';
  document.getElementById('deviceCodeBackdrop').classList.add('open');
  document.getElementById('deviceCode').textContent = d.user_code;

  pollAuth();
}

async function pollAuth() {
  const r = await fetch('/api/auth/poll', {method: 'POST'});
  const d = await r.json();
  if (d.status === 'pending') {
    setTimeout(pollAuth, 3000);
  } else if (d.status === 'ok') {
    document.getElementById('authStatus').className = 'auth-status success';
    document.getElementById('authStatus').textContent = '✓ Signed in!';
    setTimeout(onAuthenticated, 800);
  } else {
    document.getElementById('authStatus').className = 'auth-status error';
    document.getElementById('authStatus').textContent = '✗ ' + (d.error || 'Sign-in failed');
    document.getElementById('configForm').style.display = 'block';
    document.getElementById('deviceCodeBackdrop').classList.remove('open');
  }
}

function cancelAuth() {
  document.getElementById('configForm').style.display = 'block';
  document.getElementById('deviceCodeBackdrop').classList.remove('open');
}

let _currentDisplayName = '';

function _setModeBadge(isAppMode, displayName) {
  S._currentAppMode    = isAppMode;
  _currentDisplayName = displayName || '';
  // Keep Sources modal status dot in sync if it's open
  const dot = document.getElementById('srcM365StatusDot');
  if (dot) dot.className = 'srcmgmt-status ' + (isAppMode !== null && isAppMode !== undefined ? 'green' : 'grey');
}

async function onAuthenticated() {
  const r = await fetch('/api/auth/status');
  const d = await r.json();
  if (d.display_name || d.displayName || d.email) {
      _setModeBadge(d.app_mode, d.display_name || d.displayName || d.email);
  }
  document.getElementById('authScreen').style.display = 'none';
  document.getElementById('scannerScreen').style.display = 'flex';
  loadUsers();
  loadTrend();  // show existing trend if DB has history
  loadProfiles();  // populate profile dropdown (15c)
}

function reconfigure() {
  // Show the auth screen with current credentials pre-filled so user can
  // update the client secret without losing client_id / tenant_id.
  document.getElementById('scannerScreen').style.display = 'none';
  document.getElementById('authScreen').style.display    = 'flex';
  document.getElementById('configForm').style.display    = 'block';
  document.getElementById('deviceCodeBackdrop').classList.remove('open');
}

async function signOut() {
  await fetch('/api/auth/signout', {method: 'POST'});
  document.getElementById('scannerScreen').style.display = 'none';
  document.getElementById('authScreen').style.display = 'flex';
  document.getElementById('configForm').style.display = 'block';
  document.getElementById('deviceCodeBackdrop').classList.remove('open');
  S.flaggedData = []; S.filteredData = [];
  document.getElementById('grid').innerHTML = '';
  document.getElementById('grid').style.display = 'none';
  const _lss2 = document.getElementById('lastScanSummary'); if (_lss2) _lss2.style.display = 'none';
  document.getElementById('emptyState').style.display = 'flex';
}

// ── Check auth on load ────────────────────────────────────────────────────────

// Date presets
(function() {
  const presets = document.querySelectorAll('.date-preset');
  const hidden  = document.getElementById('olderThan');
  const dateIn  = document.getElementById('olderThanDate');
  function setPreset(btn) {
    presets.forEach(p => p.classList.remove('selected'));
    btn.classList.add('selected');
    const years = parseInt(btn.dataset.years);
    if (years === 0) {
      hidden.value = '0';
      dateIn.value = new Date().toISOString().slice(0, 10);
    } else {
      const d = new Date();
      d.setFullYear(d.getFullYear() - years);
      hidden.value = Math.round(years * 365.25).toString();
      dateIn.value = d.toISOString().slice(0, 10);
    }
  }
  presets.forEach(btn => btn.addEventListener('click', () => setPreset(btn)));
  dateIn.addEventListener('change', () => {
    presets.forEach(p => p.classList.remove('selected'));
    if (dateIn.value) {
      const diffDays = Math.round((Date.now() - new Date(dateIn.value)) / 86400000);
      hidden.value = diffDays.toString();
    } else {
      hidden.value = '0';
    }
  });
  // Trigger default (2yr selected)
  const def = document.querySelector('.date-preset.selected');
  if (def) setPreset(def);
  // Toggle attach size row visibility
  document.getElementById('optAttachments').addEventListener('change', function() {
    document.getElementById('attachSizeRow').style.opacity = this.checked ? '1' : '0.4';
  });
})();

// ── Viewer mode bootstrap ─────────────────────────────────────────────────────
if (window.VIEWER_MODE) {
  document.body.classList.add('viewer-mode');
  document.getElementById('authScreen').style.display    = 'none';
  document.getElementById('scannerScreen').style.display = 'flex';
  try { loadTrend(); } catch(e) {}
} else {
(async function() {
  try {
    const r = await fetch('/api/auth/status');
    const d = await r.json();
  if (d.authenticated) {
    // Load saved credentials into fields
    if (d.client_id) document.getElementById('clientId').value = d.client_id;
    if (d.tenant_id) document.getElementById('tenantId').value = d.tenant_id;
    if (d.client_secret) document.getElementById('clientSecret').value = d.client_secret;
      _setModeBadge(d.app_mode, d.display_name || d.email || '');
    document.getElementById('authScreen').style.display = 'none';
    document.getElementById('scannerScreen').style.display = 'flex';
    try { loadUsers(); } catch(e) {}
    try { loadProfiles(); } catch(e) {}
    try { loadTrend(); } catch(e) {}
  } else {
    // Pre-fill saved credentials
    if (d.client_id) document.getElementById('clientId').value = d.client_id;
    if (d.tenant_id) document.getElementById('tenantId').value = d.tenant_id;
    if (d.client_secret) document.getElementById('clientSecret').value = d.client_secret;
  }
  } catch(e) { console.error('Auth status check failed:', e); }
})();
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.handleSignIn = handleSignIn;
window.startAuth = startAuth;
window.pollAuth = pollAuth;
window.cancelAuth = cancelAuth;
window._setModeBadge = _setModeBadge;
window.onAuthenticated = onAuthenticated;
window.reconfigure = reconfigure;
window.signOut = signOut;
window._currentDisplayName = _currentDisplayName;
