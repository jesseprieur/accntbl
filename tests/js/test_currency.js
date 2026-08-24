// Run with: node tests/js/test_currency.js
const assert = require("assert");
const { format } = require("../../app/static/js/currency.js");

assert.strictEqual(format(42.5), "42.50");
assert.strictEqual(format(-13.2), "-13.20");
assert.strictEqual(format(0), "0.00");
assert.strictEqual(format("19.995"), "20.00");

console.log("test_currency: all assertions passed");
