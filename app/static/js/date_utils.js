// Shared date helpers. "Today" must always come from the browser's local
// clock, not the server's, so the app stays consistent with the user's own
// timezone regardless of where the server process happens to run.
(function () {
  function today() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  window.DateUtils = { today };
})();
