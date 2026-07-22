(function () {
  const container = document.getElementById("transactions-window");
  const tbody = document.getElementById("transactions-tbody");
  if (!container || !tbody) return;

  const today = container.dataset.today;
  const windowUrl = container.dataset.windowUrl;
  const showSkippedToggle = document.getElementById("show-skipped-toggle");

  const PAGE_DAYS = 30;
  const FUTURE_LIMIT_DAYS = 365;
  const SCROLL_THRESHOLD_PX = 100;

  let earliestLoaded = null; // Date
  let latestLoaded = null; // Date
  let loadingPast = false;
  let loadingFuture = false;
  let reachedPastStart = false; // no more history before earliestLoaded
  let reachedFutureLimit = false;

  function toDate(isoString) {
    return new Date(`${isoString}T00:00:00`);
  }

  function addDays(date, days) {
    const result = new Date(date);
    result.setDate(result.getDate() + days);
    return result;
  }

  function toIso(date) {
    return date.toISOString().slice(0, 10);
  }

  function formatAmount(value) {
    return value ? Number(value).toFixed(2) : "";
  }

  function escapeAttr(value) {
    return String(value == null ? "" : value).replace(/"/g, "&quot;");
  }

  function editableCell(field, value, editable) {
    if (!editable) {
      return `<td>${value == null ? "" : value}</td>`;
    }
    return `<td><input type="text" class="form-control form-control-sm border-0" data-field="${field}" value="${escapeAttr(value)}"></td>`;
  }

  function buildRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.date = row.date;
    tr.dataset.id = row.id == null ? "" : row.id;
    if (row.is_negative) {
      tr.classList.add("table-danger");
    }
    if (row.date === today) {
      tr.classList.add("table-primary");
    }
    const isSkipped = row.occurrence_status === "skipped";
    const editable = !row.is_virtual && !isSkipped;
    const skippable = editable && row.recurring_series_id != null;
    const unskippable = !row.is_virtual && row.recurring_series_id != null && isSkipped;
    if (isSkipped) {
      tr.classList.add("text-muted");
    }
    tr.innerHTML = `
      ${editableCell("date", row.date, editable)}
      ${editableCell("name", row.name, editable)}
      ${editableCell("cash_amount", formatAmount(row.cash_amount), editable)}
      ${editableCell("credit_amount", formatAmount(row.credit_amount), editable)}
      <td>${row.running_total == null ? "" : formatAmount(row.running_total)}</td>
      ${editableCell("notes", row.notes || "", editable)}
      <td>
        ${skippable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="skip">Skip</button>' : ""}
        ${unskippable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="unskip">Un-skip</button>' : ""}
        ${!row.is_virtual ? '<button type="button" class="btn btn-outline-danger btn-sm" data-action="delete">Delete</button>' : ""}
      </td>
    `;
    return tr;
  }

  function saveField(tr, field, input) {
    const id = tr.dataset.id;
    if (!id) return;
    const value = input.value.trim();
    const body = {};
    if (field === "cash_amount" || field === "credit_amount") {
      body[field] = value === "" ? null : value;
    } else {
      body[field] = value;
    }

    fetch(`/transactions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          alert(data.error || "Failed to save change.");
          return;
        }
        reloadLoadedWindow();
      });
  }

  tbody.addEventListener(
    "blur",
    (event) => {
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || !input.dataset.field) return;
      const tr = input.closest("tr");
      if (!tr) return;
      saveField(tr, input.dataset.field, input);
    },
    true
  );

  tbody.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
      event.target.blur();
    }
  });

  function deleteRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;
    if (!window.confirm("Delete this transaction?")) return;

    fetch(`/transactions/${id}`, { method: "DELETE" })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          alert(data.error || "Failed to delete transaction.");
          return;
        }
        reloadLoadedWindow();
      });
  }

  function skipRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;
    if (!window.confirm("Skip this occurrence?")) return;

    fetch(`/transactions/${id}/skip`, { method: "POST" })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          alert(data.error || "Failed to skip occurrence.");
          return;
        }
        reloadLoadedWindow();
      });
  }

  function unskipRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;

    fetch(`/transactions/${id}/unskip`, { method: "POST" })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          alert(data.error || "Failed to un-skip occurrence.");
          return;
        }
        reloadLoadedWindow();
      });
  }

  tbody.addEventListener("click", (event) => {
    const deleteButton = event.target.closest('[data-action="delete"]');
    if (deleteButton) {
      const tr = deleteButton.closest("tr");
      if (tr) deleteRow(tr);
      return;
    }

    const skipButton = event.target.closest('[data-action="skip"]');
    if (skipButton) {
      const tr = skipButton.closest("tr");
      if (tr) skipRow(tr);
      return;
    }

    const unskipButton = event.target.closest('[data-action="unskip"]');
    if (unskipButton) {
      const tr = unskipButton.closest("tr");
      if (tr) unskipRow(tr);
    }
  });

  if (showSkippedToggle) {
    showSkippedToggle.addEventListener("change", reloadLoadedWindow);
  }

  function reloadLoadedWindow() {
    if (earliestLoaded === null || latestLoaded === null) return;
    const scrollTop = container.scrollTop;
    fetchWindow(earliestLoaded, latestLoaded).then((data) => {
      renderInitialRows(data.rows);
      container.scrollTop = scrollTop;
    });
  }

  function renderInitialRows(rows) {
    tbody.innerHTML = "";

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-muted">No transactions in this window.</td></tr>';
      return;
    }

    rows.forEach((row) => tbody.appendChild(buildRow(row)));
  }

  function clearEmptyState() {
    const emptyRow = tbody.querySelector("td.text-muted");
    if (emptyRow) {
      emptyRow.closest("tr").remove();
    }
  }

  function appendRows(rows) {
    if (rows.length === 0) return;
    clearEmptyState();
    rows.forEach((row) => tbody.appendChild(buildRow(row)));
  }

  function prependRows(rows) {
    if (rows.length === 0) return;
    clearEmptyState();
    const previousScrollHeight = container.scrollHeight;
    const previousScrollTop = container.scrollTop;
    const fragment = document.createDocumentFragment();
    rows.forEach((row) => fragment.appendChild(buildRow(row)));
    tbody.insertBefore(fragment, tbody.firstChild);
    container.scrollTop = previousScrollTop + (container.scrollHeight - previousScrollHeight);
  }

  function scrollToToday() {
    const todayRow = tbody.querySelector(`tr[data-date="${today}"]`);
    if (todayRow) {
      todayRow.scrollIntoView({ block: "center" });
    }
  }

  function fetchWindow(start, end) {
    const includeSkipped = showSkippedToggle && showSkippedToggle.checked ? "&include_skipped=1" : "";
    return fetch(`${windowUrl}?start=${toIso(start)}&end=${toIso(end)}${includeSkipped}`).then(
      (response) => response.json()
    );
  }

  function loadPast() {
    if (loadingPast || reachedPastStart || earliestLoaded === null) return;
    loadingPast = true;
    const end = addDays(earliestLoaded, -1);
    const start = addDays(end, -(PAGE_DAYS - 1));
    fetchWindow(start, end)
      .then((data) => {
        if (data.rows.length === 0) {
          reachedPastStart = true;
        } else {
          prependRows(data.rows);
        }
        earliestLoaded = start;
      })
      .finally(() => {
        loadingPast = false;
      });
  }

  function loadFuture() {
    if (loadingFuture || reachedFutureLimit || latestLoaded === null) return;
    const futureLimit = addDays(toDate(today), FUTURE_LIMIT_DAYS);
    if (latestLoaded >= futureLimit) {
      reachedFutureLimit = true;
      return;
    }
    loadingFuture = true;
    const start = addDays(latestLoaded, 1);
    let end = addDays(start, PAGE_DAYS - 1);
    if (end > futureLimit) {
      end = futureLimit;
    }
    fetchWindow(start, end)
      .then((data) => {
        appendRows(data.rows);
        latestLoaded = end;
        if (end >= futureLimit) {
          reachedFutureLimit = true;
        }
      })
      .finally(() => {
        loadingFuture = false;
      });
  }

  container.addEventListener("scroll", () => {
    if (container.scrollTop <= SCROLL_THRESHOLD_PX) {
      loadPast();
    }
    if (
      container.scrollHeight - container.scrollTop - container.clientHeight <=
      SCROLL_THRESHOLD_PX
    ) {
      loadFuture();
    }
  });

  fetch(windowUrl)
    .then((response) => response.json())
    .then((data) => {
      renderInitialRows(data.rows);
      earliestLoaded = toDate(data.start);
      latestLoaded = toDate(data.end);
      scrollToToday();
    });

  const addForm = document.getElementById("add-transaction-form");
  if (addForm) {
    const addModalEl = document.getElementById("add-transaction-modal");
    const addError = document.getElementById("add-transaction-error");

    addForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(addForm);
      const body = {
        name: formData.get("name"),
        date: formData.get("date"),
        cash_amount: formData.get("cash_amount") || null,
        credit_amount: formData.get("credit_amount") || null,
        notes: formData.get("notes") || null,
      };

      fetch("/transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            addError.textContent = data.error || "Failed to add transaction.";
            addError.classList.remove("d-none");
            return;
          }
          addError.classList.add("d-none");
          addForm.reset();
          const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(addModalEl) : null;
          if (modal) modal.hide();
          reloadLoadedWindow();
        });
    });
  }

  const seriesCadenceSelect = document.getElementById("add-series-cadence");
  const seriesCustomFields = document.getElementById("add-series-custom-fields");
  function toggleSeriesCustomFields() {
    if (seriesCadenceSelect && seriesCustomFields) {
      seriesCustomFields.classList.toggle("d-none", seriesCadenceSelect.value !== "custom");
    }
  }
  if (seriesCadenceSelect) {
    seriesCadenceSelect.addEventListener("change", toggleSeriesCustomFields);
    toggleSeriesCustomFields();
  }

  const addSeriesForm = document.getElementById("add-series-form");
  if (addSeriesForm) {
    const addSeriesModalEl = document.getElementById("add-series-modal");
    const addSeriesError = document.getElementById("add-series-error");

    addSeriesForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(addSeriesForm);
      const body = {
        name: formData.get("name"),
        kind: formData.get("kind"),
        amount: formData.get("amount"),
        cadence_type: formData.get("cadence_type"),
        custom_interval_value: formData.get("custom_interval_value") || null,
        custom_interval_unit: formData.get("custom_interval_unit") || null,
        start_date: formData.get("start_date"),
        end_date: formData.get("end_date") || null,
        notes: formData.get("notes") || null,
      };

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
          const modal = window.bootstrap
            ? window.bootstrap.Modal.getOrCreateInstance(addSeriesModalEl)
            : null;
          if (modal) modal.hide();
          reloadLoadedWindow();
        });
    });
  }
})();
