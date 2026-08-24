// The one implementation of money formatting on the frontend — every file
// that renders a dollar amount uses this instead of its own
// `Number(value).toFixed(2)`. UMD-ish export so this can be loaded as a
// plain <script> in the browser and also required directly from a
// Node-based unit test.
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.Currency = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  function format(value) {
    return Number(value).toFixed(2);
  }

  return { format };
});
