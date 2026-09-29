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

## Application structure

The app is organized by resource, not as one growing file per layer. Each
resource gets its own blueprint; cross-cutting math lives in shared service
modules so no calculation is implemented twice.

- **Routes** (`app/routes/`): one blueprint per resource —
  `transactions`, `recurring_series`, `checking_accounts`, `credit_cards`
  (also owns `credit_due_overrides`, since that's a credit-card concern),
  `categories`, `backup`, `auth`. Three blueprints are page shells only,
  rendering a template and delegating all data-fetching to the resource
  blueprints/services: `main` (the main table and Recurring Series pages),
  `settings` (the Settings page), and `statistics` (the Statistics page,
  which also owns its own data route). No blueprint owns more than one
  resource's CRUD.
- **Services** (`app/services/`):
  - `dates.py` — the one implementation of month/interval arithmetic
    (`add_months`, `month_bounds`, `rolling_months`). Every feature that
    needs calendar math (recurring occurrence generation, running-total
    windows, statistics breakdowns) imports from here instead of
    reimplementing it.
  - `formatting.py` — the one implementation of money/percentage
    formatting for server-rendered and JSON responses. Every route/service
    that serializes a dollar amount or a `%` uses this instead of
    reimplementing `"${:,.2f}".format(...)` inline.
  - `parsing.py` — the one implementation of request-payload parsing and
    field resolution (dates, decimals, enums, `credit_card_id`/`category_id`
    defaulting) shared by the `transactions` and `recurring_series`
    blueprints, which otherwise validate near-identical fields.
  - `recurring.py`, `running_total.py`, `credit_card.py`, `statistics.py`,
    `backup.py` — one feature's business logic each, built on top of
    `dates.py`/`formatting.py`/`parsing.py`, never duplicating them.
  - `balance_adjustment.py` — the one implementation of "compute today's
    computed balance, diff it against a user-entered actual balance, write
    the adjustment transaction, and snapshot the before running-total
    extremes," shared by the `checking_accounts` and `credit_cards`
    blueprints (see "Balance adjustments" below) instead of each
    reimplementing it.
- **Models** (`app/models.py`): shared column shapes are defined once via a
  mixin (see "Budget classification" below) rather than copy-pasted onto
  each model that needs them.
- **Frontend** (`app/static/js/`): `currency.js`'s `Currency.format` is the
  one money-formatting implementation, used by every JS file that renders
  a dollar amount instead of each reimplementing `Number(value).toFixed(2)`.

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
- as_of_date (date the starting_balance was true — treated as "today"
  baseline for forward projection; see Open Questions)

### `credit_cards`
Multiple physical cards supported. Exactly one row must have
`is_default = true` at all times, enforced at the app layer (not a DB
constraint, since SQLite partial-unique-index-on-boolean is awkward via
Alembic batch mode).
- id
- name (e.g. "Default Credit Card", "Amex Business")
- is_default (bool)
- statement_close_day (int, day of month statement closes)
- payment_due_offset_days (int, days after close that payment is due)
- starting_balance (decimal, required at creation, may be negative or
  positive, immutable afterward — seeds the amount already owed on this card
  before the app starts tracking Credit +/- transactions on it; see "Credit
  card payment logic" below for how it's applied)
- starting_balance_due_date (date, set once at creation, never
  recalculated or exposed for editing — see "Credit card payment logic")

Deleting a card is blocked if any `transactions` or `recurring_series` still
reference it (must reassign those first) or if it is the current default
(must promote another card to default first). If only one card exists, it
cannot be deleted at all.

### `categories`
User-managed labels for transactions/series, used together with the fixed
`needs_wants_savings` classification (see "Budget classification" below).
Managed on the Settings page.
- id
- name (unique)
- icon (nullable, string — a Bootstrap Icons class name, e.g. `bi-cart`; see
  "Category icons" below)

The table is **seeded with two permanent rows, `Uncategorized` and `Balance
Adjustment`**, by the base migration, and neither can be deleted (they're
fallback/system rows, not regular user categories). `Balance Adjustment` is
applied automatically to every adjustment transaction written by the
"Balance adjustments" flow (see below) — it's not user-assignable from the
normal category picker on the transaction/series forms, since it would be
misleading on anything but an actual balance-reconciliation row. Every other
transaction/series `category_id` is a required FK — there is no `NULL`
category state to special-case anywhere in the codebase (reporting, deletion
checks, forms). Deleting any other category in use is blocked (must reassign
referencing transactions/series to another category first, `Uncategorized`
included), mirroring the `credit_cards` deletion-blocking pattern.

### Category icons

Each category may have an icon, shown everywhere the category is displayed
or chosen, so categories are recognizable at a glance instead of by name
text alone. Bootstrap Icons is already loaded app-wide, so no new
dependency is introduced — `Category.icon` stores a Bootstrap Icons class
name, rendered as `<i class="bi {icon}">`.

- The Settings page offers a curated grid of ~30-40 preset Bootstrap Icons
  classes (shopping, home, transport, health, food, entertainment,
  utilities, travel, kids, pets, gifts, savings, etc.) rather than free
  text, validated server-side against the same preset list on create/edit.
- Every category picker in the app (transaction form, series form, category
  management) is a shared custom dropdown component (native `<select>`
  cannot render icon glyphs) backed by a single reusable widget, not a
  one-off per form.
- A category with no icon renders a neutral fallback glyph (`bi-tag`).

### Budget classification

Every transaction and recurring series carries two independent,
orthogonal classification attributes:

- **`needs_wants_savings`**: a fixed 3-value enum (`need` | `want` |
  `savings`), not nullable, defaulting to `need`. Structural to the
  feature (budgeting rule-of-thumb breakdown) — not user-extensible, unlike
  `categories`.
- **`category_id`**: a required FK to `categories` (defaulting to the
  seeded `Uncategorized` row — see `categories` above).

Both are for classification/reporting only — they never affect
running-total math, credit card payment logic, or occurrence generation.

Because `Transaction` and `RecurringSeries` both need exactly this pair of
columns, they're defined once as a shared SQLAlchemy mixin
(`BudgetClassificationMixin` in `app/models.py`) and applied to both models,
rather than declared twice. This is a code-sharing device only — each row's
classification is still independent (a series and its generated occurrences
can carry different values after a detach/edit; see "Recurring series
editing semantics").

Editing either attribute follows the same detach-on-save rule as any other
field on an attached series occurrence — it is not special-cased.

### `recurring_series`
Template for generating repeated transactions.
- id
- name
- kind (`cash` | `credit`) — determines which column the generated
  occurrences populate
- credit_card_id (nullable FK to `credit_cards` — required when kind=credit,
  null when kind=cash; defaults to the current default card at creation
  time, user may pick a different card in the form)
- amount (decimal, signed: positive = inflow, negative = outflow)
- cadence_type (`weekly` | `biweekly` | `monthly` | `semi_monthly` |
  `quarterly` | `yearly` | `custom`)
- custom_interval_value (int, nullable — used when cadence_type = custom)
- custom_interval_unit (`days` | `weeks` | `months`, nullable)
- start_date
- end_date (nullable — no end means repeats through the 1-year window)
- notes (optional)
- amount_logic (nullable JSON — optional conditional/escalating override of
  plain `amount` per occurrence; see "Advanced amount logic" below)
- `needs_wants_savings` / `category_id` — via `BudgetClassificationMixin`
  (see "Budget classification"); inherited by every occurrence generated
  from this series unless the occurrence is later detached and re-edited.

### `transactions`
Concrete line items shown in the table. Both one-off and materialized
recurring occurrences live here.
- id
- name
- kind (`cash` | `credit` — `cash` affects running total directly; `credit`
  logs spend against a specific credit card and does NOT affect running
  total directly, only via that card's auto-generated payment-due row)
- credit_card_id (nullable FK to `credit_cards` — required when kind=credit,
  null when kind=cash; defaults to the current default card, user may pick
  a different card when adding/editing the transaction; if generated from a
  series, inherited from `recurring_series.credit_card_id` unless
  overridden after detach)
- amount (decimal, signed: positive = inflow, negative = outflow)
- date
- notes (optional)
- recurring_series_id (nullable — set if generated from a series)
- `needs_wants_savings` / `category_id` — via `BudgetClassificationMixin`
  (see "Budget classification").
- occurrence_status (`attached` | `detached` | `skipped`, only meaningful
  when `recurring_series_id` is set — default `attached`):
  - `attached`: still managed by the series; series edits regenerate/update
    this row normally.
  - `detached`: user edited or deleted this single occurrence; it is fully
    independent and never touched by future series edits again.
  - `skipped`: user chose "skip this occurrence"; row is hidden from the
    table but preserved for history/audit, series otherwise continues
    normally. Un-skipping sets this back to `attached`.

### `balance_snapshots`
A point-in-time record written automatically whenever a balance adjustment
is made (see "Balance adjustments" below), so the Statistics page can show a
history of what the forward projection looked like right before each
correction. Only the "before" state is stored — the "after" state is always
recoverable either from the live Running-Total Extremes table (if this is
the most recent snapshot) or from the next snapshot's "before" values (if a
later adjustment has since been made), so there's no pair to keep in sync.
- id
- created_at (timestamp)
- account_type (`checking` | `credit_card`)
- credit_card_id (nullable FK to `credit_cards` — set when
  `account_type = credit_card`, null for `checking`)
- window_start_date (= "today" at the moment of the adjustment)
- window_end_date (= `window_start_date` + 12 months)
- min_amount / min_date, max_amount / max_date (the 12-month window's
  running-total extremes as of immediately *before* the adjustment
  transaction was written)

## Advanced amount logic

`recurring_series.amount_logic` lets a series' per-occurrence amount deviate
from its plain `amount`, evaluated at each occurrence date by
`resolve_amount()`. Editable on the add/edit recurring series forms via a
Basic/Advanced mode toggle above the Amount field (Basic just shows the
plain Amount field; Advanced keeps Amount visible as the default/"else"
amount and reveals the rest of the amount-logic controls below it). When
unset, the series behaves exactly as if the column didn't exist. Two modes
(not combined):

- **Conditional**: an ordered list of date-threshold rules (`if transaction
  date >= month/day[/year] then amount = x`, `elseif ... then amount = y`,
  else the plain Amount field). Rules are checked top-to-bottom, first match
  wins.
- **Escalating**: increases or decreases the amount on each subsequent
  occurrence, by either an absolute amount (linear) or a percentage
  (compounding), applied to `abs(amount)` and floored at zero, then
  reapplying the original sign (an outflow stays an outflow as it shrinks
  toward zero, never flips to an inflow).

Applies at every occurrence-materialization site (series create/update,
backup import regeneration) — an occurrence's stored `amount` is always the
resolved value for its date, not a formula.

## Credit card payment logic

A credit card payment-due row is NOT a line item you create manually each
cycle. Instead, this runs independently **per card**:

1. Statement periods are defined by each card's own `statement_close_day`,
   recurring monthly.
2. `amount` is negative for money spent on the card, positive for refunds.
   For each closed statement period, sum `amount` on all kind=credit
   transactions dated within that period **and belonging to that card**
   (`credit_card_id`). "Closed" describes the period's own start/close
   boundary, not a real-time cutoff against today — the table is a 1-year
   *forward* forecast, so future statement periods still produce projected
   due rows from already-scheduled recurring credit transactions.
3. That sum is the *computed estimate* for that card/period's payment-due
   row, dated `statement_close_day + payment_due_offset_days`, added
   directly (not subtracted) to the running total.
4. Recalculated on the fly at render/query time (not persisted) — credit
   transactions remain editable indefinitely, and personal-scale data
   volume makes recomputation cheap.
5. **Editable override:** real-world statements often include fees,
   interest, or timing quirks the transaction table doesn't capture, so the
   user can overwrite the computed estimate for a given (card, due date)
   with a manual value, stored in `credit_due_overrides`:
   - id
   - credit_card_id (FK)
   - due_date (date — matches the computed due date for that period)
   - amount (decimal — the corrected total due, replaces the computed sum)
   - notes (optional)
   - unique on (`credit_card_id`, `due_date`)

   When an override exists, the payment-due row uses it instead of the
   computed sum and is marked "overridden" (vs. "estimated") in the UI. The
   underlying Credit +/- transactions are unaffected; only the aggregated
   due-row amount is replaced. Deleting the override row reverts to the
   computed estimate.

   **This table is a deliberate, temporary stopgap**, not a permanent core
   mechanic: it exists because entering every one of the 30-40 small
   monthly card transactions individually isn't worth it today, so the
   override lets the due amount be corrected by hand instead. Once a
   transaction-import feature exists (importing a card's real transactions
   directly), `credit_due_overrides` and its UI should be removed in favor
   of the computed sum always being accurate. Not scheduled — no import
   feature is planned yet.
6. **Starting balance seeding:** at card creation, `starting_balance_due_date`
   is computed once (and stored, immutably) as the due date of the most
   recently *closed* statement period as of "now." That due date's computed
   sum has `starting_balance` added to it. This only ever affects that one
   due date and is overridden like any other computed estimate.
7. The generated payment-due row behaves like a normal cash row in the table
   but is not inline-editable like a normal transaction; it exposes a
   distinct "edit estimate" control that writes to `credit_due_overrides`.

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

## Balance adjustments

The projected checking balance and each credit card's projected balance can
drift from the real-world numbers over time (unrecorded cash spend, bank
fees, etc.). Rather than editing the immutable `checking_accounts.as_of_date`
/`credit_cards.starting_balance` fields (which would silently discard the
distinction between historical fact and correction), reconciling either
balance is done via an **"Update Balance"** action, available per checking
account and per credit card wherever they're managed (see "Frontend"), and
implemented once in `app/services/balance_adjustment.py`, shared by the
`checking_accounts` and `credit_cards` blueprints:

1. The user enters the real, current balance for that account/card.
2. The app computes that account/card's *computed* balance as of today:
   - **Checking**: the running total's value as of "today" (see "Running
     total calculation") — pooled across all `checking_accounts`, since cash
     transactions aren't tied to a specific account (see "Open questions").
   - **Credit card**: `starting_balance` plus the sum of all `amount` on
     that card's kind=credit transactions dated on or before today
     (excluding `skipped` rows) — the amount currently owed on the card,
     which is a running total similar to checking's but scoped to one card
     and never reduced by payment-due rows (those move money in the
     checking ledger, not this card's own balance).
3. `delta = entered_balance - computed_balance`.
4. Before writing anything, a `balance_snapshots` row is written capturing
   the 12-month Running-Total Extremes window as it stood right before this
   change (see the `balance_snapshots` data model above).
5. A one-off adjustment transaction is created dated today for `delta`:
   kind=cash (no `credit_card_id`) for a checking adjustment, kind=credit
   (with `credit_card_id` set) for a card adjustment. Both are tagged with
   the seeded, permanent `Balance Adjustment` category (see "categories")
   so they're visually distinguishable from real budget activity and
   excluded from the Needs/Wants/Savings and spend-by-category breakdowns
   (see "Statistics page").
6. If `delta` is zero, no snapshot or transaction is written — there's
   nothing to reconcile or record.

The adjustment transaction behaves like any other one-off row afterward
(editable/deletable via the normal Edit Transaction modal) — the "Update
Balance" action is just a convenience for producing the correct one-off
delta instead of the user computing and entering it by hand.

## Month-end markers

A virtual row is inserted at the end of every calendar month (not persisted —
computed at render time like the credit card payment-due row), showing that
month's closing running total and the change versus the previous month's
close.

## Recurring series editing semantics

Editing the series template itself (name, amount, cadence, etc.) happens on
the dedicated **Recurring Series page**, not from the main table. Saving
there offers two modes:
- **Save for all occurrences**: edits the series template directly;
  regenerates/updates all `attached` occurrences as usual.
- **Save for future events (after a date)**: detaches all `attached`
  occurrences on or before the selected date (leaving their current values
  untouched as independent one-offs), then applies the edit to the series
  template so only occurrences after that date reflect the new values.
  Requires an explicit confirmation step (permanently splits the series'
  history).

Editing a table row opens one of two modals (Ajax PATCH under the hood),
chosen by the row's current `occurrence_status`:
- **Edit Occurrence modal** — for an `attached` row. Same field layout as
  "Add transaction" (name/date, Kind toggle + amount, credit card selector
  for Kind=Credit, budget classification, notes), plus a persistent notice
  that saving will detach this occurrence. Saving detaches
  (`occurrence_status = 'detached'`, same row/id) and applies the edit;
  cancelling discards changes and leaves the row `attached`.
- **Edit Transaction modal** — for a `detached` row or a plain one-off. Same
  field layout, no detach notice.
- There is no separate "Detach" button — detaching is a side effect of
  saving via the Edit Occurrence modal.
- Skip / Un-skip / Delete remain row-level buttons on the table.

The delete/skip action on a row is state-dependent, and the button label
reflects which behavior will happen:
- `attached` row: button reads **"Skip"**. Sets `occurrence_status =
  'skipped'` — hidden from the table, series otherwise continues normally.
  "Un-skip" reverses this back to `attached`.
- `detached` row (or a plain one-off): button reads **"Delete"**.
  Hard-deletes the row.

"Delete series" removes the `recurring_series` row and:
- hard-deletes all of its `attached` and `skipped` occurrences.
- leaves `detached` occurrences in place, nulling `recurring_series_id`
  (and `occurrence_status`) so they survive as plain one-off rows.
- requires explicit confirmation (destructive, irreversible).
- is a separate entry point from the per-row table UI, since it's a much
  higher-blast-radius action than acting on a single occurrence.

## Recurring occurrence generation

`app/services/recurring.py::generate_occurrences(series, range_start,
range_end)` produces concrete dates for a `recurring_series` within a range,
clipped to the series' own `start_date`/`end_date`, using the shared month
arithmetic in `app/services/dates.py`. Cadence semantics:

- `weekly`/`biweekly`: fixed 7/14-day interval from `start_date`.
- `monthly`/`quarterly`/`yearly`: same day-of-month as `start_date`, every
  1/3/12 months; day is clamped to the last day of the target month if it
  doesn't exist there (e.g. Jan 31 monthly → Feb 28).
- `semi_monthly`: twice per month, calendar-fixed to the 15th and the last
  day of the month, regardless of `start_date`'s day-of-month.
- `custom`: `custom_interval_value` + `custom_interval_unit` (`days` /
  `weeks` / `months`), same day/month arithmetic as above.

## Auth

Simple single-user login (username/password against `users` table, hashed
password, Flask session-based auth). No self-registration UI needed for v1
— user is seeded directly.

## Frontend

- Server-rendered Bootstrap layout, Ajax (fetch) for inline row edits and
  infinite scroll.
- Settings page manages checking accounts, credit cards, and categories
  (add/edit/delete each, per the delete-blocking rules in their respective
  data model sections).
- A top-level Statistics page (see "Statistics page").
- Table loads an initial window of rows around "today", then fetches more
  via Ajax as the user scrolls (future, up to 1 year out, or past history).
- Row edit = one of two modals (Edit Transaction / Edit Occurrence, chosen
  by the row's state), same field set as the Add Transaction modal, saved
  via Ajax PATCH (see "Recurring series editing semantics").
- Adding a one-off transaction = a small form/modal on the main table page,
  including budget classification; choosing kind=credit reveals the credit
  card selector.
- Credit card payment-due rows show which card they belong to (when more
  than one card exists) and an "edit estimate" affordance for
  `credit_due_overrides`.
- Recurring series management lives on its own **Recurring Series page**,
  separate from the main table, so series-template edits don't get confused
  with editing a single row.
- An "Update Balance" button sits next to each checking account row and each
  credit card row on the Settings page (see "Balance adjustments").

## Statistics page

A top-level page, alongside the main table / Recurring Series / Settings
pages, with its own blueprint and service module (`services/statistics.py`,
built on the shared `services/dates.py`). Four independent sections, all
computed at render time (not persisted — same rationale as the credit-card
payment-due estimate), except Balance Adjustment History, which reads the
persisted `balance_snapshots` table.

**Running-total extremes**: one table, one row per forward-looking window
(**3 months**, **6 months**, **1 year**, each `[today, today + N]`), using
the same cash running total defined in "Running total calculation" (skipped
rows excluded). Each row shows the minimum running total and its date, and
the maximum and its date. Ties go to the earliest date.

**Balance Adjustment History**: a table listing every row in
`balance_snapshots`, most recent first, with columns Account (checking, or
the credit card's name), When (`created_at`), Start Date (`window_start_date`),
End Date (`window_end_date`), Min ($ + date), and Max ($ + date) — the same
min/max columns as the 12-month row of the Running-Total Extremes table
above, plus the window's own start/end dates. Since only the "before" state
is ever stored, comparing consecutive rows for the same account (or a row
against the live Running-Total Extremes table, for the most recent
adjustment) shows the before/after effect of each balance correction — see
"Balance adjustments" and the `balance_snapshots` data model. Empty until
the first balance adjustment is made.

**Needs/Wants/Savings/Leftover breakdown**: a second table, driven by a
month dropdown (current month + next 11, a rolling 12-month-forward window,
plus an "Average" option). Scope: both `kind=cash` and `kind=credit`
transactions dated in the selected month (deliberately including credit
spend here, unlike the running total, so overspending shows up before its
due date), excluding `skipped` occurrences, generated/virtual rows, and any
transaction in the `Balance Adjustment` category (a reconciliation plug, not
real budget activity — see "Balance adjustments").
- `Income` = sum of `amount` where `amount > 0`, regardless of
  `needs_wants_savings`.
- `Needs`/`Wants`/`Savings` = sum of `amount` (outflows) filtered to the
  matching `needs_wants_savings` value, shown as a positive magnitude.
- `Leftover` = `Income - (Needs + Wants + Savings)` — can go negative.
- Each of Needs/Wants/Savings/Leftover's `%` = its value divided by
  `Income` (the stable denominator for the classic budgeting-ratio
  convention); `—` for all rows if `Income` is zero that month.
- "Average": mean dollar value per bucket across the 12 months, with `%`
  computed from those averaged dollars (not averaged `%`s).

**Spend-by-category breakdown**: a third table, driven by the same month
dropdown (selecting a month re-renders both breakdown tables together) —
one row per `categories` row, value and `%` columns.
- Same scope as the NWS/Leftover breakdown, but positive amounts are
  excluded entirely (from both sums and the `%` denominator) — this table
  is spend-only.
- `value` for a category = sum of `amount` (outflows) for that
  `category_id` in the month, as a positive magnitude.
- `%` = value divided by total spend across all categories that month;
  `—` if total spend is zero.
- Every category always renders as a row (even $0), ordered by descending
  value; "Average" works the same way as the other breakdown.

## Per Month column (Recurring Series page)

The Recurring Series list gains a **Per Month** column showing each series'
average monthly cost/income, so cadences with different periods are
comparable at a glance:

- `monthly`: `amount` as-is.
- `weekly`: `amount * 52 / 12`.
- `biweekly`: `amount * 26 / 12`.
- `semi_monthly`: `amount * 2`.
- `quarterly`: `amount / 3`.
- `yearly`: `amount / 12`.
- `custom`: normalized to a monthly rate using `custom_interval_value` /
  `custom_interval_unit` (e.g. `days` → `amount * (30.44 / interval_value)`,
  `weeks` → `amount * (52 / 12) / interval_value`, `months` → `amount /
  interval_value`).

When `amount_logic` is set, this column uses the plain `amount` field (the
base/else amount), not a resolved per-occurrence value — this is a
display-only convenience figure, not used in running-total math.

## Backup / import-export

Motivated by an accidental data loss (named Docker volume deleted by
`docker-compose down -v`); the bind-mount (see "Tech stack") is the primary
fix, but a portable, human-recoverable backup format is still useful for
point-in-time snapshots and recovering from DB corruption.

- Format: single JSON file.
- Export is a full snapshot of everything needed to fully reconstruct app
  state ("Download backup" button on the Settings page, GET, streams
  `application/json` with a timestamped filename). Included tables:
  - `checking_accounts`, `credit_cards` (all fields), `credit_due_overrides`,
    `categories` (all fields).
  - `recurring_series` (all fields) — importing regenerates `attached`
    occurrences via the existing recurring-occurrence generator, so
    individual `attached` transaction rows are NOT exported.
  - `transactions` where `recurring_series_id IS NULL` OR
    `occurrence_status IN ('detached', 'skipped')` — every row that isn't a
    currently-`attached` series occurrence. Balance-adjustment transactions
    are ordinary one-off rows (`recurring_series_id IS NULL`) and are
    included by this same rule, no special-casing needed.
  - `balance_snapshots` (all fields) — historical record, restored as-is.
  - top-level `schema_version` (latest Alembic revision id at export time),
    so import can detect/reject an incompatible schema.
  - `users` is excluded — a restore always keeps the current environment's
    user(s).
- Import is a full restore, not a merge: a "Restore from backup" control on
  the Settings page (file upload → POST), gated behind a confirmation modal.
  Choosing a file triggers a client-side pre-check (valid JSON, matching
  `schema_version`, all expected top-level keys) with a pass/fail indicator
  before the server re-validates authoritatively.
  Server-side steps:
  1. Validate `schema_version` matches current Alembic head; reject
     otherwise (no schema migration on import — out of scope).
  2. Single DB transaction: delete all rows from `balance_snapshots`,
     `transactions`, `recurring_series`, `credit_due_overrides`,
     `credit_cards`, `checking_accounts`, `categories` (FK-safe order), then
     insert the backup's rows in reverse order.
  3. Re-run the recurring-occurrence generator for every imported series
     over the standard window, to regenerate `attached` rows.
  4. On any failure, roll back — the app must never be left with a
     partially-restored DB.
- Not in scope for v1: scheduled/automatic backups, partial/selective
  restore, cross-schema-version migration on import.

## Tech stack

- Backend: Python, Flask
- ORM/migrations: SQLAlchemy + Alembic, `render_as_batch` enabled for
  SQLite-safe migrations. `Flask-Migrate`'s `Migrate()` already defaults
  `render_as_batch=True`/`compare_type=True` into `configure_args`, which
  `migrations/env.py`'s `run_migrations_online()` forwards automatically —
  do not re-pass `render_as_batch=True` explicitly when calling `Migrate()`,
  it raises `TypeError: multiple values for keyword argument`. The schema
  is kept as a single base migration rather than one file per incremental
  change — see "Data model" for what it creates; add new migrations from
  here forward rather than re-consolidating routinely.
- DB: SQLite (single file on a persistent volume)
- Frontend: Bootstrap + vanilla JS/Ajax (no heavy JS framework — keep simple)
- Local/dev: Docker Compose (flask app container, SQLite file bind-mounted
  from `./data` on the host — a named volume was tried first but is deleted
  by `docker-compose down -v`/volume-prune operations; the bind mount
  survives those and is visible/backup-able as a normal file)
- Deployment target: single small container (e.g. Fly.io) with a persistent
  volume for the SQLite file — chosen for low-cost, low-traffic single-user
  hosting without a separate managed database service.

## Open questions / deferred decisions

- Multiple `checking_accounts` with different `as_of_date` values: v1
  assumes all accounts' `as_of_date` are effectively "today" at time of
  entry. If accounts drift out of sync, running-total baseline math may
  need revisiting.
- Currency/timezone: assume single currency (USD) and a single timezone
  (system default) for v1 — no multi-currency/timezone support planned.
- `credit_due_overrides` retirement: see "Credit card payment logic" —
  intentionally kept until a transaction-import feature exists; not
  currently planned/scheduled.
