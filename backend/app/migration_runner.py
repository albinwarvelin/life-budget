from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parent.parent
_migration_lock = Lock()


def upgrade_database_to_head(config_filename: str) -> None:
    """Apply one database's pending Alembic revisions from any working directory.

    Learning stores are separate SQLite files, so it is easy to migrate the
    financial database and accidentally omit one model database. Running this
    guarded check before first model use keeps ORM metadata and tables aligned.
    """
    with _migration_lock:
        config = Config(str(BACKEND_ROOT / config_filename))
        script_location = config.get_main_option("script_location")
        config.set_main_option("script_location", str(BACKEND_ROOT / script_location))
        command.upgrade(config, "head")
