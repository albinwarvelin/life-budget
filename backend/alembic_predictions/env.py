from logging.config import fileConfig

from alembic import context
from alembic import op  # noqa: F401 - imported so Alembic can load revision modules
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.prediction_db import PredictionBase
from app import prediction_models  # noqa: F401 - registers learning tables

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().prediction_database_url.replace("%", "%%"))
target_metadata = PredictionBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
