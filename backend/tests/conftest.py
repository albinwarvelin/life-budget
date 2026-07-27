import os
import tempfile
from pathlib import Path


# Application modules create their engines at import time. Pytest imports this
# conftest first, so point every persistent store and upload path at one
# disposable directory before test modules can load app.main. This prevents
# synthetic test merchants and categories from polluting the user's models.
_test_directory = tempfile.TemporaryDirectory(prefix="life-budget-tests-")
_test_path = Path(_test_directory.name)
os.environ["DATABASE_URL"] = f"sqlite:///{(_test_path / 'budget.db').as_posix()}"
os.environ["LEARNING_DATABASE_URL"] = f"sqlite:///{(_test_path / 'learning.db').as_posix()}"
os.environ["TYPE_LEARNING_DATABASE_URL"] = (
    f"sqlite:///{(_test_path / 'type-learning.db').as_posix()}"
)
os.environ["DESCRIPTION_LEARNING_DATABASE_URL"] = (
    f"sqlite:///{(_test_path / 'description-learning.db').as_posix()}"
)
os.environ["UPLOAD_DIR"] = str(_test_path / "uploads")


def pytest_sessionfinish() -> None:
    """Close global SQLite pools before Windows removes the temporary files."""
    from app.db import engine
    from app.description_learning_db import description_learning_engine
    from app.learning_db import learning_engine
    from app.type_learning_db import type_learning_engine

    for database_engine in (
        engine,
        learning_engine,
        type_learning_engine,
        description_learning_engine,
    ):
        database_engine.dispose()
    _test_directory.cleanup()
