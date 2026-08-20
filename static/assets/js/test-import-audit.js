(() => {
  const form = document.querySelector('[data-audit-run-form]');
  const overlay = document.querySelector('[data-audit-overlay]');
  if (!form || !overlay) return;

  const button = form.querySelector('[data-audit-run-button]');
  const message = overlay.querySelector('[data-audit-message]');
  const detail = overlay.querySelector('[data-audit-detail]');
  const bar = overlay.querySelector('[data-audit-bar]');
  const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
  let running = false;

  const setProgress = (percent, text, subtext) => {
    const safe = Math.max(0, Math.min(100, Number(percent) || 0));
    if (bar) bar.style.width = `${safe}%`;
    if (message) message.textContent = text || 'Auditing questions…';
    if (detail && subtext) detail.textContent = subtext;
  };

  const open = () => {
    overlay.classList.add('is-active');
    overlay.setAttribute('aria-hidden', 'false');
    document.documentElement.classList.add('tic-upload-busy');
  };

  const close = () => {
    overlay.classList.remove('is-active');
    overlay.setAttribute('aria-hidden', 'true');
    document.documentElement.classList.remove('tic-upload-busy');
  };

  const requestBatch = async (restart) => {
    const body = new FormData();
    body.append('restart', restart ? '1' : '0');
    if (csrf) body.append('csrfmiddlewaretoken', csrf.value);
    const response = await fetch(form.action, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || `Audit request failed (HTTP ${response.status}).`);
    return data;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (running) return;
    running = true;
    if (button) button.disabled = true;
    open();
    setProgress(2, 'Preparing the first AI batch…', 'No Redis or Celery worker is involved.');

    try {
      let first = true;
      const restartFirstBatch = form.dataset.auditRestart !== '0';
      while (true) {
        const data = await requestBatch(first && restartFirstBatch);
        first = false;
        setProgress(
          data.percent,
          data.message || `AI audit: ${data.done || 0}/${data.total || 0}`,
          `Checked ${data.done || 0} of ${data.total || 0} staging questions.`
        );
        if (data.complete) break;
      }
      setProgress(100, 'AI audit complete', 'Refreshing the review screen with the newest findings…');
      window.setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      setProgress(0, 'AI audit stopped', error.message || 'The audit provider could not complete the request.');
      if (button) button.disabled = false;
      running = false;
      window.setTimeout(close, 3500);
    }
  });
})();
