(function () {
  "use strict";

  document.documentElement.classList.add("js-pages");

  var revealTargets = Array.prototype.slice.call(document.querySelectorAll(".card, .practice-card, .no-cards, .edit-profile-container, .dashboard-panel, .content-card, .form-card"));
  revealTargets.forEach(function (item) {
    if (!item.hasAttribute("data-page-reveal")) {
      item.setAttribute("data-page-reveal", "");
    }
  });

  var items = Array.prototype.slice.call(document.querySelectorAll("[data-page-reveal]"));
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
  }, { threshold: 0.1, rootMargin: "0px 0px -7% 0px" });

  items.forEach(function (item, index) {
    item.style.transitionDelay = Math.min(index * 45, 240) + "ms";
    observer.observe(item);
  });
})();
