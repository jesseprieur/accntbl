// Shared custom category-dropdown widget, used everywhere a category_id is
// picked (add-transaction modal, add/edit-series modals, inline row edit).
// Native <option> elements can't render icon glyphs, so this renders a
// Bootstrap dropdown instead, backed by a hidden `category_id` input so
// existing save/read code (FormData.get("category_id"), table.js's
// data-field loop, recurring_series.js's form.elements) keeps working
// unchanged. Every transaction/series has a real category_id (defaulting
// to "Uncategorized" — see specs.md § `categories`), so the menu never
// needs a synthetic "no category" entry.
(function () {
  const dataEl = document.getElementById("categories-data");
  const categories = dataEl ? JSON.parse(dataEl.textContent) : [];
  const FALLBACK_ICON = "bi-tag";

  function iconFor(category) {
    return (category && category.icon) || FALLBACK_ICON;
  }

  function findCategory(categoryId) {
    if (categoryId == null || categoryId === "") return null;
    return categories.find((c) => String(c.id) === String(categoryId)) || null;
  }

  function toggleLabelHtml(category) {
    return category
      ? `<i class="bi ${iconFor(category)}"></i> ${Escape.html(category.name)}`
      : "Category";
  }

  function itemHtml(category) {
    return `<li><a class="dropdown-item category-picker-item" href="#" data-category-id="${category.id}"><i class="bi ${iconFor(category)}"></i> ${Escape.html(category.name)}</a></li>`;
  }

  function html(selectedId, options) {
    options = options || {};
    const name = options.name || "category_id";
    const selected = findCategory(selectedId);
    const items = categories.map(itemHtml).join("");
    return (
      '<div class="dropdown category-picker">' +
      '<button class="btn btn-outline-secondary btn-sm dropdown-toggle w-100 text-start" type="button" data-bs-toggle="dropdown" aria-expanded="false">' +
      `<span class="category-picker-toggle-label">${toggleLabelHtml(selected)}</span></button>` +
      `<ul class="dropdown-menu category-picker-menu">${items}</ul>` +
      `<input type="hidden" name="${name}" data-field="category_id" value="${selected ? selected.id : ""}">` +
      "</div>"
    );
  }

  function mount(container, selectedId, options) {
    container.innerHTML = html(selectedId, options);
  }

  function setValue(pickerRoot, categoryId) {
    const selected = findCategory(categoryId);
    pickerRoot.querySelector(".category-picker-toggle-label").innerHTML = toggleLabelHtml(selected);
    pickerRoot.querySelector('input[data-field="category_id"]').value = selected ? selected.id : "";
  }

  document.addEventListener("click", function (event) {
    const item = event.target.closest(".category-picker-item");
    if (!item) return;
    event.preventDefault();
    const picker = item.closest(".category-picker");
    if (!picker) return;
    setValue(picker, item.dataset.categoryId);
    picker.querySelector('input[data-field="category_id"]').dispatchEvent(new Event("change", { bubbles: true }));
  });

  document.querySelectorAll("[data-category-picker]").forEach(function (el) {
    mount(el, el.dataset.categoryPickerSelected || "", { name: el.dataset.categoryPickerName || "category_id" });
  });

  window.CategoryPicker = { categories, html, mount, setValue, findCategory };
})();
