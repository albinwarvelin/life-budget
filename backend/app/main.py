from fastapi import FastAPI

app = FastAPI(title="Life Budget API", version="0.1.0")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a lightweight readiness response."""
    return {"status": "ok"}
