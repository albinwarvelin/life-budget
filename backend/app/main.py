from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.budget import router as budget_router

app = FastAPI(title="Life Budget API", version="0.1.0")
# Vite proxies requests in development, but this also permits an explicit
# VITE_API_BASE_URL when the frontend and backend run on different origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(budget_router, prefix="/api/v1", tags=["budget"])


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a lightweight readiness response."""
    return {"status": "ok"}
