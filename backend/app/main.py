from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.frontend import mount_production_frontend
from app.routers.budget import router as budget_router
from app.routers.imports import router as imports_router
from app.routers.learning_models import router as learning_models_router

settings = get_settings()
app = FastAPI(title="Life Budget API", version="0.1.0")
# Vite proxies requests in development, but this also permits an explicit
# VITE_API_BASE_URL when the frontend and backend run on different origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(budget_router, prefix="/api/v1", tags=["budget"])
app.include_router(imports_router, prefix="/api/v1", tags=["imports"])
app.include_router(learning_models_router, prefix="/api/v1", tags=["learning-models"])


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a lightweight readiness response."""
    return {"status": "ok"}


# Register the SPA fallback last so concrete API and health routes always win.
# Development keeps using Vite's dev server and proxy; production serves the
# already-built frontend from the same localhost Uvicorn process.
if settings.app_env.lower() == "production":
    mount_production_frontend(app, settings.frontend_dist_dir)
