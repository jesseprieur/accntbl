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
      return `${label} (every ${series.custom_interval_value} ${series.custom_interval_unit})`;
    }
    return label;
  }

  function buildRow(series) {
    const tr = document.createElement("tr");
    tr.dataset.id = series.id;
    tr.innerHTML = `
      <td>${Escape.html(series.name)}</td>
      <td>${series.kind}</td>
      <td>${series.amount}</td>
      <td>${cadenceLabel(series)}</td>
      <td>${series.start_date}</td>
      <td>${series.end_date || ""}</td>
      <td>${Escape.html(series.notes || "")}</td>
      <td class="text-nowrap">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit"><i class="bi bi-pencil"></i> Edit</button>
        <button type="button" class="btn btn-outline-danger btn-sm" data-action="delete"><i class="bi bi-trash"></i> Delete</button>
      </td>
    `;
    return tr;
  }

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
        toggleEditSeriesCustomFields();
        toggleEditSeriesCardField();
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
      };
      if (kind === "credit") {
        body.credit_card_id = formData.get("credit_card_id");
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
