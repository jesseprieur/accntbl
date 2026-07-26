// Pure client-side validation for the inline transaction row editor (see
// specs.md Polish phase "Form validation"). UMD-ish export so this can be
// loaded as a plain <script> in the browser and also required directly from
// a Node-based unit test.
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.Validation = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

  function isValidNumber(value) {
    return value !== "" && !Number.isNaN(Number(value));
  }

  // values: { name, date, cash_amount, credit_amount }
  // Returns an error string, or null if the row is valid.
  function validateTransactionEdit(values) {
    if (!values.name || !values.name.trim()) {
      return "Name is required.";
    }
    if (!values.date || !DATE_RE.test(values.date)) {
      return "Date must be a valid YYYY-MM-DD date.";
    }

    const hasCash = values.cash_amount !== "" && values.cash_amount != null;
    const hasCredit = values.credit_amount !== "" && values.credit_amount != null;

    if (hasCash && hasCredit) {
      return "Enter an amount in only one of Cash or Credit, not both.";
    }
    if (!hasCash && !hasCredit) {
      return "Amount is required.";
    }
    if (hasCash && !isValidNumber(values.cash_amount)) {
      return "Cash amount must be a number.";
    }
    if (hasCredit && !isValidNumber(values.credit_amount)) {
      return "Credit amount must be a number.";
    }

    return null;
  }

  return { validateTransactionEdit };
});
