import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        db.session.add(
            User(username="anita", password_hash=generate_password_hash("secret123"))
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "anita", "password": "secret123"})
    return client


def test_index_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.get("/")
    assert response.status_code == 302


def test_index_renders_transactions_window(client):
    response = client.get("/")
    assert response.status_code == 200

    body = response.get_data(as_text=True)

    assert 'data-window-url="/transactions/window"' in body
    assert 'id="transactions-tbody"' in body
    assert "table.js" in body
    assert "date_utils.js" in body


def test_index_uses_bootstrap_toggle_buttons_for_kind(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert 'class="btn-check" name="kind" id="add-transaction-kind-cash"' in body
    assert 'class="btn-check" name="kind" id="add-transaction-kind-credit"' in body
    assert 'class="form-check-input" type="radio" name="kind"' not in body


def test_recurring_series_page_uses_bootstrap_toggle_buttons_for_kind(client):
    response = client.get("/recurring-series")
    body = response.get_data(as_text=True)

    assert 'class="btn-check" name="kind" id="add-series-kind-cash"' in body
    assert 'class="btn-check" name="kind" id="edit-series-kind-cash"' in body
    assert 'class="form-check-input" type="radio" name="kind"' not in body


def test_base_layout_loads_bootstrap_icons(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert "bootstrap-icons" in body


def test_index_buttons_use_icons(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert '<i class="bi bi-plus-lg"></i> Add transaction' in body
    assert '<i class="bi bi-arrow-repeat"></i> Recurring Series' in body
    assert '<i class="bi bi-gear"></i> Settings' in body
    assert '<i class="bi bi-box-arrow-right"></i> Log out' in body


def test_settings_page_buttons_use_icons(client):
    response = client.get("/settings/")
    body = response.get_data(as_text=True)

    assert '<i class="bi bi-arrow-left"></i> Back' in body
    assert '<i class="bi bi-plus-lg"></i> Add' in body


def test_recurring_series_page_buttons_use_icons(client):
    response = client.get("/recurring-series")
    body = response.get_data(as_text=True)

    assert '<i class="bi bi-plus-lg"></i> Add recurring series' in body
    assert '<i class="bi bi-arrow-left"></i> Back' in body


def test_statistics_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.get("/statistics")
    assert response.status_code == 302


def test_statistics_page_renders_windows_table(client):
    response = client.get("/statistics")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "3 months" in body
    assert "6 months" in body
    assert "12 months" in body


def test_statistics_nav_link_present_on_other_pages(client):
    for path in ("/", "/recurring-series", "/settings/"):
        body = client.get(path).get_data(as_text=True)
        assert 'href="/statistics"' in body


def test_statistics_page_renders_breakdown_tables_and_month_dropdown(client):
    response = client.get("/statistics")
    body = response.get_data(as_text=True)

    assert 'id="statistics-month-select"' in body
    assert 'id="needs-wants-savings-body"' in body
    assert 'id="spend-by-category-body"' in body
    assert '<option value="average"' in body
    assert "statistics.js" in body


def test_statistics_breakdown_endpoint_returns_needs_wants_savings_and_category_data(app, client):
    import datetime as dt

    from app.extensions import db
    from app.models import Category, Kind, NeedsWantsSavings, Transaction

    today = dt.date.today()
    month_value = today.strftime("%Y-%m")

    with app.app_context():
        category = Category(name="Groceries", icon="bi-cart")
        db.session.add(category)
        db.session.commit()
        db.session.add_all(
            [
                Transaction(
                    name="Paycheck",
                    kind=Kind.cash,
                    amount="2000.00",
                    date=today,
                    needs_wants_savings=NeedsWantsSavings.need,
                ),
                Transaction(
                    name="Groceries",
                    kind=Kind.cash,
                    amount="-150.00",
                    date=today,
                    needs_wants_savings=NeedsWantsSavings.need,
                    category_id=category.id,
                ),
            ]
        )
        db.session.commit()

    response = client.get(f"/statistics/breakdown?month={month_value}")
    assert response.status_code == 200
    data = response.get_json()

    nws_rows = {row["label"]: row for row in data["needs_wants_savings"]["rows"]}
    assert nws_rows["Income"]["value"] == "$2,000.00"
    assert nws_rows["Needs"]["value"] == "$150.00"
    assert nws_rows["Leftover"]["value"] == "$1,850.00"

    category_rows = {row["name"]: row for row in data["spend_by_category"]["rows"]}
    assert category_rows["Groceries"]["value"] == "$150.00"
    assert category_rows["Uncategorized"]["value"] == "$0.00"


def test_statistics_breakdown_endpoint_average_option(client):
    response = client.get("/statistics/breakdown?month=average")
    assert response.status_code == 200
    data = response.get_json()

    assert {row["label"] for row in data["needs_wants_savings"]["rows"]} == {
        "Income",
        "Needs",
        "Wants",
        "Savings",
        "Leftover",
    }
