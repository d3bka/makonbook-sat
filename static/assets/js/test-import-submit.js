(() => {
  const form = document.querySelector('[data-import-upload-form]');
  const overlay = document.querySelector('[data-import-upload-overlay]');
  if (!form || !overlay) return;

  const button = form.querySelector('[data-import-submit-button]');
  const message = overlay.querySelector('[data-import-upload-message]');
  const phases = [
    'Uploading the structured PDFs securely…',
    'Locking duplicate submissions…',
    'Reading the structured PDF markers…',
    'Extracting tables, graphs, and diagrams…',
    'Validating question blocks and answer keys…',
    'Assigning support-teacher reviewers…',
  ];
  let locked = false;
  let phaseTimer = null;

  const reset = () => {
    locked = false;
    form.removeAttribute('aria-busy');
    overlay.classList.remove('is-active');
    overlay.setAttribute('aria-hidden', 'true');
    document.documentElement.classList.remove('tic-upload-busy');
    if (button) button.disabled = false;
    if (phaseTimer) window.clearInterval(phaseTimer);
    phaseTimer = null;
  };

  form.addEventListener('submit', (event) => {
    if (locked) {
      event.preventDefault();
      return;
    }
    if (!form.checkValidity()) return;

    event.preventDefault();
    locked = true;
    form.setAttribute('aria-busy', 'true');
    if (button) {
      button.disabled = true;
      const label = button.querySelector('span');
      if (label) label.textContent = 'Upload in progress…';
    }

    overlay.classList.add('is-active');
    overlay.setAttribute('aria-hidden', 'false');
    document.documentElement.classList.add('tic-upload-busy');

    let phase = 0;
    if (message) message.textContent = phases[phase];
    phaseTimer = window.setInterval(() => {
      phase = Math.min(phases.length - 1, phase + 1);
      if (message) message.textContent = phases[phase];
      if (phase === phases.length - 1 && phaseTimer) {
        window.clearInterval(phaseTimer);
        phaseTimer = null;
      }
    }, 1350);

    // Give the browser one frame to paint the slide-down sheet before the
    // potentially large multipart upload starts. Native validation already ran.
    window.setTimeout(() => {
      HTMLFormElement.prototype.submit.call(form);
    }, 120);
  });

  window.addEventListener('pageshow', (event) => {
    if (event.persisted) reset();
  });
})();
