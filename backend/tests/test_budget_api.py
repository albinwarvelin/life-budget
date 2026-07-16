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
        },
    )
    assert created.status_code == 201
    response = client.get("/api/v1/transactions", params={"transaction_type": "transfer"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["transaction_type"] == "transfer"
