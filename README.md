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
- **Recurring items**: create a series with a cadence (weekly, biweekly,
  monthly, semi-monthly, quarterly, yearly, or a custom "every N days/weeks/
  months") and it populates the table automatically. You can edit or skip a
  single occurrence without touching the rest of the series.
- **Credit card**: one default card with a statement-close day and a
  payment-due offset. The app sums your logged Credit +/- purchases per
  statement period and turns that into the Cash payment due on the due date
  — no manual entry of the payment amount each month.
- **History**: past transactions stay visible (scroll up) — this isn't just
  a forward-looking projection, it's a running ledger.

## Architecture

- **Backend**: Python + Flask
- **Database**: MySQL, accessed via SQLAlchemy, schema managed with Alembic
- **Frontend**: server-rendered pages styled with Bootstrap, Ajax (fetch)
  for inline row editing and infinite scroll through the transaction table
- **Auth**: simple single-user login (username/password stored, hashed, in
  the database)
- **Local development**: Docker Compose brings up the Flask app and a MySQL
  container together
- **Future deployment** (not built yet): AWS Lambda + S3, or GCP Cloud Run +
  Cloud Storage, as lower-cost/low-traffic hosting options once the app is
  further along

See `specs.md` for full design details and rationale, and
`implementation_plan.md` for build progress.

## Repo structure

```
accntbl/
├── app/                  # Flask application (routes, models, templates, static)
├── migrations/           # Alembic migration scripts
├── docker/               # Dockerfile(s) and related config
├── docker-compose.yml    # Local dev: web + db services
├── .env.example          # Required environment variables (copy to .env)
├── specs.md              # Design source of truth (for Claude/devs)
├── implementation_plan.md # Build checklist
└── README.md             # This file
```

(Structure will fill in as the project is built — see
implementation_plan.md for current status.)

## Running locally

```bash
cp .env.example .env      # fill in DB credentials, secret key, etc.
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
`docker compose exec web flask db downgrade -1`.

(Checking account and credit card settings are created via the **Settings**
page at `/settings`.)

## Usage

1. Log in with the single configured user.
2. Visit **Settings** to set up your checking account(s) starting balance
   and the credit card's statement close day / payment due offset.
3. On the main table, add one-off transactions or recurring series (name,
   kind, amount, cadence, start date, optional end date). Editing an
   existing series is available via the API but not yet exposed in the UI.
4. Scroll down to project up to a year forward; scroll up to review history.
5. Watch for highlighted rows — that's when your projected balance goes
   negative.

## Example

- Checking account: $2,500 starting balance
- Recurring income: "Paycheck", +$2,000, biweekly
- Recurring expense: "Rent", -$1,800, monthly on the 1st
- Credit card: statement closes on the 20th, due 20 days later; you log
  groceries and subscriptions as Credit +/- transactions throughout the
  month, and the app generates the payment-due Cash transaction for you
