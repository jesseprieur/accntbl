(function () {
  const container = document.getElementById("transactions-window");
  const tbody = document.getElementById("transactions-tbody");
  if (!container || !tbody) return;

  const today = container.dataset.today;
  const windowUrl = container.dataset.windowUrl;
  const defaultCreditCardId = container.dataset.defaultCreditCardId || "";
  const showSkippedToggle = document.getElementById("show-skipped-toggle");

  const creditCardsDataEl = document.getElementById("credit-cards-data");
  const creditCards = creditCardsDataEl ? JSON.parse(creditCardsDataEl.textContent) : [];

  function cardName(cardId) {
    const card = creditCards.find((c) => String(c.id) === String(cardId));
    return card ? card.name : "";
  }

  function cardOptionsHtml(selectedId) {
    const selected = selectedId == null ? defaultCreditCardId : String(selectedId);
    return creditCards
      .map((card) => {
        const value = String(card.id);
        return `<option value="${value}" ${value === selected ? "selected" : ""}>${Escape.html(card.name)}</option>`;
      })
      .join("");
  }

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

  function spanWithClass(formatted, cls) {
    return `<span class="${cls}">${formatted}</span>`;
  }

  function amountSpan(value) {
    const formatted = formatAmount(value);
    if (!formatted) return "";
    return spanWithClass(formatted, ColorCoding.amountClass(value));
  }

  function runningTotalSpan(row) {
    if (row.running_total == null) return "";
    return spanWithClass(formatAmount(row.running_total), ColorCoding.runningTotalClass(row.is_negative));
  }

  // Raw row data keyed by transaction id, so an in-progress edit can be
  // cancelled back to its last-known-good values without a round trip.
  const rowDataById = new Map();
  // Payment-due (virtual) rows have no transaction id, so they're keyed by
  // card + due date instead, for the "edit estimate" modal to prefill from.
  const paymentDueRowsByKey = new Map();

  function paymentDueKey(creditCardId, dueDate) {
    return `${creditCardId}:${dueDate}`;
  }

  function initNotesPopover(button, notes) {
    if (!button || !window.bootstrap) return;
    button.setAttribute("data-bs-content", notes);
    new window.bootstrap.Popover(button, { title: "Notes" });
  }

  function buildRow(row) {
    if (row.is_month_end) {
      return buildMonthEndRow(row);
    }
    if (row.id != null) {
      rowDataById.set(String(row.id), row);
    } else if (row.is_virtual && row.credit_card_id != null) {
      paymentDueRowsByKey.set(paymentDueKey(row.credit_card_id, row.date), row);
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
    const isSeriesAttached = isAttached && row.recurring_series_id != null;
    const isPaymentDue = row.is_virtual && row.credit_card_id != null;
    const rowBorderClass = ColorCoding.rowBorderClass(row);
    const editable = !row.is_virtual && !isSkipped;
    const skippable = !row.is_virtual && isSeriesAttached;
    const unskippable = !row.is_virtual && isSkipped && row.recurring_series_id != null;
    const deletable = !row.is_virtual && !isSkipped && !isSeriesAttached;
    if (isSkipped) {
      tr.classList.add("text-muted");
    }
    if (row.recurring_series_id != null) {
      tr.dataset.seriesId = row.recurring_series_id;
    }
    if (rowBorderClass) {
      tr.classList.add(rowBorderClass);
    }
    if (isPaymentDue) {
      tr.dataset.creditCardId = row.credit_card_id;
      tr.classList.add(row.is_override ? "payment-due-overridden" : "payment-due-estimated");
    }
    const paymentDueLabel = isPaymentDue
      ? `${creditCards.length > 1 ? `${Escape.html(cardName(row.credit_card_id))} — ` : ""}<span class="badge ${row.is_override ? "text-bg-warning" : "text-bg-secondary"}">${row.is_override ? "Overridden" : "Estimated"}</span>`
      : "";
    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${row.name}${paymentDueLabel ? `<br>${paymentDueLabel}` : ""}</td>
      <td>${amountSpan(row.cash_amount)}</td>
      <td>${amountSpan(row.credit_amount)}</td>
      <td>${runningTotalSpan(row)}</td>
      <td class="text-nowrap">
        ${row.notes ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="notes" data-bs-toggle="popover" data-bs-trigger="focus" data-bs-placement="top"><i class="bi bi-info-circle"></i> Notes</button>' : ""}
        ${editable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit"><i class="bi bi-pencil"></i> Edit</button>' : ""}
        ${skippable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="skip"><i class="bi bi-skip-forward"></i> Skip</button>' : ""}
        ${unskippable ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="unskip"><i class="bi bi-arrow-counterclockwise"></i> Un-skip</button>' : ""}
        ${deletable ? '<button type="button" class="btn btn-outline-danger btn-sm" data-action="delete"><i class="bi bi-trash"></i> Delete</button>' : ""}
        ${isPaymentDue ? '<button type="button" class="btn btn-outline-secondary btn-sm" data-action="edit-estimate"><i class="bi bi-pencil"></i> Edit estimate</button>' : ""}
      </td>
    `;
    if (row.notes) {
      initNotesPopover(tr.querySelector('[data-action="notes"]'), row.notes);
    }
    return tr;
  }

  function buildEditRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.date = row.date;
    tr.dataset.id = row.id;
    const isCredit = row.credit_amount != null;
    tr.innerHTML = `
      <td><input type="date" class="form-control form-control-sm border-0" data-field="date" value="${Escape.html(row.date)}" required></td>
      <td>
        <input type="text" class="form-control form-control-sm border-0" data-field="name" value="${Escape.html(row.name)}" required>
        <input type="text" class="form-control form-control-sm border-0 mt-1" data-field="notes" placeholder="Notes" value="${Escape.html(row.notes || "")}">
      </td>
      <td><input type="number" step="0.01" class="form-control form-control-sm border-0" data-field="cash_amount" value="${Escape.html(formatAmount(row.cash_amount))}"></td>
      <td>
        <input type="number" step="0.01" class="form-control form-control-sm border-0" data-field="credit_amount" value="${Escape.html(formatAmount(row.credit_amount))}">
        <select class="form-select form-select-sm mt-1 ${isCredit ? "" : "d-none"}" data-card-select>
          ${cardOptionsHtml(row.credit_card_id)}
        </select>
      </td>
      <td>${row.running_total == null ? "" : formatAmount(row.running_total)}</td>
      <td class="text-nowrap">
        <button type="button" class="btn btn-primary btn-sm" data-action="save"><i class="bi bi-check-lg"></i> Save</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-action="cancel"><i class="bi bi-x-lg"></i> Cancel</button>
      </td>
    `;
    const creditAmountInput = tr.querySelector('[data-field="credit_amount"]');
    const cardSelect = tr.querySelector("[data-card-select]");
    if (creditAmountInput && cardSelect) {
      creditAmountInput.addEventListener("input", () => {
        cardSelect.classList.toggle("d-none", !creditAmountInput.value);
      });
    }
    return tr;
  }

  function buildEditRowErrorRow(message) {
    const tr = document.createElement("tr");
    tr.classList.add("edit-row-error");
    tr.innerHTML = `<td colspan="6" class="text-danger small py-1">${Escape.html(message)}</td>`;
    return tr;
  }

  function clearEditRowError(tr) {
    const next = tr.nextElementSibling;
    if (next && next.classList.contains("edit-row-error")) {
      next.remove();
    }
  }

  function showEditRowError(tr, message) {
    clearEditRowError(tr);
    tr.after(buildEditRowErrorRow(message));
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
        : `(${Number(change) >= 0 ? "+" : ""}${formatAmount(change)})`;

    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${row.name}</td>
      <td></td>
      <td></td>
      <td>${runningTotalSpan(row)}</td>
      <td>${changeLabel}</td>
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

    const validationError = Validation.validateTransactionEdit(values);
    if (validationError) {
      showEditRowError(tr, validationError);
      return;
    }
    clearEditRowError(tr);

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
      const cardSelect = tr.querySelector("[data-card-select]");
      if (cardSelect) body.credit_card_id = cardSelect.value;
    }

    fetch(`/transactions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          showEditRowError(tr, data.error || "Failed to save change.");
          return;
        }
        reloadLoadedWindow();
      })
      .catch(() => showEditRowError(tr, AppErrors.NETWORK_ERROR_MESSAGE));
  }

  function deleteRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;
    if (!window.confirm("Delete this transaction?")) return;

    fetch(`/transactions/${id}`, { method: "DELETE" })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          AppErrors.show(data.error || "Failed to delete transaction.");
          return;
        }
        reloadLoadedWindow();
      })
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
  }

  function skipRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;
    if (!window.confirm("Skip this occurrence?")) return;

    fetch(`/transactions/${id}/skip`, { method: "POST" })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          AppErrors.show(data.error || "Failed to skip occurrence.");
          return;
        }
        reloadLoadedWindow();
      })
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
  }

  function unskipRow(tr) {
    const id = tr.dataset.id;
    if (!id) return;

    fetch(`/transactions/${id}/unskip`, { method: "POST" })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          AppErrors.show(data.error || "Failed to un-skip occurrence.");
          return;
        }
        reloadLoadedWindow();
      })
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
  }

  const editEstimateModalEl = document.getElementById("edit-estimate-modal");
  const editEstimateForm = document.getElementById("edit-estimate-form");
  const editEstimateError = document.getElementById("edit-estimate-error");
  const editEstimateClearButton = document.getElementById("edit-estimate-clear");

  function openEditEstimateModal(creditCardId, dueDate) {
    if (!editEstimateForm || !editEstimateModalEl) return;
    const row = paymentDueRowsByKey.get(paymentDueKey(creditCardId, dueDate));
    if (!row) return;
    editEstimateForm.elements["credit_card_id"].value = creditCardId;
    editEstimateForm.elements["due_date"].value = dueDate;
    editEstimateForm.elements["amount"].value = formatAmount(row.cash_amount);
    editEstimateForm.elements["notes"].value = row.notes || "";
    editEstimateError.classList.add("d-none");
    editEstimateClearButton.classList.toggle("d-none", !row.is_override);
    const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(editEstimateModalEl) : null;
    if (modal) modal.show();
  }

  if (editEstimateForm) {
    editEstimateForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(editEstimateForm);
      const body = {
        credit_card_id: formData.get("credit_card_id"),
        due_date: formData.get("due_date"),
        amount: formData.get("amount"),
        notes: formData.get("notes") || null,
      };
      fetch("/transactions/credit-due-overrides", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            editEstimateError.textContent = data.error || "Failed to save estimate.";
            editEstimateError.classList.remove("d-none");
            return;
          }
          editEstimateError.classList.add("d-none");
          const modal = window.bootstrap
            ? window.bootstrap.Modal.getOrCreateInstance(editEstimateModalEl)
            : null;
          if (modal) modal.hide();
          reloadLoadedWindow();
        })
        .catch(() => {
          editEstimateError.textContent = AppErrors.NETWORK_ERROR_MESSAGE;
          editEstimateError.classList.remove("d-none");
        });
    });
  }

  if (editEstimateClearButton) {
    editEstimateClearButton.addEventListener("click", () => {
      const creditCardId = editEstimateForm.elements["credit_card_id"].value;
      const dueDate = editEstimateForm.elements["due_date"].value;
      fetch(
        `/transactions/credit-due-overrides?credit_card_id=${encodeURIComponent(creditCardId)}&due_date=${encodeURIComponent(dueDate)}`,
        { method: "DELETE" }
      )
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            editEstimateError.textContent = data.error || "Failed to clear override.";
            editEstimateError.classList.remove("d-none");
            return;
          }
          const modal = window.bootstrap
            ? window.bootstrap.Modal.getOrCreateInstance(editEstimateModalEl)
            : null;
          if (modal) modal.hide();
          reloadLoadedWindow();
        })
        .catch(() => {
          editEstimateError.textContent = AppErrors.NETWORK_ERROR_MESSAGE;
          editEstimateError.classList.remove("d-none");
        });
    });
  }

  tbody.addEventListener("click", (event) => {
    const editEstimateButton = event.target.closest('[data-action="edit-estimate"]');
    if (editEstimateButton) {
      const tr = editEstimateButton.closest("tr");
      if (tr) openEditEstimateModal(tr.dataset.creditCardId, tr.dataset.date);
      return;
    }

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
      if (row) {
        clearEditRowError(tr);
        tr.replaceWith(buildViewRow(row));
      }
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
    fetchWindow(earliestLoaded, latestLoaded)
      .then((data) => {
        renderInitialRows(data.rows);
        container.scrollTop = scrollTop;
      })
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));
  }

  function renderInitialRows(rows) {
    tbody.innerHTML = "";

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-muted">No transactions in this window.</td></tr>';
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
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE))
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
      .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE))
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
    })
    .catch(() => AppErrors.show(AppErrors.NETWORK_ERROR_MESSAGE));

  const addForm = document.getElementById("add-transaction-form");
  if (addForm) {
    const addModalEl = document.getElementById("add-transaction-modal");
    const addError = document.getElementById("add-transaction-error");
    const addCardField = document.getElementById("add-transaction-card-field");

    const toggleAddCardField = () => {
      const checked = addForm.querySelector('input[name="kind"]:checked');
      if (addCardField) addCardField.classList.toggle("d-none", !checked || checked.value !== "credit");
    };
    addForm.querySelectorAll('input[name="kind"]').forEach((radio) => {
      radio.addEventListener("change", toggleAddCardField);
    });
    toggleAddCardField();

    addForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(addForm);
      const kind = formData.get("kind");
      const body = {
        name: formData.get("name"),
        date: formData.get("date"),
        kind,
        amount: formData.get("amount"),
        notes: formData.get("notes") || null,
      };
      if (kind === "credit") {
        body.credit_card_id = formData.get("credit_card_id");
      }

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
          toggleAddCardField();
          const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(addModalEl) : null;
          if (modal) modal.hide();
          reloadLoadedWindow();
        })
        .catch(() => {
          addError.textContent = AppErrors.NETWORK_ERROR_MESSAGE;
          addError.classList.remove("d-none");
        });
    });
  }

})();
