(function () {
  document.documentElement.classList.add('js-test-window');
  document.addEventListener('DOMContentLoaded', function () {
    if (!document.body.classList.contains('mk-test-window')) {
      return;
    }
    var targets = document.querySelectorAll('header, main, footer, .ready-shell, .question-container, .answers-container, .description, .single-desc, .module-card, .attempt-card, .reference-card, [data-test-reveal]');
    targets.forEach(function (el, index) {
      el.setAttribute('data-test-reveal', '');
      el.style.transitionDelay = Math.min(index * 35, 240) + 'ms';
    });

    var readyShell = document.querySelector('.ready-shell');
    if (readyShell) {
      readyShell.classList.add('is-visible');
    }
    if (!('IntersectionObserver' in window)) {
      targets.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    targets.forEach(function (el) { observer.observe(el); });
  });
})();

(function () {
  function markCurrentQuestionInModal() {
    var current = document.getElementById('currentQuestionIndex');
    if (!current) return;
    var value = parseInt(current.textContent || '1', 10);
    if (!Number.isFinite(value)) return;
    document.querySelectorAll('.rect-question').forEach(function (item, index) {
      var textNumber = parseInt(item.textContent || '', 10);
      var isCurrent = textNumber === value || index + 1 === value;
      item.classList.toggle('is-current', isCurrent);
      if (isCurrent) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
  }

  function decorateTimer() {
    var timer = document.getElementById('timer');
    if (!timer) return;
    var parts = (timer.textContent || '').trim().split(':').map(function (part) { return parseInt(part, 10); });
    if (parts.some(function (part) { return !Number.isFinite(part); })) return;
    var seconds = parts.length === 2 ? parts[0] * 60 + parts[1] : parts[0];
    timer.classList.toggle('is-warning', seconds > 0 && seconds <= 300);
  }

  function initTestTakingPolish() {
    if (!document.body.classList.contains('mk-test-window') || !document.body.classList.contains('scroll-hide')) return;
    document.body.classList.add('mk-test-taking-ui');
    markCurrentQuestionInModal();
    decorateTimer();

    var current = document.getElementById('currentQuestionIndex');
    if (current && 'MutationObserver' in window) {
      new MutationObserver(markCurrentQuestionInModal).observe(current, { childList: true, characterData: true, subtree: true });
    }

    var timer = document.getElementById('timer');
    if (timer && 'MutationObserver' in window) {
      new MutationObserver(decorateTimer).observe(timer, { childList: true, characterData: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTestTakingPolish);
  } else {
    initTestTakingPolish();
  }
})();

(function () {
  function numberFromText(selector, fallback) {
    var node = document.querySelector(selector);
    if (!node) return fallback;
    var value = parseInt((node.textContent || '').trim(), 10);
    return Number.isFinite(value) ? value : fallback;
  }

  function setButtonVisible(button, visible) {
    if (!button) return;
    button.style.display = visible ? 'inline-flex' : 'none';
    button.setAttribute('aria-hidden', visible ? 'false' : 'true');
    button.tabIndex = visible ? 0 : -1;
  }

  function repairFooterActions() {
    if (!document.body || !document.body.classList.contains('mk-test-window')) return;

    var footer = document.querySelector('footer');
    var footerRight = document.querySelector('.footer-right');
    if (!footer || !footerRight) return;

    footer.classList.add('mk-footer-repaired');
    footerRight.classList.add('mk-footer-actions-ready');

    var backButton = document.getElementById('backButton');
    var nextButton = document.getElementById('nextButton');
    var finishButton = document.getElementById('finishButton');

    if (!backButton && typeof window.prevQuestion === 'function') {
      backButton = document.createElement('button');
      backButton.id = 'backButton';
      backButton.type = 'button';
      backButton.className = 'nav-button';
      backButton.textContent = 'Back';
      backButton.addEventListener('click', window.prevQuestion);
      footerRight.appendChild(backButton);
    }

    if (!nextButton && typeof window.nextQuestion === 'function') {
      nextButton = document.createElement('button');
      nextButton.id = 'nextButton';
      nextButton.type = 'button';
      nextButton.className = 'nav-button';
      nextButton.textContent = 'Next';
      nextButton.addEventListener('click', window.nextQuestion);
      footerRight.appendChild(nextButton);
    }

    if (!finishButton && typeof window.finishTest === 'function') {
      finishButton = document.createElement('button');
      finishButton.id = 'finishButton';
      finishButton.type = 'button';
      finishButton.className = 'nav-button';
      finishButton.textContent = 'Finish Test';
      finishButton.addEventListener('click', window.finishTest);
      footerRight.appendChild(finishButton);
    }

    var current = numberFromText('#currentQuestionIndex', 1);
    var total = Math.max(numberFromText('#totalQuestions', 1), 1);

    setButtonVisible(backButton, current > 1);
    setButtonVisible(nextButton, current < total);
    setButtonVisible(finishButton, current >= total);

    var hasVisibleAction = [backButton, nextButton, finishButton].some(function (button) {
      return button && button.style.display !== 'none';
    });

    if (!hasVisibleAction && nextButton) {
      setButtonVisible(nextButton, true);
    }
  }

  function initFooterRepair() {
    if (!document.body || !document.body.classList.contains('mk-test-window')) return;
    repairFooterActions();

    var current = document.getElementById('currentQuestionIndex');
    var total = document.getElementById('totalQuestions');
    var footerRight = document.querySelector('.footer-right');

    if ('MutationObserver' in window) {
      var observer = new MutationObserver(function () {
        window.requestAnimationFrame(repairFooterActions);
      });
      [current, total, footerRight].forEach(function (node) {
        if (node) observer.observe(node, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
      });
    }

    window.addEventListener('resize', repairFooterActions, { passive: true });
    window.setTimeout(repairFooterActions, 0);
    window.setTimeout(repairFooterActions, 250);
    window.setTimeout(repairFooterActions, 800);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFooterRepair);
  } else {
    initFooterRepair();
  }
})();

(function () {
  function pulse(button, className) {
    if (!button) return;
    button.classList.remove(className);
    // Force reflow so the animation can replay on repeated clicks.
    void button.offsetWidth;
    button.classList.add(className);
    window.setTimeout(function () { button.classList.remove(className); }, 460);
  }

  function syncActionButtonState() {
    var crossButton = document.querySelector('.crossing-options');
    if (crossButton) {
      var crossActive = crossButton.classList.contains('active-options') || document.body.classList.contains('is-eliminate-mode');
      crossButton.setAttribute('role', 'button');
      crossButton.setAttribute('tabindex', '0');
      crossButton.setAttribute('aria-label', crossActive ? 'Cross-answer mode on' : 'Cross out answers');
      crossButton.setAttribute('aria-pressed', crossActive ? 'true' : 'false');
      crossButton.setAttribute('title', crossActive ? 'Cross-answer mode on' : 'Cross out answers');
    }

    var penButton = document.getElementById('pen-button');
    if (penButton) {
      var penActive = penButton.classList.contains('active') || document.body.classList.contains('pen-mode');
      penButton.setAttribute('aria-label', penActive ? 'Highlighter on' : 'Toggle highlighter');
      penButton.setAttribute('aria-pressed', penActive ? 'true' : 'false');
      penButton.setAttribute('title', penActive ? 'Highlighter on' : 'Toggle highlighter');
    }

    var clearButton = document.getElementById('clear-button');
    if (clearButton) {
      clearButton.setAttribute('aria-label', 'Clear highlights');
      clearButton.setAttribute('title', 'Clear highlights');
    }
  }

  function initActionButtonsPolish() {
    if (!document.body || !document.body.classList.contains('mk-test-window')) return;
    syncActionButtonState();

    var clearButton = document.getElementById('clear-button');
    if (clearButton && !clearButton.dataset.mkClearPolished) {
      clearButton.dataset.mkClearPolished = '1';
      clearButton.addEventListener('click', function () {
        pulse(clearButton, 'is-clearing');
      });
    }

    var crossButton = document.querySelector('.crossing-options');
    if (crossButton && !crossButton.dataset.mkCrossKeyboard) {
      crossButton.dataset.mkCrossKeyboard = '1';
      crossButton.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          crossButton.click();
        }
      });
    }

    if ('MutationObserver' in window) {
      var observer = new MutationObserver(syncActionButtonState);
      observer.observe(document.body, { attributes: true, attributeFilter: ['class'], subtree: false });
      ['pen-button', 'clear-button'].forEach(function (id) {
        var node = document.getElementById(id);
        if (node) observer.observe(node, { attributes: true, attributeFilter: ['class', 'style'] });
      });
      if (crossButton) observer.observe(crossButton, { attributes: true, attributeFilter: ['class', 'style'] });
    }

    window.setTimeout(syncActionButtonState, 0);
    window.setTimeout(syncActionButtonState, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initActionButtonsPolish);
  } else {
    initActionButtonsPolish();
  }
})();

(function () {
  function syncMarkReviewButton() {
    if (!document.body || !document.body.classList.contains('mk-test-window')) return;
    var markButton = document.querySelector('.bookmark');
    if (!markButton) return;

    var active = markButton.classList.contains('filledbook');
    markButton.classList.add('mk-mark-review-button');
    markButton.setAttribute('role', 'button');
    markButton.setAttribute('tabindex', '0');
    markButton.setAttribute('aria-pressed', active ? 'true' : 'false');
    markButton.setAttribute('title', active ? 'Remove mark for review' : 'Mark this question for review');
  }

  function initMarkReviewPolish() {
    if (!document.body || !document.body.classList.contains('mk-test-window')) return;
    syncMarkReviewButton();

    document.addEventListener('keydown', function (event) {
      var target = event.target;
      if (!target || !target.classList || !target.classList.contains('bookmark')) return;
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        target.click();
      }
    });

    if ('MutationObserver' in window) {
      var rootObserver = new MutationObserver(function () {
        syncMarkReviewButton();
      });
      rootObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    }

    window.setTimeout(syncMarkReviewButton, 0);
    window.setTimeout(syncMarkReviewButton, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMarkReviewPolish);
  } else {
    initMarkReviewPolish();
  }
})();

(function () {
  function getModal() {
    return document.getElementById('questionModal');
  }

  function setModalOpen(open) {
    var modal = getModal();
    if (!modal || !document.body || !document.body.classList.contains('mk-test-window')) return;

    modal.classList.toggle('is-open', !!open);
    modal.classList.remove('is-closing');
    document.body.classList.toggle('question-modal-open', !!open);
    modal.setAttribute('aria-hidden', open ? 'false' : 'true');
    modal.style.display = open ? 'flex' : 'none';
  }

  window.openQuestionModal = function () {
    setModalOpen(true);
  };

  window.closeQuestionModal = function () {
    setModalOpen(false);
  };

  window.toggleQuestionModal = function (force) {
    var modal = getModal();
    if (!modal) return;
    if (typeof force === 'boolean') {
      setModalOpen(force);
      return;
    }
    var isOpen = modal.classList.contains('is-open') || modal.style.display === 'block' || modal.style.display === 'flex';
    setModalOpen(!isOpen);
  };

  function initModalLockFix() {
    if (!document.body || !document.body.classList.contains('mk-test-window')) return;
    var modal = getModal();
    if (!modal) return;

    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-hidden', 'true');

    // Critical: old CSS made the modal visible by default. Start closed every time.
    setModalOpen(false);

    modal.addEventListener('click', function (event) {
      if (event.target === modal) {
        event.preventDefault();
        setModalOpen(false);
      }
    });

    var close = modal.querySelector('.close-button');
    if (close && !close.dataset.mkModalCloseBound) {
      close.dataset.mkModalCloseBound = '1';
      close.setAttribute('role', 'button');
      close.setAttribute('tabindex', '0');
      close.setAttribute('aria-label', 'Close question navigator');
      close.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        setModalOpen(false);
      });
      close.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          setModalOpen(false);
        }
      });
    }

    modal.querySelectorAll('.rect-question').forEach(function (item) {
      if (item.dataset.mkModalQuestionBound) return;
      item.dataset.mkModalQuestionBound = '1';
      item.addEventListener('click', function () {
        window.setTimeout(function () { setModalOpen(false); }, 0);
      });
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        setModalOpen(false);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initModalLockFix, { once: true });
  } else {
    initModalLockFix();
  }
})();
