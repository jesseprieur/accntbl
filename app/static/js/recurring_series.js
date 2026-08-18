(function () {
  const tbody = document.getElementById("series-tbody");
  if (!tbody) return;

  const CADENCE_LABELS = {
    weekly: "Weekly",
    biweekly: "Biweekly",
    monthly: "Monthly",
    semi_monthly: "Semi-monthly",
    quarterly: "Quarterly",
    yearly: "Yearly",
    custom: "Custom",
  };

  function cadenceLabel(series) {
    const label = CADENCE_LABELS[series.cadence_type] || series.cadence_type;
    if (series.cadence_type === "custom") {
      return `Every ${series.custom_interval_value} ${series.custom_interval_unit}`;
    }
    return label;
  }

  function perMonthLabel(series) {
    const value = Number(series.per_month);
    if (Number.isNaN(value)) return series.per_month;
    return value.toFixed(2);
  }

  function buildRow(series) {
    const tr = document.createElement("tr");
    tr.dataset.id = series.id;
    tr.innerHTML = `
      <td>${Escape.html(series.name)}</td>
      <td>${series.kind}</td>
      <td>${series.amount}</td>
      <td>${perMonthLabel(series)}</td>
      <td>${cadenceLabel(series)}</td>
      <td>${series.start_date}</td>
      <td>${series.end_date || ""}</td>
      <td class="text-nowrap">
        ${series.notes ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="notes" data-bs-toggle="popover" data-bs-trigger="focus" data-bs-placement="top"><i class="bi bi-info-circle"></i> Notes</button>' : ""}
        <button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit"><i class="bi bi-pencil"></i> Edit</button>
        <button type="button" class="btn btn-outline-danger btn-sm" data-action="delete"><i class="bi bi-trash"></i> Delete</button>
      </td>
    `;
    if (series.notes) {
      const notesButton = tr.querySelector('[data-action="notes"]');
      if (notesButton && window.bootstrap) {
        notesButton.setAttribute("data-bs-content", series.notes);
        new window.bootstrap.Popover(notesButton, { title: "Notes" });
      }
    }
    return tr;
  }

  function initAmountLogicPanel(root) {
    if (!root) return null;

    const modeRadios = root.querySelectorAll("[data-amount-logic-mode]");
    const advancedSection = root.querySelector("[data-amount-logic-advanced]");
    const basicHint = root.querySelector("[data-amount-logic-basic-hint]");
    const typeRadios = root.querySelectorAll("[data-amount-logic-type]");
    const panels = root.querySelectorAll("[data-amount-logic-panel]");
    const rulesContainer = root.querySelector("[data-amount-logic-rules]");
    const ruleTemplate = root.querySelector("[data-amount-logic-rule-template]");
    const addRuleButton = root.querySelector('[data-amount-logic-action="add-rule"]');
    const escalationValueInput = root.querySelector('[data-amount-logic-field="value"]');
    const escalationAdjustmentSelect = root.querySelector('[data-amount-logic-field="adjustment_type"]');

    function selectedMode() {
      const checked = root.querySelector("[data-amount-logic-mode]:checked");
      return checked ? checked.value : "basic";
    }

    function selectedType() {
      const checked = root.querySelector("[data-amount-logic-type]:checked");
      return checked ? checked.value : "conditional";
    }

    function showPanelFor(type) {
      panels.forEach((panel) => {
        panel.classList.toggle("d-none", panel.dataset.amountLogicPanel !== type);
      });
    }

    function showAdvancedFor(mode) {
      const isAdvanced = mode === "advanced";
      if (advancedSection) advancedSection.classList.toggle("d-none", !isAdvanced);
      if (basicHint) basicHint.classList.toggle("d-none", !isAdvanced);
      if (isAdvanced) showPanelFor(selectedType());
    }

    modeRadios.forEach((radio) => radio.addEventListener("change", () => showAdvancedFor(selectedMode())));
    typeRadios.forEach((radio) => radio.addEventListener("change", () => showPanelFor(selectedType())));

    function addRuleRow(rule) {
      if (!ruleTemplate || !rulesContainer) return;
      const fragment = ruleTemplate.content.cloneNode(true);
      const row = fragment.querySelector("[data-amount-logic-rule-row]");
      if (rule) {
        row.querySelector('[data-amount-logic-field="until_month"]').value = rule.until_month ?? "";
        row.querySelector('[data-amount-logic-field="until_day"]').value = rule.until_day ?? "";
        row.querySelector('[data-amount-logic-field="until_year"]').value = rule.until_year ?? "";
        row.querySelector('[data-amount-logic-field="amount"]').value = rule.amount ?? "";
      }
      rulesContainer.appendChild(row);
    }

    if (addRuleButton) {
      addRuleButton.addEventListener("click", () => addRuleRow());
    }

    if (rulesContainer) {
      rulesContainer.addEventListener("click", (event) => {
        const removeButton = event.target.closest('[data-amount-logic-action="remove-rule"]');
        if (removeButton) {
          const row = removeButton.closest("[data-amount-logic-rule-row]");
          if (row) row.remove();
        }
      });
    }

    function reset() {
      root.querySelector('[data-amount-logic-mode][value="basic"]').checked = true;
      root.querySelector('[data-amount-logic-type][value="conditional"]').checked = true;
      showAdvancedFor("basic");
      if (rulesContainer) rulesContainer.innerHTML = "";
      if (escalationValueInput) escalationValueInput.value = "";
      if (escalationAdjustmentSelect) escalationAdjustmentSelect.value = "amount";
    }

    function populate(amountLogic) {
      reset();
      if (!amountLogic) return;
      if (amountLogic.type === "conditional") {
        root.querySelector('[data-amount-logic-mode][value="advanced"]').checked = true;
        root.querySelector('[data-amount-logic-type][value="conditional"]').checked = true;
        showAdvancedFor("advanced");
        (amountLogic.rules || []).forEach((rule) => addRuleRow(rule));
      } else if (amountLogic.type === "escalating") {
        root.querySelector('[data-amount-logic-mode][value="advanced"]').checked = true;
        root.querySelector('[data-amount-logic-type][value="escalating"]').checked = true;
        showAdvancedFor("advanced");
        if (escalationValueInput) escalationValueInput.value = amountLogic.value ?? "";
        if (escalationAdjustmentSelect) escalationAdjustmentSelect.value = amountLogic.adjustment_type || "amount";
      }
    }

    function serialize() {
      if (selectedMode() !== "advanced") return null;
      const type = selectedType();
      if (type === "conditional") {
        const rules = Array.from(rulesContainer.querySelectorAll("[data-amount-logic-rule-row]")).map((row) => ({
          until_month: row.querySelector('[data-amount-logic-field="until_month"]').value,
          until_day: row.querySelector('[data-amount-logic-field="until_day"]').value,
          until_year: row.querySelector('[data-amount-logic-field="until_year"]').value || null,
          amount: row.querySelector('[data-amount-logic-field="amount"]').value,
        }));
        return {
          type: "conditional",
          rules,
          else_amount: null,
        };
      }
      if (type === "escalating") {
        return {
          type: "escalating",
          adjustment_type: escalationAdjustmentSelect ? escalationAdjustmentSelect.value : "amount",
          value: escalationValueInput ? escalationValueInput.value : "",
        };
      }
      return null;
    }

    showAdvancedFor(selectedMode());

    return { serialize, populate, reset };
  }

  const addAmountLogic = initAmountLogicPanel(document.querySelector('[data-amount-logic-root][data-prefix="add-series"]'));
  const editAmountLogic = initAmountLogicPanel(document.querySelector('[data-amount-logic-root][data-prefix="edit-series"]'));

  function loadSeries() {
    fetch("/transactions/series")
      .then((response) => response.json())
      .then((data) => {
        tbody.innerHTML = "";
        if (data.series.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" class="text-muted">No recurring series yet.</td></tr>';
          return;
        }
        data.series.forEach((series) => tbody.appendChild(buildRow(series)));
      })
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
  }

  loadSeries();

  function toggleCustomFields(select, fields) {
    if (select && fields) {
      fields.classList.toggle("d-none", select.value !== "custom");
    }
  }

  const seriesCadenceSelect = document.getElementById("add-series-cadence");
  const seriesCustomFields = document.getElementById("add-series-custom-fields");
  const toggleSeriesCustomFields = () => toggleCustomFields(seriesCadenceSelect, seriesCustomFields);
  if (seriesCadenceSelect) {
    seriesCadenceSelect.addEventListener("change", toggleSeriesCustomFields);
    toggleSeriesCustomFields();
  }

  function toggleCardField(form, cardField) {
    if (!form || !cardField) return;
    const checked = form.querySelector('input[name="kind"]:checked');
    cardField.classList.toggle("d-none", !checked || checked.value !== "credit");
  }

  const addSeriesForm = document.getElementById("add-series-form");
  const addSeriesCardField = document.getElementById("add-series-card-field");
  const toggleAddSeriesCardField = () => toggleCardField(addSeriesForm, addSeriesCardField);
  if (addSeriesForm) {
    addSeriesForm.querySelectorAll('input[name="kind"]').forEach((radio) => {
      radio.addEventListener("change", toggleAddSeriesCardField);
    });
    toggleAddSeriesCardField();
  }

  if (addSeriesForm) {
    const addSeriesModalEl = document.getElementById("add-series-modal");
    const addSeriesError = document.getElementById("add-series-error");

    if (addSeriesModalEl) {
      addSeriesModalEl.addEventListener("show.bs.modal", () => {
        addSeriesForm.elements["start_date"].value = DateUtils.today();
        if (addAmountLogic) addAmountLogic.reset();
      });
    }

    addSeriesForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(addSeriesForm);
      const kind = formData.get("kind");
      const body = {
        name: formData.get("name"),
        kind,
        amount: formData.get("amount"),
        cadence_type: formData.get("cadence_type"),
        custom_interval_value: formData.get("custom_interval_value") || null,
        custom_interval_unit: formData.get("custom_interval_unit") || null,
        start_date: formData.get("start_date"),
        end_date: formData.get("end_date") || null,
        notes: formData.get("notes") || null,
        amount_logic: addAmountLogic ? addAmountLogic.serialize() : null,
        needs_wants_savings: formData.get("needs_wants_savings"),
        category_id: formData.get("category_id"),
      };
      if (kind === "credit") {
        body.credit_card_id = formData.get("credit_card_id");
      }

      fetch("/transactions/series", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            addSeriesError.textContent = data.error || "Failed to add recurring series.";
            addSeriesError.classList.remove("d-none");
            return;
          }
          addSeriesError.classList.add("d-none");
          addSeriesForm.reset();
          toggleSeriesCustomFields();
          toggleAddSeriesCardField();
          const modal = window.bootstrap
            ? window.bootstrap.Modal.getOrCreateInstance(addSeriesModalEl)
            : null;
          if (modal) modal.hide();
          loadSeries();
        })
        .catch(() => {
          addSeriesError.textContent = AppErrors.NETWORK_ERROR_MESSAGE;
          addSeriesError.classList.remove("d-none");
        });
    });
  }

  const editSeriesForm = document.getElementById("edit-series-form");
  const editSeriesModalEl = document.getElementById("edit-series-modal");
  const editSeriesCadenceSelect = document.getElementById("edit-series-cadence");
  const editSeriesCustomFields = document.getElementById("edit-series-custom-fields");
  const editSeriesCardField = document.getElementById("edit-series-card-field");
  const toggleEditSeriesCardField = () => toggleCardField(editSeriesForm, editSeriesCardField);

  const toggleEditSeriesCustomFields = () =>
    toggleCustomFields(editSeriesCadenceSelect, editSeriesCustomFields);
  if (editSeriesCadenceSelect) {
    editSeriesCadenceSelect.addEventListener("change", toggleEditSeriesCustomFields);
  }
  if (editSeriesForm) {
    editSeriesForm.querySelectorAll('input[name="kind"]').forEach((radio) => {
      radio.addEventListener("change", toggleEditSeriesCardField);
    });
  }

  const editSeriesEffectiveDateField = document.getElementById("edit-series-effective-date-field");
  const toggleEditSeriesEffectiveDateField = () => {
    if (!editSeriesForm || !editSeriesEffectiveDateField) return;
    const checked = editSeriesForm.querySelector('input[name="save_mode"]:checked');
    editSeriesEffectiveDateField.classList.toggle("d-none", !checked || checked.value !== "future");
  };
  if (editSeriesForm) {
    editSeriesForm.querySelectorAll('input[name="save_mode"]').forEach((radio) => {
      radio.addEventListener("change", toggleEditSeriesEffectiveDateField);
    });
  }

  function openEditSeriesModal(seriesId) {
    if (!editSeriesForm || !editSeriesModalEl) return;
    fetch(`/transactions/series/${seriesId}`)
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          AppErrors.show(data.error || "Failed to load recurring series.");
          return;
        }
        editSeriesForm.elements["series_id"].value = data.id;
        editSeriesForm.elements["name"].value = data.name;
        editSeriesForm.elements["kind"].value = data.kind;
        editSeriesForm.elements["amount"].value = data.amount;
        editSeriesForm.elements["cadence_type"].value = data.cadence_type;
        editSeriesForm.elements["custom_interval_value"].value = data.custom_interval_value || "";
        editSeriesForm.elements["custom_interval_unit"].value = data.custom_interval_unit || "days";
        editSeriesForm.elements["start_date"].value = data.start_date;
        editSeriesForm.elements["end_date"].value = data.end_date || "";
        editSeriesForm.elements["notes"].value = data.notes || "";
        if (data.credit_card_id != null) {
          editSeriesForm.elements["credit_card_id"].value = data.credit_card_id;
        }
        editSeriesForm.elements["needs_wants_savings"].value = data.needs_wants_savings;
        if (data.category_id != null) {
          editSeriesForm.elements["category_id"].value = data.category_id;
        }
        editSeriesForm.elements["save_mode"].value = "all";
        editSeriesForm.elements["effective_date"].value = "";
        if (editAmountLogic) editAmountLogic.populate(data.amount_logic);
        toggleEditSeriesCustomFields();
        toggleEditSeriesCardField();
        toggleEditSeriesEffectiveDateField();
        document.getElementById("edit-series-error").classList.add("d-none");
        const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(editSeriesModalEl) : null;
        if (modal) modal.show();
      })
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
  }

  if (editSeriesForm) {
    const editSeriesError = document.getElementById("edit-series-error");

    editSeriesForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(editSeriesForm);
      const seriesId = formData.get("series_id");
      const kind = formData.get("kind");
      const body = {
        name: formData.get("name"),
        kind,
        amount: formData.get("amount"),
        cadence_type: formData.get("cadence_type"),
        custom_interval_value: formData.get("custom_interval_value") || null,
        custom_interval_unit: formData.get("custom_interval_unit") || null,
        start_date: formData.get("start_date"),
        end_date: formData.get("end_date") || null,
        notes: formData.get("notes") || null,
        amount_logic: editAmountLogic ? editAmountLogic.serialize() : null,
        needs_wants_savings: formData.get("needs_wants_savings"),
        category_id: formData.get("category_id"),
      };
      if (kind === "credit") {
        body.credit_card_id = formData.get("credit_card_id");
      }

      const saveMode = formData.get("save_mode");
      if (saveMode === "future") {
        const effectiveDate = formData.get("effective_date");
        if (!effectiveDate) {
          editSeriesError.textContent = "An effective date is required to save changes for future occurrences only.";
          editSeriesError.classList.remove("d-none");
          return;
        }
        if (
          !window.confirm(
            `Occurrences on or before ${effectiveDate} will be detached and left the same. Occurrences after ${effectiveDate} will use the new values. Continue?`
          )
        ) {
          return;
        }
        body.save_mode = "future";
        body.effective_date = effectiveDate;
      }

      fetch(`/transactions/series/${seriesId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            editSeriesError.textContent = data.error || "Failed to update recurring series.";
            editSeriesError.classList.remove("d-none");
            return;
          }
          editSeriesError.classList.add("d-none");
          const modal = window.bootstrap
            ? window.bootstrap.Modal.getOrCreateInstance(editSeriesModalEl)
            : null;
          if (modal) modal.hide();
          loadSeries();
        })
        .catch(() => {
          editSeriesError.textContent = AppErrors.NETWORK_ERROR_MESSAGE;
          editSeriesError.classList.remove("d-none");
        });
    });
  }

  tbody.addEventListener("click", (event) => {
    const editButton = event.target.closest('[data-action="edit"]');
    if (editButton) {
      const tr = editButton.closest("tr");
      if (tr) openEditSeriesModal(tr.dataset.id);
      return;
    }

    const deleteButton = event.target.closest('[data-action="delete"]');
    if (deleteButton) {
      const tr = deleteButton.closest("tr");
      if (!tr) return;
      const name = tr.querySelector("td").textContent;
      if (!window.confirm(`Permanently delete the recurring series "${name}" and all of its attached occurrences?`)) {
        return;
      }
      fetch(`/transactions/series/${tr.dataset.id}`, { method: "DELETE" })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            AppErrors.show(data.error || "Failed to delete recurring series.");
            return;
          }
          loadSeries();
        })
        .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
    }
  });
})();
