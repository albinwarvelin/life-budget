from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import learning_db
from app.description_learning_db import DescriptionLearningBase
from app.learning_db import LearningBase
from app.learning_models import CategoryPattern
from app.models import Category
from app.routers.learning_models import (
    _category_signal_labels,
    test_description_prediction as run_description_prediction,
)
from app.schemas_learning import CategoryPredictionRequest, DescriptionPredictionRequest
from app.services.category_learning import predict_categories
from app.services.description_learning import learn_description, predict_description
from app.services.type_learning import learn_transaction_type, predict_transaction_type
from app.type_learning_db import TypeLearningBase


def memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def test_category_signal_ids_receive_localized_graph_labels() -> None:
    category = Category(
        name="Groceries",
        localized_names={"en": "Groceries", "sv": "Matvaror"},
        kind="expense",
    )

    label, localized = _category_signal_labels("category_amount_band", "7|SEK:100-249", category)

    assert label == "Groceries / SEK:100-249"
    assert localized["sv"] == "Matvaror / SEK:100-249"


def test_compound_signal_labels_use_category_names_not_ids() -> None:
    category = Category(
        name="Groceries",
        localized_names={"en": "Groceries", "sv": "Matvaror"},
        kind="expense",
    )

    label, localized = _category_signal_labels(
        "merchant_category_amount_band", "ica|7|SEK:100-249", category
    )

    assert label == "ica / Groceries / SEK:100-249"
    assert localized["sv"] == "ica / Matvaror / SEK:100-249"
    assert "7" not in label

    token_label, token_localized = _category_signal_labels(
        "merchant_token_category_band", "ica|7|SEK:100-249", category
    )
    assert token_label == "ica / Groceries / SEK:100-249"
    assert token_localized["sv"] == "ica / Matvaror / SEK:100-249"


def test_category_learning_schema_checks_alembic_before_first_use(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(learning_db, "_schema_ready", False)
    monkeypatch.setattr(
        learning_db,
        "upgrade_database_to_head",
        lambda config_filename: calls.append(config_filename),
    )

    learning_db.ensure_learning_schema()
    learning_db.ensure_learning_schema()

    assert calls == ["alembic_learning.ini"]


def test_single_merchant_word_contributes_without_a_full_phrase_match() -> None:
    main_engine = memory_engine()
    learning_engine = memory_engine()
    Base.metadata.create_all(main_engine)
    LearningBase.metadata.create_all(learning_engine)
    with Session(main_engine) as main_db, Session(learning_engine) as learning_db:
        category = Category(name="Groceries", localized_names={}, kind="expense")
        main_db.add(category)
        main_db.commit()
        learning_db.add(
            CategoryPattern(
                pattern_type="merchant_token",
                pattern_text="ica",
                category_id=category.id,
                account_id=None,
                transaction_type="expense",
                weight=0.5,
                observations=1,
            )
        )
        learning_db.commit()

        result = predict_categories(
            main_db,
            learning_db,
            CategoryPredictionRequest(merchant="Stockholm ICA Nära", transaction_type="expense"),
        )

        assert result[0].category_id == category.id


def test_category_amount_band_is_weak_but_breaks_equal_merchant_evidence() -> None:
    main_engine = memory_engine()
    learning_engine = memory_engine()
    Base.metadata.create_all(main_engine)
    LearningBase.metadata.create_all(learning_engine)
    with Session(main_engine) as main_db, Session(learning_engine) as learning_db:
        coffee = Category(name="Cafe", localized_names={}, kind="expense")
        fuel = Category(name="Fuel", localized_names={}, kind="expense")
        main_db.add_all([coffee, fuel])
        main_db.commit()
        for category, band in ((coffee, "SEK:0-49"), (fuel, "SEK:1000-1999")):
            learning_db.add_all(
                [
                    CategoryPattern(
                        pattern_type="merchant",
                        pattern_text="okq8",
                        category_id=category.id,
                        account_id=None,
                        transaction_type="expense",
                        weight=4,
                        observations=1,
                    ),
                    CategoryPattern(
                        pattern_type="merchant_token",
                        pattern_text="okq8",
                        category_id=category.id,
                        account_id=None,
                        transaction_type="expense",
                        weight=0.5,
                        observations=1,
                    ),
                    CategoryPattern(
                        pattern_type="merchant_amount_band",
                        pattern_text=f"okq8|{band}",
                        category_id=category.id,
                        account_id=None,
                        transaction_type="expense",
                        weight=0.35,
                        observations=1,
                    ),
                ]
            )
        learning_db.commit()

        low = predict_categories(
            main_db,
            learning_db,
            CategoryPredictionRequest(
                merchant="OKQ8",
                transaction_type="expense",
                amount=Decimal("35"),
                currency_code="SEK",
            ),
        )
        high = predict_categories(
            main_db,
            learning_db,
            CategoryPredictionRequest(
                merchant="OKQ8",
                transaction_type="expense",
                amount=Decimal("1500"),
                currency_code="SEK",
            ),
        )

        assert low[0].category_id == coffee.id
        assert high[0].category_id == fuel.id


def test_type_model_uses_amount_magnitude_as_low_weight_context() -> None:
    engine = memory_engine()
    TypeLearningBase.metadata.create_all(engine)
    with Session(engine) as db:
        for _ in range(4):
            learn_transaction_type(
                db,
                amount=Decimal("35"),
                currency_code="SEK",
                merchant="Station",
                category_id=4,
                transaction_type="expense",
            )
            learn_transaction_type(
                db,
                amount=Decimal("1500"),
                currency_code="SEK",
                merchant="Station",
                category_id=4,
                transaction_type="transfer",
            )

        low = predict_transaction_type(
            db, amount=Decimal("35"), currency_code="SEK", merchant="Station", category_id=4
        )
        high = predict_transaction_type(
            db, amount=Decimal("1500"), currency_code="SEK", merchant="Station", category_id=4
        )

        assert low.transaction_type == "expense"
        assert high.transaction_type == "transfer"


def test_description_model_learns_different_text_for_different_amount_bands() -> None:
    engine = memory_engine()
    DescriptionLearningBase.metadata.create_all(engine)
    with Session(engine) as db:
        learn_description(
            db,
            merchant="OKQ8",
            amount=Decimal("35"),
            currency_code="SEK",
            category_id=1,
            transaction_type="expense",
            description="Coffee",
        )
        learn_description(
            db,
            merchant="OKQ8",
            amount=Decimal("1500"),
            currency_code="SEK",
            category_id=1,
            transaction_type="expense",
            description="Fuel",
        )

        low = predict_description(
            db,
            merchant="OKQ8",
            amount=Decimal("35"),
            currency_code="SEK",
            category_id=1,
            transaction_type="expense",
        )
        high = predict_description(
            db,
            merchant="OKQ8",
            amount=Decimal("1500"),
            currency_code="SEK",
            category_id=1,
            transaction_type="expense",
        )

        assert low.description == "Coffee"
        assert high.description == "Fuel"


def test_description_model_uses_compounds_from_a_shared_merchant_token() -> None:
    """A brand token should transfer evidence between differently named stores."""
    engine = memory_engine()
    DescriptionLearningBase.metadata.create_all(engine)
    with Session(engine) as db:
        learn_description(
            db,
            merchant="Stockholm ICA Nara",
            amount=Decimal("120"),
            currency_code="SEK",
            category_id=7,
            transaction_type="expense",
            description="Groceries",
        )
        learn_description(
            db,
            merchant="OKQ8",
            amount=Decimal("1500"),
            currency_code="SEK",
            category_id=4,
            transaction_type="expense",
            description="Fuel",
        )

        prediction = predict_description(
            db,
            merchant="Uppsala ICA Kvantum",
            amount=Decimal("120"),
            currency_code="SEK",
            category_id=7,
            transaction_type="expense",
        )

        assert prediction.description == "Groceries"
        signal_types = {
            contribution.signal_type
            for contribution in prediction.candidates[0].contributions
        }
        assert "merchant_token_category_band" in signal_types
        assert "merchant_token_amount_band" in signal_types


def test_generic_transaction_type_bias_cannot_create_description_prediction() -> None:
    engine = memory_engine()
    DescriptionLearningBase.metadata.create_all(engine)
    descriptions = [
        "Mat",
        "Mat",
        "Mat",
        "Fuel",
        "Parking",
        "Rent",
        "Coffee",
        "Travel",
        "Phone",
        "Books",
        "Health",
    ]
    with Session(engine) as db:
        for index, description in enumerate(descriptions):
            learn_description(
                db,
                merchant=f"Merchant {index}",
                amount=Decimal("100"),
                currency_code="SEK",
                category_id=index + 1,
                transaction_type="expense",
                description=description,
            )

        prediction = predict_description(
            db,
            merchant="Entirely new merchant",
            amount=Decimal("9000"),
            currency_code="SEK",
            category_id=None,
            transaction_type="expense",
        )

        assert prediction.description is None
        assert prediction.confidence == 0
        assert "overall description bias" in prediction.reason


def test_description_prediction_api_explains_interaction_contributions() -> None:
    engine = memory_engine()
    DescriptionLearningBase.metadata.create_all(engine)
    with Session(engine) as db:
        learn_description(
            db,
            merchant="OKQ8",
            amount=Decimal("35"),
            currency_code="SEK",
            category_id=4,
            transaction_type="expense",
            description="Coffee",
        )
        learn_description(
            db,
            merchant="OKQ8",
            amount=Decimal("1500"),
            currency_code="SEK",
            category_id=4,
            transaction_type="expense",
            description="Fuel",
        )

        response = run_description_prediction(
            DescriptionPredictionRequest(
                merchant="OKQ8",
                amount=Decimal("35"),
                currency_code="SEK",
                category_id=4,
                transaction_type="expense",
            ),
            db,
        )

        assert response.description == "Coffee"
        assert response.candidates[0].description == "Coffee"
        assert response.candidates[0].contributions[0].signal_type == (
            "merchant_category_amount_band"
        )
        assert response.candidates[0].contributions[0].conditional_probability == 1
        assert response.candidates[0].contributions[0].baseline_probability == 0.5
