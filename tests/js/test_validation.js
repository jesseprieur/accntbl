// Run with: node tests/js/test_validation.js
const assert = require("assert");
const { validateTransactionEdit } = require("../../app/static/js/validation.js");

const base = { name: "Groceries", date: "2026-07-25", cash_amount: "12.34", credit_amount: "" };

// A fully valid cash row passes.
assert.strictEqual(validateTransactionEdit(base), null);

// A fully valid credit row passes.
assert.strictEqual(
  validateTransactionEdit({ ...base, cash_amount: "", credit_amount: "-5.00" }),
  null
);

// Required fields.
assert.strictEqual(validateTransactionEdit({ ...base, name: "" }), "Name is required.");
assert.strictEqual(validateTransactionEdit({ ...base, name: "   " }), "Name is required.");
assert.strictEqual(validateTransactionEdit({ ...base, date: "" }), "Date must be a valid YYYY-MM-DD date.");
assert.strictEqual(
  validateTransactionEdit({ ...base, date: "07/25/2026" }),
  "Date must be a valid YYYY-MM-DD date."
);

// Amount presence/exclusivity.
assert.strictEqual(
  validateTransactionEdit({ ...base, cash_amount: "", credit_amount: "" }),
  "Amount is required."
);
assert.strictEqual(
  validateTransactionEdit({ ...base, cash_amount: "12.34", credit_amount: "5.00" }),
  "Enter an amount in only one of Cash or Credit, not both."
);

// Numeric validation.
assert.strictEqual(
  validateTransactionEdit({ ...base, cash_amount: "not-a-number" }),
  "Cash amount must be a number."
);
assert.strictEqual(
  validateTransactionEdit({ ...base, cash_amount: "", credit_amount: "not-a-number" }),
  "Credit amount must be a number."
);

console.log("test_validation: all assertions passed");
