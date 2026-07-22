(function () {
  const container = document.getElementById("transactions-window");
  const tbody = document.getElementById("transactions-tbody");
  if (!container || !tbody) return;

  const today = container.dataset.today;
  const windowUrl = container.dataset.windowUrl;

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

  function buildRow(row) {
    const tr = document.createElement("tr");
    tr.dataset.date = row.date;
    if (row.is_negative) {
      tr.classList.add("table-danger");
    }
    if (row.date === today) {
      tr.classList.add("table-primary");
    }
    tr.innerHTML = `
      <td>${row.date}</td>
      <td>${row.name}</td>
      <td>${formatAmount(row.cash_amount)}</td>
      <td>${formatAmount(row.credit_amount)}</td>
      <td>${formatAmount(row.running_total)}</td>
      <td>${row.notes || ""}</td>
    `;
    return tr;
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
    return fetch(`${windowUrl}?start=${toIso(start)}&end=${toIso(end)}`).then((response) =>
      response.json()
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
})();
