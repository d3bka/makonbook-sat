(() => {
  'use strict';

  const shell = document.querySelector('.tic-shell');
  if (!shell || !window.fetch || !window.FormData) return;

  const postForm = async (form) => {
    const response = await fetch(form.action || window.location.href, {
      method: (form.method || 'POST').toUpperCase(),
      body: new FormData(form),
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_) {
      payload = { ok: false, error: 'The server returned an unexpected response.' };
    }
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `Request failed (${response.status}).`);
    }
    return payload;
  };

  const showNotice = (message, type = 'success') => {
    if (!message) return;
    let box = shell.querySelector('[data-tic-live-notice]');
    if (!box) {
      box = document.createElement('div');
      box.dataset.ticLiveNotice = '1';
      shell.prepend(box);
    }
    box.className = `tic-alert tic-live-alert ${type}`;
    box.textContent = message;
    window.clearTimeout(showNotice._timer);
    showNotice._timer = window.setTimeout(() => box.remove(), 4800);
  };

  const setBusy = (button, busy, text = 'Working…') => {
    if (!button) return;
    if (busy) {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.classList.add('is-loading');
      button.innerHTML = `<span class="tic-inline-spinner" aria-hidden="true"></span><span>${text}</span>`;
    } else {
      button.disabled = false;
      button.classList.remove('is-loading');
      if (button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
        delete button.dataset.originalHtml;
      }
    }
  };

  const updateAvailabilityCard = (form, isOpen) => {
    const card = form.closest('[data-published-test-card]');
    const badge = card && card.querySelector('[data-availability-badge]');
    const button = form.querySelector('[data-availability-button]');
    const stateInput = form.querySelector('input[name="state"]');

    form.dataset.currentState = isOpen ? 'open' : 'closed';
    if (stateInput) stateInput.value = isOpen ? 'closed' : 'open';

    if (badge) {
      badge.className = isOpen ? 'tic-mini-badge' : 'tic-status failed';
      badge.textContent = isOpen ? 'MAKONBOOK OPEN' : 'MAKONBOOK CLOSED';
    }
    if (button) {
      button.classList.toggle('danger', isOpen);
      button.classList.toggle('primary', !isOpen);
      button.innerHTML = isOpen
        ? '<i class="bi bi-lock-fill"></i> <span>Close MakonBook access</span>'
        : '<i class="bi bi-unlock-fill"></i> <span>Open MakonBook access</span>';
    }
  };

  document.querySelectorAll('[data-tic-availability-form]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const currentState = form.dataset.currentState || 'open';
      const testName = form.dataset.testName || 'this test';
      const closing = currentState === 'open';
      const question = closing
        ? `Close ${testName} across MakonBook? Students, Teachers, Support Teachers and all Classroom attempts will be blocked. Guest Mode and Manager/Admin/Tester QA remain available.`
        : `Reopen ${testName} across MakonBook?`;
      if (!window.confirm(question)) return;

      const button = form.querySelector('[data-availability-button]');
      setBusy(button, true, closing ? 'Closing…' : 'Opening…');
      try {
        const payload = await postForm(form);
        updateAvailabilityCard(form, Boolean(payload.is_available));
        showNotice(payload.message, payload.is_available ? 'success' : 'warning');
      } catch (error) {
        showNotice(error.message, 'error');
      } finally {
        if (button) {
          button.disabled = false;
          button.classList.remove('is-loading');
        }
      }
    });
  });

  const updateFailedCounter = () => {
    const form = document.querySelector('[data-tic-clear-failed]');
    if (!form) return;
    const count = document.querySelectorAll('[data-import-job][data-job-status="failed"]').length;
    form.dataset.failedCount = String(count);
    const button = form.querySelector('button');
    if (count <= 0) {
      form.remove();
    } else if (button) {
      button.innerHTML = `<i class="bi bi-trash3"></i> Clear failed (${count})`;
    }
  };

  const ensureQueueEmptyState = () => {
    const list = document.querySelector('.tic-list');
    if (!list || list.querySelector('[data-import-job]')) return;
    if (list.querySelector('.tic-empty')) return;
    list.insertAdjacentHTML(
      'beforeend',
      '<div class="tic-empty"><i class="bi bi-file-earmark-pdf"></i><h3>No staging imports</h3><p>The publishing queue is clean. Upload a PDF when you are ready to build another test.</p></div>'
    );
  };

  document.querySelectorAll('[data-tic-draft-delete]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const name = form.dataset.jobName || 'this draft';
      const count = Number(form.dataset.questionCount || 0);
      const detail = count ? ` ${count} extracted question(s) will be removed.` : '';
      if (!window.confirm(`Delete staging draft “${name}”?${detail} This does not delete a separately published MakonBook test.`)) return;

      const row = form.closest('[data-import-job]');
      const button = form.querySelector('button');
      setBusy(button, true, '');
      row && row.classList.add('is-removing');
      try {
        const payload = await postForm(form);
        if (row) {
          row.classList.add('is-removed');
          window.setTimeout(() => {
            row.remove();
            updateFailedCounter();
            ensureQueueEmptyState();
          }, 180);
        }
        showNotice(payload.message, 'success');
      } catch (error) {
        row && row.classList.remove('is-removing');
        setBusy(button, false);
        showNotice(error.message, 'error');
      }
    });
  });

  const clearFailedForm = document.querySelector('[data-tic-clear-failed]');
  if (clearFailedForm) {
    clearFailedForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const count = Number(clearFailedForm.dataset.failedCount || 0);
      if (!window.confirm(`Delete all ${count} FAILED staging import(s)? Their uploaded PDFs and staging questions will be removed.`)) return;
      const button = clearFailedForm.querySelector('button');
      setBusy(button, true, 'Clearing…');
      try {
        const payload = await postForm(clearFailedForm);
        document.querySelectorAll('[data-import-job][data-job-status="failed"]').forEach((row) => row.remove());
        clearFailedForm.remove();
        ensureQueueEmptyState();
        const suffix = payload.skipped ? ` ${payload.skipped} could not be deleted safely.` : '';
        showNotice(`${payload.message || 'Failed drafts cleared.'}${suffix}`, payload.skipped ? 'warning' : 'success');
      } catch (error) {
        setBusy(button, false);
        showNotice(error.message, 'error');
      }
    });
  }

  const publishedDeleteForm = document.querySelector('[data-tic-published-delete]');
  if (publishedDeleteForm) {
    publishedDeleteForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = publishedDeleteForm.querySelector('button[type="submit"]');
      setBusy(button, true, 'Deleting…');
      try {
        const payload = await postForm(publishedDeleteForm);
        window.location.assign(payload.redirect_url || publishedDeleteForm.dataset.redirectUrl || '/sat/test-imports/published/');
      } catch (error) {
        setBusy(button, false);
        showNotice(error.message, 'error');
      }
    });
  }
})();
