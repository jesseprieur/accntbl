# Implementation Plan

Checkboxes track progress across Claude sessions. See specs.md for full
design rationale before implementing any item below. Organized as a build
order for the app's current target architecture (see specs.md §
"Application structure") — not a historical log of how the app actually
got here. Items already true of the running app are checked; structural
items the codebase hasn't caught up to yet (blueprint split, shared
services, NOT-NULL categories, mixin) are unchecked even though the
feature they support is live, so they stay visible as real follow-up work.

## Project scaffolding
- [x] Initialize repo structure (`app/`, `migrations/`, `docker/`, etc.)
- [x] `docker-compose.yml` with a single `web` (Flask) service; SQLite file
      persisted via a bind mount to `./data` on the host — see specs.md §
      "Tech stack"
- [x] Flask app factory + config (dev/test/prod via env vars)
- [x] SQLAlchemy setup + Alembic init — see specs.md § "Tech stack" for the
      `render_as_batch` configuration gotcha
- [x] `.env.example` with Flask secret key and app config
- [ ] `app/routes/` package with one blueprint per resource
      (`transactions`, `recurring_series`, `checking_accounts`,
      `credit_cards`, `categories`, `backup`, `statistics`, `auth`, `main`)
      — see specs.md § "Application structure". Currently `transactions.py`
      and `settings.py` each hold multiple unrelated resources' CRUD and
      need to be split.
- [ ] `app/services/dates.py`: shared month/interval arithmetic
      (`add_months`, `month_bounds`, `rolling_months`), consumed by
      `recurring.py`, `running_total.py`, and `statistics.py` instead of
      each defining its own `_add_months`/`_month_bounds`.
- [ ] `app/services/formatting.py`: shared money/percent formatting,
      consumed by every route/service that serializes a dollar amount
      instead of each defining its own.
- [ ] Shared `formatCurrency` JS helper, imported by every static JS file
      that renders a dollar amount instead of each reimplementing
      `toFixed(2)`.

## Data model
- [x] `users` model + seed script/CLI command to create the single user
- [x] `checking_accounts` model
- [x] `credit_cards` model (multiple rows, `is_default` bool)
- [x] `credit_due_overrides` model (`credit_card_id`, `due_date`, `amount`,
      `notes`, unique on card+due_date) — intentional stopgap, see specs.md
      § "Credit card payment logic"
- [x] `categories` model with `icon`
- [ ] Seed a permanent, non-deletable `Uncategorized` category row on
      migration; make `category_id` NOT NULL on both `transactions` and
      `recurring_series`, defaulting to it — see specs.md § `categories`.
      Currently `category_id` is nullable (retrofitted after transactions
      already existed) and every consumer has to handle `NULL`.
- [ ] `BudgetClassificationMixin` (`needs_wants_savings` + `category_id`)
      applied to both `Transaction` and `RecurringSeries` — see specs.md §
      "Budget classification". Currently declared independently on each
      model.
- [x] `recurring_series` model (with `credit_card_id`, `amount_logic`)
- [x] `transactions` model (with `recurring_series_id`, `occurrence_status`
      enum: `attached` | `detached` | `skipped`, `credit_card_id`)
- [x] App-level enforcement that exactly one `credit_cards` row is
      `is_default` at all times (on create/edit/delete)
- [x] Block deleting a credit card that's still referenced by any
      transaction/series, or that is the current default; block deleting
      the last remaining card entirely
- [x] Alembic migrations for all of the above

## Auth
- [x] Login page (username/password)
- [x] Session-based auth, `@login_required` on all app routes
- [x] Logout

## Core domain services
- [x] Recurring occurrence generator (given a `recurring_series`, produce
      concrete dates within a date range, honoring cadence_type/custom
      interval/start/end date), built on `services/dates.py`
- [x] Credit card statement period calculator, keyed by `credit_card_id`,
      computed independently per card
- [x] Credit card payment-due amount calculator (sum, override precedence,
      starting-balance seeding) — see specs.md § "Credit card payment
      logic"
- [x] Running total calculator (baseline + ascending walk through
      transactions, `occurrence_status != skipped`, plus generated CC
      payments)
- [x] Basic/Advanced amount-logic toggle on recurring series forms —
      conditional date-based rules and escalating (absolute/percentage)
      rules — see specs.md § "Advanced amount logic"
- [x] Unit tests for all of the above

## Settings pages (accounts / credit cards / categories)
- [x] View/edit checking accounts (add/edit/remove, starting balance,
      as_of_date)
- [x] View/edit list of credit cards (add/edit/delete, set default)
- [x] View/edit list of categories (add/edit, icon picker; delete blocked
      while referenced, `Uncategorized` never deletable) — see specs.md §
      `categories`, "Category icons"
- [x] Shared custom category-dropdown widget (icon+name), used everywhere
      a category is picked, backed by a hidden `category_id` field

## Recurring Series page
- [x] View/edit/delete/add recurring series
- [x] Credit card selector (shown only when kind=credit, defaults to the
      default card)
- [x] "Save for all occurrences" vs "save for future events after a date"
      split-save mode, with confirmation on the future-events option
- [x] Budget classification (needs_wants_savings + category) on add/edit
      form — see specs.md § "Budget classification"
- [x] "Per Month" column on the series list, normalizing each cadence to a
      monthly rate — see specs.md § "Per Month column"

## Main table view
- [x] Backend endpoint: paginated transaction window by date range (merges
      real `transactions` rows + virtual CC payment-due rows, computes
      running total)
- [x] Table page renders initial window and scrolls to "today"
- [x] Ajax infinite scroll (future up to 1 year, past history)
- [x] Negative running-total values visually highlighted
- [x] Month-end virtual rows (closing running total + change vs. previous
      month) — see specs.md § "Month-end markers"
- [x] Color coded rows (detached/single/recurring border colors, positive
      /negative amount colors, negative running total, month-end)

## Row editing
(state-dependent edit/detach/delete/skip semantics: see specs.md §
"Recurring series editing semantics")
- [x] Edit action opens a modal (Edit Occurrence for an attached row,
      causing detach on save; Edit Transaction for a one-off/detached row)
      instead of in-place inline editing
- [x] Delete/Skip row button, state-dependent label and behavior
- [x] "Un-skip" action for skipped rows
- [x] Add one-off transaction (modal/form), with credit card selector for
      kind=credit and budget classification fields
- [x] Both edit modals and the add-transaction form use the shared
      category-dropdown widget

## Statistics page
(own blueprint + service module — see specs.md § "Application structure")
- [x] Nav entry + route, alongside Table / Recurring Series / Settings
- [ ] Move statistics routes/serialization out of `main.py` into their own
      `statistics` blueprint, per "Application structure" — currently
      grafted onto `main_bp` despite having its own service/template/JS.
- [x] Running-total extremes table (3/6/12-month windows, min/max + date,
      tie-break to earliest date)
- [x] Needs/Wants/Savings/Leftover breakdown (month dropdown + Average,
      zero-Income handling) — see specs.md § "Statistics page"
- [x] Spend-by-category breakdown (same month dropdown, positive amounts
      excluded, "None"/zero-spend handling — will become "every category
      always has a value" once categories are NOT NULL)
- [x] Unit tests for all three sections

## Backup / import-export
(see specs.md § "Backup / import-export")
- [x] Export endpoint: full JSON snapshot + `schema_version`
- [x] Import endpoint: schema-version validation, client-side pre-check,
      single-transaction full replace with rollback on failure
- [x] Re-run recurring-occurrence generator per imported series on import
- [x] Settings page: download/restore controls behind a confirmation modal
- [x] Unit tests: export/import round-trip, schema mismatch rejection,
      rollback on failure

## Polish / validation
- [x] Bootstrap components (radio toggle buttons, etc.) over raw HTML
- [x] Icons for buttons (edit, save, cancel, settings, recurring, logout)
- [x] Form validation (dates, numeric amounts, required fields)
- [x] Enforce "cash XOR credit" at the schema layer
- [x] Basic error handling/flash messages

## Testing & local run
- [x] `docker-compose up` brings up the app cleanly from scratch
- [x] Seed script for local dev (sample accounts/transactions)
- [x] README instructions verified end-to-end on a clean machine/checkout
