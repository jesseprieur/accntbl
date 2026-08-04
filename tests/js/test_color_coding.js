// Run with: node tests/js/test_color_coding.js
const assert = require("assert");
const { amountClass, runningTotalClass, rowBorderClass } = require("../../app/static/js/color_coding.js");

// Positive/negative/zero/empty transaction amounts.
assert.strictEqual(amountClass(42.5), "tx-amount-positive");
assert.strictEqual(amountClass(-13.2), "tx-amount-negative");
assert.strictEqual(amountClass(0), "");
assert.strictEqual(amountClass(null), "");
assert.strictEqual(amountClass(""), "");

// Running total highlighting is driven solely by the is_negative flag.
assert.strictEqual(runningTotalClass(true), "running-total-negative");
assert.strictEqual(runningTotalClass(false), "");

// Row border color coding: green for attached series occurrences, yellow
// for detached-from-series occurrences, blue for plain one-offs, none for
// skipped/virtual rows.
assert.strictEqual(
  rowBorderClass({ recurring_series_id: 1, occurrence_status: "attached" }),
  "series-attached-row"
);
assert.strictEqual(
  rowBorderClass({ recurring_series_id: 1, occurrence_status: "detached" }),
  "tx-detached-row"
);
assert.strictEqual(rowBorderClass({ recurring_series_id: null, occurrence_status: "attached" }), "tx-single-row");
assert.strictEqual(rowBorderClass({ recurring_series_id: null, occurrence_status: null }), "tx-single-row");
assert.strictEqual(rowBorderClass({ recurring_series_id: 1, occurrence_status: "skipped" }), "");
assert.strictEqual(rowBorderClass({ recurring_series_id: null, is_virtual: true }), "");
assert.strictEqual(rowBorderClass(null), "");

console.log("test_color_coding: all assertions passed");
