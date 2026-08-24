(function () {
  const container = document.getElementById("transactions-window");
  const tbody = document.getElementById("transactions-tbody");
  if (!container || !tbody) return;

  const today = DateUtils.today();
  const windowUrl = container.dataset.windowUrl;
  const defaultCreditCardId = container.dataset.defaultCreditCardId || "";
  const showSkippedToggle = document.getElementById("show-skipped-toggle");

  const creditCardsDataEl = document.getElementById("credit-cards-data");
  const creditCards = creditCardsDataEl ? JSON.parse(creditCardsDataEl.textContent) : [];

  function cardName(cardId) {
    const card = creditCards.find((c) => String(c.id) === String(cardId));
    return card ? card.name : "";
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

  const formatAmount = ColorCoding.formatAmount;

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

  // Raw row data keyed by transaction id, so opening the edit modal can
  // populate its fields without a round trip.
  const rowDataById = new Map();
  // Assigned once the edit-transaction modal is wired up below.
  let openEditTransactionModal = () => {};
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
      if (row) openEditTransactionModal(row);
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

    if (addModalEl) {
      addModalEl.addEventListener("show.bs.modal", () => {
        addForm.elements["date"].value = DateUtils.today();
      });
    }

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
        needs_wants_savings: formData.get("needs_wants_savings"),
        category_id: formData.get("category_id"),
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
          const addTransactionCategoryPicker = addForm.querySelector(".category-picker");
          if (addTransactionCategoryPicker) {
            CategoryPicker.setValue(addTransactionCategoryPicker, "");
          }
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

  const editForm = document.getElementById("edit-transaction-form");
  if (editForm) {
    const editModalEl = document.getElementById("edit-transaction-modal");
    const editModalLabel = document.getElementById("edit-transaction-modal-label");
    const editError = document.getElementById("edit-transaction-error");
    const editCardField = document.getElementById("edit-transaction-card-field");
    const editDetachNotice = document.getElementById("edit-transaction-detach-notice");
    const editCategoryPickerEl = document.getElementById("edit-transaction-category-picker");

    const toggleEditCardField = () => {
      const checked = editForm.querySelector('input[name="kind"]:checked');
      if (editCardField) editCardField.classList.toggle("d-none", !checked || checked.value !== "credit");
    };
    editForm.querySelectorAll('input[name="kind"]').forEach((radio) => {
      radio.addEventListener("change", toggleEditCardField);
    });

    // Populates the shared Edit Transaction/Edit Occurrence modal from an
    // already-loaded row (rowDataById) rather than an extra fetch, and
    // switches its title/notice depending on whether saving will detach
    // this row from its series (see specs.md "Recurring series editing
    // semantics").
    openEditTransactionModal = function (row) {
      const isSeriesOccurrence =
        row.occurrence_status === "attached" && row.recurring_series_id != null;
      const isCredit = row.credit_amount != null;

      editForm.elements["id"].value = row.id;
      editForm.elements["name"].value = row.name;
      editForm.elements["date"].value = row.date;
      editForm.elements["notes"].value = row.notes || "";
      editForm.elements["kind"].value = isCredit ? "credit" : "cash";
      editForm.elements["amount"].value = formatAmount(isCredit ? row.credit_amount : row.cash_amount);
      editForm.elements["credit_card_id"].value = row.credit_card_id != null ? row.credit_card_id : defaultCreditCardId;
      editForm.elements["needs_wants_savings"].value = row.needs_wants_savings || "need";
      toggleEditCardField();

      if (editCategoryPickerEl) {
        CategoryPicker.mount(editCategoryPickerEl, row.category_id);
      }

      if (editModalLabel) {
        editModalLabel.textContent = isSeriesOccurrence ? "Edit occurrence" : "Edit transaction";
      }
      if (editDetachNotice) {
        editDetachNotice.classList.toggle("d-none", !isSeriesOccurrence);
      }
      if (editError) editError.classList.add("d-none");

      const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(editModalEl) : null;
      if (modal) modal.show();
    };

    editForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(editForm);
      const id = formData.get("id");
      const kind = formData.get("kind");
      const amount = formData.get("amount");

      const validationError = Validation.validateTransactionEdit({
        name: formData.get("name"),
        date: formData.get("date"),
        cash_amount: kind === "cash" ? amount : "",
        credit_amount: kind === "credit" ? amount : "",
      });
      if (validationError) {
        editError.textContent = validationError;
        editError.classList.remove("d-none");
        return;
      }

      const body = {
        name: formData.get("name"),
        date: formData.get("date"),
        notes: formData.get("notes") || null,
        needs_wants_savings: formData.get("needs_wants_savings"),
        category_id: formData.get("category_id"),
        kind,
        amount,
      };
      if (kind === "credit") {
        body.credit_card_id = formData.get("credit_card_id");
      }

      fetch(`/transactions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            editError.textContent = data.error || "Failed to save change.";
            editError.classList.remove("d-none");
            return;
          }
          editError.classList.add("d-none");
          const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(editModalEl) : null;
          if (modal) modal.hide();
          reloadLoadedWindow();
        })
        .catch(() => {
          editError.textContent = AppErrors.NETWORK_ERROR_MESSAGE;
          editError.classList.remove("d-none");
        });
    });
  }

})();
