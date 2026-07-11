(function () {
  "use strict";

  var storageKey = "sat-makon-theme";
  var allowed = { system: true, light: true, dark: true };
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

  function getSavedMode() {
    try {
      var saved = localStorage.getItem(storageKey);
      return allowed[saved] ? saved : "system";
    } catch (error) {
      return "system";
    }
  }

  function saveMode(mode) {
    try {
      if (mode === "system") {
        localStorage.removeItem(storageKey);
      } else {
        localStorage.setItem(storageKey, mode);
      }
    } catch (error) {}
  }

  function resolveMode(mode) {
    if (mode === "light" || mode === "dark") return mode;
    return media && media.matches ? "light" : "dark";
  }

  function iconFor(mode, resolved) {
    if (mode === "system") return resolved === "light" ? "◑" : "◐";
    return mode === "light" ? "☀" : "☾";
  }

  function labelFor(mode) {
    if (mode === "light") return "Light";
    if (mode === "dark") return "Dark";
    return "System";
  }

  function applyTheme(mode) {
    var resolved = resolveMode(mode);
    var root = document.documentElement;
    root.dataset.themeMode = mode;
    root.dataset.theme = resolved;
    root.style.colorScheme = resolved;

    document.querySelectorAll("[data-theme-switcher]").forEach(function (switcher) {
      var label = switcher.querySelector("[data-theme-label]");
      var icon = switcher.querySelector("[data-theme-icon]");
      if (label) label.textContent = labelFor(mode);
      if (icon) icon.textContent = iconFor(mode, resolved);

      switcher.querySelectorAll("[data-theme-choice]").forEach(function (choice) {
        choice.setAttribute("aria-checked", String(choice.dataset.themeChoice === mode));
      });
    });
  }

  function closeAll(except) {
    document.querySelectorAll("[data-theme-switcher].is-open").forEach(function (switcher) {
      if (switcher === except) return;
      switcher.classList.remove("is-open");
      var toggle = switcher.querySelector("[data-theme-toggle]");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    });
  }

  function setupSwitcher(switcher) {
    var toggle = switcher.querySelector("[data-theme-toggle]");
    if (toggle) {
      toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        var willOpen = !switcher.classList.contains("is-open");
        closeAll(switcher);
        switcher.classList.toggle("is-open", willOpen);
        toggle.setAttribute("aria-expanded", String(willOpen));
      });
    }

    switcher.querySelectorAll("[data-theme-choice]").forEach(function (choice) {
      choice.addEventListener("click", function (event) {
        event.stopPropagation();
        var mode = choice.dataset.themeChoice;
        if (!allowed[mode]) return;
        saveMode(mode);
        applyTheme(mode);
        closeAll();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-theme-switcher]").forEach(setupSwitcher);
    applyTheme(getSavedMode());
  });

  document.addEventListener("click", function () {
    closeAll();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeAll();
  });

  if (media) {
    var onSystemThemeChange = function () {
      if (getSavedMode() === "system") applyTheme("system");
    };
    if (media.addEventListener) {
      media.addEventListener("change", onSystemThemeChange);
    } else if (media.addListener) {
      media.addListener(onSystemThemeChange);
    }
  }
})();
