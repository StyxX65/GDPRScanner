// ── Scheduler — multi-job (#19) ─────────────────────────────────────────────

var _schedJobs = [];

function schedLoad() {
  fetch('/api/scheduler/jobs').then(function(r){ return r.json(); }).then(function(d) {
    _schedJobs = d.jobs || [];
    schedRenderJobs();
    schedLoadHistory();
    // Fetch status AFTER rendering so run buttons exist in the DOM
    return fetch('/api/scheduler/status').then(function(r){ return r.json(); });
  }).then(function(d) {
    if (!d) return;
    var noAps = document.getElementById('schedNoAps');
    if (noAps) noAps.style.display = d.available ? 'none' : 'block';
    schedUpdateSidebarIndicator(d);
    (d.jobs || []).forEach(function(js) {
      var descEl = document.getElementById('schedDesc_' + js.id);
      if (!descEl) return;
      var j2 = _schedJobs.find(function(x){ return x.id === js.id; });
      var freqLabel = !j2 ? '' : (j2.frequency === 'weekly' ? 'Weekly' : j2.frequency === 'monthly' ? 'Monthly' : 'Daily');
      var timeStr = !j2 ? '' : String(j2.hour||0).padStart(2,'0') + ':' + String(j2.minute||0).padStart(2,'0');
      var base = freqLabel + ' ' + timeStr;
      var runBtn = document.getElementById('schedRunBtn_' + js.id);
      if (js.is_running) {
        descEl.textContent = base + ' \u00b7 Running...';
        if (runBtn) { runBtn.style.borderColor='#22c55e'; runBtn.style.color='#22c55e'; }
      } else if (js.next_run) {
        var dt = new Date(js.next_run);
        descEl.textContent = base + ' \u00b7 Next: ' + dt.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
        if (runBtn) { runBtn.style.borderColor='var(--border)'; runBtn.style.color='var(--muted)'; }
      } else {
        descEl.textContent = base + (js.enabled ? '' : ' \u00b7 Disabled');
        if (runBtn) { runBtn.style.borderColor='var(--border)'; runBtn.style.color='var(--muted)'; }
      }
    });
  }).catch(function(e){ console.warn('schedLoad:', e); });
}

function schedRenderJobs() {
  var list = document.getElementById('schedJobList');
  if (!list) return;
  if (!_schedJobs.length) {
    list.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:4px 0">No scheduled scans yet.</div>';
    return;
  }
  list.innerHTML = _schedJobs.map(function(j) {
    var sid  = _esc(j.id);
    var sname = _esc(j.name || 'Unnamed');
    var freqLabel = j.frequency === 'weekly' ? 'Weekly' : j.frequency === 'monthly' ? 'Monthly' : 'Daily';
    var timeStr = String(j.hour||0).padStart(2,'0') + ':' + String(j.minute||0).padStart(2,'0');
    var desc = freqLabel + ' ' + timeStr;
    var chk = j.enabled ? ' checked' : '';
    return '<div style="display:flex;align-items:center;gap:6px;padding:5px 6px;border:1px solid var(--border);border-radius:6px;background:var(--surface)">'
      + '<label class="toggle" style="flex:unset;margin:0"><input type="checkbox"'+chk+' onchange="schedToggleEnabled(\''+sid+'\',this.checked)"><span class="toggle-slider"></span></label>'
      + '<div style="flex:1;min-width:0">'
      + '<div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+sname+'</div>'
      + '<div id="schedDesc_'+sid+'" style="font-size:10px;color:var(--muted)">'+desc+'</div>'
      + '</div>'
      + '<button onclick="schedRunJob(\''+sid+'\')" id="schedRunBtn_'+sid+'" style="background:none;border:1px solid var(--border);color:var(--muted);padding:2px 7px;border-radius:4px;font-size:10px;cursor:pointer" title="Run now">&#9654;</button>'
      + '<button onclick="schedEditJob(\''+sid+'\')" style="background:none;border:1px solid var(--border);color:var(--muted);padding:2px 7px;border-radius:4px;font-size:10px;cursor:pointer" title="Edit">&#9998;</button>'
      + '<button onclick="schedDeleteJob(\''+sid+'\')" style="background:none;border:1px solid var(--danger);color:var(--danger);padding:2px 7px;border-radius:4px;font-size:10px;cursor:pointer" title="Delete">&#10005;</button>'
      + '</div>';
  }).join('');
}

function schedToggleEnabled(id, enabled) {
  var j = _schedJobs.find(function(x){ return x.id === id; });
  if (!j) return;
  var updated = Object.assign({}, j, {enabled: enabled});
  fetch('/api/scheduler/jobs/save', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(updated)
  }).then(function(r){ return r.json(); }).then(function(d) {
    if (d.error) { alert('Error: ' + d.error); return; }
    j.enabled = enabled;
    schedLoad();
  }).catch(function(e){ alert('Error: ' + e); });
}

function schedAddJob() {
  document.getElementById('schedEditId').value = '';
  document.getElementById('schedName').value = '';
  document.getElementById('schedEnabled').checked = true;
  document.getElementById('schedFrequency').value = 'daily';
  document.getElementById('schedDow').value = 'mon';
  document.getElementById('schedDom').value = 1;
  document.getElementById('schedHour').value = 2;
  document.getElementById('schedMinute').value = 0;
  document.getElementById('schedAutoEmail').checked = false;
  document.getElementById('schedAutoRetention').checked = false;
  var titleEl = document.getElementById('schedEditorTitle');
  if (titleEl) titleEl.textContent = t('m365_sched_editor_new', 'New scheduled scan');
  schedPopulateProfiles('');
  schedToggleFreqRows();
  document.getElementById('schedJobEditor').style.display = 'block';
  document.getElementById('schedSaveStatus').textContent = '';
  document.getElementById('schedName').focus();
}

function schedEditJob(id) {
  var j = _schedJobs.find(function(x){ return x.id === id; });
  if (!j) return;
  document.getElementById('schedEditId').value = j.id;
  document.getElementById('schedName').value = j.name || '';
  document.getElementById('schedEnabled').checked = !!j.enabled;
  document.getElementById('schedFrequency').value = j.frequency || 'daily';
  document.getElementById('schedDow').value = j.day_of_week || 'mon';
  document.getElementById('schedDom').value = j.day_of_month || 1;
  document.getElementById('schedHour').value = j.hour != null ? j.hour : 2;
  document.getElementById('schedMinute').value = j.minute != null ? j.minute : 0;
  document.getElementById('schedAutoEmail').checked = !!j.auto_email;
  document.getElementById('schedAutoRetention').checked = !!j.auto_retention;
  var titleEl = document.getElementById('schedEditorTitle');
  if (titleEl) titleEl.textContent = t('m365_sched_editor_edit', 'Edit scheduled scan');
  schedPopulateProfiles(j.profile_id || '');
  schedToggleFreqRows();
  document.getElementById('schedJobEditor').style.display = 'block';
  document.getElementById('schedSaveStatus').textContent = '';
}

function schedCancelEdit() {
  document.getElementById('schedJobEditor').style.display = 'none';
}

function schedSaveJob() {
  var name = document.getElementById('schedName').value.trim();
  if (!name) {
    var st = document.getElementById('schedSaveStatus');
    st.textContent = t('m365_sched_name_required', 'Name is required');
    st.style.color = 'var(--danger)';
    document.getElementById('schedName').focus();
    return;
  }
  var job = {
    id:             document.getElementById('schedEditId').value || '',
    name:           name,
    enabled:        document.getElementById('schedEnabled').checked,
    frequency:      document.getElementById('schedFrequency').value,
    day_of_week:    document.getElementById('schedDow').value,
    day_of_month:   parseInt(document.getElementById('schedDom').value) || 1,
    hour:           parseInt(document.getElementById('schedHour').value) || 0,
    minute:         parseInt(document.getElementById('schedMinute').value) || 0,
    profile_id:     document.getElementById('schedProfile').value,
    auto_email:     document.getElementById('schedAutoEmail').checked,
    auto_retention: document.getElementById('schedAutoRetention').checked,
  };
  var st = document.getElementById('schedSaveStatus');
  st.style.color = 'var(--muted)'; st.textContent = 'Saving...';
  fetch('/api/scheduler/jobs/save', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(job)
  }).then(function(r){ return r.json(); }).then(function(d) {
    if (d.error) { st.style.color='var(--danger)'; st.textContent=d.error; return; }
    st.style.color = 'var(--accent)'; st.textContent = '\u2713 Saved';
    setTimeout(function(){ st.textContent=''; }, 1500);
    document.getElementById('schedJobEditor').style.display = 'none';
    schedLoad();
  }).catch(function(e){ st.style.color='var(--danger)'; st.textContent=e.message; });
}

function schedDeleteJob(id) {
  var j = _schedJobs.find(function(x){ return x.id === id; });
  var name = j ? j.name : id;
  if (!confirm('Delete "' + name + '"?')) return;
  fetch('/api/scheduler/jobs/delete', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({id: id})
  }).then(function(r){ return r.json(); }).then(function(d) {
    if (d.error) { alert('Delete failed: ' + d.error); return; }
    schedLoad();
  }).catch(function(e){ alert('Delete error: ' + e); });
}

function schedRunJob(id) {
  var j = _schedJobs.find(function(x){ return x.id === id; });
  var name = j ? j.name : 'this scan';
  if (!confirm('Run "' + name + '" now?')) return;
  fetch('/api/scheduler/jobs/run_now', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({id: id})
  }).then(function(r){ return r.json(); }).then(function(d) {
    if (d.error) alert(d.error);
    else schedLoad();
  });
}

function schedToggleFreqRows() {
  var freq = document.getElementById('schedFrequency');
  if (!freq) return;
  var val = freq.value;
  var dowRow = document.getElementById('schedDowRow');
  var domRow = document.getElementById('schedDomRow');
  if (dowRow) dowRow.style.display = val === 'weekly'  ? 'flex' : 'none';
  if (domRow) domRow.style.display = val === 'monthly' ? 'flex' : 'none';
}

function schedPopulateProfiles(selectedId) {
  fetch('/api/profiles').then(function(r){ return r.json(); }).then(function(d) {
    var sel = document.getElementById('schedProfile');
    if (!sel) return;
    var firstOpt = sel.options[0];
    sel.innerHTML = '';
    sel.appendChild(firstOpt);
    (d.profiles || []).forEach(function(p) {
      var o = document.createElement('option');
      o.value = p.id || p.name;
      o.textContent = p.name;
      if ((p.id || p.name) === selectedId) o.selected = true;
      sel.appendChild(o);
    });
  });
}

function schedLoadHistory() {
  var el = document.getElementById('schedHistory');
  if (!el) return;
  fetch('/api/scheduler/history?limit=10').then(function(r){ return r.json(); }).then(function(d) {
    var runs = d.runs || [];
    if (!runs.length) { el.innerHTML = '<em>No scheduled runs yet</em>'; return; }
    var html = '';
    runs.forEach(function(r) {
      var ts = r.started_at ? new Date(r.started_at * 1000).toLocaleString() : '-';
      var icon = r.status === 'completed' ? '\u2713' : r.status === 'failed' ? '\u2716' : '\u23f3';
      var jname = r.job_name ? '<strong>' + _esc(r.job_name) + '</strong> - ' : '';
      html += icon + ' ' + jname + ts + ' - ' + (r.flagged||0) + ' flagged';
      if (r.emailed) html += ' \u2709';
      if (r.error) html += ' <span style="color:var(--danger)">' + _esc(r.error.substring(0,60)) + '</span>';
      html += '<br>';
    });
    el.innerHTML = html;
  });
}

function schedUpdateSidebarIndicator(d) {
  var wrap = document.getElementById('schedNextIndicator');
  var txt  = document.getElementById('schedNextText');
  if (!wrap || !txt) return;
  if (d && d.enabled && d.next_run) {
    try {
      var dt = new Date(d.next_run);
      txt.textContent = t('m365_sched_next', 'Next') + ': ' + dt.toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
      wrap.style.display = 'inline-flex';
    } catch(e) { wrap.style.display = 'none'; }
  } else {
    wrap.style.display = 'none';
  }
}

// Poll scheduler status every 60s
setInterval(function() {
  fetch('/api/scheduler/status').then(function(r){ return r.json(); }).then(function(d) {
    schedUpdateSidebarIndicator(d);
  }).catch(function(){});
}, 60000);
document.addEventListener('DOMContentLoaded', function() {
  fetch('/api/scheduler/status').then(function(r){ return r.json(); }).then(function(d) {
    schedUpdateSidebarIndicator(d);
  }).catch(function(){});
});

// ── General tab ───────────────────────────────────────────────────────────────

function stPopulateGeneral() {
  stLoadPinStatus();
  // Populate language selector (mirrors the hidden langSelect)
  const src = document.getElementById('langSelect');
  const dst = document.getElementById('langSelectSettings');
  if (src && dst && dst.options.length === 0) {
    Array.from(src.options).forEach(function(opt) {
      const o = document.createElement('option');
      o.value = opt.value; o.textContent = opt.textContent;
      if (opt.selected) o.selected = true;
      dst.appendChild(o);
    });
  } else if (src && dst) {
    dst.value = src.value;
  }
  // Populate About rows
  fetch('/api/about').then(function(r){ return r.json(); }).then(function(d) {
    const set = function(id, val) { const el=document.getElementById(id); if(el) el.textContent=val||'\u2014'; };
    set('st-about-python',  d.python);
    set('st-about-msal',    d.msal);
    set('st-about-requests',d.requests);
    set('st-about-openpyxl',d.openpyxl);
  }).catch(function(){});
}

// ── Email tab ─────────────────────────────────────────────────────────────────

function stLoadSmtp() {
  fetch('/api/smtp/config').then(function(r){ return r.json(); }).then(function(d) {
    const set = function(id, val) { const el=document.getElementById(id); if(el) el.value=val||''; };
    set('st-smtpHost', d.host);
    set('st-smtpPort', d.port || 587);
    set('st-smtpUser', d.user);
    set('st-smtpFrom', d.from_addr);
    set('st-smtpTo',   Array.isArray(d.recipients) ? d.recipients.join(', ') : (d.recipients||''));
    const tls = document.getElementById('st-smtpTls');
    if (tls) tls.checked = d.starttls !== false;
    const pw = document.getElementById('st-smtpPw');
    if (pw) pw.value = d.has_password ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' : '';
  }).catch(function(){});
}

async function stSmtpSave() {
  const st = document.getElementById('st-smtpStatus');
  const rawPw = document.getElementById('st-smtpPw').value;
  const pw = rawPw === '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' ? null : rawPw;
  const body = {
    host:       document.getElementById('st-smtpHost').value.trim(),
    port:       parseInt(document.getElementById('st-smtpPort').value) || 587,
    user:       document.getElementById('st-smtpUser').value.trim(),
    from_addr:  document.getElementById('st-smtpFrom').value.trim(),
    recipients: document.getElementById('st-smtpTo').value.split(/[,;]/).map(function(s){return s.trim();}).filter(Boolean),
    starttls:   document.getElementById('st-smtpTls').checked,
  };
  if (pw !== null) body.password = pw;
  st.style.color = 'var(--muted)'; st.textContent = t('m365_smtp_saving','Saving...');
  try {
    const r = await fetch('/api/smtp/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const d = await r.json();
    if (d.error) { st.style.color='var(--danger)'; st.textContent=d.error; return; }
    st.style.color='var(--accent)'; st.textContent='\u2714 '+t('m365_smtp_saved','Saved');
  } catch(e){ st.style.color='var(--danger)'; st.textContent=e.message; }
}

async function stSmtpTest() {
  const st = document.getElementById('st-smtpStatus');
  await stSmtpSave();
  if (st) { st.style.color='var(--muted)'; st.textContent=t('m365_smtp_testing','Testing connection\u2026'); }
  try {
    const r = await fetch('/api/smtp/test', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({})});
    const d = await r.json();
    if (d.ok) {
      let msg;
      if (d.method === 'graph') {
        msg = t('m365_smtp_test_ok_graph','Test email sent via Microsoft Graph to') + ' ' + (d.recipients||[]).join(', ');
      } else if (d.method === 'smtp') {
        msg = t('m365_smtp_test_ok_smtp','Test email sent via SMTP to') + ' ' + (d.recipients||[]).join(', ');
        if (d.graph_also_failed) msg += ' ' + t('m365_smtp_graph_also_failed','(⚠ Graph also failed — Mail.Send not granted)');
      } else {
        msg = d.message || t('m365_smtp_test_ok','Test email sent');
      }
      if (st) { st.style.color='var(--accent)'; st.textContent='\u2714 ' + msg; }
    } else {
      if (st) { st.style.color='var(--danger)'; st.textContent='\u2717 ' + (d.error || t('m365_smtp_test_fail','Connection failed')); }
    }
  } catch(e) {
    if (st) { st.style.color='var(--danger)'; st.textContent='\u2717 ' + e.message; }
  }
}

async function stSmtpSend() {
  const st = document.getElementById('st-smtpStatus');
  // First save current field values
  await stSmtpSave();
  // Check we have recipients
  const recipStr = document.getElementById('st-smtpTo').value.trim();
  if (!recipStr) {
    if (st) { st.style.color='var(--danger)'; st.textContent=t('m365_smtp_no_recipients','Enter at least one recipient.'); }
    return;
  }
  const recipients = recipStr.split(/[,;]/).map(function(s){return s.trim();}).filter(Boolean);
  const rawPw = document.getElementById('st-smtpPw').value;
  const cfg = {
    host:      document.getElementById('st-smtpHost').value.trim(),
    port:      parseInt(document.getElementById('st-smtpPort').value) || 587,
    username:  document.getElementById('st-smtpUser').value.trim(),
    password:  rawPw === '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' ? null : rawPw,
    from_addr: document.getElementById('st-smtpFrom').value.trim(),
    use_tls:   document.getElementById('st-smtpTls').checked,
    use_ssl:   false,
  };
  if (st) { st.style.color='var(--muted)'; st.textContent=t('m365_smtp_sending','Sending\u2026'); }
  try {
    const r = await fetch('/api/send_report', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({recipients, smtp:cfg})});
    const d = await r.json();
    if (d.status === 'sent') {
      if (st) { st.style.color='var(--accent)'; st.textContent=t('m365_smtp_sent','\u2714 Sent'); }
      log(t('m365_smtp_sent','Report sent to') + ' ' + recipients.join(', '), 'ok');
    } else {
      if (st) { st.style.color='var(--danger)'; st.textContent=d.error||'Send failed'; }
      log('Email send failed: '+(d.error||''),'err');
    }
  } catch(e){
    if (st) { st.style.color='var(--danger)'; st.textContent=e.message; }
  }
}

// ── Database tab ──────────────────────────────────────────────────────────────

function stLoadDbStats() {
  fetch('/api/db/stats').then(function(r){ return r.json(); }).then(function(d) {
    const el = document.getElementById('st-dbStats');
    if (!el) return;
    if (d.error) { el.textContent = d.error; return; }
    el.innerHTML =
      '<span>' + t('m365_stat_scanned','Scanned items') + '</span>: <strong>' + (d.total_items||0) + '</strong><br>' +
      '<span>' + t('m365_stat_flagged','Flagged items') + '</span>: <strong>' + (d.flagged_items||0) + '</strong><br>' +
      '<span>' + t('m365_db_scans','Scans') + '</span>: <strong>' + (d.total_scans||0) + '</strong>';
  }).catch(function(){ });
}

function stResetDB() {
  if (!confirm(t('m365_db_reset_confirm','Reset database? All scan results will be deleted.'))) return;
  requirePin(t('m365_settings_enter_pin_reset','Enter admin PIN to reset the database.'), function(pin) {
    fetch('/api/db/reset', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({confirm:'yes', pin:pin})
    }).then(function(r){ return r.json(); }).then(function(d) {
      if (d.error === 'incorrect_pin') { log(t('m365_settings_pin_wrong','Incorrect PIN \u2014 reset cancelled.'), 'err'); return; }
      if (d.error) { log('Reset failed: '+d.error, 'err'); return; }
      stLoadDbStats();
      log(t('m365_db_reset_done','Database reset'));
    }).catch(function(e){ log('Reset failed: '+e,'err'); });
  });
}

// Redirect old openSmtpModal to Settings email tab
function openSmtpModal(send) {
  openSettings('email');
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.schedLoad = schedLoad;
window.schedRenderJobs = schedRenderJobs;
window.schedToggleEnabled = schedToggleEnabled;
window.schedAddJob = schedAddJob;
window.schedEditJob = schedEditJob;
window.schedCancelEdit = schedCancelEdit;
window.schedSaveJob = schedSaveJob;
window.schedDeleteJob = schedDeleteJob;
window.schedRunJob = schedRunJob;
window.schedToggleFreqRows = schedToggleFreqRows;
window.schedPopulateProfiles = schedPopulateProfiles;
window.schedLoadHistory = schedLoadHistory;
window.schedUpdateSidebarIndicator = schedUpdateSidebarIndicator;
window.stPopulateGeneral = stPopulateGeneral;
window.stLoadSmtp = stLoadSmtp;
window.stSmtpSave = stSmtpSave;
window.stSmtpTest = stSmtpTest;
window.stSmtpSend = stSmtpSend;
window.stLoadDbStats = stLoadDbStats;
window.stResetDB = stResetDB;
window.openSmtpModal = openSmtpModal;
window._schedJobs = _schedJobs;
