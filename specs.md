# specs.md — Source of Truth

This file is the persistent design record for this project, meant to give any
fresh Claude session (or human) full context without re-deriving decisions.
It is NOT a task list (see implementation_plan.md) and NOT user docs (see
README.md). Update it whenever a design decision changes.

## Problem

Personal finance forecasting tool. Answers one question: "will my checking
balance ever go negative in the next year, given known/recurring income and
expenses?"

## Core concept

A single scrollable, editable table of transactions ("line items") ordered by
date, spanning past history through 1 year in the future. Each row can be a
one-off or generated from a recurring series. A running total column tracks
projected checking balance over time.

## Data model

### `users`
Single user for now, but modeled as a table (not env vars) so credentials can
change without redeploy.
- id
- username
- password_hash

### `checking_accounts`
Starts with 1 row, but the model supports adding more. Sum of all accounts'
current balances is the baseline for the running total.
- id
- name
- starting_balance (decimal)
- as_of_date (date the starting_balance was true — treated as "today" baseline
  for forward projection; see Open Questions)

### `credit_card_settings`
Single hardcoded/default card (singleton row) for v1. Multiple physical cards
are NOT modeled — if the user gets a second card, they track it manually via
a regular recurring cash expense.
- id (always 1 row for now)
- name (e.g. "Default Credit Card")
- statement_close_day (int, day of month statement closes)
- payment_due_offset_days (int, days after close that payment is due)
- starting_balance (decimal, optional seed for amount currently owed before
  the app starts tracking Credit +/- transactions)

### `recurring_series`
Template for generating repeated transactions.
- id
- name
- kind (`cash` | `credit`) — determines which column the generated
  occurrences populate
- amount (decimal, signed: positive = inflow, negative = outflow)
- cadence_type (`weekly` | `biweekly` | `monthly` | `semi_monthly` |
  `quarterly` | `yearly` | `custom`)
- custom_interval_value (int, nullable — used when cadence_type = custom)
- custom_interval_unit (`days` | `weeks` | `months`, nullable)
- start_date
- end_date (nullable — no end means repeats through the 1-year window)
- notes (optional)

### `transactions`
Concrete line items shown in the table. Both one-off and materialized
recurring occurrences live here.
- id
- name
- kind (`cash` | `credit` — `cash` affects running total directly; `credit`
  logs spend against the default credit card and does NOT affect running
  total directly, only via the auto-generated payment-due row)
- amount (decimal, signed: positive = inflow, negative = outflow)
- date
- notes (optional)
- recurring_series_id (nullable — set if generated from a series)
- occurrence_status (`attached` | `detached` | `skipped`, only meaningful
  when `recurring_series_id` is set — default `attached`):
  - `attached`: still managed by the series; series edits regenerate/update
    this row normally.
  - `detached`: user edited or deleted this single occurrence; it is fully
    independent and never touched by future series edits again.
  - `skipped`: user chose "skip this occurrence"; row is hidden from the
    table but preserved for history/audit, series otherwise continues
    normally. Un-skipping sets this back to `attached` (see below) — there
    is currently no "un-detach" action.

## Credit card payment logic

The credit card is NOT a line item you create manually each cycle. Instead:

1. Statement periods are defined by `statement_close_day`, recurring monthly.
2. `amount` is negative for money spent on the card, positive for
   refunds. For each closed statement period, sum `amount` on all kind=credit
   transactions dated within that period.
3. That sum becomes the `cash_amount` of an auto-generated payment-due
   transaction, dated `statement_close_day + payment_due_offset_days`, added
   directly (not subtracted) to the running total — a net-spend period
   produces a negative sum, which reduces the running total on the due date.
4. This is recalculated on the fly at render/query time (not persisted as a
   stored aggregate) — since credit transactions in a period remain editable
   indefinitely and must auto-recalculate the payment-due amount. Given
   personal-scale data volume, recomputing per request is cheap and avoids
   cache-invalidation complexity.
5. The generated payment-due row behaves like a normal cash row in the table
   (shows up, affects running total) but is not independently editable/
   deletable — editing the underlying Credit +/- transactions is how you
   change it. (Open question: should the user be able to override the due
   date/amount directly? Default to "no" for v1 — revisit if annoying.)

## Running total calculation

1. Baseline = sum of all `checking_accounts.starting_balance`.
2. Walk all transactions where `occurrence_status != 'skipped'` (or
   `recurring_series_id` is null) in ascending date order.
3. Running total += `amount` for each kind=cash row (kind=credit rows never
   affect it directly).
4. Any row where running total < 0 is visually flagged (highlighted) in the
   UI.

Past-dated transactions remain in the table (scrollable above "today") for
historical record-keeping, not just future projection.

## Month-end markers

A virtual row is inserted at the end of every calendar month (not persisted —
computed at render time like the credit card payment-due row), showing that
month's closing running total and the change versus the previous month's
close. Exact visual treatment (grey/bordered, bold, etc.) is tracked as a
Polish-phase item in implementation_plan.md, not fixed here.

## Recurring series editing semantics

Editing the series template itself (name, amount, cadence, etc.) happens on
the dedicated **Recurring Series page** (see Frontend), not from the main
table. Saving there regenerates/updates all `attached` occurrences.

Editing a table row is always an inline edit (Ajax PATCH) with explicit
save/cancel controls — there is no separate "open series form" flow
triggered from a row anymore:
- `attached` row: inline edit; **saving** any field detaches this single
  occurrence (`occurrence_status = 'detached'`, same row/id) and applies
  the edit to it — the row becomes an independent one-off from then on,
  no longer touched by future series edits. **Cancelling** discards the
  changes and leaves the row `attached`.
- `detached` row (or a plain one-off): inline edit with save/cancel;
  saving affects only that transaction, cancelling discards the changes.
- There is no separate "Detach" button — detaching is a side effect of
  saving an edit to an `attached` row, not its own action.

The delete/skip action on a row is state-dependent, and the button label
reflects which behavior will happen:
- `attached` row: button reads **"Skip"**. Sets `occurrence_status =
  'skipped'` — hidden from the table, series otherwise continues
  normally. Does not touch row content, so there's nothing for a later
  series edit to clobber. "Un-skip" reverses this back to `attached`.
- `detached` row (or a plain one-off): button reads **"Delete"**.
  Hard-deletes the row.
- (Rejected: hiding the original and spawning a new one-off row in its
  place — the hidden original would still count toward the running total,
  double-counting the event. Reusing the same row avoids this.)

"Delete series" removes the `recurring_series` row and:
- hard-deletes all of its `attached` and `skipped` occurrences (they only
  exist because the series generated them, and lose their audit purpose
  once the series is gone).
- leaves `detached` occurrences in place, nulling `recurring_series_id`
  (and `occurrence_status`) so they survive as plain one-off rows.
- requires explicit confirmation before calling the delete endpoint
  (destructive, irreversible).
- is deliberately a separate entry point from the per-row table UI, since
  it's a much higher-blast-radius action than acting on a single occurrence
  — see Frontend section.

## Recurring occurrence generation

`app/services/recurring.py::generate_occurrences(series, range_start,
range_end)` produces concrete dates for a `recurring_series` within a range,
clipped to the series' own `start_date`/`end_date`. Cadence semantics:

- `weekly`/`biweekly`: fixed 7/14-day interval from `start_date`.
- `monthly`/`quarterly`/`yearly`: same day-of-month as `start_date`, every
  1/3/12 months; day is clamped to the last day of the target month if it
  doesn't exist there (e.g. Jan 31 monthly → Feb 28).
- `semi_monthly`: twice per month, calendar-fixed to the 15th and the last
  day of the month (regardless of `start_date`'s day-of-month); `start_date`/
  `end_date` still clip which occurrences are included.
- `custom`: `custom_interval_value` + `custom_interval_unit` (`days` /
  `weeks` / `months`), same day/month arithmetic as above.

## Auth

Simple single-user login (username/password against `users` table, hashed
password, Flask session-based auth). No self-registration UI needed for v1
— user is seeded directly.

## Frontend

- Server-rendered Bootstrap layout, Ajax (fetch) for inline row edits and
  infinite scroll.
- Table loads an initial window of rows around "today", then fetches more via
  Ajax as the user scrolls down (future, up to 1 year out) or up (past
  history).
- Row edit = inline editable fields (name, cash/credit amount, date, notes)
  with explicit save/cancel, saved via Ajax PATCH (see "Recurring series
  editing semantics" for the attached-row detach-on-save behavior).
- Adding a one-off transaction = a small form/modal on the main table page.
- Recurring series management (add/edit/delete) lives on its own
  **Recurring Series page**, separate from the main table — deliberately
  NOT modals on the main table, to keep series-template edits (which
  affect every attached occurrence) from being confused with editing a
  single row. Deleting a series there requires explicit confirmation
  before the delete request is sent (destructive, irreversible — see
  "Recurring series editing semantics" for what happens to its
  occurrences).

## Tech stack

- Backend: Python, Flask
- ORM/migrations: SQLAlchemy + Alembic
- DB: SQLite (single file on a persistent volume)
- Frontend: Bootstrap + vanilla JS/Ajax (no heavy JS framework — keep simple)
- Local/dev: Docker Compose (flask app container, SQLite file in a named volume)
- Deployment target: single small container (e.g. Fly.io) with a persistent
  volume for the SQLite file — chosen for low-cost, low-traffic single-user
  hosting without a separate managed database service.

## Open questions / deferred decisions

- Multiple `checking_accounts` with different `as_of_date` values: v1 assumes
  all accounts' `as_of_date` are effectively "today" at time of entry. If
  accounts drift out of sync, running-total baseline math may need revisiting.
- Whether to allow direct override of an auto-generated credit card
  payment-due row (currently: no, derive only from Credit +/- transactions).
- Currency/timezone: assume single currency (USD) and a single timezone
  (system default) for v1 — no multi-currency/timezone support planned.
