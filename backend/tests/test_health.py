from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.database_engine import create_database_engine
from app.frontend import mount_production_frontend
from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_frontend_serves_assets_and_spa_routes(tmp_path: Path) -> None:
    """Production serving supports direct navigation without masking bad APIs."""
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<h1>Life Budget</h1>", encoding="utf-8")
    (assets / "app.js").write_text("console.info('ready')", encoding="utf-8")
    production_app = FastAPI()
    mount_production_frontend(production_app, dist)
    production_client = TestClient(production_app)

    assert production_client.get("/").text == "<h1>Life Budget</h1>"
    assert production_client.get("/settings/learning").text == "<h1>Life Budget</h1>"
    assert production_client.get("/assets/app.js").text == "console.info('ready')"
    assert production_client.get("/api/v1/missing").status_code == 404


def test_sqlite_engine_enforces_foreign_keys() -> None:
    engine = create_database_engine("sqlite://", poolclass=StaticPool)

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA busy_timeout")) == 10_000
