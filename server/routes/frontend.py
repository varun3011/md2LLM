import os

import httpx
from fastapi import APIRouter

from server.config import MODELS_DIR, OUTPUT_DIR

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "output_dir": str(OUTPUT_DIR),
        "models_dir": str(MODELS_DIR),
    }


@router.get("/setup/status")
async def setup_status():
    ollama_running = False
    ollama_model_count = 0

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            ollama_running = True
            ollama_model_count = len(response.json().get("models", []))
    except Exception:
        pass

    local_model_count = len(list(MODELS_DIR.glob("*.gguf"))) if MODELS_DIR.exists() else 0
    training_data_files = []
    if OUTPUT_DIR.exists():
        training_data_files = [
            path
            for path in OUTPUT_DIR.glob("*training_data.jsonl")
            if path.is_file()
        ]

    return {
        "backend_running": True,
        "frontend_running": True,
        "ollama_running": ollama_running,
        "models_found": ollama_model_count + local_model_count > 0,
        "training_data_exists": len(training_data_files) > 0,
        "model_count": ollama_model_count + local_model_count,
        "ollama_model_count": ollama_model_count,
        "local_model_count": local_model_count,
        "training_data_files": len(training_data_files),
    }
