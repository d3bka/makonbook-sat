(() => {
  const root = document.querySelector('[data-import-progress]');
  if (!root) return;

  const statusUrl = root.dataset.statusUrl;
  const activeStatuses = new Set(['queued', 'processing']);
  const bar = root.querySelector('[data-progress-bar]');
  const percentEl = root.querySelector('[data-progress-percent]');
  const messageEl = root.querySelector('[data-progress-message]');
  const warningEl = root.querySelector('[data-progress-warning]');
  const badge = document.querySelector('[data-import-status-badge]');
  const liveLog = document.querySelector('[data-live-log]');
  let currentStatus = root.dataset.status || '';
  let failures = 0;
  let timer = null;

  const renderLog = (rows) => {
    if (!liveLog || !Array.isArray(rows)) return;
    liveLog.replaceChildren();
    [...rows].reverse().forEach((row) => {
      const p = document.createElement('p');
      const small = document.createElement('small');
      if (row.at) {
        const date = new Date(row.at);
        small.textContent = Number.isNaN(date.getTime()) ? row.at : date.toLocaleString();
      }
      p.appendChild(small);
      p.append(document.createTextNode(row.message || ''));
      liveLog.appendChild(p);
    });
  };

  const render = (data) => {
    const percent = Math.max(0, Math.min(100, Number(data.percent) || 0));
    root.classList.remove('is-hidden');
    if (bar) bar.style.width = `${percent}%`;
    if (percentEl) percentEl.textContent = `${percent}%`;
    if (messageEl) messageEl.textContent = data.message || data.status_label || 'Processing...';
    if (badge) {
      badge.textContent = data.status_label || data.status;
      badge.className = `tic-status ${data.status || ''}`;
      badge.dataset.importStatusBadge = '';
    }
    if (warningEl) {
      const warning = data.worker_warning || '';
      warningEl.textContent = warning;
      warningEl.classList.toggle('is-hidden', !warning);
    }
    renderLog(data.log);

    if (!activeStatuses.has(data.status) && activeStatuses.has(currentStatus)) {
      window.setTimeout(() => window.location.reload(), 650);
      return;
    }
    currentStatus = data.status;
  };

  const poll = async () => {
    try {
      const response = await fetch(statusUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      failures = 0;
      render(data);
      if (activeStatuses.has(data.status)) {
        timer = window.setTimeout(poll, 1800);
      }
    } catch (error) {
      failures += 1;
      if (warningEl && failures >= 2) {
        warningEl.textContent = 'Live progress is temporarily unavailable. The background task may still be running.';
        warningEl.classList.remove('is-hidden');
      }
      timer = window.setTimeout(poll, Math.min(8000, 1800 + failures * 1000));
    }
  };

  if (activeStatuses.has(currentStatus)) poll();
  window.addEventListener('beforeunload', () => timer && clearTimeout(timer));
})();
