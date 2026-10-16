(function () {
  var storageKey = "steepwell-theme";
  var root = document.documentElement;

  function savedTheme() {
    try {
      return localStorage.getItem(storageKey) === "dark" ? "dark" : "light";
    } catch (error) {
      return "light";
    }
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem(storageKey, theme);
      return true;
    } catch (error) {
      return false;
    }
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var toggle = document.getElementById("theme-toggle");
    if (toggle) {
      toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }
  }

  applyTheme(savedTheme());

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(root.getAttribute("data-theme"));
    document.getElementById("theme-toggle").addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      saveTheme(next);
      applyTheme(next);
    });
  });
})();
