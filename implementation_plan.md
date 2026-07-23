# Implementation Plan

Checkboxes track progress across Claude sessions. See specs.md for full
design rationale before implementing any item below.

## 0. Project scaffolding
- [x] Initialize repo structure (`app/`, `migrations/`, `docker/`, etc.)
- [x] `docker-compose.yml` with `web` (Flask) + `db` (MySQL) services
- [x] Flask app factory + config (dev/test/prod via env vars)
- [x] SQLAlchemy setup + Alembic init
- [x] `.env.example` with DB creds, Flask secret key

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
- [x] Credit card payment-due amount calculator (sum `credit_amount`
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

## 5. Main table view
- [x] Backend endpoint: paginated transaction window by date range
      (merges real `transactions` rows + virtual CC payment-due rows,
      computes running total)
- [x] Table page renders initial window centered on "today"
- [x] Ajax infinite scroll: fetch more future rows on scroll down (up to
      1 year out), fetch more past rows on scroll up
- [x] Negative running-total rows visually highlighted

## 6. Row editing
- [ ] Fix edit row button: state-dependent behavior — `attached` occurrence
      → clicking edit opens the edit recurring series form (pre-filled),
      saving updates the series and propagates to all `attached` occurrences
      (there's currently no UI path to edit a series other than this);
      `detached` occurrence or plain one-off → inline edit (name,
      cash_amount, credit_amount, date, notes) via Ajax PATCH, affecting only
      that row (unchanged from today)
- [ ] Fix delete/detach row button: state-dependent behavior + label —
      `attached` occurrence → "Detach" button, sets `occurrence_status =
      detached` on the same row (no hard delete, no new row created);
      `detached` occurrence or plain one-off → "Delete" button, hard-deletes
      the row (currently the same "Delete" button/action handles both cases
      and never actually hard-deletes an already-detached row)
- [x] "Skip this occurrence" action for recurring rows
      (`occurrence_status = skipped`)
- [x] "Un-skip" action for recurring rows (`occurrence_status = skipped` →
      `attached`; no "un-detach" equivalent yet)
- [x] Add one-off transaction (modal/form)
- [x] Add recurring series (modal/form: name, kind, amount, cadence, start
      date, optional end date)
- [x] Edit recurring series (propagates to `occurrence_status = attached`
      occurrences only)
- [ ] Delete recurring series: "Delete recurring series" button at top of
      main table page (separate from per-row delete) opens a modal —
      dropdown of existing series, Delete button, confirmation prompt, then
      deletes the series row + hard-deletes its `attached`/`skipped`
      occurrences, nulling `recurring_series_id` on any `detached` ones

## 7. Polish / validation
- [ ] Form validation (dates, numeric amounts, required fields)
- [ ] Enforce "cash_amount XOR credit_amount" at the app layer
- [ ] Basic error handling/flash messages

## 8. Testing & local run
- [ ] `docker-compose up` brings up app + DB cleanly from scratch
- [ ] Seed script for local dev (sample accounts/transactions)
- [ ] README instructions verified end-to-end on a clean machine/checkout

## Later (not in scope yet — do not build until asked)
- [ ] Deployment to AWS Lambda + S3 or GCP Cloud Run + GCS
- [ ] Multiple physical credit cards
- [ ] Savings/investment account tracking + transfers into checking
