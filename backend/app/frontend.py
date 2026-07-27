from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_production_frontend(app: FastAPI, dist_directory: str | Path) -> None:
    """Serve one validated Vite build with client-side routing fallbacks.

    API paths deliberately remain API-shaped 404 responses instead of returning
    ``index.html``. Every other unknown browser route falls back to the SPA
    entry point so refreshing ``/transactions`` or ``/settings`` still works.
    """
    dist_path = Path(dist_directory).resolve()
    index_path = dist_path / "index.html"
    if not index_path.is_file():
        raise RuntimeError(
            f"Production frontend build not found at {index_path}. "
            "Run `npm run build` in frontend first."
        )

    assets_path = dist_path / "assets"
    if assets_path.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

    @app.get("/{requested_path:path}", include_in_schema=False)
    def serve_frontend(requested_path: str) -> FileResponse:
        if requested_path == "api" or requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")

        candidate = (dist_path / requested_path).resolve()
        # is_relative_to prevents a crafted path from escaping the build
        # directory even if a future web-server layer stops normalizing URLs.
        if candidate.is_relative_to(dist_path) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path)
