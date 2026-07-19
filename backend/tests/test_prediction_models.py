from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.description_learning_db import DescriptionLearningBase
from app.learning_db import LearningBase
from app.learning_models import CategoryPattern
from app.models import Category
from app.schemas_learning import CategoryPredictionRequest
from app.services.category_learning import predict_categories
from app.services.description_learning import learn_description, predict_description
from app.services.type_learning import learn_transaction_type, predict_transaction_type
from app.type_learning_db import TypeLearningBase


def memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


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
