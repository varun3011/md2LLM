import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from server.config import FRONTEND_DIR
from server.routes.chat import router as chat_router
from server.routes.frontend import router as frontend_router
from server.routes.jobs import router as jobs_router
from server.routes.models import router as models_router
from server.routes.training import router as training_router

app = FastAPI(title="md2LLM API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_tasks():
    """
    Remove stale per-session training files when the server starts.
    """
    import time

    from server.config import OUTPUT_DIR

    cutoff = time.time() - 86400
    patterns_to_clean = [
        "train_config_*.json",
        "train_progress_*.json",
        "train_config_*.json.tmp",
    ]

    cleaned = 0
    for pattern in patterns_to_clean:
        for file_path in OUTPUT_DIR.glob(pattern):
            try:
                if file_path.stat().st_mtime < cutoff:
                    file_path.unlink()
                    cleaned += 1
            except Exception:
                pass

    if cleaned > 0:
        print(f"Startup: cleaned {cleaned} old session files from output/")
    else:
        print("Startup: output/ folder is clean")


app.include_router(frontend_router)
app.include_router(jobs_router)
app.include_router(models_router)
app.include_router(training_router)
app.include_router(chat_router)

dist_dir = FRONTEND_DIR / "dist"
if dist_dir.exists() and (dist_dir / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")


@app.get("/", response_class=HTMLResponse)
async def root():
    index = dist_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse("<p>Run 'npm run build' in the frontend folder first.</p>")


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_spa(full_path: str):
    """Serve React SPA for all non-API routes."""
    if full_path.startswith("api/") or full_path == "docs" or full_path.startswith("openapi"):
        return HTMLResponse(status_code=404, content="<p>Not found.</p>")
    index = dist_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse("<p>Run 'npm run build' in the frontend folder first.</p>")


if __name__ == "__main__":
    print("\nmd2LLM Server")
    print("─────────────────────────────")
    print("  API:      http://localhost:8000")
    print("  UI:       http://localhost:8000")
    print("  API docs: http://localhost:8000/docs")
    print("─────────────────────────────\n")

    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["pipeline", "server"],
    )
