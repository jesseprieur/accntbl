# accntbl

A personal finance forecasting tool. It answers one question: **will my
checking balance ever go negative in the next year?**

## What it does

You maintain a single scrollable table of transactions — one-off or
recurring (paycheck, rent, subscriptions, etc.) — and the app projects a
running checking-account balance forward up to a year from today. Any date
where the projected balance would go negative is highlighted so you can catch
it before it happens.

It also tracks a credit card's spending separately: purchases you log as
"Credit" don't touch your checking balance directly, but they automatically
roll up into a monthly payment-due amount based on the card's statement
close date, which *does* hit your checking balance on its due date.

## Key ideas

- **Checking accounts**: one or more accounts, each with a starting balance.
  Their sum is the baseline your running total is built from. (Savings/
  investment accounts are out of scope — this tool only forecasts checking.)
- **Transactions table**: every row has a name, date, an optional Cash +/-
  amount (affects your running balance), an optional Credit +/- amount
  (logged against the credit card, doesn't affect balance directly), and
  optional notes.
- **Recurring items**: create a series (on the dedicated Recurring Series
  page) with a cadence (weekly, biweekly, monthly, semi-monthly, quarterly,
  yearly, or a custom "every N days/weeks/months") and it populates the
  table automatically. On the main table, **Skip** hides a single
  occurrence without touching the rest of the series (reversible via
  Un-skip). Editing a row still tied to the series is a normal inline
  edit — saving it detaches just that occurrence (it becomes a standalone
  transaction, editable/deletable on its own from then on) while the rest
  of the series is unaffected; cancelling the edit leaves it attached.
- **Credit cards**: manage one or more cards on the Settings page, each with
  its own statement-close day, payment-due offset, and starting balance;
  exactly one is marked the default. When logging a Credit +/- transaction
  (or a credit-kind recurring series), pick which card it belongs to
  (defaults to the default card). The app sums logged Credit +/- purchases
  per statement period and turns that into the Cash payment due on the due
  date — no manual entry of the payment amount each month.
- **History**: past transactions stay visible (scroll up) — this isn't just
  a forward-looking projection, it's a running ledger.
- **Month-end markers**: a virtual row is inserted at the end of every month,
  showing that month's closing balance and the change versus the previous
  month's close.
- **Color-coded rows**: positive amounts are green and negative amounts are
  red; rows still attached to a recurring series get a green left border;
  a row detached from a series gets a yellow left border; a plain one-off
  row gets a blue left border; a negative running balance is highlighted
  bright red and bold; month-end rows get a grey top border.

## Architecture

- **Backend**: Python + Flask
- **Database**: SQLite (single file on a persistent volume), accessed via
  SQLAlchemy, schema managed with Alembic
- **Frontend**: server-rendered pages styled with Bootstrap, Ajax (fetch)
  for inline row editing and infinite scroll through the transaction table
- **Auth**: simple single-user login (username/password stored, hashed, in
  the database)
- **Local development**: Docker Compose brings up the Flask app container,
  with the SQLite file persisted via a bind mount to `./data` on the host
  (survives `docker compose down -v`, unlike a named volume)
- **Future deployment** (not built yet): a single small container (e.g. Fly.io
  or a low-cost VPS) with a persistent volume for the SQLite file — chosen
  over a managed MySQL/Postgres instance to keep hosting costs near-zero for
  this single-user app

See `specs.md` for full design details and rationale, and
`implementation_plan.md` for build progress.

## Repo structure

```
accntbl/
├── app/                  # Flask application (routes, models, templates, static)
├── migrations/           # Alembic migration scripts
├── docker/               # Dockerfile(s) and related config
├── docker-compose.yml    # Local dev: web service (SQLite bind-mounted from ./data)
├── .env.example          # Required environment variables (copy to .env)
├── specs.md              # Design source of truth (for Claude/devs)
├── implementation_plan.md # Build checklist
└── README.md             # This file
```

(Structure will fill in as the project is built — see
implementation_plan.md for current status.)

## Running locally

```bash
cp .env.example .env      # fill in Flask secret key, etc.
docker compose up --build
```

The app will be available at `http://localhost:5000` (or whatever port is
configured in `.env`). On first run, apply the database migrations and
create the initial user:

```bash
docker compose exec web flask db upgrade
docker compose exec web flask create-user
```

Run `flask db upgrade` again any time you pull changes that add new
migrations. To roll back the most recent migration, use
`docker compose exec web flask db downgrade -- -1` (the `--` is required so
the leading dash isn't parsed as an option flag).

To try the app with sample data instead of starting from scratch, run
`docker compose exec web flask seed-demo-data` — it seeds a checking
account, a default credit card, a few recurring series, and a couple of
one-off transactions. It's a no-op (refuses to run) if any checking
account already exists, so it's safe against accidentally overwriting
real data.

(Checking account and credit card settings are created via the **Settings**
page at `/settings`.)

## Usage

1. Log in with the single configured user.
2. Visit **Settings** to set up your checking account(s) starting balance
   and your credit card(s) (name, statement close day, payment due offset,
   starting balance, which one is the default).
3. On the main table, add one-off transactions. Use the **Recurring Series**
   page to add/edit/delete recurring series (name, kind, amount, cadence,
   start date, optional end date). See "Key ideas" above for how
   editing/detaching a recurring row on the main table works.
4. Scroll down to project up to a year forward; scroll up to review history.
5. Watch for highlighted rows — that's when your projected balance goes
   negative.
6. To remove an entire recurring series (not just one occurrence), use the
   Recurring Series page — pick the series, confirm, and it's gone.

## Example

- Checking account: $2,500 starting balance
- Recurring income: "Paycheck", +$2,000, biweekly
- Recurring expense: "Rent", -$1,800, monthly on the 1st
- Credit card: statement closes on the 20th, due 20 days later; you log
  groceries and subscriptions as Credit +/- transactions throughout the
  month, and the app generates the payment-due Cash transaction for you
