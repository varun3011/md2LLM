import json
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException

from server.config import MODELS_DIR, OUTPUT_DIR
from server.services.registry import create_model

router = APIRouter(prefix="/api")


def _custom_paths_file() -> Path:
    return OUTPUT_DIR / "custom_paths.json"


def _load_custom_paths() -> list[dict]:
    custom_paths_file = _custom_paths_file()
    if not custom_paths_file.exists():
        return []
    try:
        with custom_paths_file.open() as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def _fetch_ollama_models() -> tuple[list[dict], bool]:
    models = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
        if response.status_code != 200:
            return models, False

        data = response.json()
        for model in data.get("models", []):
            name = model.get("name", "")
            models.append(
                {
                    "id": f"ollama:{name}",
                    "name": name,
                    "model_name": name,
                    "source": "ollama",
                    "size_mb": round(model.get("size", 0) / 1024 / 1024, 1),
                    "ready": True,
                    "path": None,
                    "load_command": None,
                }
            )
            create_model(
                model_id=f"ollama_{name.replace(':', '_')}",
                display_name=name,
                base_model_repo=None,
                training_run_id=None,
                dataset_id=None,
                artifact_path=None,
                model_format="ollama",
                readiness_status="ready",
                deployment_status="draft",
                tags=["ollama"],
            )
        return models, True
    except Exception:
        return [], False


@router.get("/models")
async def list_models():
    """
    Returns models from three sources merged together:
    1. Ollama API - models already pulled and ready
    2. Local models/ folder - .gguf files trained by md2LLM
    3. User-added custom paths - stored in output/custom_paths.json
    """
    models, ollama_running = await _fetch_ollama_models()

    if MODELS_DIR.exists():
        for model_file in MODELS_DIR.glob("*.gguf"):
            already_in_ollama = any(
                model["name"] == model_file.stem for model in models if model["source"] == "ollama"
            )
            models.append(
                {
                    "id": f"local:{model_file.stem}",
                    "name": model_file.stem,
                    "model_name": model_file.stem,
                    "source": "local",
                    "size_mb": round(model_file.stat().st_size / 1024 / 1024, 1),
                    "ready": already_in_ollama,
                    "path": str(model_file),
                    "load_command": f"ollama run {model_file}",
                }
            )
            create_model(
                model_id=f"local_{model_file.stem}",
                display_name=model_file.stem,
                base_model_repo=None,
                training_run_id=None,
                dataset_id=None,
                artifact_path=str(model_file),
                model_format="gguf",
                readiness_status="ready" if already_in_ollama else "available",
                deployment_status="draft",
                tags=["local"],
            )

    for entry in _load_custom_paths():
        raw_path = entry.get("path", "")
        path = Path(raw_path)
        if path.exists():
            already_in_ollama = any(
                model["name"] == path.stem for model in models if model["source"] == "ollama"
            )
            models.append(
                {
                    "id": f"custom:{path.stem}",
                    "name": entry.get("label") or path.stem,
                    "model_name": path.stem,
                    "source": "custom",
                    "size_mb": round(path.stat().st_size / 1024 / 1024, 1),
                    "ready": already_in_ollama,
                    "path": str(path),
                    "load_command": f"ollama run {path}",
                }
            )
            create_model(
                model_id=f"custom_{path.stem}",
                display_name=entry.get("label") or path.stem,
                base_model_repo=None,
                training_run_id=None,
                dataset_id=None,
                artifact_path=str(path),
                model_format="gguf",
                readiness_status="ready" if already_in_ollama else "available",
                deployment_status="draft",
                tags=["custom"],
            )
        else:
            models.append(
                {
                    "id": f"custom:{raw_path}",
                    "name": entry.get("label") or Path(raw_path).stem,
                    "model_name": Path(raw_path).stem,
                    "source": "custom",
                    "size_mb": 0,
                    "ready": False,
                    "path": raw_path,
                    "load_command": None,
                    "error": "File not found",
                }
            )

    return {
        "models": models,
        "ollama_running": ollama_running,
        "total": len(models),
        "ready_count": sum(1 for model in models if model["ready"]),
    }


@router.post("/models/add")
async def add_custom_model(
    path: str = Form(...),
    label: str = Form(default=""),
):
    """
    Add a custom model path provided by the user.
    Validates the file exists and is a .gguf file.
    Saves to output/custom_paths.json.
    """
    model_path = Path(path.strip()).expanduser()

    if not model_path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    if model_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Choose a .gguf model file, not a folder",
        )
    if not model_path.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    if model_path.suffix.lower() != ".gguf":
        raise HTTPException(status_code=400, detail="Only .gguf model files are supported")

    custom_paths = _load_custom_paths()
    existing_paths = [entry.get("path") for entry in custom_paths]
    normalized_path = str(model_path.resolve())
    if normalized_path in existing_paths or str(model_path) in existing_paths:
        raise HTTPException(status_code=400, detail="This model path is already added")

    new_entry = {
        "path": normalized_path,
        "label": label.strip() or model_path.stem,
        "added_at": str(model_path.stat().st_mtime),
    }
    custom_paths.append(new_entry)

    OUTPUT_DIR.mkdir(exist_ok=True)
    with _custom_paths_file().open("w") as file:
        json.dump(custom_paths, file, indent=2)

    return {
        "message": "Model added successfully",
        "model": {
            "name": new_entry["label"],
            "path": new_entry["path"],
            "size_mb": round(model_path.stat().st_size / 1024 / 1024, 1),
        },
    }


@router.delete("/models/remove")
async def remove_custom_model(path: str):
    """
    Remove a custom model path from the saved list.
    Only removes from the list - does not delete the actual file.
    """
    custom_paths_file = _custom_paths_file()
    if not custom_paths_file.exists():
        raise HTTPException(status_code=404, detail="No custom models found")

    with custom_paths_file.open() as file:
        custom_paths = json.load(file)

    original_count = len(custom_paths)
    custom_paths = [entry for entry in custom_paths if entry["path"] != path]

    if len(custom_paths) == original_count:
        raise HTTPException(status_code=404, detail="Model path not found")

    with custom_paths_file.open("w") as file:
        json.dump(custom_paths, file, indent=2)

    return {"message": "Model removed from list"}


@router.get("/models/ollama-status")
async def ollama_status():
    """
    Quick check if Ollama is running.
    Used by frontend to show helpful message if not running.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("models", []))
            return {
                "running": True,
                "model_count": model_count,
                "message": f"Ollama running with {model_count} models",
            }
    except Exception:
        pass

    return {
        "running": False,
        "model_count": 0,
        "message": "Ollama not running. Start it with: ollama serve",
    }
