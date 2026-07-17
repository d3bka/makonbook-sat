(function () {
  "use strict";

  document.documentElement.classList.add("js-classroom");

  function revealClassroomItems() {
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-classroom-reveal]"));
    if (!items.length) return;

    if (!("IntersectionObserver" in window)) {
      items.forEach(function (item) { item.classList.add("is-visible"); });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });

    items.forEach(function (item, index) {
      item.style.transitionDelay = Math.min(index * 55, 260) + "ms";
      observer.observe(item);
    });
  }

  function bindPanels() {
    document.addEventListener("click", function (event) {
      var trigger = event.target.closest("[data-classroom-toggle]");
      if (!trigger) return;

      var targetId = trigger.getAttribute("data-classroom-toggle");
      var target = document.getElementById(targetId);
      if (!target) return;

      var isOpen = target.classList.toggle("open");
      target.classList.toggle("is-open", isOpen);
      trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
  }

  function bindActionForms() {
    document.addEventListener("submit", function (event) {
      var form = event.target.closest("[data-classroom-action-form]");
      if (!form) return;

      var confirmation = form.getAttribute("data-confirm-message");
      if (confirmation && !window.confirm(confirmation)) {
        event.preventDefault();
        return;
      }

      var button = form.querySelector('button[type="submit"]');
      if (!button || button.disabled) {
        if (button && button.disabled) event.preventDefault();
        return;
      }

      button.disabled = true;
      button.classList.add("is-loading");
      var loadingLabel = button.getAttribute("data-action-label");
      if (loadingLabel) button.textContent = loadingLabel;
    });
  }

  function bindCopyCode() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest("[data-copy-classroom-code]");
      if (!button) return;

      var code = button.getAttribute("data-copy-classroom-code") || "";
      if (!code) return;

      var previousText = button.textContent;
      var setCopied = function () {
        button.textContent = "Copied";
        button.classList.add("is-copied");
        window.setTimeout(function () {
          button.textContent = previousText;
          button.classList.remove("is-copied");
        }, 1400);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(setCopied).catch(function () {
          window.prompt("Copy classroom code", code);
        });
      } else {
        window.prompt("Copy classroom code", code);
      }
    });
  }

  revealClassroomItems();
  bindPanels();
  bindActionForms();
  bindCopyCode();
})();
