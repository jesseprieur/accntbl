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
- cash_amount (decimal, nullable/0 — affects running total)
- credit_amount (decimal, nullable/0 — does NOT affect running total; logs
  spend against the default credit card)
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

Note: a transaction row has EITHER a meaningful cash_amount OR credit_amount,
not both (enforced at the app layer, not DB constraint, to keep schema
simple).

## Credit card payment logic

The credit card is NOT a line item you create manually each cycle. Instead:

1. Statement periods are defined by `statement_close_day`, recurring monthly.
2. For each closed statement period, sum all `credit_amount` transactions
   dated within that period.
3. That sum becomes the `cash_amount` of an auto-generated payment-due
   transaction, dated `statement_close_day + payment_due_offset_days`.
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
3. Running total += `cash_amount` for each row (credit_amount never affects
   it).
4. Any row where running total < 0 is visually flagged (highlighted) in the
   UI.

Past-dated transactions remain in the table (scrollable above "today") for
historical record-keeping, not just future projection.

## Recurring series editing semantics

- Editing the series (e.g. changing amount) regenerates/updates all
  occurrences with `occurrence_status = 'attached'`.
- Editing a table row is also state-dependent:
  - Row is `attached`: clicking edit opens the **edit recurring series**
    form (pre-filled for that row's series), not an inline single-row edit —
    there's currently no other UI path to edit a series, and inline-editing
    an attached row's fields directly would be misleading since a future
    series edit could overwrite them anyway. Saving that form updates the
    series and regenerates/updates all `attached` occurrences as described
    above.
  - Row is `detached` (or a plain one-off with no `recurring_series_id`):
    clicking edit does a normal inline single-row edit via Ajax PATCH,
    affecting only that transaction. This is unchanged from today.
  - There is still no way to detach-then-edit a single occurrence in one
    step — detach it first (see delete/detach behavior below), then edit it
    as a standalone row.
- The delete action on a recurring occurrence is state-dependent, and the UI
  button label reflects which behavior will happen:
  - Row is `attached`: button reads **"Detach"**. Sets
    `occurrence_status = 'detached'` in place (same row, same id, stays
    visible) — it does NOT hard-delete or create a new row. This exists
    because hard-deleting an `attached` row would just have it regenerated
    by the next series edit; detaching is what actually "removes" it from
    the series going forward while keeping the transaction itself.
  - Row is already `detached` (or has no `recurring_series_id` at all — a
    plain one-off): button reads **"Delete"**. Hard-deletes the row, same as
    any one-off transaction.
  - Rejected alternative: hiding the original occurrence and spawning a new
    one-off row in its place. Rejected because the hidden original would
    still have `occurrence_status = 'detached'` (not `'skipped'`), so it
    would still be included in the running-total walk — double-counting the
    same financial event alongside the new row. Reusing the same row avoids
    this entirely.
- "Skip once" sets `occurrence_status = 'skipped'` on a single occurrence —
  hidden from the table, series otherwise continues normally.
- "Un-skip" sets `occurrence_status` back to `attached` — the row becomes
  visible again and rejoins the series, so future series edits will update
  it. This is safe because skipping never changes a row's content, only its
  visibility, so there's nothing for a series edit to clobber. (Contrast
  with `detached`, which exists specifically to protect a deliberate
  customization from being overwritten — that's why there's no equivalent
  "un-detach" for now.)
- "Delete series" removes the `recurring_series` row entirely and:
  - hard-deletes all of its `attached` and `skipped` occurrences (they only
    exist because the series generated them; skipped rows lose their
    audit-history purpose once the series they belong to is gone).
  - `detached` occurrences are NOT deleted — they're already independent
    one-off transactions by design. Their `recurring_series_id` is set to
    `NULL` (and `occurrence_status` cleared) so they survive as plain
    one-off rows instead of dangling on a deleted FK.
  - This is a destructive, irreversible action — the UI must require an
    explicit confirmation step before calling the delete endpoint.
  - Deliberately kept separate from the per-row table UI (which only ever
    acts on a single occurrence) since deleting a whole series is a much
    higher-blast-radius action — see Frontend section for entry point.

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
- Row edit = inline editable fields (name, cash/credit amount, date, notes),
  saved via Ajax PATCH.
- Adding a recurring item = a small form/modal (name, kind, amount, cadence,
  start date, optional end date).
- Deleting a whole recurring series = a "Delete recurring series" button at
  the top of the main table page (deliberately NOT part of the per-row table
  controls, to keep it from being confused with deleting a single
  occurrence). Opens a modal: dropdown listing all existing
  `recurring_series` (by name), a Delete button, then a confirmation prompt
  before the delete request is actually sent.

## Tech stack

- Backend: Python, Flask
- ORM/migrations: SQLAlchemy + Alembic
- DB: MySQL
- Frontend: Bootstrap + vanilla JS/Ajax (no heavy JS framework — keep simple)
- Local/dev: Docker Compose (flask app container + mysql container)
- Future deployment targets (not designed for yet, just kept in mind so we
  don't paint ourselves into a corner): AWS Lambda + S3, or GCP Cloud Run +
  GCS. No serverless-specific code/abstractions until we actually get there.

## Open questions / deferred decisions

- Multiple `checking_accounts` with different `as_of_date` values: v1 assumes
  all accounts' `as_of_date` are effectively "today" at time of entry. If
  accounts drift out of sync, running-total baseline math may need revisiting.
- Whether to allow direct override of an auto-generated credit card
  payment-due row (currently: no, derive only from Credit +/- transactions).
- Currency/timezone: assume single currency (USD) and a single timezone
  (system default) for v1 — no multi-currency/timezone support planned.
