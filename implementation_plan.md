# Implementation Plan

Checkboxes track progress across Claude sessions. See specs.md for full
design rationale before implementing any item below. Organized by feature
area (not build-chronological order) — read as "everything needed to bring
the app from nothing to its current state," with new/unbuilt features
grouped at the bottom.

## Project scaffolding
- [x] Initialize repo structure (`app/`, `migrations/`, `docker/`, etc.)
- [x] `docker-compose.yml` with a single `web` (Flask) service; SQLite file
      persisted via a bind mount to `./data` on the host (no separate DB
      service/container) — see specs.md § "Tech stack"
- [x] Flask app factory + config (dev/test/prod via env vars)
- [x] SQLAlchemy setup + Alembic init — see specs.md § "Tech stack" for the
      `render_as_batch` configuration gotcha
- [x] `.env.example` with Flask secret key and app config

## Data model
- [x] `users` model + seed script/CLI command to create the single user
- [x] `checking_accounts` model
- [x] `credit_cards` model (multiple rows, `is_default` bool)
- [x] `credit_due_overrides` model (`credit_card_id`, `due_date`, `amount`,
      `notes`, unique on card+due_date)
- [x] `recurring_series` model (with `credit_card_id`, `amount_logic`)
- [x] `transactions` model (with `recurring_series_id`, `occurrence_status`
      enum: `attached` | `detached` | `skipped`, `credit_card_id`)
- [x] App-level enforcement that exactly one `credit_cards` row is
      `is_default` at all times (on create/edit/delete)
- [x] Block deleting a credit card that's still referenced by any
      transaction/series, or that is the current default (must
      reassign/promote first); block deleting the last remaining card
      entirely
- [x] Alembic migrations for all of the above

## Auth
- [x] Login page (username/password)
- [x] Session-based auth, `@login_required` on all app routes
- [x] Logout

## Core domain logic
- [x] Recurring occurrence generator (given a `recurring_series`, produce
      concrete dates within a date range, honoring cadence_type/custom
      interval/start/end date)
- [x] Credit card statement period calculator (given `statement_close_day`,
      a date range → list of period boundaries), keyed by `credit_card_id`,
      computed independently per card
- [x] Credit card payment-due amount calculator (sum `amount` on kind=credit
      transactions per closed period per card → generates virtual cash
      transaction on due date; override precedence via
      `credit_due_overrides`; `starting_balance`/`starting_balance_due_date`
      seeding) — see specs.md § "Credit card payment logic"
- [x] Running total calculator (baseline from `checking_accounts` +
      ascending walk through transactions with `occurrence_status != skipped`
      /generated CC payments)
- [x] Basic/Advanced amount-logic toggle on recurring series forms — see
      specs.md § "Advanced amount logic"
    - [x] Conditional if/elseif date-based amount rules
    - [x] Escalating increase/decrease (absolute amount or percentage) per
          occurrence
- [x] Unit tests for all of the above (cadence edge cases, custom intervals,
      statement period boundaries, negative balance detection, multiple
      cards, default-card enforcement, override precedence, delete-blocking
      rules)

## Settings page
- [x] View/edit checking accounts (add/edit/remove, starting balance,
      as_of_date)
- [x] View/edit list of credit cards (add/edit/delete, set default)
- [x] View/edit list of `categories` (add new category; starts empty, no
      seeded row; any category still referenced by a transaction/series
      cannot be deleted) — see specs.md § `categories`, "Needs/Wants/Savings
      and categories"

## Category icons
(see specs.md § "Category icons" for full design)
- [x] `categories.icon` column (nullable string) + Alembic migration
- [x] Preset list (~30-40 Bootstrap Icons class names) defined server-side,
      used for validation and for rendering the picker
- [x] `create_category`/new `edit_category` route: validate submitted icon
      against the preset list; support editing name + icon on existing
      categories (not just create/delete)
- [x] Settings page: icon column in the categories list, icon picker grid
      wired into both the create-category row and the new edit flow
- [x] `_categories_context()`/`categories_json` includes `icon`
- [x] Shared custom category-dropdown widget (vanilla JS, built on the
      existing Bootstrap dropdown JS) showing icon+name in the closed
      toggle and open menu, backed by a hidden `category_id` field
      compatible with existing save/read code (`table.js` `saveRow`,
      `FormData.get("category_id")`, `recurring_series.js` modal populate)
- [x] Replace the 4 existing native category `<select>`s (add-transaction
      modal, add-series modal, edit-series modal, inline transaction-row
      edit) with the shared widget
- [x] Categories without an icon render a fallback glyph (e.g. `bi-tag`)
- [x] Unit/manual verification: icon persists through create/edit/backup
      export-import round-trip; widget correctly sets/reads `category_id`
      in all 4 locations

## Recurring Series page
- [x] View/edit/delete/add recurring series
- [x] Credit card selector (shown only when kind=credit, defaults to the
      default card)
- [x] "Save for all occurrences" vs "save for future events after a date"
      split-save mode, with confirmation on the future-events option (see
      specs.md § "Recurring series editing semantics")
- [x] needsWantsSavings selector on add/edit form (default `Need`) — see
      specs.md § "Needs/Wants/Savings and categories"
- [x] category selector on add/edit form (default null, "Category"
      placeholder) — see specs.md § "Needs/Wants/Savings and categories"
- [x] "Per Month" column on the series list, normalizing each cadence to a
      monthly rate — see specs.md § "Per Month column (Recurring Series
      page)"

## Main table view
- [x] Backend endpoint: paginated transaction window by date range
      (merges real `transactions` rows + virtual CC payment-due rows,
      computes running total)
- [x] Table page renders initial window centered on "today"
- [x] Ajax infinite scroll: fetch more future rows on scroll down (up to
      1 year out), fetch more past rows on scroll up
- [x] Negative running-total rows visually highlighted
- [x] Month-end virtual rows: showing closing running total and change vs.
      previous month (see specs.md § "Month-end markers")
- [x] Color coded rows (detached=yellow border, single=blue border,
      recurring=green border, negative amount=light red, positive
      amount=green, negative running total=bright red, month-end=grey
      bordered/bold)

## Row editing
(state-dependent edit/detach/delete/skip semantics: see specs.md §
"Recurring series editing semantics")
- [ ] Edit action opens a modal (see "Transaction edit modals" below)
      instead of an in-place inline edit row; state-dependent which modal
      opens (series -> Edit Occurrence modal, which causes detach as soon
      as any field is edited and saved — cancelling/dismissing discards
      changes and the transaction stays attached; single/detached -> Edit
      Transaction modal with the same save/cancel semantics)
- [x] Delete/Skip row button for single transactions: state dependent + label
      ("Skip" action for series item, which skips the current iteration;
      "Delete" for single transactions, which deletes the single transaction)
- [x] "Un-skip" action for recurring rows
- [x] Add one-off transaction (modal/form), with credit card selector when
      kind=credit
- [x] needsWantsSavings + category fields on the row-edit modals and the
      add-one-off-transaction form (default `Need` / null with "Category"
      placeholder) — see specs.md § "Needs/Wants/Savings and categories"

## Transaction edit modals
(replaces prior in-place inline row editing; see specs.md §
"Recurring series editing semantics" for full design)
- [ ] Remove `buildEditRow`/in-place inline edit-row rendering and its
      dedicated inline error-row handling in `table.js`
- [ ] Edit Transaction modal (`index.html`): for plain one-off/detached
      rows — same field set/layout as the existing Add Transaction modal
      (name, date, Kind toggle + single amount field, credit card
      selector shown only for Kind=Credit, Needs/Wants/Savings toggle,
      category dropdown, notes), submits PATCH `/transactions/<id>`
- [ ] Edit Occurrence modal (`index.html`): for attached series
      occurrences — same fields as above, plus a persistent notice that
      saving will detach this occurrence from its series; submits the
      same PATCH endpoint (existing unconditional detach-on-edit backend
      behavior in `app/transactions.py` `update()` is unchanged)
- [ ] "Edit" button click handler picks which modal to open based on
      `row.occurrence_status`, populating fields from the already-loaded
      in-memory row data (`rowDataById`) rather than an extra fetch
- [ ] Port client-side validation from `Validation.validateTransactionEdit`
      into the new modal submit handlers
- [ ] Both new modals use the shared custom category-dropdown widget (see
      "Category icons") rather than a plain `<select>`
- [ ] Manual verification: editing a plain one-off, editing a detached
      row, and editing an attached occurrence (confirm detach + series
      template itself unaffected) all save correctly and match prior
      inline-edit behavior; Skip/Un-skip/Delete buttons unaffected

## Statistics page
- [ ] New nav entry + route, alongside Table / Recurring Series / Settings
- [ ] Backend calculation: for each of 3 months / 6 months / 1 year
      (`[today, today+N]`), find the min and max cash running total and the
      date each occurs on, reusing the existing running-total calculator —
      see specs.md § "Statistics page"
- [ ] Page template: single table, one row per window, columns for
      min (value + date) and max (value + date)
- [ ] Unit tests: min/max correctness per window, tie-breaking (earliest
      date wins), window boundaries

## Backup / import-export
(see specs.md § "Backup / import-export" for full design)
- [x] Export endpoint: GET, streams full JSON snapshot (`checking_accounts`,
      `credit_cards`, `credit_due_overrides`, `recurring_series`,
      non-`attached` `transactions`, top-level `schema_version`) as a
      timestamped file download
- [x] Import endpoint: POST with file upload, validates `schema_version`
      against current Alembic head, rejects on mismatch
- [x] Import: client-side pre-upload validation with a pass/fail indicator
- [x] Import: single-transaction full replace (delete existing rows in
      FK-safe order, insert backup rows), rollback whole operation on any
      failure
- [x] Import: re-run recurring-occurrence generator per imported series to
      regenerate `attached` transaction rows over the standard window
- [x] Settings page: "Download backup" button + "Restore from backup" file
      upload control, gated behind an explicit confirmation modal
- [x] Unit tests: export produces valid/complete snapshot; import round-trip
      (export → wipe → import → data matches); schema_version mismatch
      rejected; `skipped` occurrences survive round-trip; import failure
      leaves DB unchanged (rollback)
- [x] Extend export/import to include `categories`, and the
      `needs_wants_savings`/`category_id` fields on `recurring_series` and
      `transactions` — see specs.md § "Backup / import-export"

## Polish / validation
- [x] Use bootstrap-specific components to clean up the UI (eg. radio
      toggle buttons vs radio buttons)
- [x] Icons for buttons (edit, save, cancel, settings (gear icon), recurring
      series (repeat icon), logout, etc.)
- [x] Form validation (dates, numeric amounts, required fields)
- [x] Enforce "cash XOR credit" at the schema layer (`transactions.kind` +
      single `amount` column, same shape as `recurring_series`)
- [x] Basic error handling/flash messages

## Testing & local run
- [x] `docker-compose up` brings up app + DB cleanly from scratch
- [x] Seed script for local dev (sample accounts/transactions)
- [x] README instructions verified end-to-end on a clean machine/checkout
