// ── Viewer token management (#33) ─────────────────────────────────────────────
// Share button → modal to create, copy, and revoke read-only viewer links.

async function _getShareBaseUrl() {
  // Use the machine's LAN IP so links work for remote users, not just localhost.
  try {
    const r = await fetch('/api/local_ip');
    if (r.ok) {
      const d = await r.json();
      if (d.ip && d.ip !== '127.0.0.1') {
        return 'http://' + d.ip + ':' + window.location.port;
      }
    }
  } catch(e) {}
  return window.location.origin;
}

function openShareModal() {
  document.getElementById('shareBackdrop').classList.add('open');
  document.getElementById('shareNewLinkRow').style.display = 'none';
  document.getElementById('shareLabel').value = '';
  document.getElementById('shareExpiry').value = '30';
  const scopeSel = document.getElementById('shareScope');
  if (scopeSel) scopeSel.value = '';
  _renderTokenList();
  fetch('/api/viewer/pin').then(function(r){ return r.json(); }).then(function(d) {
    const el = document.getElementById('sharePinStatus');
    if (el) el.textContent = d.pin_set ? t('share_pin_set', 'Set') : t('share_pin_not_set', 'Not set');
  }).catch(function(){});
}

function closeShareModal() {
  document.getElementById('shareBackdrop').classList.remove('open');
}

async function _renderTokenList() {
  const list = document.getElementById('shareTokenList');
  list.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:4px 0">' + t('lbl_loading', 'Loading…') + '</div>';
  try {
    const r = await fetch('/api/viewer/tokens');
    const tokens = await r.json();
    if (!tokens.length) {
      list.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:4px 0">' + t('share_no_links', 'No active links.') + '</div>';
      return;
    }
    list.innerHTML = '';
    tokens.forEach(tok => {
      const expires = tok.expires_at
        ? new Date(tok.expires_at * 1000).toLocaleDateString(undefined, {day:'numeric', month:'short', year:'numeric'})
        : t('share_expires_never', 'Never');
      const lastUsed = tok.last_used_at
        ? new Date(tok.last_used_at * 1000).toLocaleDateString(undefined, {day:'numeric', month:'short'})
        : '—';
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-size:12px';
      const roleVal  = tok.scope?.role || '';
      const roleLbl  = roleVal === 'student' ? t('share_scope_student', 'Elever')
                     : roleVal === 'staff'   ? t('share_scope_staff',   'Ansatte')
                     : '';
      const roleBadge = roleLbl
        ? '<span style="font-size:9px;padding:1px 5px;border-radius:10px;background:var(--accent);color:#fff;margin-left:5px;font-weight:600;vertical-align:middle">' + roleLbl + '</span>'
        : '';
      row.innerHTML =
        '<div style="flex:1;min-width:0">' +
          '<div style="font-weight:500;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' +
            (tok.label || '<span style="color:var(--muted);font-style:italic">' + t('share_unlabelled', 'Unlabelled') + '</span>') +
            roleBadge +
          '</div>' +
          '<div style="font-size:10px;color:var(--muted);margin-top:1px">' +
            t('share_expires_prefix', 'Expires:') + ' ' + expires + ' &nbsp;·&nbsp; ' + t('share_last_used', 'Last used:') + ' ' + lastUsed +
          '</div>' +
        '</div>' +
        '<button title="' + t('share_copy_link_prompt', 'Copy link:') + '" onclick="copyTokenLink(\'' + tok.token + '\',this)" ' +
          'style="height:24px;padding:0 8px;background:none;border:1px solid var(--border);color:var(--muted);border-radius:4px;font-size:11px;cursor:pointer;flex-shrink:0">' + t('log_copy', 'Copy') + '</button>' +
        '<button title="' + t('share_revoke', 'Revoke') + '" onclick="revokeToken(\'' + tok.token + '\',this.closest(\'div[style]\'))" ' +
          'style="height:24px;padding:0 8px;background:none;border:1px solid var(--danger);color:var(--danger);border-radius:4px;font-size:11px;cursor:pointer;flex-shrink:0">' + t('share_revoke', 'Revoke') + '</button>';
      list.appendChild(row);
    });
  } catch(e) {
    list.innerHTML = '<div style="font-size:12px;color:var(--danger);padding:4px 0">' + t('share_load_error', 'Failed to load links.') + '</div>';
  }
}

async function createShareLink() {
  const label   = document.getElementById('shareLabel').value.trim();
  const expiry  = document.getElementById('shareExpiry').value;
  const role    = document.getElementById('shareScope')?.value || '';
  const body    = {label};
  if (expiry) body.expires_days = parseInt(expiry);
  if (role)   body.scope = {role};
  try {
    const r = await fetch('/api/viewer/tokens', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error('Server error ' + r.status);
    const entry = await r.json();
    const url = (await _getShareBaseUrl()) + '/view?token=' + encodeURIComponent(entry.token);
    const urlInput = document.getElementById('shareNewLinkUrl');
    urlInput.value = url;
    document.getElementById('shareNewLinkRow').style.display = 'block';
    document.getElementById('shareCopyBtn').textContent = t('log_copy', 'Copy');
    document.getElementById('shareLabel').value = '';
    _renderTokenList();
  } catch(e) {
    alert(t('share_create_error', 'Failed to create link:') + ' ' + e.message);
  }
}

function copyShareLink() {
  const url = document.getElementById('shareNewLinkUrl').value;
  _copyText(url, document.getElementById('shareCopyBtn'));
}

async function copyTokenLink(token, btn) {
  const url = (await _getShareBaseUrl()) + '/view?token=' + encodeURIComponent(token);
  _copyText(url, btn);
}

function _copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = t('share_copied', 'Copied!');
    setTimeout(() => { btn.textContent = orig; }, 1800);
  }).catch(() => {
    // Fallback for HTTP contexts
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      const orig = btn.textContent;
      btn.textContent = t('share_copied', 'Copied!');
      setTimeout(() => { btn.textContent = orig; }, 1800);
    } catch(_) {}
  });
}

async function revokeToken(token, rowEl) {
  if (!confirm(t('share_revoke_confirm', 'Revoke this link? Anyone using it will immediately lose access.'))) return;
  try {
    const r = await fetch('/api/viewer/tokens/' + encodeURIComponent(token), {method: 'DELETE'});
    if (!r.ok) throw new Error('Server error ' + r.status);
    rowEl.remove();
    const list = document.getElementById('shareTokenList');
    if (!list.children.length) {
      list.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:4px 0">' + t('share_no_links', 'No active links.') + '</div>';
    }
    // Hide the copy row if the just-revoked token was the last created
    const newRow = document.getElementById('shareNewLinkRow');
    if (newRow) {
      const shownUrl = document.getElementById('shareNewLinkUrl')?.value || '';
      if (shownUrl.includes(token)) newRow.style.display = 'none';
    }
  } catch(e) {
    alert(t('share_revoke_error', 'Failed to revoke:') + ' ' + e.message);
  }
}

// ── Viewer PIN — Settings UI ──────────────────────────────────────────────────

async function stLoadViewerPinStatus() {
  try {
    const r = await fetch('/api/viewer/pin');
    const d = await r.json();
    const statusEl     = document.getElementById('stViewerPinStatus');
    const currentRow   = document.getElementById('stViewerCurrentPinRow');
    const clearBtn     = document.getElementById('stViewerPinClearBtn');
    if (d.pin_set) {
      if (statusEl)   statusEl.textContent   = '\u2714 ' + t('viewer_pin_is_set', 'Viewer PIN is set');
      if (currentRow) currentRow.style.display = '';
      if (clearBtn)   clearBtn.style.display   = '';
    } else {
      if (statusEl)   statusEl.textContent   = t('viewer_pin_not_set_msg', 'No PIN set \u2014 /view requires a token link');
      if (currentRow) currentRow.style.display = 'none';
      if (clearBtn)   clearBtn.style.display   = 'none';
    }
  } catch(e) {}
}

async function stSaveViewerPin() {
  const newPin     = (document.getElementById('stViewerNewPin')?.value    || '').trim();
  const currentPin = (document.getElementById('stViewerCurrentPin')?.value || '').trim();
  const st         = document.getElementById('stViewerPinSaveStatus');
  if (!newPin) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = t('m365_settings_pin_required', 'PIN is required.'); }
    return;
  }
  if (!/^\d{4,8}$/.test(newPin)) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = t('viewer_pin_format', 'PIN must be 4\u20138 digits.'); }
    return;
  }
  if (st) { st.style.color = 'var(--muted)'; st.textContent = t('viewer_pin_saving', 'Saving\u2026'); }
  try {
    const r = await fetch('/api/viewer/pin', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pin: newPin, current_pin: currentPin}),
    });
    const d = await r.json();
    if (!r.ok) {
      if (st) { st.style.color = 'var(--danger)'; st.textContent = d.error || 'Error.'; }
      return;
    }
    if (st) { st.style.color = 'var(--accent)'; st.textContent = '\u2714 ' + t('viewer_pin_saved', 'PIN saved'); }
    if (document.getElementById('stViewerNewPin'))    document.getElementById('stViewerNewPin').value    = '';
    if (document.getElementById('stViewerCurrentPin')) document.getElementById('stViewerCurrentPin').value = '';
    stLoadViewerPinStatus();
  } catch(e) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = e.message; }
  }
}

async function stClearViewerPin() {
  const currentPin = (document.getElementById('stViewerCurrentPin')?.value || '').trim();
  const st         = document.getElementById('stViewerPinSaveStatus');
  if (!currentPin) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = t('m365_settings_pin_required', 'PIN is required.'); }
    document.getElementById('stViewerCurrentPin')?.focus();
    return;
  }
  if (!confirm(t('viewer_pin_clear_confirm', 'Remove the viewer PIN? /view will require a token link again.'))) return;
  try {
    const r = await fetch('/api/viewer/pin', {
      method: 'DELETE', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({current_pin: currentPin}),
    });
    const d = await r.json();
    if (!r.ok) {
      if (st) { st.style.color = 'var(--danger)'; st.textContent = d.error || 'Error.'; }
      return;
    }
    if (st) { st.style.color = 'var(--muted)'; st.textContent = t('viewer_pin_cleared', 'PIN cleared'); }
    stLoadViewerPinStatus();
  } catch(e) {
    if (st) { st.style.color = 'var(--danger)'; st.textContent = e.message; }
  }
}

// ── Window exports ────────────────────────────────────────────────────────────
window.openShareModal       = openShareModal;
window.closeShareModal      = closeShareModal;
window.createShareLink      = createShareLink;
window.copyShareLink        = copyShareLink;
window.copyTokenLink        = copyTokenLink;
window.revokeToken          = revokeToken;
window.stLoadViewerPinStatus = stLoadViewerPinStatus;
window.stSaveViewerPin      = stSaveViewerPin;
window.stClearViewerPin     = stClearViewerPin;
