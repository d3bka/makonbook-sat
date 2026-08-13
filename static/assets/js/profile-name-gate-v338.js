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

  const touched = new Set();
  const apostrophes = new Set(["'", '’', '‘', 'ʻ', 'ʼ', '`', '´']);
  const punctuation = new Set([...apostrophes, '-']);
  const separators = new Set([...punctuation, ' ']);

  const isLetter = (char) => {
    if (!char) return false;
    return char.toLocaleUpperCase() !== char.toLocaleLowerCase();
  };

  const normalizeName = (value) => {
    let normalized = String(value || '').trim().replace(/\s+/g, ' ');
    if (typeof normalized.normalize === 'function') {
      normalized = normalized.normalize('NFC');
    }
    return normalized;
  };

  const validateName = (rawValue, label) => {
    const value = normalizeName(rawValue);

    if (!value) return `Enter your ${label.toLowerCase()}.`;
    if (value.length < 2 || value.length > 50) {
      return `${label} must be between 2 and 50 characters.`;
    }

    let letters = 0;
    for (const char of value) {
      if (isLetter(char)) {
        letters += 1;
        continue;
      }
      if (separators.has(char)) continue;
      return `${label} can contain only letters, spaces, hyphens, and apostrophes.`;
    }

    if (letters < 2) return `${label} must contain at least 2 letters.`;
    if (!isLetter(value[0]) || !isLetter(value[value.length - 1])) {
      return `${label} must start and end with a letter.`;
    }

    for (let index = 1; index < value.length; index += 1) {
      if (punctuation.has(value[index - 1]) && punctuation.has(value[index])) {
        return `${label} has repeated punctuation.`;
      }
    }

    return '';
  };

  const setFieldError = (name, message = '') => {
    const node = errorNodes[name];
    const input = form.elements[name];
    const field = input?.closest('.profile-name-gate__field');

    if (node) node.textContent = message;
    field?.classList.toggle('has-error', Boolean(message));
    if (input) input.setAttribute('aria-invalid', message ? 'true' : 'false');
  };

  const clearErrors = () => {
    Object.keys(errorNodes).forEach((name) => setFieldError(name, ''));
    if (status) status.textContent = '';
  };

  const setErrors = (errors = {}) => {
    let firstInvalid = null;
    Object.entries(errors).forEach(([name, message]) => {
      setFieldError(name, message || '');
      const input = form.elements[name];
      if (input && !firstInvalid) firstInvalid = input;
    });
    if (firstInvalid) firstInvalid.focus();
  };

  const validateField = (input, force = false) => {
    const name = input.name;
    const label = name === 'first_name' ? 'First name' : 'Last name';
    const message = validateName(input.value, label);

    if (force || touched.has(name) || message.includes('only letters')) {
      setFieldError(name, message);
    } else {
      setFieldError(name, '');
    }
    return message;
  };

  [firstInput, lastInput].forEach((input) => {
    input.addEventListener('input', () => {
      if (status) status.textContent = '';
      validateField(input, false);
    });

    input.addEventListener('blur', () => {
      touched.add(input.name);
      validateField(input, true);
    });
  });

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

    const firstName = normalizeName(firstInput.value);
    const lastName = normalizeName(lastInput.value);
    firstInput.value = firstName;
    lastInput.value = lastName;

    touched.add('first_name');
    touched.add('last_name');

    const clientErrors = {};
    const firstError = validateName(firstName, 'First name');
    const lastError = validateName(lastName, 'Last name');
    if (firstError) clientErrors.first_name = firstError;
    if (lastError) clientErrors.last_name = lastError;

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
