(() => {
  const toggle = document.querySelector('[data-notice-toggle]');
  const layer = document.querySelector('[data-notice-layer]');
  if (!toggle || !layer) return;

  const closers = layer.querySelectorAll('[data-notice-close]');
  const badge = document.querySelector('[data-notice-badge]');
  let markedRead = false;

  const getCookie = (name) => {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1')}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : '';
  };

  const markRead = async () => {
    if (markedRead) return;
    markedRead = true;
    const url = layer.dataset.readUrl;
    if (!url) return;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-CSRFToken': (layer.querySelector('[data-notice-csrf-form] input[name=csrfmiddlewaretoken]') || {}).value || getCookie('csrftoken'),
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('mark-read failed');
      if (badge) badge.remove();
      layer.querySelectorAll('.makon-notice-item.is-unread').forEach((item) => item.classList.remove('is-unread'));
    } catch (_) {
      markedRead = false;
    }
  };

  const open = () => {
    layer.classList.add('is-open');
    layer.setAttribute('aria-hidden', 'false');
    toggle.setAttribute('aria-expanded', 'true');
    document.body.classList.add('makon-notice-open');
    markRead();
    const closeButton = layer.querySelector('.makon-notice-close');
    if (closeButton) closeButton.focus({ preventScroll: true });
  };

  const close = () => {
    layer.classList.remove('is-open');
    layer.setAttribute('aria-hidden', 'true');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('makon-notice-open');
  };

  toggle.addEventListener('click', () => {
    if (layer.classList.contains('is-open')) close();
    else open();
  });
  closers.forEach((item) => item.addEventListener('click', close));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && layer.classList.contains('is-open')) close();
  });
})();
