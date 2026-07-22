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
- [ ] Table page renders initial window centered on "today"
- [ ] Ajax infinite scroll: fetch more future rows on scroll down (up to
      1 year out), fetch more past rows on scroll up
- [ ] Negative running-total rows visually highlighted

## 6. Row editing
- [ ] Inline edit (name, cash_amount, credit_amount, date, notes) via Ajax
      PATCH
- [ ] Delete row (single occurrence → sets `occurrence_status = detached`;
      one-off → hard delete)
- [ ] "Skip this occurrence" action for recurring rows
      (`occurrence_status = skipped`)
- [ ] "Un-skip" action for recurring rows (`occurrence_status = skipped` →
      `attached`; no "un-detach" equivalent yet)
- [ ] Add one-off transaction (modal/form)
- [ ] Add recurring series (modal/form: name, kind, amount, cadence, start
      date, optional end date)
- [ ] Edit recurring series (propagates to `occurrence_status = attached`
      occurrences only)

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
