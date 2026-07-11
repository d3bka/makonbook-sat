(function () {
  document.documentElement.classList.add('js-final-pages');

  function markRevealTargets() {
    var selectors = [
      '.form-wrap', '.join-wrap', '.status-card', '.denied-card', '.success-container',
      '.limit-container', '.review-container', '.attempt-card', '.retake-info', '.review-info',
      '.time-details', '.restart-btn-container', '.blog table', '.blog .table', '.blog .card'
    ];
    document.querySelectorAll(selectors.join(',')).forEach(function (el, index) {
      if (!el.hasAttribute('data-final-reveal')) el.setAttribute('data-final-reveal', '');
      el.style.transitionDelay = Math.min(index * 35, 280) + 'ms';
    });
  }

  function reveal() {
    var targets = document.querySelectorAll('[data-final-reveal]');
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
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    targets.forEach(function (el) { observer.observe(el); });
  }

  function improveJoinCode() {
    document.querySelectorAll('input[name="join_code"], .join-input').forEach(function (input) {
      input.setAttribute('autocomplete', 'one-time-code');
      input.addEventListener('input', function () {
        input.value = input.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, input.maxLength || 6);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    markRevealTargets();
    improveJoinCode();
    reveal();
  });
})();
