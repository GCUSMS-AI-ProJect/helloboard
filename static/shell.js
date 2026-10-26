"use strict";
(() => {
  const { t } = window.HelloBoardI18n;
  const $ = (selector) => document.querySelector(selector);
  // Every dialog uses the same lifecycle so closing waits for its exit motion.
  const dialogClosures = new WeakMap();
  const registeredDialogs = new WeakSet();
  function savedPreference(name) {
    const key = "helloboard." + name;
    const current = localStorage.getItem(key);
    if (current !== null) return current;
    const legacyKey = "hellowifi." + name;
    const legacy = localStorage.getItem(legacyKey);
    if (legacy !== null) {
      localStorage.setItem(key, legacy);
      localStorage.removeItem(legacyKey);
    }
    return legacy;
  }
  function renderThemeToggle() {
    const button = $("#theme-toggle");
    const dark = window.HelloBoardTheme.theme === "dark";
    button.setAttribute("aria-checked", String(dark));
    button.setAttribute("aria-label", t("深色模式"));
    button.title = t(dark ? "切换为浅色模式" : "切换为深色模式");
  }
  renderThemeToggle();
  $("#theme-toggle").addEventListener("click", () => window.HelloBoardTheme.toggle());
  window.addEventListener("helloboard:theme", renderThemeToggle);
  window.addEventListener("helloboard:language", renderThemeToggle);
  function renderSidebarToggle() {
    const collapsed = document.documentElement.dataset.sidebar === "collapsed";
    const button = $("#sidebar-toggle");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", t(collapsed ? "展开侧栏" : "收起侧栏"));
    button.title = button.getAttribute("aria-label");
  }
  function setSidebar(collapsed, persist = true) {
    document.documentElement.dataset.sidebar = collapsed
      ? "collapsed"
      : "expanded";
    renderSidebarToggle();
    if (persist) {
      try {
        localStorage.setItem(
          "helloboard.sidebar",
          collapsed ? "collapsed" : "expanded",
        );
      } catch {}
    }
  }
  try {
    setSidebar(savedPreference("sidebar") === "collapsed", false);
  } catch {
    setSidebar(false, false);
  }
  // Restore the saved layout before enabling its transitions.
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      document.documentElement.dataset.sidebarReady = "true";
    }),
  );
  $("#sidebar-toggle").addEventListener("click", () => {
    setSidebar(document.documentElement.dataset.sidebar !== "collapsed");
  });
  for (const item of document.querySelectorAll(".sidebar .nav-item")) {
    item.addEventListener("keydown", (event) => {
      if (event.key === "Escape") item.classList.add("tooltip-dismissed");
    });
    for (const event of ["pointerleave", "blur"])
      item.addEventListener(event, () =>
        item.classList.remove("tooltip-dismissed"),
      );
  }
  function canCloseDialog(dialog) {
    return (
      !window.HelloBoardCanCloseDialog ||
      window.HelloBoardCanCloseDialog(dialog)
    );
  }
  function showDialog(dialog) {
    if (!registeredDialogs.has(dialog)) {
      registeredDialogs.add(dialog);
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        if (canCloseDialog(dialog)) closeDialog(dialog);
      });
      dialog.addEventListener("click", (event) => {
        const rect = dialog.getBoundingClientRect();
        if (
          event.target === dialog &&
          (event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom) &&
          canCloseDialog(dialog)
        )
          closeDialog(dialog);
      });
    }
    const closing = dialogClosures.get(dialog);
    if (closing) {
      clearTimeout(closing.timer);
      closing.resolve();
      dialogClosures.delete(dialog);
    }
    dialog.classList.remove("closing");
    if (!dialog.open) dialog.showModal();
  }
  function closeDialog(dialog) {
    if (!dialog.open) return Promise.resolve();
    if (dialogClosures.has(dialog)) return dialogClosures.get(dialog).promise;
    dialog.classList.add("closing");
    const duration = matchMedia("(prefers-reduced-motion: reduce)").matches
      ? 0
      : dialog.classList.contains("side-panel")
        ? 260
        : 220;
    let resolve;
    const promise = new Promise((done) => {
      resolve = done;
    });
    const timer = setTimeout(() => {
      dialog.close();
      dialog.classList.remove("closing");
      dialogClosures.delete(dialog);
      resolve();
    }, duration);
    dialogClosures.set(dialog, { promise, resolve, timer });
    return promise;
  }
  let requestedLayout,
    layoutRevision = 0,
    layoutTransition = null,
    layoutMotion = null;
  function setLayout(layout, persist = true) {
    layout = layout === "relaxed" ? "relaxed" : "compact";
    if (persist) {
      try {
        localStorage.setItem("helloboard.layout", layout);
      } catch {}
    }
    if (requestedLayout === layout) return;
    requestedLayout = layout;
    const revision = ++layoutRevision;
    layoutTransition?.skipTransition();
    layoutMotion?.cancel();
    const apply = () => {
      // An interrupted snapshot must not restore an earlier choice.
      if (revision !== layoutRevision) return;
      document.documentElement.dataset.layout = layout;
      for (const name of ["relaxed", "compact"])
        $("#layout-" + name).setAttribute(
          "aria-pressed",
          String(name === layout),
        );
    };
    if (
      !persist ||
      document.hidden ||
      matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      apply();
      return;
    }
    if (document.startViewTransition) {
      try {
        const transition = document.startViewTransition(apply);
        layoutTransition = transition;
        transition.ready.catch(() => {});
        transition.finished
          .catch(() => {})
          .finally(() => {
            if (layoutTransition === transition) layoutTransition = null;
          });
        return;
      } catch {
        // Older browsers still apply the layout and get a light entrance fade.
      }
    }
    apply();
    layoutMotion = $("#main").animate(
      [
        { opacity: 0.65, transform: "translateY(4px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { duration: 280, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
    );
  }
  try {
    setLayout(savedPreference("layout"), false);
  } catch {
    setLayout("compact", false);
  }
  for (const name of ["relaxed", "compact"])
    $("#layout-" + name).addEventListener("click", () => setLayout(name));

  window.addEventListener("helloboard:language", renderSidebarToggle);
  Object.assign(window, {
    setSidebar,
    renderSidebarToggle,
    setLayout,
    showDialog,
    closeDialog,
  });
})();
