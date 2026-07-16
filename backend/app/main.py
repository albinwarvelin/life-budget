from fastapi import FastAPI

from app.routers.budget import router as budget_router

app = FastAPI(title="Life Budget API", version="0.1.0")
app.include_router(budget_router, prefix="/api/v1", tags=["budget"])


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a lightweight readiness response."""
    return {"status": "ok"}
