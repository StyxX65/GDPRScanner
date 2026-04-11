import { S } from './state.js';
// Global error trap — logs JS errors to console without blocking the page
window.onerror = function(msg, src, line, col, err) {
  console.error('JS Error [' + (src||'').split('/').pop() + ':' + line + '] ' + msg, err);
  return false;
};
window.addEventListener('unhandledrejection', function(e) {
  console.error('Unhandled promise rejection:', e.reason);
});

// ── Theme ────────────────────────────────────────────────────────────────────
function openAbout() {
  document.getElementById('aboutBackdrop').classList.add('open');
  fetch('/api/about').then(r => r.json()).then(d => {
    document.getElementById('about-python').textContent   = d.python   || '—';
    document.getElementById('about-msal').textContent     = d.msal     || '—';
    document.getElementById('about-requests').textContent = d.requests || '—';
    document.getElementById('about-openpyxl').textContent = d.openpyxl || '—';
  }).catch(() => {});
}
function closeAbout() {
  document.getElementById('aboutBackdrop').classList.remove('open');
}

// ── Mode info modal ───────────────────────────────────────────────────────────
function openModeInfo() {
  const isApp = S._currentAppMode === true;
  const title   = document.getElementById('modeInfoTitle');
  const sub     = document.getElementById('modeInfoSubtitle');
  const rows    = document.getElementById('modeInfoRows');

  if (isApp) {
    title.textContent = t('m365_mode_app', '🔑 App mode — org-wide');
    sub.textContent   = t('m365_auth_mode_app_short', 'Application permissions · client credentials');
    rows.innerHTML = `
      <div class="about-row"><span>${t('m365_info_permissions','Permissions')}</span><span>Application</span></div>
      <div class="about-row"><span>${t('m365_info_signin','Sign-in required')}</span><span>${t('m365_info_no','No')}</span></div>
      <div class="about-row"><span>${t('m365_info_scope','Scope')}</span><span>${t('m365_info_scope_org','All users in tenant')}</span></div>
      <div class="about-row"><span>${t('m365_info_consent','Admin consent')}</span><span>${t('m365_info_required','Required')}</span></div>
      <div style="margin-top:12px;font-size:11px;color:var(--muted);line-height:1.6">
        ${t('m365_info_app_desc','The app authenticates with a Client Secret and accesses all users\' data directly via Microsoft Graph — no interactive sign-in needed. Ideal for automated or scheduled scans.')}
      </div>`;
  } else {
    title.textContent = t('m365_mode_delegated', '👤 Delegated');
    sub.textContent   = t('m365_auth_mode_delegated_short', 'Delegated permissions · device code flow');
    rows.innerHTML = `
      <div class="about-row"><span>${t('m365_info_permissions','Permissions')}</span><span>Delegated</span></div>
      <div class="about-row"><span>${t('m365_info_signin','Sign-in required')}</span><span>${t('m365_info_yes','Yes')}</span></div>
      <div class="about-row"><span>${t('m365_info_scope','Scope')}</span><span>${t('m365_info_scope_user','Signed-in user only')}</span></div>
      <div class="about-row"><span>${t('m365_info_admin','Global Admin')}</span><span>${t('m365_info_expands_scope','Expands scope to all users')}</span></div>
      <div style="margin-top:12px;font-size:11px;color:var(--muted);line-height:1.6">
        ${t('m365_info_delegated_desc','The app acts on behalf of the signed-in user via the device code flow. By default only that user\'s data is accessible. A Global Admin can grant broader consent to scan all users.')}
      </div>`;
  }
  document.getElementById('modeInfoBackdrop').classList.add('open');
}
function closeModeInfo() {
  document.getElementById('modeInfoBackdrop').classList.remove('open');
}

function toggleTheme() {
  const t = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
  document.body.dataset.theme = t;
  document.getElementById('themeBtn').textContent = t === 'dark' ? '🌙' : '☀️';
  try { localStorage.setItem('m365_theme', t); } catch(e) {}
}
(function() {
  try {
    const t = localStorage.getItem('m365_theme');
    if (t) {
      document.body.dataset.theme = t;
      const btn = document.getElementById('themeBtn');
      if (btn) btn.textContent = t === 'dark' ? '🌙' : '☀️';
    }
  } catch(e) {}
})();

// ── Language selector ─────────────────────────────────────────────────────────
fetch('/api/langs').then(r => r.json()).then(d => {
  const sel = document.getElementById('langSelect');
  if (!sel || !d.langs || d.langs.length < 2) {
    if (sel) sel.style.display = 'none';
    return;
  }
  d.langs.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l.code;
    opt.textContent = l.name;
    if (l.code === d.current) opt.selected = true;
    sel.appendChild(opt);
  });
}).catch(() => {
  const sel = document.getElementById('langSelect');
  if (sel) sel.style.display = 'none';
});

async function setLang(code) {
  const r = await fetch('/api/set_lang', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({lang: code})
  });
  const d = await r.json();
  if (d.translations) {
    // Update the in-memory LANG dict and re-apply all translations in place.
    // This keeps all scan results, cards, and state intact.
    Object.assign(LANG, d.translations);
    applyI18n();
    // Re-render the grid so card text (source badges etc.) picks up new strings
    if (S.flaggedData.length) renderGrid(S.filteredData.length ? S.filteredData : S.flaggedData);
  }
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.openAbout = openAbout;
window.closeAbout = closeAbout;
window.openModeInfo = openModeInfo;
window.closeModeInfo = closeModeInfo;
window.toggleTheme = toggleTheme;
window.setLang = setLang;
