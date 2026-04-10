import os

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
