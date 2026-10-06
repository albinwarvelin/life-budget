from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account
from app.schemas_learning import (
    CategoryPrediction,
    CategoryPredictionRequest,
    ModelStatus,
    PredictionRequest,
    PredictionResponse,
)
from app.services.predictions import model_status, observed_row, predict, retrain_models

router = APIRouter()


@router.get("/learning-models/status", response_model=ModelStatus)
def status(db: Session = Depends(get_db)) -> dict:
    """Aggregate evaluation only; training examples stay in the local database."""
    return model_status(db)


@router.post("/learning-models/retrain", response_model=ModelStatus)
def retrain(db: Session = Depends(get_db)) -> dict:
    """The user explicitly requests fitting against the current reviewed ledger."""
    return retrain_models(db)


@router.post("/learning-models/predict", response_model=PredictionResponse)
def test_prediction(payload: PredictionRequest, db: Session = Depends(get_db)) -> dict:
    """Testing a draft never teaches the learner."""
    if payload.account_id is not None:
        account = db.get(Account, payload.account_id)
        if not account or account.currency_code != payload.currency_code.upper():
            raise HTTPException(status_code=400, detail="Account must exist and match currency")
    return predict(db, observed_row(**payload.model_dump()))


@router.post("/category-suggestions", response_model=list[CategoryPrediction])
def suggest_categories(
    payload: CategoryPredictionRequest, db: Session = Depends(get_db)
) -> list[dict]:
    """Manual entry supplies its chosen type; description is deliberately unused."""
    account = db.get(Account, payload.account_id) if payload.account_id else None
    currency = payload.currency_code or (account.currency_code if account else "UNK")
    row = observed_row(
        merchant=payload.merchant,
        amount=payload.amount,
        currency_code=currency,
        account_id=payload.account_id,
        transaction_type=payload.transaction_type,
    )
    result = predict(db, row, transaction_type=payload.transaction_type)["outputs"]["category"]
    return [
        {
            "category_id": int(candidate["key"]),
            "confidence": candidate["probability"],
            "reason": result["reason"],
        }
        for candidate in result["candidates"]
    ]
