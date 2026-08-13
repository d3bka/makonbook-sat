(() => {
  'use strict';

  const gate = document.querySelector('[data-profile-name-gate]');
  if (!gate) return;

  const form = gate.querySelector('[data-profile-name-form]');
  const submit = gate.querySelector('[data-profile-name-submit]');
  const firstInput = gate.querySelector('[data-profile-first-name]');
  const lastInput = gate.querySelector('[data-profile-last-name]');
  const status = gate.querySelector('[data-profile-name-status]');
  const endpoint = gate.dataset.endpoint;

  if (!form || !submit || !firstInput || !lastInput || !endpoint) return;

  const errorNodes = {
    first_name: gate.querySelector('[data-profile-error="first_name"]'),
    last_name: gate.querySelector('[data-profile-error="last_name"]'),
  };

  const clearErrors = () => {
    Object.entries(errorNodes).forEach(([name, node]) => {
      if (node) node.textContent = '';
      const input = form.elements[name];
      if (input) input.closest('.profile-name-gate__field')?.classList.remove('has-error');
    });
    if (status) status.textContent = '';
  };

  const setErrors = (errors = {}) => {
    let firstInvalid = null;
    Object.entries(errors).forEach(([name, message]) => {
      const node = errorNodes[name];
      const input = form.elements[name];
      if (node) node.textContent = message || '';
      if (input) {
        input.closest('.profile-name-gate__field')?.classList.add('has-error');
        if (!firstInvalid) firstInvalid = input;
      }
    });
    if (firstInvalid) firstInvalid.focus();
  };

  const openGate = () => {
    gate.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      requestAnimationFrame(() => gate.classList.add('is-open'));
    });

    window.setTimeout(() => {
      const target = !firstInput.value.trim() ? firstInput : lastInput;
      try {
        target.focus({ preventScroll: true });
      } catch (_) {
        target.focus();
      }
    }, 480);
  };

  const finishGate = (payload) => {
    const fullName = (payload.full_name || '').trim();
    if (fullName) {
      document.querySelectorAll('[data-header-user-name]').forEach((node) => {
        node.textContent = fullName;
      });
    }

    gate.classList.add('is-done');
    gate.classList.remove('is-open');
    gate.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => gate.remove(), 560);
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearErrors();

    const firstName = firstInput.value.trim();
    const lastName = lastInput.value.trim();
    const clientErrors = {};

    if (!firstName) clientErrors.first_name = 'Enter your first name.';
    if (!lastName) clientErrors.last_name = 'Enter your last name.';

    if (Object.keys(clientErrors).length) {
      setErrors(clientErrors);
      return;
    }

    gate.classList.add('is-saving');
    submit.disabled = true;
    const label = submit.querySelector('span');
    const previousLabel = label ? label.textContent : '';
    if (label) label.textContent = 'Saving…';

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch (_) {
        payload = {};
      }

      if (!response.ok || !payload.ok) {
        setErrors(payload.errors || {});
        if (!payload.errors && status) {
          status.textContent = 'Could not save your name. Please try again.';
        }
        return;
      }

      finishGate(payload);
    } catch (_) {
      if (status) status.textContent = 'Connection problem. Check your internet and try again.';
    } finally {
      gate.classList.remove('is-saving');
      submit.disabled = false;
      if (label) label.textContent = previousLabel || 'Save & continue';
    }
  });

  /* This prompt intentionally cannot be dismissed while required name fields
     are empty. It disappears permanently as soon as both names are saved. */
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && gate.classList.contains('is-open')) {
      event.preventDefault();
    }
  });

  openGate();
})();
