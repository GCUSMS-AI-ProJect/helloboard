"use strict";
// Run before styles paint, including on navigation, so saved dark mode never
// starts with a light page. This script needs neither the API nor a framework.
window.HelloBoardTheme = (() => {
  const key = "helloboard.theme";
  const system = matchMedia("(prefers-color-scheme: dark)");
  const valid = (value) => value === "dark" || value === "light";
  let explicit = null;
  let transitionTimer;
  try {
    const saved = localStorage.getItem(key);
    if (valid(saved)) explicit = saved;
  } catch {}
  function apply(theme, animate = false) {
    const root = document.documentElement;
    if (animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      root.dataset.themeSwitching = "true";
      clearTimeout(transitionTimer);
      transitionTimer = setTimeout(() => delete root.dataset.themeSwitching, 220);
    }
    root.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content", theme === "dark" ? "#14171c" : "#f5f5f7",
    );
    window.dispatchEvent(new Event("helloboard:theme"));
  }
  function set(theme) {
    if (!valid(theme)) return;
    explicit = theme;
    try {
      localStorage.setItem(key, theme);
    } catch {}
    apply(theme, true);
  }
  apply(explicit || (system.matches ? "dark" : "light"));
  system.addEventListener("change", () => {
    if (!explicit) apply(system.matches ? "dark" : "light", true);
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== key && event.key !== null) return;
    explicit = valid(event.newValue) ? event.newValue : null;
    apply(explicit || (system.matches ? "dark" : "light"), true);
  });
  return {
    set,
    toggle() {
      set(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    },
    get theme() {
      return document.documentElement.dataset.theme;
    },
  };
})();
