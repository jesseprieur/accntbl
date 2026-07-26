// Pure helpers for table row/cell color coding (see specs.md Polish phase).
// UMD-ish export so this can be loaded as a plain <script> in the browser
// and also required directly from a Node-based unit test.
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ColorCoding = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  function formatAmount(value) {
    return value ? Number(value).toFixed(2) : "";
  }

  function amountClass(value) {
    if (value == null || value === "") return "";
    const num = Number(value);
    if (num === 0) return "";
    return num > 0 ? "tx-amount-positive" : "tx-amount-negative";
  }

  function runningTotalClass(isNegative) {
    return isNegative ? "running-total-negative" : "";
  }

  return { formatAmount, amountClass, runningTotalClass };
});
