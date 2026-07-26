// Run with: node tests/js/test_color_coding.js
const assert = require("assert");
const { amountClass, runningTotalClass } = require("../../app/static/js/color_coding.js");

// Positive/negative/zero/empty transaction amounts.
assert.strictEqual(amountClass(42.5), "tx-amount-positive");
assert.strictEqual(amountClass(-13.2), "tx-amount-negative");
assert.strictEqual(amountClass(0), "");
assert.strictEqual(amountClass(null), "");
assert.strictEqual(amountClass(""), "");

// Running total highlighting is driven solely by the is_negative flag.
assert.strictEqual(runningTotalClass(true), "running-total-negative");
assert.strictEqual(runningTotalClass(false), "");

console.log("test_color_coding: all assertions passed");
