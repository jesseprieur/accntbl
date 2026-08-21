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
User-managed labels for transactions/series, separate from the fixed
`needsWantsSavings` classification below. Managed on the Settings page (add
new categories; no seeded rows to start — the table is empty until the user
adds their own).
- id
- name (unique)
- icon (nullable, string — a Bootstrap Icons class name, e.g. `bi-cart`;
  see "Category icons" below)

Not seeded — `category_id` is nullable and defaults to `NULL` (no category)
for every existing and new transaction/series until the user adds categories
via Settings and assigns one. Deleting a category in use is blocked (must
reassign referencing transactions/series to another category, or to no
category, first), mirroring the `credit_cards` deletion-blocking pattern.
Categories are editable after creation (name and icon), unlike credit cards
there is no default/is-default concept to enforce.

## Category icons

Each category may have an icon, shown everywhere the category is displayed
or chosen, so categories are recognizable at a glance instead of by name
text alone. Bootstrap Icons is already loaded app-wide, so no new
dependency is introduced — `Category.icon` simply stores a Bootstrap Icons
class name (e.g. `bi-cart`), rendered as `<i class="bi {icon}">`.

- **Picker, not free text**: the Settings page offers a curated grid of a
  fixed preset list of ~30-40 Bootstrap Icons classes (shopping, home,
  transport, health, food, entertainment, utilities, travel, kids, pets,
  gifts, savings, etc.) rather than a free-text class-name field, to avoid
  typos/invalid classes and keep the visual language consistent. The preset
  list is validated server-side on create/edit (reject any submitted value
  not in the list) as well as rendered client-side as the picker.
- **Custom dropdown everywhere, not native `<select>`**: native HTML
  `<option>` elements cannot render icon glyphs, so every category picker in
  the app (add-transaction modal, add/edit recurring series modals, inline
  transaction-row edit) is a hand-rolled dropdown widget instead of a plain
  `<select>` — showing the selected category's icon+name in the closed
  toggle and in every row of the open menu. Under the hood each widget still
  maintains a hidden `category_id` field with the same `name`/`data-field`
  the existing save/read code already expects, so transaction/series
  save logic does not change.
- Categories without an icon (e.g. legacy rows created before this feature)
  render a neutral fallback glyph (e.g. `bi-tag`) rather than blank space.

### `recurring_series`
Template for generating repeated transactions.
- id
- name
- kind (`cash` | `credit`) — determines which column the generated
  occurrences populate
- credit_card_id (nullable FK to `credit_cards` — required when kind=credit,
  null when kind=cash; defaults to the current default card at creation time,
  user may pick a different card in the form)
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
- needs_wants_savings (`need` | `want` | `savings`, not nullable, defaults
  to `need`) — classification inherited by every occurrence generated from
  this series unless the occurrence is later detached and re-edited (see
  "Recurring series editing semantics" — same inheritance rules as any other
  series field).
- category_id (nullable FK to `categories`, defaults to `NULL` at creation)
  — same inheritance behavior as `needs_wants_savings`.

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
- needs_wants_savings (`need` | `want` | `savings`, not nullable, defaults
  to `need`) — see "Needs/Wants/Savings and categories" below.
- category_id (nullable FK to `categories`, defaults to `NULL`) — see
  "Needs/Wants/Savings and categories" below.
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

## Advanced amount logic

`recurring_series.amount_logic` lets a series' per-occurrence amount deviate
from its plain `amount`, evaluated at each occurrence date by
`resolve_amount()`. Editable on the add/edit recurring series forms via a
Basic/Advanced mode toggle shown directly above the Amount field (Basic is
the default and just shows the plain Amount field; Advanced keeps Amount
visible — it now doubles as the default/starting/"else" amount — and reveals
the rest of the amount-logic controls below it, replacing the old bottom-of-
form 'Advanced' accordion). When unset (Basic mode, or Advanced with no rules
configured), the series behaves exactly as if the column didn't exist (plain
`amount` every occurrence). Two modes (not combined):

- **Conditional**: an ordered list of date-threshold rules (`if transaction
  date >= month/day[/year] then amount = x`, `elseif ... then amount = y`,
  `else amount = <the Amount field above>`). Rules are checked top-to-bottom,
  first match wins; if none match, falls back to `else_amount` if the
  backend value is set, otherwise the plain `amount`. The form no longer
  collects a separate "else amount" input — it always submits `else_amount:
  null` and relies on the Amount field as the effective else value — but the
  backend/data model still accepts an explicit `else_amount` for backward
  compatibility with existing rows.
- **Escalating**: increases or decreases the amount on each subsequent
  occurrence, by either an absolute amount (linear) or a percentage
  (compounding), applied to `abs(amount)` and floored at zero, then
  reapplying the original sign (so an outflow stays an outflow as it shrinks
  toward zero, never flips to an inflow).

Applies at every occurrence-materialization site (series create/update,
backup import regeneration) — an occurrence's stored `amount` is always the
resolved value for its date, not a formula.

## Needs/Wants/Savings and categories

Every transaction and recurring series carries two independent, orthogonal
classification attributes, both editable wherever amount/date/etc. are
already editable (one-off add/edit form, recurring series add/edit form,
inline row edit):

- **`needsWantsSavings`**: a fixed 3-value enum (`Need` | `Want` |
  `Savings`), defaulting to `Need`. Not user-extensible — these three
  buckets are structural to the feature (budgeting rule-of-thumb style
  breakdown), unlike `categories` below.
- **`category`**: a user-managed, open-ended label (see `categories` in
  "Data model"). Not seeded — the list starts empty and users add categories
  via the Settings page. A dropdown on every transaction/series form,
  defaulting to null (no category), shown with a "Category" placeholder
  until the user picks one.

Editing either attribute on an `attached` series occurrence follows the same
detach-on-save rule as any other field (see "Recurring series editing
semantics") — it is not special-cased.

Both attributes are for classification/reporting only in this phase; they do
not affect running-total math, credit card payment logic, or occurrence
generation. (A future phase may add spend-by-category or
needs/wants/savings-ratio reporting to the Statistics page.)

## Credit card payment logic

A credit card payment-due row is NOT a line item you create manually each
cycle. Instead, this runs independently **per card**:

1. Statement periods are defined by each card's own `statement_close_day`,
   recurring monthly.
2. `amount` is negative for money spent on the card, positive for
   refunds. For each closed statement period, sum `amount` on all kind=credit
   transactions dated within that period **and belonging to that card**
   (`credit_card_id`). "Closed" here describes the period's own start/close
   boundary (the window being summed), not a real-time cutoff against
   today: the table view is a 1-year *forward* forecast (see "Frontend"),
   so future statement periods must still produce projected due rows from
   already-scheduled recurring credit transactions — otherwise forecasting
   beyond one statement cycle would show no credit-card outflows at all.
   The only calculation that uses a real "as of now" cutoff is
   `starting_balance_due_date` (point 6 below).
3. That sum is the *computed estimate* for that card/period's payment-due
   row, dated `statement_close_day + payment_due_offset_days` (using that
   card's own offset), added directly (not subtracted) to the running total
   — a net-spend period produces a negative sum, which reduces the running
   total on the due date.
4. The computed estimate is recalculated on the fly at render/query time
   (not persisted as a stored aggregate) — since credit transactions in a
   period remain editable indefinitely and must auto-recalculate the
   estimate. Given personal-scale data volume, recomputing per request is
   cheap and avoids cache-invalidation complexity.
5. **Editable override:** because real-world statements often include fees,
   interest, or timing quirks the transaction table doesn't capture, the
   user can overwrite the computed estimate for a given (card, due date)
   with a manual value, stored in `credit_due_overrides`:
   - id
   - credit_card_id (FK)
   - due_date (date — matches the computed due date for that period)
   - amount (decimal — the corrected total due, replaces the computed sum)
   - notes (optional)
   - unique on (`credit_card_id`, `due_date`)
   When an override row exists for a (card, due date), the payment-due row
   uses the override `amount` instead of the computed sum, and is visually
   marked as "overridden" (vs. "estimated") in the UI. The underlying
   Credit +/- transactions are unaffected and still shown individually;
   only the aggregated due-row amount is replaced. Clearing the override
   (deleting the `credit_due_overrides` row) reverts to the computed
   estimate.
6. **Starting balance seeding:** at card creation, `starting_balance_due_date`
   is computed once (and stored, immutably) as the due date of the most
   recently *closed* statement period as of "now" — i.e. the next payment
   already coming due whose statement period is fully in the past, so no
   Credit +/- transactions could have been entered for it yet. That due
   date's computed sum (step 2 above) has `starting_balance` added to it
   (can be negative, e.g. existing spend on a card added mid-cycle, or
   positive/zero for a brand-new card). This only ever affects that one
   due date — it does not recur or affect any other period — and is
   overridden like any other computed estimate if the user sets a
   `credit_due_overrides` row for that (card, due date).
7. The generated payment-due row behaves like a normal cash row in the table
   (shows up, affects running total) but the Credit +/- transactions
   underneath it are still edited individually — the row itself is not
   inline-editable like a normal transaction; instead it exposes a distinct
   "edit estimate" control that writes to `credit_due_overrides`.

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
table. Saving there offers two modes:
- **Save for all occurrences**: edits the series template directly;
  regenerates/updates all `attached` occurrences as usual.
- **Save for future events (after a date)**: detaches all `attached`
  occurrences on or before the selected date (leaving their current values
  untouched as independent one-offs, per the `detached` semantics above),
  then applies the edit to the series template so only occurrences after
  that date reflect the new values. Because this permanently splits the
  series' history, it requires an explicit confirmation step before
  submitting.

Editing a table row opens one of two modals (Ajax PATCH under the hood),
chosen by the row's current `occurrence_status`, rather than editing the
row in place within the table. The previous in-place inline-edit row held
too many fields (name, notes, needs/wants/savings, category, cash amount,
credit amount, credit card) to be usable and is retired in favor of these:
- **Edit Occurrence modal** — opened for an `attached` row. Uses the same
  field layout as "Add transaction" (name/date, Kind toggle + a single
  amount field, credit card selector shown only for Kind=Credit,
  Needs/Wants/Savings toggle, category dropdown, notes), plus a persistent
  notice that saving will detach this occurrence from its series.
  **Saving** any field detaches this single occurrence
  (`occurrence_status = 'detached'`, same row/id) and applies the edit to
  it — the row becomes an independent one-off from then on, no longer
  touched by future series edits. **Cancelling**/dismissing the modal
  discards the changes and leaves the row `attached`.
- **Edit Transaction modal** — opened for a `detached` row or a plain
  one-off (no `recurring_series_id`). Same field layout, no detach notice;
  saving affects only that transaction, cancelling discards the changes.
- There is no separate "Detach" button — detaching is a side effect of
  saving an edit via the Edit Occurrence modal, not its own action.
- Both modals populate their fields from the row data already loaded into
  the table's in-memory row map (the same source the old inline edit row
  used) rather than an extra fetch, since that data is already complete
  and up to date once the table has loaded the row.
- Skip / Un-skip / Delete remain row-level buttons on the table, unchanged
  — only the "Edit" action moved into a modal.

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
- Settings page manages a list of credit cards (add/edit/delete, mark one as
  default) rather than a single singleton form; delete is blocked per the
  rules in the `credit_cards` data model section above. It also manages the
  list of `categories` (add new; starts empty; any category still
  referenced by a transaction/series cannot be deleted).
- A top-level Statistics page (see "Statistics page") shows the running-total
  min/max table.
- Table loads an initial window of rows around "today", then fetches more via
  Ajax as the user scrolls down (future, up to 1 year out) or up (past
  history).
- Row edit = one of two modals (Edit Transaction / Edit Occurrence, chosen
  by the row's state) with the same field set as the Add Transaction modal
  (name, date, Kind toggle + amount, credit card selector when
  Kind=Credit, needsWantsSavings, category, notes), saved via Ajax PATCH
  (see "Recurring series editing semantics" for the attached-row
  detach-on-save behavior and why there are two modals).
- Adding a one-off transaction = a small form/modal on the main table page;
  includes needsWantsSavings (default Need) and category (default null,
  shown with a "Category" placeholder) selectors; choosing kind=credit
  reveals the credit card selector (default preselected, user may pick
  another card).
- Credit card payment-due rows show which card they belong to (when more
  than one card exists) and an "edit estimate" affordance to set/clear the
  override in `credit_due_overrides`, distinct from normal row editing.
- Recurring series management (add/edit/delete) lives on its own
  **Recurring Series page**, separate from the main table — deliberately
  NOT modals on the main table, to keep series-template edits (which
  affect every attached occurrence) from being confused with editing a
  single row. Deleting a series there requires explicit confirmation
  before the delete request is sent (destructive, irreversible — see
  "Recurring series editing semantics" for what happens to its
  occurrences).

## Statistics page

A new top-level page, alongside the main table / Recurring Series /
Settings pages, showing a single table of running-total extremes over three
forward-looking windows: **3 months**, **6 months**, and **1 year**, each
measured as `[today, today + N]` (matches the main table's forward
projection horizon — 1 year is the outer bound already computed elsewhere,
so no new occurrence-generation range is needed).

For each window, using the same cash running total defined in "Running
total calculation" (kind=cash rows and generated credit-card payment-due
rows only, skipped rows excluded), the table shows one row per window with:
- Minimum running total in that window, and the date it occurs on
- Maximum running total in that window, and the date it occurs on

Computed at render time (not persisted), same rationale as the credit-card
payment-due estimate: cheap at personal-scale data volume and avoids
cache-invalidation complexity. If a window contains a tie for min or max,
the earliest occurring date wins.

## Per Month column (Recurring Series page)

The Recurring Series list gains a **Per Month** column showing each series'
average monthly cost/income, so cadences with different periods (weekly,
quarterly, yearly, etc.) are comparable at a glance:

- `monthly`: `amount` as-is.
- `weekly`: `amount * 52 / 12`.
- `biweekly`: `amount * 26 / 12`.
- `semi_monthly`: `amount * 2`.
- `quarterly`: `amount / 3`.
- `yearly`: `amount / 12`.
- `custom`: normalized to a monthly rate using `custom_interval_value` /
  `custom_interval_unit` (e.g. `days` → `amount * (30.44 / interval_value)`,
  `weeks` → `amount * (52 / 12) / interval_value`, `months` → `amount /
  interval_value`), using a 30.44-day average month for the `days` case
  since calendar months vary in length.

When `amount_logic` is set (see "Advanced amount logic"), this column uses
the plain `amount` field (the base/else amount), not a resolved per-
occurrence value — escalating/conditional series don't have one true
"amount" to average, and computing a true date-window average would require
picking an arbitrary window. This is a display-only convenience figure, not
used in running-total math.

## Backup / import-export

Motivated by an accidental data loss (named Docker volume deleted by
`docker-compose down -v`); the bind-mount change above (see Tech stack) is
the primary fix, but a portable, human-recoverable backup format is still
useful for point-in-time snapshots, moving between machines, and recovering
from DB corruption.

- Format: single JSON file (chosen over YAML for native
  `json.dumps`/`json.load` support with no new dependency; also trivially
  diffable and versionable if the user wants to keep snapshots in git
  outside this repo).
- Export is a full snapshot of everything needed to fully reconstruct app
  state, exposed as a "Download backup" button on the Settings page (GET
  endpoint, streams `application/json` with a timestamped filename, e.g.
  `accntbl-backup-2026-08-04.json`). Included tables:
  - `checking_accounts` (all fields)
  - `credit_cards` (all fields, including `is_default`)
  - `credit_due_overrides` (all fields)
  - `categories` (all fields)
  - `recurring_series` (all fields, including `needs_wants_savings` and
    `category_id`) — importing these regenerates their
    `attached` occurrences via the existing recurring-occurrence generator,
    so individual `attached` transaction rows are deliberately NOT exported;
    re-deriving them avoids double-storing data that's already fully
    determined by the series definition.
  - `transactions` (including `needs_wants_savings` and `category_id`)
    where `recurring_series_id IS NULL` OR
    `occurrence_status IN ('detached', 'skipped')` — i.e. every row that
    is NOT a currently-`attached` series occurrence, since those regenerate
    on import. `skipped` rows are included so the skip decision survives a
    restore (otherwise the series would silently regenerate that occurrence
    on import).
  - top-level `schema_version` field (matches the latest Alembic revision
    id at export time) so import can detect/reject backups from an
    incompatible schema rather than silently corrupting data.
  - `users` is deliberately excluded — credentials aren't "data" to back up
    and re-importing a password hash across environments is a security
    smell; a restore always keeps the current environment's user(s).
- Import is a full restore, not a merge: a "Restore from backup" control on
  the Settings page (file upload → POST), gated behind a confirmation modal
  that says explicitly this replaces all current data.
  Before the upload is even submitted, choosing a file triggers a
  client-side pre-check (correct JSON, correct `schema_version`, all
  expected top-level keys present) that shows a green check icon and
  enables the upload button on success, or a red X and a disabled upload
  button on failure — a fast UX guard in front of the same validation the
  server re-runs authoritatively in step 1 below (the client check is not
  a substitute for server-side validation).
  Server-side steps once uploaded:
  1. Validate `schema_version` matches current Alembic head; reject with a
     clear error otherwise (no partial-schema migration-on-import — out of
     scope for v1).
  2. Wrap in a single DB transaction: delete all rows from
     `transactions`, `recurring_series`, `credit_due_overrides`,
     `credit_cards`, `checking_accounts`, `categories` (in FK-safe order),
     then insert the backup's rows for each in the reverse order.
  3. Re-run the recurring-occurrence generator for every imported
     `recurring_series` over the standard past-history-through-1-year-out
     window, to regenerate `attached` transaction rows (mirrors what
     happens today when a series is first created/edited).
  4. On any failure, roll back the transaction — the app must never be left
     with a partially-restored (inconsistent) DB.
- Not in scope for v1: scheduled/automatic backups, partial/selective
  restore, cross-schema-version migration on import.

## Tech stack

- Backend: Python, Flask
- ORM/migrations: SQLAlchemy + Alembic, `render_as_batch` enabled for
  SQLite-safe migrations. `Flask-Migrate`'s `Migrate()` already defaults
  `render_as_batch=True`/`compare_type=True` into `configure_args`, which
  `migrations/env.py`'s `run_migrations_online()` forwards automatically —
  do not re-pass `render_as_batch=True` explicitly when calling `Migrate()`,
  it raises `TypeError: multiple values for keyword argument`.
- DB: SQLite (single file on a persistent volume)
- Frontend: Bootstrap + vanilla JS/Ajax (no heavy JS framework — keep simple)
- Local/dev: Docker Compose (flask app container, SQLite file bind-mounted
  from `./data` on the host — a named volume was tried first but is deleted
  by `docker-compose down -v`/volume-prune operations; the bind mount survives
  those and is visible/backup-able as a normal file)
- Deployment target: single small container (e.g. Fly.io) with a persistent
  volume for the SQLite file — chosen for low-cost, low-traffic single-user
  hosting without a separate managed database service.

## Open questions / deferred decisions

- Multiple `checking_accounts` with different `as_of_date` values: v1 assumes
  all accounts' `as_of_date` are effectively "today" at time of entry. If
  accounts drift out of sync, running-total baseline math may need revisiting.
- Currency/timezone: assume single currency (USD) and a single timezone
  (system default) for v1 — no multi-currency/timezone support planned.
