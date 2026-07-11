(function () {
  'use strict';

  document.documentElement.classList.add('js');

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      fn();
    }
  }

  function revealLearningBlocks() {
    var roots = document.querySelectorAll('.mk-learning');
    if (!roots.length) return;

    var selectors = [
      '.section-header', '.top-bar', '.detail-head', '.head', '.access-hero',
      '.practice-card', '.vocab-card', '.adm-card', '.unit-card', '.flashcard',
      '.quiz-card', '.result-card', '.summary-item', '.section-card', '.word-item',
      '.side-card', '.chat-shell', '.section-block', '.test-card', '.checkbox-row', '.section-row',
      '.progress-table-wrap', '.empty-box', '.no-cards'
    ].join(',');

    var items = [];
    roots.forEach(function (root) {
      root.querySelectorAll(selectors).forEach(function (item) {
        if (!item.hasAttribute('data-learning-reveal')) {
          item.setAttribute('data-learning-reveal', '');
        }
        items.push(item);
      });
    });

    if (!items.length) return;

    if (!('IntersectionObserver' in window)) {
      items.forEach(function (item) { item.classList.add('is-visible'); });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

    items.forEach(function (item, index) {
      item.style.transitionDelay = Math.min(index % 8, 6) * 35 + 'ms';
      observer.observe(item);
    });
  }

  function enhanceTabs() {
    document.addEventListener('click', function (event) {
      var button = event.target.closest('.mk-learning .tab-button');
      if (!button) return;
      var tabs = button.closest('.tabs');
      if (!tabs) return;
      tabs.querySelectorAll('.tab-button').forEach(function (tab) {
        tab.classList.toggle('active', tab === button);
        tab.setAttribute('aria-selected', tab === button ? 'true' : 'false');
      });
    });
  }

  function enhanceChat() {
    var chatBody = document.getElementById('chatBody');
    var chatInput = document.getElementById('chatInput');
    var chatForm = document.getElementById('chatForm');
    if (!chatInput || !chatForm) return;

    function resizeInput() {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 220) + 'px';
    }

    chatInput.addEventListener('input', resizeInput);
    resizeInput();

    chatForm.addEventListener('submit', function () {
      var button = chatForm.querySelector('button[type="submit"]');
      if (button) {
        button.classList.add('is-sending');
        button.textContent = 'Sending...';
      }
    });

    if (chatBody) {
      window.setTimeout(function () {
        chatBody.scrollTop = chatBody.scrollHeight;
      }, 80);
    }
  }

  function enhanceAccessCards() {
    document.querySelectorAll('.mk-access-page .test-card, .mk-access-page .checkbox-row, .mk-access-page .section-row, .mk-access-page .radio-row').forEach(function (card) {
      var input = card.querySelector('input[type="checkbox"], input[type="radio"]');
      if (!input) return;

      function sync() {
        card.classList.toggle('is-checked', input.checked);
      }

      input.addEventListener('change', sync);
      sync();
    });
  }

  ready(function () {
    revealLearningBlocks();
    enhanceTabs();
    enhanceChat();
    enhanceAccessCards();
  });
}());
