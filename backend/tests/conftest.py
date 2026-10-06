import os
import tempfile
from pathlib import Path

import pytest


# Application modules create their engines at import time. Pytest imports this
# conftest first, so point every persistent store and upload path at one
# disposable directory before test modules can load app.main. This prevents
# synthetic test merchants and categories from polluting the user's models.
_test_directory = tempfile.TemporaryDirectory(prefix="life-budget-tests-")
_test_path = Path(_test_directory.name)
os.environ["DATABASE_URL"] = f"sqlite:///{(_test_path / 'budget.db').as_posix()}"
os.environ["PREDICTION_DATABASE_URL"] = f"sqlite:///{(_test_path / 'predictions.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_test_path / "uploads")


def pytest_sessionfinish() -> None:
    """Close global SQLite pools before Windows removes the temporary files."""
    from app.db import engine
    from app.prediction_db import prediction_engine

    engine.dispose()
    prediction_engine.dispose()
    _test_directory.cleanup()


# Each financial test fixture has its own ledger. Reset its disposable projection
# too, rather than silently accumulating synthetic labels across tests.


@pytest.fixture(autouse=True)
def isolated_predictions():
    from app.prediction_db import PredictionBase, prediction_engine
    from app import prediction_db, prediction_models  # noqa: F401

    PredictionBase.metadata.drop_all(prediction_engine)
    PredictionBase.metadata.create_all(prediction_engine)
    prediction_db._schema_ready = True
    yield
