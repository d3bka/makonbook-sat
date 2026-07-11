
(() => {
  const items = Array.from(document.querySelectorAll('details.faq-item'));
  if (!items.length) return;

  const DURATION = 320;

  const setExpanded = (item, expanded) => {
    const summary = item.querySelector('summary');
    if (summary) summary.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  };

  const getPanel = (item) => item.querySelector('p');

  const syncOpenItem = (item) => {
    const panel = getPanel(item);
    item.classList.add('faq-enhanced');
    item.classList.toggle('is-open', item.open);
    setExpanded(item, item.open);

    if (!panel) return;
    if (item.open) {
      panel.style.maxHeight = `${panel.scrollHeight}px`;
    } else {
      panel.style.maxHeight = '0px';
    }
  };

  const closeItem = (item) => {
    if (!item.open || item.dataset.faqAnimating === 'closing') return;

    const panel = getPanel(item);
    item.dataset.faqAnimating = 'closing';
    item.classList.add('is-closing');
    item.classList.remove('is-open');
    setExpanded(item, false);

    if (panel) {
      panel.style.maxHeight = `${panel.scrollHeight}px`;
      panel.offsetHeight; // force reflow
      requestAnimationFrame(() => {
        panel.style.maxHeight = '0px';
      });
    }

    window.setTimeout(() => {
      item.removeAttribute('open');
      item.classList.remove('is-closing');
      delete item.dataset.faqAnimating;
    }, DURATION);
  };

  const openItem = (item) => {
    if (item.open && item.classList.contains('is-open')) return;

    const panel = getPanel(item);
    item.dataset.faqAnimating = 'opening';

    items.forEach((other) => {
      if (other !== item) closeItem(other);
    });

    item.setAttribute('open', '');
    item.classList.add('is-open');
    setExpanded(item, true);

    if (panel) {
      panel.style.maxHeight = '0px';
      panel.offsetHeight; // force reflow
      requestAnimationFrame(() => {
        panel.style.maxHeight = `${panel.scrollHeight}px`;
      });
    }

    window.setTimeout(() => {
      delete item.dataset.faqAnimating;
      if (panel && item.open) {
        panel.style.maxHeight = `${panel.scrollHeight}px`;
      }
    }, DURATION);
  };

  items.forEach((item) => {
    const summary = item.querySelector('summary');
    syncOpenItem(item);

    if (!summary) return;

    summary.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();

      if (item.open && item.classList.contains('is-open')) {
        closeItem(item);
      } else {
        openItem(item);
      }
    }, true);

    summary.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      summary.click();
    });
  });

  window.addEventListener('resize', () => {
    items.forEach((item) => {
      if (!item.open) return;
      const panel = getPanel(item);
      if (panel) panel.style.maxHeight = `${panel.scrollHeight}px`;
    });
  }, { passive: true });
})();
