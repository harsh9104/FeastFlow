"""Serve the built React app from the same container as the API.

One origin means no CORS and one thing behind the ALB. Any non-API path that isn't a
real file returns index.html so deep links (/orders/12, /admin/partners) work on refresh.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, static_dir: Path) -> bool:
    index = static_dir / "index.html"
    if not index.is_file():
        return False  # API-only (local dev uses the Vite dev server instead)

    # Hashed filenames (index-abc123.js), so they can be cached for a long time.
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        # index.html must never be cached, or users keep an old build after a deploy.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
