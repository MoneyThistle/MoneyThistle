// Runs before the page is drawn: use the last known theme so dark mode doesn't flash white.
(function () {
  try {
    var ui = JSON.parse(localStorage.getItem("hl-ui") || "{}");
    var dark = ui.theme === "dark" || (ui.theme === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    if (/^#[0-9a-f]{6}$/i.test(ui.accent || "")) document.documentElement.style.setProperty("--accent", ui.accent);
  } catch (e) { /* first visit: defaults */ }
})();
