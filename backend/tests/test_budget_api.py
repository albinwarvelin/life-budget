from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_transaction_requires_matching_account_currency(client: TestClient) -> None:
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    client.post("/api/v1/currencies", json={"code": "NOK", "name": "Norwegian krone"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    )
    response = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": str(date.today()),
            "account_id": account.json()["id"],
            "amount": "10.00",
            "currency_code": "NOK",
            "transaction_type": "expense",
            "description": "Invalid currency",
            "merchant": "Test merchant",
        },
    )
    assert response.status_code == 400
    assert "match account currency" in response.json()["detail"]


def test_only_sek_and_nok_are_initially_available_but_optional_currencies_can_be_added(
    client: TestClient,
) -> None:
    # The test database starts empty because it uses metadata.create_all();
    # this mirrors the migration's initial catalog explicitly.
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    client.post("/api/v1/currencies", json={"code": "NOK", "name": "Norwegian krone"})

    initial_codes = {row["code"] for row in client.get("/api/v1/currencies").json()}
    assert initial_codes == {"SEK", "NOK"}

    # EUR is supported by the schema, but it is not a selectable default until
    # the user explicitly adds it to the currency catalog.
    before_adding = client.post(
        "/api/v1/accounts",
        json={"name": "Euro account", "account_type": "bank", "currency_code": "EUR"},
    )
    assert before_adding.status_code == 400

    added = client.post("/api/v1/currencies", json={"code": "EUR", "name": "Euro"})
    assert added.status_code == 201


def test_transfer_is_allowed_without_category_and_can_be_filtered(client: TestClient) -> None:
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    created = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-16",
            "account_id": account["id"],
            "amount": "100.00",
            "currency_code": "SEK",
            "transaction_type": "transfer",
            "description": "Move to savings",
            "merchant": "Internal transfer",
        },
    )
    assert created.status_code == 201
    response = client.get("/api/v1/transactions", params={"transaction_type": "transfer"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["transaction_type"] == "transfer"


def test_transfer_accepts_positive_and_negative_amounts(client: TestClient) -> None:
    """A transfer's sign records which direction the movement represents."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    base = {
        "transaction_date": "2026-07-18",
        "account_id": account["id"],
        "currency_code": "SEK",
        "transaction_type": "transfer",
        "merchant": "Savings transfer",
    }

    positive = client.post("/api/v1/transactions", json={**base, "amount": "100.00"})
    negative = client.post("/api/v1/transactions", json={**base, "amount": "-100.00"})

    assert positive.status_code == 201
    assert negative.status_code == 201
    assert negative.json()["amount"] == "-100.00"


def test_transactions_can_be_filtered_by_account(client: TestClient) -> None:
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    first = client.post(
        "/api/v1/accounts",
        json={"name": "First", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    second = client.post(
        "/api/v1/accounts",
        json={"name": "Second", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    payload = {
        "transaction_date": "2026-07-16",
        "amount": "10.00",
        "currency_code": "SEK",
        "transaction_type": "expense",
        "description": "Account filter",
        "merchant": "Test merchant",
    }
    client.post("/api/v1/transactions", json={**payload, "account_id": first["id"]})
    client.post("/api/v1/transactions", json={**payload, "account_id": second["id"]})
    response = client.get("/api/v1/transactions", params={"account_id": first["id"]})
    assert response.status_code == 200
    assert {item["account_id"] for item in response.json()} == {first["id"]}


def test_transaction_can_be_created_listed_updated_and_deleted(client: TestClient) -> None:
    """Verify that each manual transaction endpoint changes persisted state."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    payload = {
        "transaction_date": "2026-07-15",
        "account_id": account["id"],
        "amount": "25.50",
        "currency_code": "SEK",
        "transaction_type": "expense",
        "description": "Initial description",
        "merchant": "Test merchant",
    }

    created = client.post("/api/v1/transactions", json=payload)
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    listed = client.get("/api/v1/transactions")
    assert listed.status_code == 200
    assert listed.json()[0]["description"] == "Initial description"

    updated_payload = {**payload, "description": "Updated description", "amount": "30.00"}
    updated = client.put(f"/api/v1/transactions/{transaction_id}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated description"
    assert updated.json()["amount"] == "30.00"

    deleted = client.delete(f"/api/v1/transactions/{transaction_id}")
    assert deleted.status_code == 204
    assert client.delete(f"/api/v1/transactions/{transaction_id}").status_code == 404
    assert client.get("/api/v1/transactions").json() == []


def test_reimbursement_is_a_distinct_transaction_type(client: TestClient) -> None:
    """Reimbursements use their own category/type instead of ordinary income."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories", json={"name": "Paid back", "kind": "reimbursement"}
    ).json()

    response = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-17",
            "account_id": account["id"],
            "amount": "50.00",
            "currency_code": "SEK",
            "transaction_type": "reimbursement",
            "description": "Lunch reimbursement",
            "merchant": "Restaurant",
            "category_id": category["id"],
        },
    )
    assert response.status_code == 201
    assert response.json()["transaction_type"] == "reimbursement"


def test_transaction_attachment_can_be_uploaded_and_removed(client: TestClient) -> None:
    """Attachments are stored locally and their metadata follows the transaction."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    transaction = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-17",
            "account_id": account["id"],
            "amount": "20.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "description": "Receipt test",
            "merchant": "Shop",
        },
    ).json()

    uploaded = client.post(
        f"/api/v1/transactions/{transaction['id']}/attachment",
        files={"file": ("receipt.png", b"fake image bytes", "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["attachment_filename"] == "receipt.png"

    removed = client.delete(f"/api/v1/transactions/{transaction['id']}/attachment")
    assert removed.status_code == 204


def test_savings_accepts_positive_and_negative_amounts(client: TestClient) -> None:
    """Positive savings deposits and negative savings withdrawals are preserved."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Savings", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories", json={"name": "Savings movement", "kind": "savings"}
    ).json()
    base = {
        "transaction_date": "2026-07-18",
        "account_id": account["id"],
        "currency_code": "SEK",
        "transaction_type": "savings",
        "description": "Savings movement",
        "merchant": "Savings account",
        "category_id": category["id"],
    }

    deposited = client.post("/api/v1/transactions", json={**base, "amount": "200.00"})
    withdrawn = client.post("/api/v1/transactions", json={**base, "amount": "-50.00"})
    assert deposited.status_code == 201
    assert withdrawn.status_code == 201
    assert withdrawn.json()["amount"] == "-50.00"


def test_account_can_be_edited_but_existing_currency_cannot_change(client: TestClient) -> None:
    """Account labels can change without rewriting transaction currency history."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    client.post("/api/v1/currencies", json={"code": "NOK", "name": "Norwegian krone"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Old name", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    edited = client.put(
        f"/api/v1/accounts/{account['id']}",
        json={"name": "New name", "account_type": "cash", "currency_code": "SEK"},
    )
    assert edited.status_code == 200
    assert edited.json()["name"] == "New name"

    client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "10.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "description": "History",
            "merchant": "Test merchant",
        },
    )
    currency_change = client.put(
        f"/api/v1/accounts/{account['id']}",
        json={"name": "New name", "account_type": "cash", "currency_code": "NOK"},
    )
    assert currency_change.status_code == 400


def test_deleting_account_removes_linked_transactions(client: TestClient) -> None:
    """The account confirmation action has a cascading domain effect."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Disposable", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "10.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "description": "Linked record",
        },
    )
    deleted = client.delete(f"/api/v1/accounts/{account['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/accounts").json() == []
    assert client.get("/api/v1/transactions").json() == []


def test_category_can_be_edited_and_deleted_without_deleting_transactions(
    client: TestClient,
) -> None:
    """Deleting a category preserves the transaction as uncategorized."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories", json={"name": "Old name", "kind": "expense"}
    ).json()
    edited = client.put(
        f"/api/v1/categories/{category['id']}",
        json={"name": "New name", "kind": "expense"},
    )
    assert edited.status_code == 200
    transaction = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "10.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "description": "Categorized record",
            "merchant": "Test merchant",
            "category_id": category["id"],
        },
    ).json()
    assert client.delete(f"/api/v1/categories/{category['id']}").status_code == 204
    remaining = client.get("/api/v1/transactions").json()
    assert remaining[0]["id"] == transaction["id"]
    assert remaining[0]["category_id"] is None


def test_category_localized_names_are_saved_and_returned(client: TestClient) -> None:
    """Category labels are returned as a locale-keyed dictionary for the UI."""
    response = client.post(
        "/api/v1/categories",
        json={
            "name": "Groceries",
            "kind": "expense",
            "localized_names": {"en": "Groceries", "sv": "Matvaror"},
        },
    )
    assert response.status_code == 201
    assert response.json()["localized_names"] == {"en": "Groceries", "sv": "Matvaror"}


def test_category_kind_can_change_after_use(client: TestClient) -> None:
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories", json={"name": "Flexible", "kind": "expense"}
    ).json()
    transaction = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "5.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "merchant": "Test merchant",
            "category_id": category["id"],
        },
    )
    assert transaction.status_code == 201
    changed = client.put(
        f"/api/v1/categories/{category['id']}",
        json={"name": "Flexible", "kind": "income"},
    )
    assert changed.status_code == 200


def test_category_suggestion_learns_from_a_saved_transaction(client: TestClient) -> None:
    """A later draft receives the category from a previous confirmed entry."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories",
        json={"name": "Groceries", "kind": "expense"},
    ).json()
    saved = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "25.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "merchant": "Unique learning merchant",
            "category_id": category["id"],
        },
    )
    assert saved.status_code == 201
    prediction = client.post(
        "/api/v1/category-suggestions",
        json={
            "merchant": "Unique learning merchant",
            "account_id": account["id"],
            "transaction_type": "expense",
        },
    )
    assert prediction.status_code == 200
    assert prediction.json()[0]["category_id"] == category["id"]


def test_category_suggestion_uses_all_merchant_words(client: TestClient) -> None:
    """A shared merchant word connects related store variants."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories", json={"name": "Groceries", "kind": "expense"}
    ).json()
    saved = client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "25.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "merchant": "ICA Kvantum",
            "category_id": category["id"],
        },
    )
    assert saved.status_code == 201
    prediction = client.post(
        "/api/v1/category-suggestions",
        json={
            "merchant": "ICA nära",
            "account_id": account["id"],
            "transaction_type": "expense",
        },
    )
    assert prediction.status_code == 200
    assert prediction.json()[0]["category_id"] == category["id"]


def test_learning_model_endpoint_exposes_safe_graph_snapshot(client: TestClient) -> None:
    """The explorer receives connections and totals, but not raw event records."""
    client.post("/api/v1/currencies", json={"code": "SEK", "name": "Swedish krona"})
    account = client.post(
        "/api/v1/accounts",
        json={"name": "Everyday", "account_type": "bank", "currency_code": "SEK"},
    ).json()
    category = client.post(
        "/api/v1/categories",
        json={
            "name": "Groceries",
            "kind": "expense",
            "localized_names": {"en": "Groceries", "sv": "Matvaror"},
        },
    ).json()
    client.post(
        "/api/v1/transactions",
        json={
            "transaction_date": "2026-07-18",
            "account_id": account["id"],
            "amount": "20.00",
            "currency_code": "SEK",
            "transaction_type": "expense",
            "merchant": "ICA Kvantum",
            "category_id": category["id"],
        },
    )

    response = client.get("/api/v1/category-learning/model")
    assert response.status_code == 200
    body = response.json()
    # The learning store deliberately outlives the isolated financial test DB,
    # so only assert that at least this event has been retained.
    assert body["event_count"] >= 1
    assert body["categories"][0]["localized_names"]["sv"] == "Matvaror"
    assert any(
        pattern["pattern_type"] == "merchant_token" and pattern["pattern_text"] == "ica"
        for pattern in body["patterns"]
    )
    assert body["scoring"]["signal_weights"]["merchant"] == 4.0
    assert body["scoring"]["similarity_threshold"] == 0.72
    assert "events" not in body
