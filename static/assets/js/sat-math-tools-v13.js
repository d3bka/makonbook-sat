(function () {
  'use strict';

  const configNode = document.getElementById('sat-test-config');
  let config = {};
  try { config = JSON.parse(configNode?.textContent || '{}'); } catch (error) { config = {}; }

  const stateKey = [
    'sat-desmos-v21',
    config.storageScope || 'unknown',
    config.attemptId || 'attempt',
    config.classroomId || 'regular',
    config.sectionName || 'math',
    config.moduleName || 'module',
  ].join(':');

  let calculator = null;
  let blankState = null;
  let currentQuestionIndex = 0;
  let loadingPromise = null;
  let states = {};
  let closeTimer = null;
  let resizeObserver = null;

  try { states = JSON.parse(localStorage.getItem(stateKey) || '{}') || {}; } catch (error) { states = {}; }

  function persist() {
    try { localStorage.setItem(stateKey, JSON.stringify(states)); } catch (error) {}
  }

  function popupElement() { return document.getElementById('calculator-popup'); }
  function openButton() { return document.getElementById('open-calculator'); }

  function setPanelState(state) {
    const loading = document.getElementById('calculator-loading');
    const calculatorNode = document.getElementById('calculator');
    const fallback = document.getElementById('calculator-fallback');
    if (loading) loading.hidden = state !== 'loading';
    if (calculatorNode) calculatorNode.hidden = state !== 'ready';
    if (fallback) fallback.hidden = state !== 'error';
  }

  function removeFailedScript() {
    document.querySelectorAll('script[data-sat-desmos-loader]').forEach((script) => script.remove());
  }

  function loadDesmosScript(force = false) {
    if (window.Desmos?.GraphingCalculator) return Promise.resolve(true);
    if (force) {
      loadingPromise = null;
      removeFailedScript();
    }
    if (loadingPromise) return loadingPromise;

    loadingPromise = new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = 'https://www.desmos.com/api/v1.10/calculator.js?apiKey=dcb31709b452b1cf9dc26972add0fda6';
      script.async = true;
      script.dataset.satDesmosLoader = '1';
      let settled = false;
      const finish = (result) => {
        if (settled) return;
        settled = true;
        resolve(result);
      };
      script.onload = () => finish(Boolean(window.Desmos?.GraphingCalculator));
      script.onerror = () => finish(false);
      document.head.appendChild(script);
      window.setTimeout(() => finish(Boolean(window.Desmos?.GraphingCalculator)), 15000);
    });
    return loadingPromise;
  }

  function resizeCalculator(delay = 0) {
    window.setTimeout(() => {
      try { calculator?.resize(); } catch (error) {}
    }, delay);
  }

  async function ensureCalculator(force = false) {
    if (calculator) {
      setPanelState('ready');
      resizeCalculator(20);
      return true;
    }

    setPanelState('loading');
    const loaded = await loadDesmosScript(force);
    const element = document.getElementById('calculator');
    if (!loaded || !element) {
      setPanelState('error');
      return false;
    }

    try {
      calculator = window.Desmos.GraphingCalculator(element, {
        expressions: true,
        keypad: true,
        settingsMenu: true,
        zoomButtons: true,
        expressionsTopbar: true,
        pointsOfInterest: true,
        trace: true,
      });
      blankState = calculator.getState();
      loadState(currentQuestionIndex);
      setPanelState('ready');
      resizeCalculator(20);
      resizeCalculator(180);

      const popup = popupElement();
      if (popup && window.ResizeObserver) {
        resizeObserver?.disconnect();
        resizeObserver = new ResizeObserver(() => resizeCalculator(0));
        resizeObserver.observe(popup);
      }
      return true;
    } catch (error) {
      console.error('Desmos initialization failed:', error);
      calculator = null;
      setPanelState('error');
      return false;
    }
  }

  function saveState(index = currentQuestionIndex) {
    if (!calculator) return;
    try {
      states[String(index)] = calculator.getState();
      persist();
    } catch (error) {
      console.warn('Desmos state could not be saved:', error);
    }
  }

  function loadState(index = currentQuestionIndex) {
    currentQuestionIndex = Number(index) || 0;
    if (!calculator) return;
    try {
      calculator.setState(states[String(currentQuestionIndex)] || blankState || { version: 10, expressions: { list: [] } });
      resizeCalculator(30);
    } catch (error) {
      console.warn('Desmos state could not be restored:', error);
    }
  }

  function constrainPopup() {
    const popup = popupElement();
    if (!popup || popup.classList.contains('is-maximized') || window.innerWidth <= 900) return;
    const rect = popup.getBoundingClientRect();
    const left = Math.min(Math.max(rect.left, 8), Math.max(window.innerWidth - rect.width - 8, 8));
    const top = Math.min(Math.max(rect.top, 8), Math.max(window.innerHeight - rect.height - 8, 8));
    popup.style.left = `${left}px`;
    popup.style.top = `${top}px`;
    popup.style.right = 'auto';
    popup.style.bottom = 'auto';
  }

  async function openCalculator() {
    const popup = popupElement();
    if (!popup) return;
    window.clearTimeout(closeTimer);
    popup.style.display = 'flex';
    popup.hidden = false;
    popup.setAttribute('aria-hidden', 'false');
    openButton()?.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => popup.classList.add('is-open'));
    constrainPopup();
    await ensureCalculator(false);
    resizeCalculator(60);
    resizeCalculator(260);
  }

  function closeCalculator() {
    saveState();
    const popup = popupElement();
    if (!popup) return;
    popup.classList.remove('is-open');
    popup.setAttribute('aria-hidden', 'true');
    openButton()?.setAttribute('aria-expanded', 'false');
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(() => {
      if (!popup.classList.contains('is-open')) popup.style.display = 'none';
    }, 180);
  }

  function toggleMaximize() {
    const popup = popupElement();
    const button = document.getElementById('desmos-maximize');
    if (!popup) return;
    const maximizing = !popup.classList.contains('is-maximized');
    if (maximizing) {
      popup.dataset.restoreStyle = popup.getAttribute('style') || '';
      popup.classList.add('is-maximized');
    } else {
      popup.classList.remove('is-maximized');
      const currentDisplay = popup.style.display;
      popup.setAttribute('style', popup.dataset.restoreStyle || '');
      popup.style.display = currentDisplay || 'flex';
    }
    if (button) {
      button.setAttribute('aria-label', maximizing ? 'Restore calculator size' : 'Maximize calculator');
      button.title = maximizing ? 'Restore size' : 'Maximize';
      const icon = button.querySelector('i');
      if (icon) icon.className = maximizing ? 'fa fa-compress' : 'fa fa-expand';
    }
    resizeCalculator(40);
    resizeCalculator(220);
  }

  function openReference() {
    document.getElementById('reference-overlay')?.classList.add('active');
  }

  function closeReference() {
    document.getElementById('reference-overlay')?.classList.remove('active');
  }

  function isToolFocused() {
    const popup = popupElement();
    const reference = document.getElementById('reference-overlay');
    if (reference?.classList.contains('active')) return true;
    if (!popup || !popup.classList.contains('is-open')) return false;
    const active = document.activeElement;
    return Boolean(active && (popup.contains(active) || active.closest?.('[class*="dcg-"]')));
  }

  function makeDraggable(popup, handle) {
    if (!popup || !handle) return;
    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;

    handle.addEventListener('pointerdown', (event) => {
      if (event.target.closest('button') || popup.classList.contains('is-maximized') || window.innerWidth <= 900) return;
      const rect = popup.getBoundingClientRect();
      dragging = true;
      offsetX = event.clientX - rect.left;
      offsetY = event.clientY - rect.top;
      handle.setPointerCapture?.(event.pointerId);
      popup.classList.add('is-dragging');
      event.preventDefault();
    });

    handle.addEventListener('pointermove', (event) => {
      if (!dragging) return;
      const maxLeft = Math.max(window.innerWidth - popup.offsetWidth, 0);
      const maxTop = Math.max(window.innerHeight - popup.offsetHeight, 0);
      popup.style.left = `${Math.min(Math.max(event.clientX - offsetX, 0), maxLeft)}px`;
      popup.style.top = `${Math.min(Math.max(event.clientY - offsetY, 0), maxTop)}px`;
      popup.style.right = 'auto';
      popup.style.bottom = 'auto';
    });

    const stop = () => {
      dragging = false;
      popup.classList.remove('is-dragging');
    };
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const popup = popupElement();
    openButton()?.setAttribute('aria-expanded', 'false');
    document.getElementById('open-calculator')?.addEventListener('click', openCalculator);
    document.getElementById('open-reference')?.addEventListener('click', openReference);
    document.getElementById('desmos-maximize')?.addEventListener('click', toggleMaximize);
    document.getElementById('retry-calculator')?.addEventListener('click', () => ensureCalculator(true));
    document.getElementById('reference-overlay')?.addEventListener('click', (event) => {
      if (event.target.id === 'reference-overlay') closeReference();
    });
    makeDraggable(popup, document.getElementById('calculator-header'));
    window.addEventListener('resize', () => {
      constrainPopup();
      resizeCalculator(50);
    });
  });

  window.openCalculator = openCalculator;
  window.closeCalculator = closeCalculator;
  window.openReference = openReference;
  window.closeReference = closeReference;
  window.SATMathTools = {
    saveState,
    loadState,
    isToolFocused,
    closeAll() { closeReference(); closeCalculator(); },
    clear() {
      states = {};
      persist();
    },
  };
})();
