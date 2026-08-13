/*
  SAT Makon landing mobile-menu stability patch (V4 / v33.6.1)

  The legacy landing.js also owns a hamburger click handler. This patch takes
  ownership in capture phase and, on mobile, portals the menu to <body> while
  it is open. That removes the menu from the sticky header's stacking/
  containing context, which is the source of the "backdrop visible, menu
  missing" bug after scrolling deep into the landing page.
*/
(() => {
  'use strict';

  const nav = document.querySelector('[data-nav]');
  const toggle = document.querySelector('[data-nav-toggle]');
  const header = document.querySelector('[data-header]');
  const body = document.body;

  if (!nav || !toggle || !body) return;

  const mobileQuery = window.matchMedia('(max-width: 1024px)');
  const originalParent = nav.parentNode;
  const anchor = document.createComment('landing-mobile-nav-anchor');
  originalParent.insertBefore(anchor, nav);

  const isOpen = () => nav.classList.contains('is-open');

  const updatePortalPosition = () => {
    if (!nav.classList.contains('landing-mobile-nav-portal')) return;

    let top = 72;
    if (header) {
      const rect = header.getBoundingClientRect();
      if (Number.isFinite(rect.bottom)) {
        top = Math.max(8, Math.min(window.innerHeight - 80, rect.bottom + 8));
      }
    } else {
      const rect = toggle.getBoundingClientRect();
      top = Math.max(8, rect.bottom + 8);
    }

    nav.style.setProperty('--landing-mobile-nav-top', `${Math.round(top)}px`);
  };

  const portalMenu = () => {
    if (!mobileQuery.matches) return;

    if (nav.parentNode !== body) {
      body.appendChild(nav);
    }

    nav.classList.add('landing-mobile-nav-portal');
    updatePortalPosition();
  };

  const restoreMenu = () => {
    nav.classList.remove('landing-mobile-nav-portal');
    nav.style.removeProperty('--landing-mobile-nav-top');

    if (anchor.parentNode && nav.parentNode !== originalParent) {
      anchor.parentNode.insertBefore(nav, anchor.nextSibling);
    }
  };

  const applyState = (open, { focusToggle = false } = {}) => {
    const shouldOpen = Boolean(open && mobileQuery.matches);

    if (shouldOpen) {
      portalMenu();
    }

    nav.classList.toggle('is-open', shouldOpen);
    toggle.classList.toggle('is-active', shouldOpen);
    body.classList.toggle('landing-menu-open', shouldOpen);

    toggle.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
    toggle.setAttribute('aria-label', shouldOpen ? 'Close menu' : 'Open menu');

    if (!shouldOpen) {
      restoreMenu();
      if (focusToggle) {
        try {
          toggle.focus({ preventScroll: true });
        } catch (_) {
          toggle.focus();
        }
      }
    }
  };

  const closeMenu = (options) => applyState(false, options);

  /* Capture phase prevents landing.js from immediately toggling the same
     classes a second time. */
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

  /* The backdrop is a pseudo-element, so its click target is the underlying
     landing shell. Any click outside the portaled nav/toggle closes the menu. */
  document.addEventListener('click', (event) => {
    if (!isOpen()) return;

    const target = event.target;
    if (!(target instanceof Element)) return;

    if (!nav.contains(target) && !toggle.contains(target)) {
      closeMenu();
    }
  });

  nav.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest('a')) closeMenu();
  });

  const resetMenu = () => closeMenu();

  window.addEventListener('pageshow', resetMenu);
  window.addEventListener('pagehide', resetMenu);

  const handleViewportChange = () => {
    if (!mobileQuery.matches) {
      closeMenu();
      return;
    }
    if (isOpen()) updatePortalPosition();
  };

  if (typeof mobileQuery.addEventListener === 'function') {
    mobileQuery.addEventListener('change', handleViewportChange);
  } else if (typeof mobileQuery.addListener === 'function') {
    mobileQuery.addListener(handleViewportChange);
  }

  window.addEventListener('orientationchange', () => {
    if (isOpen()) {
      window.setTimeout(updatePortalPosition, 80);
    }
  });

  window.addEventListener('resize', () => {
    if (isOpen()) updatePortalPosition();
  }, { passive: true });

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      if (isOpen()) updatePortalPosition();
    }, { passive: true });
  }

  /* Never inherit stale menu state from BFCache or an older patch. */
  applyState(false);
})();
