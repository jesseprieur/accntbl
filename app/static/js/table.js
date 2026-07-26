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

  function amountSpan(value) {
    const formatted = formatAmount(value);
    if (!formatted) return "";
    return `<span class="${ColorCoding.amountClass(value)}">${formatted}</span>`;
  }

  function runningTotalSpan(row) {
    if (row.running_total == null) return "";
    const cls = ColorCoding.runningTotalClass(row.is_negative);
    return `<span class="${cls}">${formatAmount(row.running_total)}</span>`;
  }

  // Raw row data keyed by transaction id, so an in-progress edit can be
  // cancelled back to its last-known-good values without a round trip.
  const rowDataById = new Map();

  function buildRow(row) {
    if (row.is_month_end) {
      return buildMonthEndRow(row);
    }
    if (row.id != null) {
      rowDataById.set(String(row.id), row);
    }
    return buildViewRow(row);
  }

  function buildViewRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.date = row.date;
    tr.dataset.id = row.id == null ? "" : row.id;
    if (row.date === today) {
      tr.classList.add("table-primary");
    }
    const isSkipped = row.occurrence_status === "skipped";
    const isAttached = row.occurrence_status === "attached";
    const editable = !row.is_virtual && !isSkipped;
    const skippable = !row.is_virtual && isAttached;
    const unskippable = !row.is_virtual && isSkipped && row.recurring_series_id != null;
    const deletable = !row.is_virtual && !isSkipped && !isAttached;
    if (isSkipped) {
      tr.classList.add("text-muted");
    }
    if (isAttached) {
      tr.dataset.seriesId = row.recurring_series_id;
      tr.classList.add("series-attached-row");
    }
    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${row.name}</td>
      <td>${amountSpan(row.cash_amount)}</td>
      <td>${amountSpan(row.credit_amount)}</td>
      <td>${runningTotalSpan(row)}</td>
      <td>${row.notes || ""}</td>
      <td class="text-nowrap">
        ${editable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit">Edit</button>' : ""}
        ${skippable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="skip">Skip</button>' : ""}
        ${unskippable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="unskip">Un-skip</button>' : ""}
        ${deletable ? '<button type="button" class="btn btn-outline-danger btn-sm" data-action="delete">Delete</button>' : ""}
      </td>
    `;
    return tr;
  }

  function buildEditRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.date = row.date;
    tr.dataset.id = row.id;
    tr.innerHTML = `
      <td><input type="date" class="form-control form-control-sm border-0" data-field="date" value="${escapeAttr(row.date)}"></td>
      <td><input type="text" class="form-control form-control-sm border-0" data-field="name" value="${escapeAttr(row.name)}"></td>
      <td><input type="text" class="form-control form-control-sm border-0" data-field="cash_amount" value="${escapeAttr(formatAmount(row.cash_amount))}"></td>
      <td><input type="text" class="form-control form-control-sm border-0" data-field="credit_amount" value="${escapeAttr(formatAmount(row.credit_amount))}"></td>
      <td>${row.running_total == null ? "" : formatAmount(row.running_total)}</td>
      <td><input type="text" class="form-control form-control-sm border-0" data-field="notes" value="${escapeAttr(row.notes || "")}"></td>
      <td class="text-nowrap">
        <button type="button" class="btn btn-primary btn-sm" data-action="save">Save</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-action="cancel">Cancel</button>
      </td>
    `;
    return tr;
  }

  function buildMonthEndRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.date = row.date;
    tr.dataset.id = "";
    tr.classList.add("table-secondary", "fw-bold", "fst-italic", "month-end-row");

    const change = row.month_over_month_change;
    const changeLabel =
      change == null
        ? ""
        : `(${Number(change) >= 0 ? "+" : ""}${formatAmount(change)} vs. prior month end)`;

    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${row.name}</td>
      <td></td>
      <td></td>
      <td>${runningTotalSpan(row)}</td>
      <td>${changeLabel}</td>
      <td></td>
    `;
    return tr;
  }

  function saveRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;

    const values = {};
    tr.querySelectorAll("[data-field]").forEach((input) => {
      values[input.dataset.field] = input.value.trim();
    });

    const body = {
      name: values.name,
      date: values.date,
      notes: values.notes || null,
    };
    if (values.cash_amount) {
      body.kind = "cash";
      body.amount = values.cash_amount;
    } else if (values.credit_amount) {
      body.kind = "credit";
      body.amount = values.credit_amount;
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
    const editButton = event.target.closest('[data-action="edit"]');
    if (editButton) {
      const tr = editButton.closest("tr");
      const row = tr && rowDataById.get(tr.dataset.id);
      if (row) tr.replaceWith(buildEditRow(row));
      return;
    }

    const cancelButton = event.target.closest('[data-action="cancel"]');
    if (cancelButton) {
      const tr = cancelButton.closest("tr");
      const row = tr && rowDataById.get(tr.dataset.id);
      if (row) tr.replaceWith(buildViewRow(row));
      return;
    }

    const saveButton = event.target.closest('[data-action="save"]');
    if (saveButton) {
      const tr = saveButton.closest("tr");
      if (tr) saveRow(tr);
      return;
    }

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
        kind: formData.get("kind"),
        amount: formData.get("amount"),
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

})();
