(() => {
  'use strict';

  const body = document.body;
  if (!body || (!body.classList.contains('mk-test-window') && !body.classList.contains('review-page'))) return;

  if (body.classList.contains('mk-test-window')) {
    const root = document.documentElement;
    let raf = 0;
    let initialViewportHeight = Math.max(window.innerHeight || 0, window.visualViewport?.height || 0);

    const update = () => {
      raf = 0;
      const vv = window.visualViewport;
      const height = Math.max(240, Math.round(vv?.height || window.innerHeight || root.clientHeight || 0));
      root.style.setProperty('--sat-js-vvh', `${height}px`);
      body.style.setProperty('--sat-vvh', `${height}px`);

      initialViewportHeight = Math.max(initialViewportHeight, window.innerHeight || 0);
      const keyboardLikelyOpen = !!vv && vv.height < Math.max(360, initialViewportHeight * 0.72) && document.activeElement && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      body.classList.toggle('sat-keyboard-open', keyboardLikelyOpen);

      const header = body.querySelector(':scope > .container > header');
      const footer = body.querySelector(':scope > .container > footer');
      if (header) {
        const headerHeight = Math.max(header.offsetHeight || 0, Math.ceil(header.getBoundingClientRect().height));
        body.style.setProperty('--sat-measured-header', `${headerHeight}px`);
      }
      if (footer && !keyboardLikelyOpen) {
        const footerHeight = Math.max(footer.offsetHeight || 0, Math.ceil(footer.getBoundingClientRect().height));
        body.style.setProperty('--sat-measured-footer', `${footerHeight}px`);
      }
    };

    const requestUpdate = () => {
      if (raf) return;
      raf = requestAnimationFrame(update);
    };

    requestUpdate();
    window.addEventListener('resize', requestUpdate, { passive: true });
    window.addEventListener('orientationchange', requestUpdate, { passive: true });
    window.visualViewport?.addEventListener('resize', requestUpdate, { passive: true });
    window.visualViewport?.addEventListener('scroll', requestUpdate, { passive: true });
    document.addEventListener('focusin', requestUpdate, true);
    document.addEventListener('focusout', () => setTimeout(requestUpdate, 60), true);

    const header = body.querySelector(':scope > .container > header');
    const footer = body.querySelector(':scope > .container > footer');
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(requestUpdate);
      if (header) observer.observe(header);
      if (footer) observer.observe(footer);
    }

    // Legacy exam CSS contains short entrance animations. Re-measure after they settle
    // so the content never overlaps the fixed navigation by a pixel or two.
    setTimeout(requestUpdate, 120);
    setTimeout(requestUpdate, 700);
  }
})();
