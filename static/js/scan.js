import { S } from './state.js';
// ── DB Export / Import (#11) ──────────────────────────────────────────────────

async function exportDB() {
  // In pywebview app, use native save dialog; in browser, use blob download
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_db_export) {
    try {
      const r = await window.pywebview.api.save_db_export();
      if (r && r.ok) { log(t('m365_db_exported','Database exported') + ': ' + r.path); }
      else if (r && r.error && r.error !== 'cancelled') { alert(t('m365_db_export_error','Export failed') + ': ' + r.error); }
    } catch(e) { alert(t('m365_db_export_error','Export failed') + ': ' + e.message); }
    return;
  }
  // Browser fallback
  try {
    const res = await fetch('/api/db/export');
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert(t('m365_db_export_error','Export failed') + ': ' + (d.error || res.statusText));
      return;
    }
    const blob = await res.blob();
    const cd   = res.headers.get('Content-Disposition') || '';
    const m    = cd.match(/filename="([^"]+)"/);
    const name = m ? m[1] : 'gdpr_export.zip';
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
    log(t('m365_db_exported','Database exported') + ': ' + name);
  } catch(e) {
    alert(t('m365_db_export_error','Export failed') + ': ' + e.message);
  }
}

function openImportDBModal() {
  const fi = document.getElementById('importDbFile');
  if (fi) fi.value = '';
  const mode = document.getElementById('importDbMode');
  if (mode) mode.value = 'merge';
  document.getElementById('importDbReplaceWarn').style.display = 'none';
  document.getElementById('importDbStatus').textContent = '';
  document.getElementById('importDbBackdrop').classList.add('open');
}

function closeImportDBModal() {
  document.getElementById('importDbBackdrop').classList.remove('open');
}

// Show/hide the replace warning when mode changes
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('importDbMode')?.addEventListener('change', function() {
    document.getElementById('importDbReplaceWarn').style.display =
      this.value === 'replace' ? 'block' : 'none';
  });
});

async function doImportDB() {
  const fi   = document.getElementById('importDbFile');
  const mode = document.getElementById('importDbMode')?.value || 'merge';
  const stat = document.getElementById('importDbStatus');
  const btn  = document.getElementById('importDbBtn');
  if (!fi?.files?.length) {
    stat.textContent = t('m365_db_import_no_file','Please select a ZIP file first.');
    stat.style.color = 'var(--danger)';
    return;
  }
  if (mode === 'replace') {
    if (!confirm(t('m365_db_import_replace_confirm',
      'Replace mode will erase ALL existing scan data and restore from the archive.\n\nMake sure you have a manual backup of ~/.gdpr_scanner.db.\n\nProceed?'))) return;
  }
  btn.disabled = true;
  stat.style.color = 'var(--muted)';
  stat.textContent = t('m365_db_importing','Importing…');
  const fd = new FormData();
  fd.append('file', fi.files[0]);
  fd.append('mode', mode);
  if (mode === 'replace') fd.append('confirm', 'yes');
  try {
    const r = await fetch('/api/db/import', { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok || d.error) {
      stat.style.color = 'var(--danger)';
      stat.textContent = '✖ ' + (d.error || r.statusText);
    } else {
      const counts = Object.entries(d.imported || {}).map(([k,v]) => `${k}: ${v}`).join(', ');
      stat.style.color = 'var(--accent)';
      stat.textContent = '✔ ' + t('m365_db_imported','Imported') + (counts ? ' (' + counts + ')' : '');
      log(t('m365_db_imported','Imported') + ' [' + mode + '] ' + fi.files[0].name);
    }
  } catch(e) {
    stat.style.color = 'var(--danger)';
    stat.textContent = '✖ ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Scan ─────────────────────────────────────────────────────────────────────
function buildScanPayload() {
  // Collect checked M365 sources from dynamic panel
  const sources = [];
  document.querySelectorAll('#sourcesPanel input[data-source-type="m365"]:checked').forEach(function(cb) {
    sources.push(cb.dataset.sourceId);
  });
  // Collect checked file sources (local/smb) — handled separately in startScan()
  // but included here so profiles and checkpoint checks are aware of them
  const fileSources = [];
  document.querySelectorAll('#sourcesPanel input[data-source-type="file"]:checked').forEach(function(cb) {
    fileSources.push(cb.dataset.sourceId);
  });
  // Collect checked Google sources
  const googleSources = [];
  document.querySelectorAll('#sourcesPanel input[data-source-type="google"]:checked').forEach(function(cb) {
    googleSources.push(cb.dataset.sourceId);
  });
  const user_ids = getSelectedUsers();
  // Merge all source types into a single array for profiles
  const allSources = sources.concat(fileSources).concat(googleSources);
  const options = {
    older_than_days:  parseInt(document.getElementById('olderThan').value) || 0,
    email_body:       document.getElementById('optEmailBody').checked,
    attachments:      document.getElementById('optAttachments').checked,
    max_attach_mb:    parseInt(document.getElementById('optMaxAttachMB').value) || 20,
    max_emails:       parseInt(document.getElementById('optMaxEmails').value) || 200,
    delta:            document.getElementById('optDelta') ? document.getElementById('optDelta').checked : false,
    scan_photos:      document.getElementById('optScanPhotos') ? document.getElementById('optScanPhotos').checked : false,
    skip_gps_images:  document.getElementById('optSkipGps') ? document.getElementById('optSkipGps').checked : false,
    min_cpr_count:    document.getElementById('optMinCpr') ? (parseInt(document.getElementById('optMinCpr').value) || 1) : 1,
    retention_enabled: document.getElementById('optRetention') ? document.getElementById('optRetention').checked : false,
    retention_years:  parseInt(document.getElementById('optRetentionYears')?.value) || 5,
    fiscal_year_end:  document.getElementById('optFiscalYearEnd')?.value || '',
  };
  return { sources, fileSources, allSources, googleSources, user_ids, options };
}

async function checkCheckpoint() {
  const payload = buildScanPayload();
  if (!payload.sources.length && !payload.fileSources.length) return;
  if (payload.sources.length && !payload.user_ids.length) return;
  try {
    const r = await fetch('/api/scan/checkpoint', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    const banner = document.getElementById('resumeBanner');
    if (d.exists) {
      const ts = d.started_at ? new Date(d.started_at * 1000).toLocaleString([], {dateStyle:'short', timeStyle:'short'}) : '';
      document.getElementById('resumeBannerText').textContent =
        t('m365_resume_banner', `Previous scan interrupted (${d.scanned_count} scanned, ${d.flagged_count} found${ts ? ' — ' + ts : ''})`);
      banner.style.display = 'flex';
    } else {
      banner.style.display = 'none';
    }
  } catch(e) { /* ignore */ }
}

async function clearCheckpointAndScan() {
  await fetch('/api/scan/clear_checkpoint', {method:'POST'});
  document.getElementById('resumeBanner').style.display = 'none';
  startScan(false);
}

async function checkDeltaStatus() {
  const cb = document.getElementById('optDelta');
  if (!cb) return;
  try {
    const r = await fetch('/api/delta/status');
    const d = await r.json();
    const row = document.getElementById('deltaStatusRow');
    const txt = document.getElementById('deltaStatusText');
    if (d.exists) {
      const src = d.count === 1 ? '1 source' : `${d.count} sources`;
      txt.textContent = t('m365_delta_tokens_saved', `Tokens saved for ${src}`);
      row.style.display = 'flex';
      row.style.alignItems = 'center';
    } else {
      row.style.display = 'none';
    }
  } catch(e) { /* ignore */ }
}

async function clearDeltaTokens() {
  await fetch('/api/delta/clear', {method:'POST'});
  document.getElementById('deltaStatusRow').style.display = 'none';
  log(t('m365_delta_cleared', 'Delta tokens cleared — next scan will be a full scan.'));
}

// ── SMTP / Email report modal ─────────────────────────────────────────────────

function openSmtpModal(focusSend) {
  document.getElementById('smtpBackdrop').classList.add('open');
  document.getElementById('smtpStatus').textContent = '';
  loadSmtpConfig();
  if (focusSend) {
    setTimeout(() => document.getElementById('smtpRecipients').focus(), 120);
  }
}

function closeSmtpModal() {
  document.getElementById('smtpBackdrop').classList.remove('open');
}

async function loadSmtpConfig() {
  try {
    const r = await fetch('/api/smtp/config');
    const d = await r.json();
    if (d.host)       document.getElementById('smtpHost').value        = d.host;
    if (d.port)       document.getElementById('smtpPort').value        = d.port;
    if (d.username)   document.getElementById('smtpUser').value        = d.username;
    if (d.from_addr)  document.getElementById('smtpFrom').value        = d.from_addr;
    if (d.recipients) document.getElementById('smtpRecipients').value  = Array.isArray(d.recipients) ? d.recipients.join(', ') : d.recipients;
    if (d.password_saved) document.getElementById('smtpPass').placeholder = '(password saved)';
    if (d.use_tls !== undefined) document.getElementById('smtpTLS').checked = d.use_tls;
    if (d.use_ssl !== undefined) document.getElementById('smtpSSL').checked = d.use_ssl;
  } catch(e) { /* ignore */ }
}

async function saveSmtpConfig() {
  const cfg = _smtpFields();
  const r = await fetch('/api/smtp/config', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(cfg)
  });
  const d = await r.json();
  const el = document.getElementById('smtpStatus');
  if (d.status === 'saved') {
    el.style.color = 'var(--success)';
    el.textContent = t('m365_smtp_saved', 'Settings saved.');
    if (cfg.password) document.getElementById('smtpPass').placeholder = '(password saved)';
  } else {
    el.style.color = 'var(--danger)';
    el.textContent = d.error || 'Error saving';
  }
}

async function sendReport() {
  const cfg = _smtpFields();
  const recipStr = document.getElementById('smtpRecipients').value.trim();
  if (!recipStr) {
    document.getElementById('smtpStatus').style.color = 'var(--danger)';
    document.getElementById('smtpStatus').textContent = t('m365_smtp_no_recipients', 'Enter at least one recipient.');
    document.getElementById('smtpRecipients').focus();
    return;
  }
  const recipients = recipStr.split(/[,;]/).map(s => s.trim()).filter(Boolean);
  const statusEl = document.getElementById('smtpStatus');
  statusEl.style.color = 'var(--muted)';
  statusEl.textContent = t('m365_smtp_sending', 'Sending…');

  const r = await fetch('/api/send_report', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({recipients, smtp: cfg})
  });
  const d = await r.json();
  if (d.status === 'sent') {
    statusEl.style.color = 'var(--success)';
    statusEl.textContent = t('m365_smtp_sent', 'Sent to ' + recipients.join(', '));
    log('Report emailed to ' + recipients.join(', '), 'ok');
  } else {
    statusEl.style.color = 'var(--danger)';
    statusEl.textContent = d.error || 'Send failed';
    log('Email send failed: ' + (d.error || ''), 'err');
  }
}

function _smtpFields() {
  return {
    host:       document.getElementById('smtpHost').value.trim(),
    port:       parseInt(document.getElementById('smtpPort').value) || 587,
    username:   document.getElementById('smtpUser').value.trim(),
    password:   document.getElementById('smtpPass').value,
    from_addr:  document.getElementById('smtpFrom').value.trim(),
    use_tls:    document.getElementById('smtpTLS').checked,
    use_ssl:    document.getElementById('smtpSSL').checked,
    recipients: document.getElementById('smtpRecipients').value,
  };
}



// ── Shared SSE event listeners (#21) ─────────────────────────────────────────
// Extracted so both startScan() and _autoConnectSSEIfRunning() share identical
// handlers — fixes the bug where replayed events from a scheduled scan were
// silently ignored because the page-load SSE only had scheduler_* listeners.

function _attachScanListeners(source) {
  source.addEventListener('scan_phase', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] scan_phase:', d.phase);
    // Ensure a progress segment exists before rendering phase text.
    // scan_phase can arrive before scan_progress (or before scan_start on replay
    // if scan_start has been pushed out of the 500-event SSE buffer).
    if (!S._m365ScanRunning && !S._googleScanRunning && !S._fileScanRunning) {
      var ph = (d.phase || '').toLowerCase();
      var phaseSrc = /google|gmail|gdrive/.test(ph) ? 'google'
                   : /^files\s*[—\-–]/.test(ph)    ? 'file'
                   : 'm365';
      if (phaseSrc === 'google')    { S._googleScanRunning = true; }
      else if (phaseSrc === 'file') { S._fileScanRunning   = true; }
      else                          { S._m365ScanRunning   = true; }
      document.getElementById('scanBtn').disabled = true;
      document.getElementById('stopBtn').style.display = 'inline-block';
      _renderProgressSegments();
    }
    _setProgressPhase(d.phase);
    log(d.phase);
  });
  source.addEventListener('scan_progress', function(e) {
    var d = JSON.parse(e.data);
    var src = d.source || 'm365';
    var pct = d.pct !== undefined ? d.pct
            : (d.total > 0 ? Math.round((d.index || d.completed || 0) / d.total * 100) : 0);
    S._srcPct[src] = pct;
    // If reconnecting mid-scan the running flag may not be set yet — ensure segment exists
    if (src === 'm365'    && !S._m365ScanRunning)   { S._m365ScanRunning   = true; document.getElementById('scanBtn').disabled = true; document.getElementById('stopBtn').style.display = 'inline-block'; _renderProgressSegments(); }
    if (src === 'google'  && !S._googleScanRunning) { S._googleScanRunning = true; document.getElementById('scanBtn').disabled = true; document.getElementById('stopBtn').style.display = 'inline-block'; _renderProgressSegments(); }
    if (src === 'file'    && !S._fileScanRunning)   { S._fileScanRunning   = true; document.getElementById('scanBtn').disabled = true; document.getElementById('stopBtn').style.display = 'inline-block'; _renderProgressSegments(); }
    var fill = document.getElementById('progressFill_' + src);
    if (fill) fill.style.width = pct + '%';
    document.getElementById('progressFile').textContent = d.file || '';
    var statsEl = document.getElementById('progressStats');
    var etaEl   = document.getElementById('progressEta');
    if (src === 'm365') {
      // M365 sends index + total + ETA — show exact counter
      if (statsEl && d.total) statsEl.textContent = (d.index || 0) + ' / ' + d.total;
      if (etaEl && d.eta !== undefined) etaEl.textContent = d.eta ? ('ETA ' + d.eta) : '';
    } else if (!S._m365ScanRunning) {
      // Google / file: no total known upfront — show running count once M365 is done
      if (statsEl && d.scanned !== undefined) statsEl.textContent = d.scanned + ' scanned';
      if (etaEl) etaEl.textContent = '';
    }
  });
  source.addEventListener('scan_file', function(e) {
    var d = JSON.parse(e.data);
    setLogLive(d.file || '');
  });
  source.addEventListener('scan_file_flagged', function(e) {
    var card = JSON.parse(e.data);
    console.log('[SSE] scan_file_flagged:', card.name || card.id);
    if (!S.flaggedData.find(function(x){ return x.id === card.id; })) {
      S.flaggedData.push(card);
      S.totalCPR += (card.cpr_count || 0);
      document.getElementById('filterBar').style.display = 'flex';
      document.getElementById('grid').style.display = S.isListView ? 'block' : 'grid';
      applyFilters();
    }
  });
  source.addEventListener('scan_error', function(e) {
    var d = JSON.parse(e.data);
    log((d.file ? d.file + ': ' : '') + d.error, 'err');
  });
  source.addEventListener('scan_cancelled', function() {
    if (S._userStartedScan) {
      S._userStartedScan = false;
      if (S.es) { S.es.close(); S.es = null; }
    }
    document.getElementById('scanBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'none';
    _clearProgressBar();
    setLogLive('');
    log('Scan stopped.', 'warn');
  });
  source.addEventListener('scan_done', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] scan_done:', d);
    S._srcPct.m365 = 100;
    S._m365ScanRunning = false;
    _renderProgressSegments();
    var _anyRunning = S._googleScanRunning || S._fileScanRunning;
    // Clear M365 counter/ETA so Google/file progress can take over the display
    if (_anyRunning) {
      var _se = document.getElementById('progressStats');
      var _ee = document.getElementById('progressEta');
      if (_se) _se.textContent = '';
      if (_ee) _ee.textContent = '';
    }
    // Only close SSE once all concurrent scans have finished.
    // Closing early would drop google_scan_done / file_scan_done events and
    // leave the UI stuck in scanning state.
    if (S._userStartedScan && !_anyRunning) {
      S._userStartedScan = false;
      if (S.es) { S.es.close(); S.es = null; }
    }
    if (!_anyRunning) setLogLive('');
    document.getElementById('scanBtn').disabled = _anyRunning;
    document.getElementById('stopBtn').style.display = _anyRunning ? 'inline-block' : 'none';
    if (!_anyRunning) _clearProgressBar();
    document.getElementById('statsSection').style.display = 'block';
    document.getElementById('statScanned').textContent = d.total_scanned;
    document.getElementById('statFlagged').textContent = d.flagged_count;
    document.getElementById('statCPR').textContent = S.totalCPR;
    document.getElementById('statsPill').style.display = 'block';
    updateStats();
    if (S.flaggedData.length) {
      document.getElementById('filterBar').style.display = 'flex';
      document.getElementById('grid').style.display = S.isListView ? 'block' : 'grid';
      applyFilters();
    } else {
      document.getElementById('emptyState').style.display = 'flex';
      document.getElementById('emptyState').innerHTML = '<div class="empty-icon">\u2705</div><div class="empty-text">' + t('m365_no_cpr_found','No CPR numbers found.') + '</div>';
    }
    var deltaNote = d.delta ? ' (\u0394 delta \u2014 ' + (d.delta_sources||0) + ' source(s) indexed)' : '';
    log('Scan complete \u2014 ' + d.flagged_count + ' flagged of ' + d.total_scanned + deltaNote, 'ok');
    if (d.delta) checkDeltaStatus();
    markOverdueCards();
    loadTrend();
    window.invalidateHistoryCache?.();
  });
  source.addEventListener('google_scan_done', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] google_scan_done:', d);
    S._srcPct.google = 100;
    S._googleScanRunning = false;
    _renderProgressSegments();
    if (!S._m365ScanRunning && !S._fileScanRunning) {
      if (S._userStartedScan) {
        S._userStartedScan = false;
        if (S.es) { S.es.close(); S.es = null; }
      }
      setLogLive('');
      document.getElementById('scanBtn').disabled = false;
      document.getElementById('stopBtn').style.display = 'none';
      _clearProgressBar();
      document.getElementById('statsSection').style.display = 'block';
      document.getElementById('statsPill').style.display = 'block';
      updateStats();
      if (S.flaggedData.length) {
        document.getElementById('filterBar').style.display = 'flex';
        document.getElementById('grid').style.display = S.isListView ? 'block' : 'grid';
        applyFilters();
      }
    }
    log('Google scan complete \u2014 ' + d.flagged_count + ' flagged of ' + d.total_scanned, 'ok');
    markOverdueCards();
    loadTrend();
    window.invalidateHistoryCache?.();
  });
  source.addEventListener('file_scan_done', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] file_scan_done:', d);
    S._srcPct.file = 100;
    S._fileScanRunning = false;
    _renderProgressSegments();
    if (!S._m365ScanRunning && !S._googleScanRunning) {
      if (S._userStartedScan) {
        S._userStartedScan = false;
        if (S.es) { S.es.close(); S.es = null; }
      }
      setLogLive('');
      document.getElementById('scanBtn').disabled = false;
      document.getElementById('stopBtn').style.display = 'none';
      _clearProgressBar();
      document.getElementById('statsSection').style.display = 'block';
      document.getElementById('statsPill').style.display = 'block';
      updateStats();
      if (S.flaggedData.length) {
        document.getElementById('filterBar').style.display = 'flex';
        document.getElementById('grid').style.display = S.isListView ? 'block' : 'grid';
        applyFilters();
      }
    }
    log('Bestandsscan fuldf\u00f8rt \u2014 ' + d.flagged_count + ' flagget af ' + d.total_scanned, 'ok');
    markOverdueCards();
    loadTrend();
    window.invalidateHistoryCache?.();
  });
  // sse_replay_done marks end of buffer replay — log a note so the user knows
  // earlier events above were replayed from an already-running scan
  source.addEventListener('sse_replay_done', function() {
    log(t('m365_sse_replay_note', 'Live log resumed \u2014 earlier entries replayed from running scan.'));
  });
}

function _attachSchedulerListeners(source) {
  source.addEventListener('scheduler_started', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] scheduler_started received:', d);
    log('\uD83D\uDD50 ' + t('m365_sched_title','Scheduled scan') + ': ' + (d.job_name||'') + '\u2026');
    // Show progress UI so scan_phase / scan_progress events are visible
    document.getElementById('scanBtn').disabled = true;
    document.getElementById('stopBtn').style.display = 'inline-block';
    S._srcPct = { m365: 0, google: 0, file: 0 }; S._m365ScanRunning = true; _renderProgressSegments();
    _setProgressPhase((d.job_name||'') + '\u2026');
    document.getElementById('progressFile').textContent = '';
  });
  source.addEventListener('scan_start', function(e) {
    // Scheduled scans also emit scan_start — show progress UI in case
    // scheduler_started was missed (e.g. browser reconnected mid-scan)
    console.log('[SSE] scan_start received');
    document.getElementById('scanBtn').disabled = true;
    document.getElementById('stopBtn').style.display = 'inline-block';
    // Ensure at least the M365 segment is rendered (scan_start is M365-only)
    if (!S._m365ScanRunning) { S._m365ScanRunning = true; _renderProgressSegments(); }
  });
  source.addEventListener('scheduler_done', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] scheduler_done received:', d);
    document.getElementById('scanBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'none';
    _clearProgressBar();
    log('\u2713 ' + t('m365_sched_title','Scheduled scan') + ' ' + (d.job_name||'') + ' \u2014 ' + (d.flagged||0) + ' flagged', 'ok');
    markOverdueCards();
    loadTrend();
  });
  source.addEventListener('scheduler_error', function(e) {
    var d = JSON.parse(e.data);
    console.log('[SSE] scheduler_error received:', d);
    document.getElementById('scanBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'none';
    _clearProgressBar();
    log('\u26A0 ' + t('m365_sched_title','Scheduled scan') + ' failed: ' + (d.error||''), 'err');
  });
}


function startScan(resume) {
  const { sources, fileSources, googleSources, user_ids, options } = buildScanPayload();
  if (!sources.length && !fileSources.length && !googleSources.length) { alert(t('m365_no_sources','No sources selected — nothing to scan.')); return; }
  if (sources.length && !user_ids.length && !googleSources.length) { alert('Select at least one account to scan.'); return; }

  // When resuming, keep existing cards; otherwise clear everything
  if (!resume) {
    S.flaggedData = []; S.filteredData = []; S.totalCPR = 0;
    document.getElementById('grid').innerHTML = '';
    document.getElementById('grid').style.display = 'none';
    document.getElementById('emptyState').style.display = 'none';
    const _lss = document.getElementById('lastScanSummary'); if (_lss) _lss.style.display = 'none';
    document.getElementById('statsSection').style.display = 'none';
    document.getElementById('statsPill').style.display = 'none';
  }
  // Exit history mode — live SSE takes over
  window.exitHistoryMode?.();
  document.getElementById('resumeBanner').style.display = 'none';
  document.getElementById('logPanel').innerHTML = '<div class="log-line log-live" id="logLive" style="display:none"></div>';
  try { sessionStorage.removeItem(_LOG_SESSION_KEY); } catch(e) {}
  S._m365ScanRunning   = sources.length > 0;
  S._googleScanRunning = googleSources.length > 0;
  S._fileScanRunning   = fileSources.length > 0;
  S._srcPct = { m365: 0, google: 0, file: 0 };
  S._progressCurrentUser = '';
  _renderProgressSegments();
  document.getElementById('scanBtn').disabled = true;
  document.getElementById('stopBtn').style.display = 'inline-block';
  // progress segments rendered by _renderProgressSegments() called above
  document.getElementById('progressFile').textContent = '';
  _setProgressPhase(t('scan_preparing', 'Preparing…'));

  const dateLabel = options.older_than_days > 0 ? ', ' + t('m365_log_older_than', 'older than') + ' ' + document.getElementById('olderThanDate').value : '';
  const modeLabel = resume ? t('m365_log_resuming', 'Resuming scan:') : t('m365_log_starting_scan', 'Starting scan:');
  var googleCount = googleSources.length > 0 ? S._allUsers.filter(function(u) {
    return u.selected !== false && (u.platform === 'google' || u.platform === 'both');
  }).length : 0;
  var totalAccounts = (sources.length > 0 ? user_ids.length : 0) + (googleSources.length > 0 && sources.length === 0 ? googleCount : 0);
  var allSourceLabels = sources.concat(googleSources);
  log(modeLabel + ' ' + allSourceLabels.join(', ') + ' — ' + (totalAccounts || googleCount) + ' ' + t('m365_log_accounts', 'account(s)') + dateLabel + '…');

  // Always close and reopen SSE — ensures a fresh queue is registered
  // before the scan fires events (prevents missed events on the server side)
  if (S.es) { S.es.close(); S.es = null; }
  S._userStartedScan = true;
  _ensureSSE();

  setTimeout(() => {
    // Fire M365 scan if any M365 sources are selected
    if (sources.length > 0) {
      fetch('/api/scan/start', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({sources, user_ids, options, resume: !!resume,
                              profile_id: S._activeProfileId || null})
      }).then(r => {
        if (r.status === 409) { log('Scan already running', 'err'); }
      }).catch(e => { log('Scan start failed: ' + e, 'err'); });
    }

    // Fire file scans for each checked file source (local/smb)
    const checkedFileIds = [];
    document.querySelectorAll('#sourcesPanel input[data-source-type="file"]:checked').forEach(function(cb) {
      checkedFileIds.push(cb.dataset.sourceId);
    });
    checkedFileIds.forEach(function(id) {
      const source = S._fileSources.find(function(s) { return s.id === id; });
      if (!source) return;
      fetch('/api/file_scan/start', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(Object.assign({}, source, {
          scan_photos:      options.scan_photos     || false,
          skip_gps_images:  options.skip_gps_images || false,
          min_cpr_count:    options.min_cpr_count   || 1,
        }))
      }).catch(e => { log('File scan error: ' + e, 'err'); });
    });

    // Fire Google Workspace scan if any Google sources are selected
    const checkedGoogleIds = [];
    document.querySelectorAll('#sourcesPanel input[data-source-type="google"]:checked').forEach(function(cb) {
      checkedGoogleIds.push(cb.dataset.sourceId);
    });
    if (checkedGoogleIds.length > 0) {
      // Collect selected Google user emails from the account list
      var selectedGoogleEmails = S._allUsers
        .filter(function(u) { return u.selected !== false && (u.platform === 'google' || u.platform === 'both'); })
        .map(function(u) { return u.platform === 'both' ? u.googleEmail : u.email; })
        .filter(Boolean);
      fetch('/api/google/scan/start', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          sources:     checkedGoogleIds,
          user_emails: selectedGoogleEmails,
          options:     options
        })
      }).then(r => {
        if (r.status === 409) { log('Google scan already running', 'err'); }
      }).catch(e => { log('Google scan error: ' + e, 'err'); });
    }

    // All scan types fired above — no fallback error needed
  }, 300);

}

function stopScan() {
  fetch('/api/scan/stop', {method:'POST'});
}

// ── Trend sparkline (#7) ──────────────────────────────────────────────────────

function drawSparkline(data) {
  const canvas = document.getElementById('sparkCanvas');
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 220;
  const H   = 60;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const flagged = data.map(d => d.flagged_count);
  const overdue = data.map(d => d.overdue_count);
  const maxVal  = Math.max(...flagged, 1) * 1.2;
  const n       = data.length;
  const xPos    = i => (i / (n - 1)) * (W - 8) + 4;
  const yPos    = v => H - 4 - (v / maxVal) * (H - 10);

  const isDark   = document.body.getAttribute('data-theme') !== 'light';
  const cBlue    = '#378ADD';
  const cAmber   = '#BA7517';
  const cFill    = isDark ? 'rgba(55,138,221,0.12)' : 'rgba(55,138,221,0.08)';

  // Fill under flagged line
  ctx.beginPath();
  ctx.moveTo(xPos(0), yPos(flagged[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(xPos(i), yPos(flagged[i]));
  ctx.lineTo(xPos(n - 1), H);
  ctx.lineTo(xPos(0), H);
  ctx.closePath();
  ctx.fillStyle = cFill;
  ctx.fill();

  // Flagged line
  ctx.beginPath();
  ctx.moveTo(xPos(0), yPos(flagged[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(xPos(i), yPos(flagged[i]));
  ctx.strokeStyle = cBlue; ctx.lineWidth = 1.5; ctx.lineJoin = 'round';
  ctx.stroke();

  // Overdue dashed line
  ctx.beginPath();
  ctx.moveTo(xPos(0), yPos(overdue[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(xPos(i), yPos(overdue[i]));
  ctx.strokeStyle = cAmber; ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([]);

  // Dot on latest point
  ctx.beginPath();
  ctx.arc(xPos(n - 1), yPos(flagged[n - 1]), 3, 0, Math.PI * 2);
  ctx.fillStyle = cBlue; ctx.fill();

  // Labels: first, middle, last date (MM-DD only)
  const lblEl = document.getElementById('sparkLabels');
  if (lblEl) {
    const fmt = d => d.scan_date.slice(5);
    lblEl.innerHTML = `<span>${fmt(data[0])}</span><span>${fmt(data[Math.floor(n/2)])}</span><span>${fmt(data[n-1])}</span>`;
  }

  // Trend change label
  const last = flagged[n - 1], prev = flagged[n - 2] || last;
  const diff = last - prev;
  const pct  = prev ? Math.round(Math.abs(diff / prev) * 100) : 0;
  const arrow = diff < 0 ? '↓' : diff > 0 ? '↑' : '→';
  const color = diff < 0 ? 'var(--success)' : diff > 0 ? 'var(--danger)' : 'var(--muted)';
  const chEl = document.getElementById('trendChange');
  if (chEl) chEl.innerHTML = `<span style="color:${color}">${arrow} ${pct}%</span>`;

  // Hover tooltip
  canvas.onmousemove = e => {
    const rect = canvas.getBoundingClientRect();
    const mx  = e.clientX - rect.left;
    const idx = Math.round(((mx - 4) / (W - 8)) * (n - 1));
    if (idx < 0 || idx >= n) return;
    const d   = data[idx];
    const tip = document.getElementById('sparkTip');
    if (!tip) return;
    tip.style.display = 'block';
    tip.textContent = `${d.scan_date}  ${d.flagged_count} / ${d.overdue_count} overdue`;
    tip.style.left = Math.min(mx, W - tip.offsetWidth - 4) + 'px';
  };
  canvas.onmouseleave = () => {
    const tip = document.getElementById('sparkTip');
    if (tip) tip.style.display = 'none';
  };
}

async function loadTrend() {
  try {
    const r = await fetch('/api/db/trend?n=10');
    if (!r.ok) return;
    const data = await r.json();
    if (!Array.isArray(data) || data.length < 2) return;
    document.getElementById('trendPanel').style.display = 'block';
    // Defer draw until canvas has layout width
    setTimeout(() => drawSparkline(data), 60);
  } catch(e) { /* DB not available */ }
}

function updateStats() {
  document.getElementById('pillFlagged').textContent = S.flaggedData.length;
  document.getElementById('pillScanned').textContent =
    parseInt(document.getElementById('progressStats').textContent.split('/')[1] || '0') || 0;
}

// ── Window exports (HTML handlers + cross-module calls) ─────────────────────
window.exportDB = exportDB;
window.openImportDBModal = openImportDBModal;
window.closeImportDBModal = closeImportDBModal;
window.doImportDB = doImportDB;
window.buildScanPayload = buildScanPayload;
window.checkCheckpoint = checkCheckpoint;
window.clearCheckpointAndScan = clearCheckpointAndScan;
window.checkDeltaStatus = checkDeltaStatus;
window.clearDeltaTokens = clearDeltaTokens;
window.openSmtpModal = openSmtpModal;
window.closeSmtpModal = closeSmtpModal;
window.loadSmtpConfig = loadSmtpConfig;
window.saveSmtpConfig = saveSmtpConfig;
window.sendReport = sendReport;
window._smtpFields = _smtpFields;
window._attachScanListeners = _attachScanListeners;
window._attachSchedulerListeners = _attachSchedulerListeners;
window.startScan = startScan;
window.stopScan = stopScan;
window.drawSparkline = drawSparkline;
window.loadTrend = loadTrend;
window.updateStats = updateStats;
