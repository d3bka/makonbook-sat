(function () {
  'use strict';

  const dashboard = document.getElementById('studentGoalDashboard');
  const settings = document.getElementById('studentGoalSettings');
  const modal = document.querySelector('[data-goal-modal]');

  if (dashboard || settings || modal) {
    document.documentElement.classList.add('js-student-goal');
  }

  function setupReveal(root) {
    if (!root) return;
    const items = Array.from(root.querySelectorAll('[data-sg-reveal]'));
    if (!items.length) return;

    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      items.forEach((item) => item.classList.add('is-visible'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -30px' });

    items.forEach((item, index) => {
      item.style.transitionDelay = `${Math.min(index * 45, 260)}ms`;
      observer.observe(item);
    });
  }

  function pad(value) {
    return String(Math.max(0, value)).padStart(2, '0');
  }

  function setupCountdown(root) {
    const countdown = root && root.querySelector('[data-exam-countdown]');
    if (!countdown) return;

    const isoDate = countdown.getAttribute('data-exam-date');
    if (!isoDate) return;

    // SAT start times vary by test centre. 08:00 keeps the date countdown
    // intuitive without claiming an official appointment time.
    const examAt = new Date(`${isoDate}T08:00:00`);
    if (Number.isNaN(examAt.getTime())) return;

    const values = {
      days: countdown.querySelector('[data-countdown-days]'),
      hours: countdown.querySelector('[data-countdown-hours]'),
      minutes: countdown.querySelector('[data-countdown-minutes]'),
      seconds: countdown.querySelector('[data-countdown-seconds]'),
    };

    function update() {
      const distance = examAt.getTime() - Date.now();
      if (distance <= 0) {
        if (values.days) values.days.textContent = '0';
        if (values.hours) values.hours.textContent = '00';
        if (values.minutes) values.minutes.textContent = '00';
        if (values.seconds) values.seconds.textContent = '00';
        countdown.setAttribute('data-exam-arrived', 'true');
        return;
      }

      const totalSeconds = Math.floor(distance / 1000);
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor((totalSeconds % 86400) / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;

      if (values.days) values.days.textContent = String(days);
      if (values.hours) values.hours.textContent = pad(hours);
      if (values.minutes) values.minutes.textContent = pad(minutes);
      if (values.seconds) values.seconds.textContent = pad(seconds);
    }

    update();
    window.setInterval(update, 1000);
  }

  function setupMotivation(root) {
    if (!root) return;
    const script = document.getElementById('student-motivation-messages');
    const text = root.querySelector('[data-motivation-text]');
    const timer = root.querySelector('[data-motivation-timer]');
    const timerValue = root.querySelector('[data-motivation-seconds-left]');
    if (!script || !text || !timer) return;

    let messages = [];
    try {
      messages = JSON.parse(script.textContent || '[]');
    } catch (error) {
      messages = [];
    }
    messages = messages.filter((item) => typeof item === 'string' && item.trim());
    if (!messages.length) return;

    const rotationSeconds = Math.max(6, Number(timer.getAttribute('data-rotation-seconds') || 15));
    let index = 0;
    let remaining = rotationSeconds;

    function renderTimer() {
      const percentage = Math.max(0, Math.min(100, (remaining / rotationSeconds) * 100));
      timer.style.setProperty('--timer-progress', `${percentage}%`);
      if (timerValue) timerValue.textContent = String(Math.max(0, Math.ceil(remaining)));
    }

    function changeMessage() {
      index = (index + 1) % messages.length;
      text.classList.add('is-changing');
      window.setTimeout(() => {
        text.textContent = messages[index];
        text.classList.remove('is-changing');
      }, 180);
    }

    text.textContent = messages[0];
    renderTimer();

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    window.setInterval(() => {
      remaining -= 0.25;
      if (remaining <= 0) {
        changeMessage();
        remaining = rotationSeconds;
      }
      renderTimer();
    }, 250);
  }

  function readUniversityData() {
    const script = document.getElementById('student-goal-universities');
    if (!script) return new Map();
    try {
      const rows = JSON.parse(script.textContent || '[]');
      return new Map(rows.map((row) => [String(row.value), row]));
    } catch (error) {
      return new Map();
    }
  }

  function setupGoalModal(root) {
    if (!root) return;

    const form = root.querySelector('[data-goal-form]');
    const select = root.querySelector('[data-goal-university-select]');
    const searchInput = root.querySelector('[data-university-search]');
    const searchResult = root.querySelector('[data-university-search-result]');
    const customFields = root.querySelector('[data-custom-university-fields]');
    const preview = root.querySelector('[data-university-preview]');
    const openButtons = Array.from(document.querySelectorAll('[data-goal-modal-open]'));
    const closeButtons = Array.from(root.querySelectorAll('[data-goal-modal-close]'));
    const universityData = readUniversityData();
    let lastFocused = null;

    function setText(selector, value) {
      const element = preview && preview.querySelector(selector);
      if (element) element.textContent = value || '—';
    }

    function updateUniversityUI() {
      if (!select || !customFields || !preview) return;
      const value = select.value;
      const isOther = value === 'other';
      const university = universityData.get(value);

      customFields.classList.toggle('is-hidden', !isOther);
      customFields.setAttribute('aria-hidden', isOther ? 'false' : 'true');
      customFields.querySelectorAll('input').forEach((input) => {
        input.disabled = !isOther;
      });

      preview.classList.toggle('is-hidden', !university);
      if (university) {
        const location = [university.city, university.country].filter(Boolean).join(', ');
        const satReference = university.average_sat_score
          ? `Published SAT reference: ${university.average_sat_score}`
          : 'SAT average is not published or is not applicable.';
        setText('[data-university-name]', university.name);
        setText('[data-university-location]', location || university.country || 'Location not set');
        setText('[data-university-rank]', university.qs_rank ? `#${university.qs_rank}` : '—');
        setText('[data-university-score]', satReference);
        setText(
          '[data-university-note]',
          university.ranking_year
            ? `${university.ranking_source || 'QS World University Rankings'} ${university.ranking_year}`
            : (university.score_note || 'MakonBook university catalogue')
        );
      }
    }

    function filterUniversities() {
      if (!select || !searchInput) return;
      const query = searchInput.value.trim().toLowerCase();
      let visible = 0;
      Array.from(select.options).forEach((option) => {
        if (!option.value || option.value === 'other') {
          option.hidden = false;
          return;
        }
        const university = universityData.get(option.value);
        const haystack = [
          option.textContent,
          university && university.name,
          university && university.city,
          university && university.country,
        ].filter(Boolean).join(' ').toLowerCase();
        const matches = !query || haystack.includes(query);
        option.hidden = !matches;
        if (matches) visible += 1;
      });
      if (searchResult) {
        searchResult.textContent = query
          ? `${visible} matching universities.`
          : `${universityData.size} universities available.`;
      }
    }

    function openModal(trigger) {
      lastFocused = trigger || document.activeElement;
      root.classList.add('is-open');
      root.setAttribute('aria-hidden', 'false');
      document.body.classList.add('sg-modal-open');
      window.setTimeout(() => {
        const focusTarget = searchInput || select || root.querySelector('input, button, select');
        if (focusTarget) focusTarget.focus({ preventScroll: true });
      }, 50);
    }

    function closeModal() {
      root.classList.remove('is-open');
      root.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('sg-modal-open');
      if (lastFocused && typeof lastFocused.focus === 'function') {
        lastFocused.focus({ preventScroll: true });
      }
    }

    openButtons.forEach((button) => {
      button.addEventListener('click', () => openModal(button));
    });
    closeButtons.forEach((button) => {
      button.addEventListener('click', closeModal);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && root.classList.contains('is-open')) {
        closeModal();
      }
    });

    if (searchInput) {
      searchInput.addEventListener('input', filterUniversities);
      filterUniversities();
    }
    if (select) {
      select.addEventListener('change', updateUniversityUI);
      updateUniversityUI();
    }

    function clearErrors() {
      root.querySelectorAll('[data-field-error]').forEach((element) => {
        element.textContent = '';
      });
      root.querySelectorAll('.sg-field.has-error').forEach((element) => {
        element.classList.remove('has-error');
      });
      const alert = root.querySelector('[data-goal-form-alert]');
      if (alert) {
        alert.hidden = true;
        alert.textContent = '';
      }
    }

    function renderErrors(errors, fallbackMessage) {
      clearErrors();
      let rendered = false;
      Object.entries(errors || {}).forEach(([field, messages]) => {
        const errorElement = root.querySelector(`[data-field-error="${field}"]`);
        if (errorElement) {
          errorElement.textContent = Array.isArray(messages) ? messages.join(' ') : String(messages);
          const fieldWrap = errorElement.closest('.sg-field');
          if (fieldWrap) fieldWrap.classList.add('has-error');
          rendered = true;
        }
      });
      const alert = root.querySelector('[data-goal-form-alert]');
      if (alert) {
        alert.textContent = fallbackMessage || (rendered
          ? 'Please correct the highlighted fields.'
          : 'The goal could not be saved. Please try again.');
        alert.hidden = false;
      }
      const modalBody = root.querySelector('.sg-goal-modal-body');
      if (modalBody) {
        modalBody.scrollTo({ top: 0, behavior: 'smooth' });
      }
      const firstError = root.querySelector('.sg-field.has-error input, .sg-field.has-error select');
      if (firstError) firstError.focus({ preventScroll: false });
    }

    function getCookie(name) {
      const prefix = `${name}=`;
      const cookies = document.cookie ? document.cookie.split(';') : [];
      for (const cookie of cookies) {
        const value = cookie.trim();
        if (value.startsWith(prefix)) {
          return decodeURIComponent(value.slice(prefix.length));
        }
      }
      return '';
    }

    function syncEmbeddedCsrfToken() {
      if (!form) return;
      const tokenInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
      if (!tokenInput) return;
      const cookieToken = getCookie('makonbook_csrftoken_v35') || getCookie('csrftoken');
      if (cookieToken) {
        tokenInput.value = cookieToken;
      }
    }

    // Use the browser's normal form submission. Django's standard POST flow is
    // more reliable behind reverse proxies than a second fetch-based CSRF
    // handshake, and before submit we sync the hidden token with the latest
    // CSRF cookie so restored tabs do not post a stale token.
    if (form) {
      form.addEventListener('submit', () => {
        clearErrors();
        syncEmbeddedCsrfToken();
        const submitButton = form.querySelector('[data-goal-submit]');
        if (submitButton && !submitButton.disabled) {
          submitButton.disabled = true;
          submitButton.setAttribute('aria-busy', 'true');
          submitButton.innerHTML = '<span class="sg-submit-spinner" aria-hidden="true"></span> Saving...';
        }
      });
    }

    if (root.getAttribute('data-auto-open') === '1') {
      openModal(null);
    }
  }

  setupReveal(dashboard);
  setupReveal(settings);
  setupCountdown(dashboard);
  setupMotivation(dashboard);
  setupGoalModal(modal);
})();
