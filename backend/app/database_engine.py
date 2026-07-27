from typing import Any

from sqlalchemy import Engine, create_engine, event


def create_database_engine(database_url: str, **engine_options: Any) -> Engine:
    """Create an engine with the safety settings shared by every SQLite store."""
    if database_url.startswith("sqlite"):
        connect_args = {
            "check_same_thread": False,
            # Background OCR learning and foreground edits can briefly overlap.
            "timeout": 10,
            **engine_options.pop("connect_args", {}),
        }
        engine_options["connect_args"] = connect_args

    engine = create_engine(database_url, **engine_options)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            # SQLite does not enforce declared foreign keys unless each
            # connection enables them explicitly.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

    return engine
