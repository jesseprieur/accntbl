// Shared HTML escaping, used anywhere server-controlled or user-entered
// values are interpolated into innerHTML template strings.
(function () {
  function html(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.Escape = { html };
})();
