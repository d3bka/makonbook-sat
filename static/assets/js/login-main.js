(function () {
  "use strict";

  document.documentElement.classList.add("js-auth");

  function setFullHeight() {
    document.querySelectorAll(".js-fullheight").forEach(function (el) {
      el.style.minHeight = window.innerHeight + "px";
    });
  }

  function setupPasswordToggles() {
    document.querySelectorAll(".toggle-password, .password-toggle").forEach(function (toggle) {
      toggle.addEventListener("click", function () {
        var selector = toggle.getAttribute("toggle") || toggle.dataset.target;
        var input = selector ? document.querySelector(selector) : toggle.parentElement.querySelector("input");
        if (!input) return;

        var isPassword = input.getAttribute("type") === "password";
        input.setAttribute("type", isPassword ? "text" : "password");
        toggle.classList.toggle("is-visible", isPassword);
        toggle.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
        if (!toggle.classList.contains("fa")) {
          toggle.textContent = isPassword ? "Hide" : "Show";
        }
      });
    });
  }

  function setupReveal() {
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-auth-reveal], [data-page-reveal]"));
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
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });

    items.forEach(function (item, index) {
      item.style.transitionDelay = Math.min(index * 55, 280) + "ms";
      observer.observe(item);
    });
  }

  function setupTilt() {
    document.querySelectorAll("[data-tilt]").forEach(function (card) {
      card.addEventListener("mousemove", function (event) {
        var rect = card.getBoundingClientRect();
        var x = ((event.clientX - rect.left) / rect.width - 0.5) * 8;
        var y = ((event.clientY - rect.top) / rect.height - 0.5) * -8;
        card.style.transform = "perspective(900px) rotateY(" + x + "deg) rotateX(" + y + "deg) translateY(-4px)";
      });
      card.addEventListener("mouseleave", function () {
        card.style.transform = "";
      });
    });
  }

  setFullHeight();
  setupPasswordToggles();
  setupReveal();
  setupTilt();
  window.addEventListener("resize", setFullHeight);
})();
