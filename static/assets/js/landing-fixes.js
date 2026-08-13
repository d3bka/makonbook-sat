/*
  SAT Makon landing mobile-menu stability patch (V3)
  Load AFTER landing.js.

  Why this owns the hamburger click:
  the legacy landing.js may already have a toggle listener. A capture-phase
  listener with stopImmediatePropagation prevents two handlers from fighting
  each other and leaving the backdrop/menu in different states.
*/
(() => {
  'use strict';

  const nav = document.querySelector('[data-nav]');
  const toggle = document.querySelector('[data-nav-toggle]');
  const body = document.body;

  if (!nav || !toggle || !body) return;

  const mobileQuery = window.matchMedia('(max-width: 1024px)');

  const isOpen = () => nav.classList.contains('is-open');

  const applyState = (open, { focusToggle = false } = {}) => {
    nav.classList.toggle('is-open', open);
    toggle.classList.toggle('is-active', open);
    body.classList.toggle('landing-menu-open', open);

    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');

    if (!open && focusToggle) {
      toggle.focus({ preventScroll: true });
    }
  };

  const closeMenu = (options) => applyState(false, options);

  /* Take ownership of the hamburger on mobile. Capture phase is deliberate:\n     it prevents a second legacy click handler from instantly toggling it back. */
  toggle.addEventListener('click', (event) => {
    if (!mobileQuery.matches) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    applyState(!isOpen());
  }, true);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isOpen()) {
      closeMenu({ focusToggle: true });
    }
  });

  /* Click on the plain backdrop / anywhere outside the menu closes it. */
  document.addEventListener('click', (event) => {
    if (!isOpen()) return;
    const target = event.target;
    if (!(target instanceof Element)) return;

    if (!nav.contains(target) && !toggle.contains(target)) {
      closeMenu();
    }
  });

  /* Navigation links should never leave an invisible open state behind. */
  nav.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest('a')) closeMenu();
  });

  const resetMenu = () => applyState(false);

  /* BFCache / history restore must always come back clean. */
  window.addEventListener('pageshow', resetMenu);
  window.addEventListener('pagehide', resetMenu);

  /* Orientation changes and desktop transitions can invalidate menu geometry. */
  const handleViewportChange = () => {
    if (isOpen()) closeMenu();
  };

  if (typeof mobileQuery.addEventListener === 'function') {
    mobileQuery.addEventListener('change', handleViewportChange);
  } else if (typeof mobileQuery.addListener === 'function') {
    mobileQuery.addListener(handleViewportChange);
  }

  window.addEventListener('orientationchange', handleViewportChange);

  /* Clean up any stale state from the previous patch immediately. */
  resetMenu();
})();
