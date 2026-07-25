# Implementation Plan

Checkboxes track progress across Claude sessions. See specs.md for full
design rationale before implementing any item below.

## 0. Project scaffolding
- [x] Initialize repo structure (`app/`, `migrations/`, `docker/`, etc.)
- [x] `docker-compose.yml` with a single `web` (Flask) service; SQLite file
  persisted in a named volume (no separate DB service/container)
- [x] Flask app factory + config (dev/test/prod via env vars)
- [x] SQLAlchemy setup + Alembic init (`render_as_batch` enabled for
  SQLite-safe migrations)
- [x] `.env.example` with Flask secret key and app config

## 1. Data model
- [x] `users` model + seed script/CLI command to create the single user
- [x] `checking_accounts` model
- [x] `credit_card_settings` model (singleton)
- [x] `recurring_series` model
- [x] `transactions` model (with `recurring_series_id`, `occurrence_status`
      enum: `attached` | `detached` | `skipped`)
- [x] Alembic migration for all tables

## 2. Auth
- [x] Login page (username/password)
- [x] Session-based auth, `@login_required` on all app routes
- [x] Logout

## 3. Core domain logic
- [x] Recurring occurrence generator (given a `recurring_series`, produce
      concrete dates within a date range, honoring cadence_type/custom
      interval/start/end date)
- [x] Credit card statement period calculator (given `statement_close_day`,
      a date range → list of period boundaries)
- [x] Credit card payment-due amount calculator (sum `amount` on kind=credit
      transactions per closed period → generates virtual cash transaction on
      due date)
- [x] Running total calculator (baseline from `checking_accounts` +
      ascending walk through transactions with `occurrence_status != skipped`
      /generated CC payments)
- [x] Unit tests for all of the above (cadence edge cases, custom intervals,
      statement period boundaries, negative balance detection)

## 4. Settings page
- [x] View/edit checking accounts (add/edit/remove, starting balance,
      as_of_date)
- [x] View/edit credit card settings (statement close day, due offset,
      starting balance)

## 5. Recurring Series page
- [ ] View/edit/delete/add recurring series

## 6. Main table view
- [x] Backend endpoint: paginated transaction window by date range
      (merges real `transactions` rows + virtual CC payment-due rows,
      computes running total)
- [x] Table page renders initial window centered on "today"
- [x] Ajax infinite scroll: fetch more future rows on scroll down (up to
      1 year out), fetch more past rows on scroll up
- [x] Negative running-total rows visually highlighted
- [x] Month-end virtual rows: showing closing running
      total and change vs. previous month (see specs.md § "Month-end
      markers")

## 7. Row editing
(state-dependent edit/detach/delete/skip semantics: see specs.md §
"Recurring series editing semantics")
- [ ] Edit row button with save/cancel: state-dependent (series -> in-line
      edit, which causes detach as soon as any field edited and saved. If 
      cancelled, changes are discarded and transaction stays attached; single
      -> in-line edit with save/cancel buttons to keep/discard changes)
- [ ] Delete/Skip row button for single transactions: state dependent + label
      ("Skip" action for series item, which skips the current iteration;
      "Delete" for single transactions, which deletes the single transaction)
- [x] "Un-skip" action for recurring rows
- [x] Add one-off transaction (modal/form)

## 8. Polish / validation
- [ ] Color coded rows
    - [ ] "Detached"/single transactions are not color-coded
    - [ ] Recurring series items have green shaded border
    - [ ] Negative transactions could be light red
    - [ ] Positive transactions could be green
    - [ ] Negative running-total should be bright red
    - [ ] Month end rows should be grey or grey bordered and maybe bold;
- [ ] Use bootstrap-specific components to clean up the UI (eg. radio
      toggle buttons vs radio buttons)
- [ ] Icons for buttons (edit, save, cancel, settings, recurring series,
      logout, etc.)
- [ ] Form validation (dates, numeric amounts, required fields)
- [x] Enforce "cash XOR credit" at the schema layer (`transactions.kind` +
      single `amount` column, same shape as `recurring_series`)
- [ ] Basic error handling/flash messages

## 9. Testing & local run
- [ ] `docker-compose up` brings up app + DB cleanly from scratch
- [ ] Seed script for local dev (sample accounts/transactions)
- [ ] README instructions verified end-to-end on a clean machine/checkout

## Later (not in scope yet — do not build until asked)
- [ ] Deployment to AWS Lambda + S3 or GCP Cloud Run + GCS
- [ ] Multiple physical credit cards
- [ ] Savings/investment account tracking + transfers into checking
