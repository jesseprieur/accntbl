// Statistics page: month dropdown re-renders the Needs/Wants/Savings/
// Leftover and spend-by-category tables together via a single Ajax call
// (see specs.md § "Spend-by-category breakdown (Statistics page)").
(function () {
  const select = document.getElementById("statistics-month-select");
  const nwsBody = document.getElementById("needs-wants-savings-body");
  const categoryBody = document.getElementById("spend-by-category-body");
  if (!select || !nwsBody || !categoryBody) return;

  function renderNeedsWantsSavings(data) {
    nwsBody.innerHTML = data.rows
      .map(
        (row) =>
          `<tr><td>${Escape.html(row.label)}</td><td>${Escape.html(row.value)}</td><td>${Escape.html(row.pct)}</td></tr>`
      )
      .join("");
  }

  function renderSpendByCategory(data) {
    categoryBody.innerHTML = data.rows
      .map((row) => {
        const icon = row.icon ? `<i class="bi ${Escape.html(row.icon)} me-1"></i>` : "";
        return `<tr><td>${icon}${Escape.html(row.name)}</td><td>${Escape.html(row.value)}</td><td>${Escape.html(row.pct)}</td></tr>`;
      })
      .join("");
  }

  select.addEventListener("change", () => {
    const month = select.value;
    fetch(`/statistics/breakdown?month=${encodeURIComponent(month)}`)
      .then((response) => {
        if (!response.ok) throw new Error("Request failed");
        return response.json();
      })
      .then((data) => {
        renderNeedsWantsSavings(data.needs_wants_savings);
        renderSpendByCategory(data.spend_by_category);
      })
      .catch(() => {
        window.AppErrors.show(window.AppErrors.NETWORK_ERROR_MESSAGE);
      });
  });
})();
