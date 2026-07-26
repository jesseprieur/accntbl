// Global error banner, shared by every page (see specs.md Polish phase
// "Basic error handling"). Used for failures that don't have a more specific
// inline spot to render in (e.g. network errors, delete/skip/unskip failures).
(function () {
  const NETWORK_ERROR_MESSAGE = "Network error. Please check your connection and try again.";

  function show(message) {
    const alertEl = document.getElementById("global-error-alert");
    const messageEl = document.getElementById("global-error-alert-message");
    if (!alertEl || !messageEl) return;
    messageEl.textContent = message;
    alertEl.classList.remove("d-none");
    alertEl.classList.add("show");
  }

  window.AppErrors = { show, NETWORK_ERROR_MESSAGE };
})();
