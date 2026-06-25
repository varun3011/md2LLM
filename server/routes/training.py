import platform
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, HTTPException

from server.config import MODELS_DIR, OUTPUT_DIR, PROJECT_ROOT
from server.services.evaluation import run_model_evaluation
from server.services.registry import (
    add_run_event,
    append_run_log,
    create_basic_evaluation,
    get_dataset,
    create_model,
    create_run,
    update_run,
)
from server.state import jobs, training_jobs

router = APIRouter(prefix="/api/training", tags=["training"])

# Priority ordered list of models known to work well for fine-tuning.
# Lower priority number = higher priority recommendation.
KNOWN_MODELS = [
    {
        "id": "llama3.2:3b",
        "display_name": "Llama 3.2 3B",
        "reason": "Best balance of quality and speed for fine-tuning",
        "min_vram_gb": 6,
        "size_gb": 2.8,
        "good_for": ["knowledge", "reasoning", "chatbot", "style"],
        "priority": 1,
        "recommended_for_mac": True,
    },
    {
        "id": "llama3.2:1b",
        "display_name": "Llama 3.2 1B",
        "reason": "Lightweight, runs on almost any machine",
        "min_vram_gb": 2,
        "size_gb": 1.3,
        "good_for": ["knowledge"],
        "priority": 2,
        "recommended_for_mac": True,
    },
    {
        "id": "phi3:mini",
        "display_name": "Phi-3 Mini",
        "reason": "Excellent on Mac Apple Silicon, very efficient",
        "min_vram_gb": 4,
        "size_gb": 2.3,
        "good_for": ["knowledge", "style"],
        "priority": 3,
        "recommended_for_mac": True,
    },
    {
        "id": "phi3:medium",
        "display_name": "Phi-3 Medium",
        "reason": "Higher quality Phi model, needs more memory",
        "min_vram_gb": 8,
        "size_gb": 7.9,
        "good_for": ["knowledge", "reasoning", "style"],
        "priority": 4,
        "recommended_for_mac": False,
    },
    {
        "id": "mistral:7b",
        "display_name": "Mistral 7B",
        "reason": "High quality results, needs more VRAM",
        "min_vram_gb": 10,
        "size_gb": 4.1,
        "good_for": ["knowledge", "reasoning", "style", "chatbot"],
        "priority": 5,
        "recommended_for_mac": False,
    },
    {
        "id": "qwen2.5:1.5b",
        "display_name": "Qwen 2.5 1.5B",
        "reason": "Smallest option, runs on CPU if needed",
        "min_vram_gb": 2,
        "size_gb": 1.0,
        "good_for": ["knowledge"],
        "priority": 6,
        "recommended_for_mac": True,
    },
    {
        "id": "qwen2.5:7b",
        "display_name": "Qwen 2.5 7B",
        "reason": "Strong quality, good for complex knowledge bases",
        "min_vram_gb": 8,
        "size_gb": 4.7,
        "good_for": ["knowledge", "reasoning", "chatbot"],
        "priority": 7,
        "recommended_for_mac": False,
    },
]

# Curated training model recommendations. Users can also provide any
# HuggingFace repo ID directly.
RECOMMENDED_MODELS = [
    {
        "hf_repo": "Qwen/Qwen2.5-1.5B-Instruct",
        "display_name": "Qwen 2.5 1.5B",
        "description": "Smallest option - runs on any Mac",
        "size_gb": 3.0,
        "min_ram_gb": 8,
        "needs_token": False,
        "good_for": ["knowledge", "style"],
        "recommended_for": ["cpu", "mlx"],
        "badge": "No token needed",
        "badge_color": "green",
    },
    {
        "hf_repo": "microsoft/Phi-3-mini-4k-instruct",
        "display_name": "Phi-3 Mini",
        "description": "Great quality for its size on Apple Silicon",
        "size_gb": 7.6,
        "min_ram_gb": 16,
        "needs_token": False,
        "good_for": ["knowledge", "style", "reasoning"],
        "recommended_for": ["mlx"],
        "badge": "No token needed",
        "badge_color": "green",
    },
    {
        "hf_repo": "Qwen/Qwen2.5-3B-Instruct",
        "display_name": "Qwen 2.5 3B",
        "description": "Good balance of quality and speed",
        "size_gb": 6.2,
        "min_ram_gb": 16,
        "needs_token": False,
        "good_for": ["knowledge", "reasoning", "chatbot"],
        "recommended_for": ["mlx", "unsloth"],
        "badge": "No token needed",
        "badge_color": "green",
    },
    {
        "hf_repo": "meta-llama/Llama-3.2-3B-Instruct",
        "display_name": "Llama 3.2 3B",
        "description": "Best quality for fine-tuning - needs HF token",
        "size_gb": 6.0,
        "min_ram_gb": 16,
        "needs_token": True,
        "good_for": ["knowledge", "reasoning", "chatbot", "style"],
        "recommended_for": ["mlx", "unsloth"],
        "badge": "Needs HF token",
        "badge_color": "amber",
    },
    {
        "hf_repo": "meta-llama/Llama-3.2-1B-Instruct",
        "display_name": "Llama 3.2 1B",
        "description": "Lightweight Llama - needs HF token",
        "size_gb": 2.5,
        "min_ram_gb": 8,
        "needs_token": True,
        "good_for": ["knowledge"],
        "recommended_for": ["mlx", "cpu"],
        "badge": "Needs HF token",
        "badge_color": "amber",
    },
    {
        "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
        "display_name": "Qwen 2.5 7B",
        "description": "High quality - needs 32GB+ RAM",
        "size_gb": 15.0,
        "min_ram_gb": 32,
        "needs_token": False,
        "good_for": ["knowledge", "reasoning", "chatbot", "style"],
        "recommended_for": ["mlx", "unsloth"],
        "badge": "No token needed",
        "badge_color": "green",
    },
]

# Gated models that require HuggingFace token.
GATED_MODELS = {
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Llama-3.2-1B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "meta-llama/Meta-Llama-3-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "mistralai/Mistral-7B-Instruct-v0.2",
}

# Fallback sizes if HuggingFace API is unavailable.
FALLBACK_SIZES_GB = {
    "meta-llama/Llama-3.2-3B-Instruct": 6.0,
    "meta-llama/Llama-3.2-1B-Instruct": 2.5,
    "meta-llama/Llama-3.1-8B-Instruct": 15.0,
    "microsoft/Phi-3-mini-4k-instruct": 7.6,
    "microsoft/Phi-3-medium-4k-instruct": 14.0,
    "microsoft/Phi-3.5-mini-instruct": 7.6,
    "mistralai/Mistral-7B-Instruct-v0.3": 14.5,
    "Qwen/Qwen2.5-1.5B-Instruct": 3.0,
    "Qwen/Qwen2.5-3B-Instruct": 6.2,
    "Qwen/Qwen2.5-7B-Instruct": 15.0,
    "Qwen/Qwen2.5-14B-Instruct": 29.0,
    "Qwen/Qwen3-1.7B": 3.5,
    "Qwen/Qwen3-4B": 8.0,
    "Qwen/Qwen3-8B": 16.0,
    "google/gemma-2-2b-it": 5.0,
    "google/gemma-2-9b-it": 18.0,
}


@router.get("/recommended-models")
async def get_recommended_models(
    approach: str = "mlx",
    goal: str = "knowledge",
    ram_gb: float = 16.0,
):
    """
    Return curated HuggingFace training model recommendations.
    """
    filtered = []
    for model in RECOMMENDED_MODELS:
        if approach not in model["recommended_for"] and "cpu" not in model["recommended_for"]:
            continue
        if model["min_ram_gb"] > ram_gb:
            continue
        if goal not in model["good_for"]:
            continue
        filtered.append({**model})

    filtered.sort(key=lambda model: model["size_gb"])
    if filtered:
        filtered[0]["top_pick"] = True

    return {
        "models": filtered,
        "approach": approach,
        "goal": goal,
        "ram_gb": ram_gb,
    }


@router.get("/recommend")
async def recommend_model(goal: str = "knowledge"):
    """
    Step 1 - Model recommendation based on installed Ollama models and hardware.
    """
    installed_models = []
    ollama_running = False

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            ollama_running = True
            data = response.json()
            installed_models = [
                {
                    "name": model["name"],
                    "size_mb": round(model.get("size", 0) / 1024 / 1024, 1),
                }
                for model in data.get("models", [])
            ]
    except Exception:
        ollama_running = False

    hardware = detect_hardware()

    installed_names = [model["name"] for model in installed_models]
    available_known = []

    for known in KNOWN_MODELS:
        for installed in installed_names:
            if installed == known["id"] or installed.startswith(f"{known['id']}-"):
                fits_hardware = True
                warning = None

                if hardware["vram_gb"] is not None:
                    if known["min_vram_gb"] > hardware["vram_gb"]:
                        fits_hardware = False
                        warning = (
                            f"Needs {known['min_vram_gb']}GB VRAM "
                            f"but only {hardware['vram_gb']}GB detected"
                        )
                elif hardware["ram_gb"] is not None:
                    if known["min_vram_gb"] > hardware["ram_gb"] * 0.6:
                        fits_hardware = False
                        warning = f"May not fit in available RAM ({hardware['ram_gb']}GB)"

                available_known.append(
                    {
                        **known,
                        "installed": True,
                        "installed_name": installed,
                        "fits_hardware": fits_hardware,
                        "warning": warning,
                    }
                )
                break

    recommended = None

    if available_known:
        goal_compatible = [model for model in available_known if goal in model.get("good_for", [])]
        fits = [model for model in (goal_compatible or available_known) if model["fits_hardware"]]

        if hardware["is_mac_silicon"]:
            mac_friendly = [
                model
                for model in (fits or goal_compatible or available_known)
                if model.get("recommended_for_mac")
            ]
            pool = mac_friendly or fits or goal_compatible or available_known
        else:
            pool = fits or goal_compatible or available_known

        if pool:
            recommended = min(pool, key=lambda model: model["priority"])

    suggestion = None
    if not available_known:
        suggestion = {
            "model": "llama3.2:3b",
            "command": "ollama pull llama3.2:3b",
            "reason": "Best starting model for fine-tuning md2LLM",
            "size_gb": 2.8,
            "time_estimate": "~2 min download on fast internet",
        }

    known_installed_names = {model["installed_name"] for model in available_known}
    other_models = [
        {
            "id": model["name"],
            "display_name": model["name"],
            "installed": True,
            "installed_name": model["name"],
            "reason": "Installed on your machine",
            "known_for_finetuning": False,
            "size_gb": round(model["size_mb"] / 1024, 1),
            "good_for": ["knowledge"],
            "fits_hardware": True,
            "warning": None,
        }
        for model in installed_models
        if model["name"] not in known_installed_names
    ]

    return {
        "recommended": recommended,
        "known_models": available_known,
        "other_models": other_models,
        "hardware": hardware,
        "ollama_running": ollama_running,
        "goal": goal,
        "suggestion": suggestion,
        "total_installed": len(installed_models),
    }


@router.get("/hardware")
async def get_hardware():
    """
    Step 2 - Full hardware detection.
    """
    hardware = detect_hardware()
    hardware["time_estimates"] = get_time_estimates(hardware)
    hardware["approach_details"] = get_approach_details(hardware)
    hardware["requirements"] = get_requirements(hardware)
    return hardware


@router.get("/training-recommendation")
async def training_recommendation(
    ram_gb: float = 8.0,
    approach: str = "mlx",
    vram_gb: float = 0.0,
    is_mac_silicon: bool = False,
):
    """
    Return whether device can handle local training.
    Called by frontend to decide which UI to show.
    """
    hardware = {
        "ram_gb": ram_gb,
        "training_approach": approach,
        "vram_gb": vram_gb if vram_gb > 0 else None,
        "is_mac_silicon": is_mac_silicon,
        "is_mac": is_mac_silicon,
        "gpu_detected": vram_gb > 0,
    }
    return get_training_recommendation(hardware)


@router.post("/configure")
async def configure_training(
    model_name: str = Form(...),
    hf_repo: str = Form(default=""),
    goal: str = Form(default="knowledge"),
    output_name: str = Form(default=""),
    output_dir: str = Form(default=""),
    epochs: int = Form(default=3),
    learning_rate: str = Form(default="auto"),
    job_id: str = Form(default=""),
    session_id: str = Form(default=""),
):
    """
    Step 3 - Validate and save training configuration.
    """
    import json
    import re
    import time

    errors = []
    hf_repo = (hf_repo or model_name).strip()

    if not session_id:
        timestamp = int(time.time())
        short_job = job_id[:6] if job_id else "new"
        session_id = f"{timestamp}_{short_job}"

    if not hf_repo or "/" not in hf_repo:
        errors.append(
            "Training model must be a valid HuggingFace repo ID, "
            "for example Qwen/Qwen2.5-1.5B-Instruct"
        )

    cleaned_output_name = output_name.strip()
    if not cleaned_output_name:
        base = hf_repo.split("/")[-1]
        base = re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-").lower()
        timestamp = datetime.now().strftime("%m%d")
        cleaned_output_name = f"md2llm-{base}-{timestamp}"
    else:
        cleaned_output_name = cleaned_output_name.lower()
        if not re.match(r"^[a-zA-Z0-9_-]+$", cleaned_output_name):
            errors.append(
                "Output name can only contain letters, numbers, hyphens, and underscores"
            )
        if len(cleaned_output_name) > 50:
            errors.append("Output name must be 50 characters or less")

    resolved_output_dir = resolve_model_output_dir(output_dir, errors)

    if not 1 <= epochs <= 5:
        errors.append("Epochs must be between 1 and 5")

    pair_count = 0
    data_file = resolve_training_data_file(job_id)
    if data_file and data_file.exists():
        with data_file.open() as handle:
            pair_count = sum(1 for line in handle if line.strip())
    else:
        errors.append("No training data found. Generate training data first.")

    if learning_rate == "auto" or not learning_rate:
        if pair_count < 200:
            lr = "1e-4"
            lr_note = "Lower rate for small dataset to prevent overfitting"
        elif pair_count < 500:
            lr = "2e-4"
            lr_note = "Standard rate for medium dataset"
        else:
            lr = "2e-4"
            lr_note = "Standard rate for large dataset"
    else:
        lr = learning_rate
        lr_note = "User specified"

    hardware = detect_hardware()
    hardware["time_estimates"] = get_time_estimates(hardware)
    hardware["approach_details"] = get_approach_details(hardware)
    hardware["requirements"] = get_requirements(hardware)
    recommendation = get_training_recommendation(hardware)

    time_estimate = calculate_time_estimate(
        pair_count=pair_count,
        epochs=epochs,
        hardware=hardware,
        model_name=hf_repo,
    )

    config = {
        "model_name": model_name,
        "hf_repo": hf_repo,
        "output_name": cleaned_output_name,
        "output_dir": str(resolved_output_dir),
        "output_path": str(resolved_output_dir / cleaned_output_name),
        "goal": goal,
        "epochs": epochs,
        "learning_rate": lr,
        "learning_rate_note": lr_note,
        "pair_count": pair_count,
        "data_file": str(data_file) if data_file else None,
        "job_id": job_id,
        "session_id": session_id,
        "hardware": hardware,
        "recommendation": recommendation,
        "time_estimate": time_estimate,
        "lora_rank": calculate_lora_rank(pair_count),
        "batch_size": calculate_batch_size(hardware),
        "max_seq_length": 2048,
        "valid": len(errors) == 0,
        "errors": errors,
    }

    config_file = OUTPUT_DIR / f"train_config_{session_id}.json"
    config["config_file"] = str(config_file)

    if config["valid"]:
        with config_file.open("w") as handle:
            json.dump(config, handle, indent=2, default=str)

    return config


@router.get("/config")
async def get_config(session_id: str = ""):
    """
    Load training configuration for a specific session.
    """
    import json

    if session_id:
        config_file = OUTPUT_DIR / f"train_config_{session_id}.json"
        if not config_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Config for session {session_id} not found",
            )
    else:
        config_files = sorted(
            OUTPUT_DIR.glob("train_config_*.json"),
            key=lambda file_path: file_path.stat().st_mtime,
            reverse=True,
        )
        if not config_files:
            raise HTTPException(
                status_code=404,
                detail="No training config found. Configure training first.",
            )
        config_file = config_files[0]

    with config_file.open() as handle:
        return json.load(handle)


async def _get_hf_repo_size(hf_repo: str, token: str = None) -> float | None:
    """
    Get the actual download size of a HuggingFace repo
    by summing .safetensors and .bin file sizes via HF API.
    Returns size in GB or falls back to FALLBACK_SIZES_GB.
    """
    try:
        import asyncio

        from huggingface_hub import HfApi

        loop = asyncio.get_event_loop()

        def _fetch():
            api = HfApi()
            info = api.repo_info(
                repo_id=hf_repo,
                token=token,
                files_metadata=True,
            )
            total = sum(
                getattr(file_info, "size", 0) or 0
                for file_info in info.siblings
                if (
                    file_info.rfilename.endswith(".safetensors")
                    or file_info.rfilename.endswith(".bin")
                )
                and not any(
                    skip in file_info.rfilename
                    for skip in ("flax_model", "tf_model", "rust_model")
                )
            )
            return round(total / 1024**3, 1) if total > 0 else None

        size = await loop.run_in_executor(None, _fetch)
        return size or FALLBACK_SIZES_GB.get(hf_repo)
    except Exception:
        return FALLBACK_SIZES_GB.get(hf_repo)


@router.get("/check-model")
async def check_model_cache(hf_repo: str):
    """
    Check if a HuggingFace model is already cached locally.
    """
    import os

    if not hf_repo or "/" not in hf_repo:
        raise HTTPException(
            status_code=400,
            detail=(
                "hf_repo must be a valid HuggingFace repo ID "
                "in format 'author/model-name'. "
                "Example: Qwen/Qwen2.5-1.5B-Instruct"
            ),
        )

    hf_repo = hf_repo.strip().strip('"').strip("'")
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")

    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    cache_folder = "models--" + hf_repo.replace("/", "--")
    cache_path = hf_cache / cache_folder

    cached = False
    cached_snapshot = None

    if cache_path.exists():
        snapshots_dir = cache_path / "snapshots"
        if snapshots_dir.exists():
            for snapshot in snapshots_dir.iterdir():
                if snapshot.is_dir():
                    model_files = list(snapshot.glob("*.safetensors")) + list(snapshot.glob("*.bin"))
                    if model_files:
                        cached = True
                        cached_snapshot = str(snapshot)
                        break

    size_gb = await _get_hf_repo_size(hf_repo, token)

    needs_hf_token = hf_repo in GATED_MODELS
    hf_token_set = bool(token)

    return {
        "hf_repo": hf_repo,
        "cached": cached,
        "cached_snapshot": cached_snapshot,
        "supported": True,
        "cache_path": str(cache_path),
        "size_gb": size_gb,
        "needs_hf_token": needs_hf_token,
        "hf_token_set": hf_token_set,
        "needs_token_setup": needs_hf_token and not hf_token_set,
        "message": (
            "Model cached locally - ready to train"
            if cached
            else (
                f"Will download ~{size_gb} GB from HuggingFace"
                if size_gb
                else "Will download from HuggingFace"
            )
        ),
        "setup_instructions": (
            {
                "steps": [
                    "Go to huggingface.co and create a free account",
                    f"Accept the license at huggingface.co/{hf_repo}",
                    "Get your token at huggingface.co/settings/tokens",
                    "Add to your .env file: HF_TOKEN=hf_your_token_here",
                    "Restart the server and try again",
                ]
            }
            if needs_hf_token and not hf_token_set
            else None
        ),
    }


# Dependency Check and Install


@router.get("/check-deps")
async def check_dependencies(approach: str = "mlx"):
    """
    Check whether the training dependencies are installed for the hardware path.
    """
    if approach in ("cpu", "colab"):
        return {
            "approach": approach,
            "installed": False,
            "ready": False,
            "missing": [],
            "install_command": None,
            "can_auto_install": False,
            "colab_required": True,
            "message": "No local GPU - use Google Colab for training",
        }

    if approach == "mlx":
        return await _check_mlx_deps()
    if approach in ("unsloth", "unsloth_small"):
        return await _check_unsloth_deps()

    return {
        "approach": approach,
        "installed": False,
        "ready": False,
        "missing": [approach],
        "message": f"Unknown approach: {approach}",
    }


async def _check_mlx_deps() -> dict:
    """
    Check if MLX is installed for Mac Apple Silicon training.
    """
    import importlib.util
    import sys

    python_version = platform.python_version()
    python_runtime_supported = sys.version_info < (3, 14)

    checks = {
        "mlx": importlib.util.find_spec("mlx") is not None,
        "mlx_lm": importlib.util.find_spec("mlx_lm") is not None,
        "apple_silicon": "arm" in platform.machine().lower(),
        "python_runtime": python_runtime_supported,
    }
    all_installed = all(checks.values())
    missing = [name for name, passed in checks.items() if not passed]
    needs_python_env = not python_runtime_supported

    setup_steps = None
    if needs_python_env:
        setup_steps = [
            "Install Python 3.12 or 3.13 if it is not already installed.",
            "Create a new virtual environment: python3.12 -m venv .venv",
            "Activate it: source .venv/bin/activate",
            "Install dependencies: pip install -r requirements.txt",
            "Install MLX: pip install -r requirements-mlx.txt",
            "Restart the backend from the activated environment.",
        ]

    return {
        "approach": "mlx",
        "installed": checks["mlx"] and checks["mlx_lm"] and checks["apple_silicon"],
        "ready": all_installed,
        "checks": checks,
        "missing": missing,
        "python_version": python_version,
        "install_command": (
            "python3.12 -m venv .venv && source .venv/bin/activate && "
            "pip install -r requirements.txt && pip install -r requirements-mlx.txt"
            if needs_python_env
            else "pip install mlx-lm" if not all_installed else None
        ),
        "can_auto_install": not needs_python_env,
        "estimated_install_time": "2-3 minutes",
        "package_size": "~500 MB",
        "setup_steps": setup_steps,
        "message": (
            "MLX is installed and ready for training"
            if all_installed
            else (
                "MLX is installed, but this server is running on Python "
                f"{python_version}. Use Python 3.12 or 3.13 for MLX training."
            )
            if needs_python_env
            else "MLX needs to be installed for Apple Silicon training"
        ),
    }


async def _check_unsloth_deps() -> dict:
    """
    Check if Unsloth and CUDA PyTorch are installed for NVIDIA GPU training.
    """
    import importlib.util

    checks = {
        "torch": False,
        "torch_cuda": False,
        "unsloth": importlib.util.find_spec("unsloth") is not None,
        "trl": importlib.util.find_spec("trl") is not None,
        "peft": importlib.util.find_spec("peft") is not None,
    }
    cuda_version = None
    torch_version = None

    try:
        import torch

        checks["torch"] = True
        torch_version = torch.__version__
        checks["torch_cuda"] = torch.cuda.is_available()
        if checks["torch_cuda"]:
            cuda_version = torch.version.cuda
    except ImportError:
        pass

    all_installed = all(checks.values())
    missing = [name for name, passed in checks.items() if not passed]
    steps = _build_unsloth_steps(checks, cuda_version, torch_version)

    return {
        "approach": "unsloth",
        "installed": all_installed,
        "ready": all_installed,
        "checks": checks,
        "missing": missing,
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "can_auto_install": False,
        "steps": steps,
        "docs_url": "docs/gpu-setup.md",
        "message": (
            f"Unsloth ready - CUDA {cuda_version}, PyTorch {torch_version}"
            if all_installed
            else "Unsloth setup required for NVIDIA GPU training"
        ),
    }


def _build_unsloth_steps(
    checks: dict,
    cuda_version: str | None,
    torch_version: str | None = None,
) -> list:
    """
    Build a step-by-step install guide based on installed packages.
    """
    steps = [
        {
            "number": 1,
            "title": "Verify NVIDIA drivers are installed",
            "command": "nvidia-smi",
            "done": checks.get("torch_cuda", False),
            "note": (
                "If nvidia-smi works you have drivers. "
                "If not, visit nvidia.com/drivers to install."
            ),
            "expected_output": "NVIDIA-SMI shows your GPU model and driver version",
        }
    ]

    if not checks.get("torch") or not checks.get("torch_cuda"):
        cuda_install = _get_torch_cuda_command(cuda_version)
        steps.append(
            {
                "number": 2,
                "title": "Install PyTorch with CUDA support",
                "command": cuda_install["command"],
                "done": checks.get("torch_cuda", False),
                "note": cuda_install["note"],
                "expected_output": "Successfully installed torch",
            }
        )
    else:
        steps.append(
            {
                "number": 2,
                "title": "PyTorch with CUDA",
                "command": None,
                "done": True,
                "note": f"Already installed - PyTorch {torch_version} with CUDA {cuda_version}",
            }
        )

    steps.append(
        {
            "number": 3,
            "title": "Verify CUDA is working",
            "command": 'python -c "import torch; print(torch.cuda.is_available())"',
            "done": checks.get("torch_cuda", False),
            "note": "Should print True. If False, your PyTorch does not have CUDA support.",
            "expected_output": "True",
        }
    )

    if not checks.get("unsloth"):
        steps.append(
            {
                "number": 4,
                "title": "Install Unsloth",
                "command": "pip install unsloth",
                "done": False,
                "note": "Unsloth makes QLoRA training faster and more memory efficient.",
                "expected_output": "Successfully installed unsloth",
            }
        )
    else:
        steps.append(
            {
                "number": 4,
                "title": "Unsloth",
                "command": None,
                "done": True,
                "note": "Already installed",
            }
        )

    missing_extras = [
        package
        for package in ("trl", "peft")
        if not checks.get(package)
    ]
    if missing_extras:
        steps.append(
            {
                "number": 5,
                "title": "Install training utilities",
                "command": f"pip install {' '.join(missing_extras)}",
                "done": False,
                "note": "TRL and PEFT are required for supervised fine-tuning.",
                "expected_output": "Successfully installed",
            }
        )
    else:
        steps.append(
            {
                "number": 5,
                "title": "Training utilities (TRL, PEFT)",
                "command": None,
                "done": True,
                "note": "Already installed",
            }
        )

    steps.append(
        {
            "number": 6,
            "title": "Come back and verify",
            "command": None,
            "done": all(checks.values()),
            "note": (
                "After installing, click the Check Again button below. "
                "All steps should show as complete."
            ),
        }
    )
    return steps


def _get_torch_cuda_command(cuda_version: str | None) -> dict:
    """
    Return the PyTorch pip install command for the detected CUDA version.
    """
    if cuda_version:
        try:
            major, minor = cuda_version.split(".")[:2]
            cuda_tag = f"cu{major}{minor}"
        except Exception:
            cuda_tag = "cu121"
    else:
        cuda_tag = "cu121"

    command = (
        "pip install torch torchvision torchaudio "
        f"--index-url https://download.pytorch.org/whl/{cuda_tag}"
    )
    notes = {
        "cu121": "For CUDA 12.1 (most common for RTX 30xx and 40xx cards)",
        "cu118": "For CUDA 11.8 (for older cards or drivers)",
        "cu124": "For CUDA 12.4 (latest NVIDIA drivers)",
    }

    return {
        "command": command,
        "cuda_tag": cuda_tag,
        "note": notes.get(cuda_tag, f"For CUDA {cuda_version}"),
    }


@router.post("/install-deps")
async def install_dependencies(approach: str = Form(...)):
    """
    Auto-install training dependencies when safe.

    Only MLX is auto-installed. NVIDIA/CUDA setup remains manual because
    the correct PyTorch wheel depends on local drivers and CUDA support.
    """
    import asyncio
    import sys
    import uuid

    from server.state import install_jobs

    if approach != "mlx":
        raise HTTPException(
            status_code=400,
            detail=(
                "Auto install only supported for MLX. "
                "For NVIDIA GPU please follow the manual steps shown."
            ),
        )

    if sys.version_info >= (3, 14):
        raise HTTPException(
            status_code=400,
            detail=(
                "MLX cannot be auto-installed into this running Python "
                f"{platform.python_version()} environment. Start the backend "
                "from a Python 3.12 or 3.13 virtual environment, then run "
                "the MLX install again."
            ),
        )

    install_job_id = str(uuid.uuid4())[:8]
    install_jobs[install_job_id] = {
        "id": install_job_id,
        "approach": approach,
        "status": "running",
        "progress": 0,
        "message": "Starting MLX installation...",
        "log": [],
        "error": None,
    }

    asyncio.create_task(_run_install(install_job_id, approach))

    return {
        "install_job_id": install_job_id,
        "status": "started",
        "message": "Installation started",
    }


async def _run_install(install_job_id: str, approach: str):
    """
    Run pip install in the background and stream output into install_jobs.
    """
    import asyncio
    import sys

    from server.state import install_jobs

    def update(progress: int, message: str, log_line: str | None = None):
        install_jobs[install_job_id]["progress"] = progress
        install_jobs[install_job_id]["message"] = message
        if log_line:
            install_jobs[install_job_id]["log"].append(log_line)

    try:
        packages = {
            "mlx": ["mlx-lm"],
        }

        pkgs = packages.get(approach, [])
        if not pkgs:
            raise ValueError(f"No packages defined for approach: {approach}")

        update(5, f"Installing {', '.join(pkgs)}...")

        for index, package in enumerate(pkgs):
            update(
                10 + (index * 30),
                f"Installing {package}...",
                f"$ pip install {package}",
            )

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                package,
                "--no-cache-dir",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded = line.decode(errors="replace").strip()
                if decoded:
                    install_jobs[install_job_id]["log"].append(decoded)
                    if "Downloading" in decoded:
                        update(
                            20 + (index * 30),
                            f"Downloading {package}...",
                            decoded,
                        )
                    elif "Installing" in decoded:
                        update(
                            50 + (index * 30),
                            f"Installing {package}...",
                            decoded,
                        )

            await process.wait()

            if process.returncode != 0:
                raise ValueError(
                    f"pip install {package} failed with exit code {process.returncode}"
                )

            update(
                40 + (index * 40),
                f"{package} installed successfully",
                f"{package} installed",
            )

        install_jobs[install_job_id].update(
            {
                "status": "complete",
                "progress": 100,
                "message": "Installation complete - ready to train",
            }
        )

    except Exception as exc:
        install_jobs[install_job_id].update(
            {
                "status": "error",
                "error": str(exc),
                "message": f"Installation failed: {str(exc)}",
            }
        )


@router.get("/install-status/{install_job_id}")
async def install_status_stream(install_job_id: str):
    """
    SSE stream for dependency install progress.
    """
    import asyncio
    import json

    from fastapi.responses import StreamingResponse
    from server.state import install_jobs

    if install_job_id not in install_jobs:
        raise HTTPException(status_code=404, detail="Install job not found")

    async def event_stream():
        while True:
            job = install_jobs.get(install_job_id, {})
            yield f"data: {json.dumps(job)}\n\n"
            if job.get("status") in ("complete", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/start")
async def start_training(session_id: str = Form(default="")):
    """
    Start training using the config saved by the configure endpoint.
    """
    import asyncio
    import json
    import uuid

    if session_id:
        config_file = OUTPUT_DIR / f"train_config_{session_id}.json"
        if not config_file.exists():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Config for session {session_id} not found. "
                    "Complete the configuration step first."
                ),
            )
    else:
        config_files = sorted(
            OUTPUT_DIR.glob("train_config_*.json"),
            key=lambda file_path: file_path.stat().st_mtime,
            reverse=True,
        )
        if not config_files:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No training config found. "
                    "Complete the configuration step first."
                ),
            )
        config_file = config_files[0]

    with config_file.open() as handle:
        config = json.load(handle)
    session_id = config.get("session_id") or session_id
    recommendation = config.get("recommendation") or get_training_recommendation(
        config.get("hardware", {})
    )
    if recommendation.get("can_train_locally") is False:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "colab_required",
                "message": recommendation.get(
                    "message",
                    "This device does not have enough resources for local training.",
                ),
                "recommendation": recommendation,
            },
        )

    data_file = config.get("data_file")
    if not data_file or not Path(data_file).exists():
        raise HTTPException(
            status_code=400,
            detail="Training data file not found. Generate training data first.",
        )

    job_id = str(uuid.uuid4())[:8]
    source_job_id = config.get("job_id")
    dataset_id = f"ds_{source_job_id}" if source_job_id else None
    if dataset_id and not get_dataset(dataset_id):
        dataset_id = None

    training_jobs[job_id] = {
        "id": job_id,
        "session_id": session_id,
        "status": "starting",
        "phase": "checking_model",
        "progress": 0,
        "total_steps": 0,
        "current_step": 0,
        "loss": None,
        "message": "Checking model cache...",
        "error": None,
        "config": config,
        "output_path": None,
        "download_gb_done": 0,
        "download_gb_total": 0,
        "download_file": "",
        "started_at": None,
        "completed_at": None,
    }

    create_run(
        run_id=job_id,
        run_type="training",
        status="running",
        dataset_id=dataset_id,
        base_model_id=config.get("hf_repo") or config.get("model_name"),
        config=config,
        hardware=config.get("hardware"),
        metrics={
            "pair_count": config.get("pair_count", 0),
            "epochs": config.get("epochs", 0),
            "learning_rate": config.get("learning_rate"),
        },
    )

    asyncio.create_task(_run_training(job_id, config))

    return {
        "job_id": job_id,
        "session_id": session_id,
        "status": "started",
        "message": "Training started. Connect to /api/training/progress/{job_id} for updates.",
    }


@router.get("/progress/{job_id}")
async def training_progress(job_id: str):
    """
    SSE endpoint for real-time training progress.
    """
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Training job not found")

    async def event_stream():
        while True:
            job = training_jobs.get(job_id, {})
            data = json.dumps(job)
            yield f"data: {data}\n\n"

            if job.get("status") in ("complete", "error"):
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}")
async def get_training_job(job_id: str):
    """Return current state of a training job as plain JSON."""
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Training job not found")
    return training_jobs[job_id]


async def _run_training(job_id: str, config: dict):
    """
    Background task that orchestrates the full training pipeline.
    """
    import asyncio
    import json
    import sys
    import time

    def update(phase, message, progress=None, **kwargs):
        training_jobs[job_id].update(
            {
                "phase": phase,
                "message": message,
                **kwargs,
            }
        )
        if progress is not None:
            training_jobs[job_id]["progress"] = progress
        append_run_log(job_id, f"{phase}: {message}")
        event_payload = {"phase": phase, **kwargs}
        if progress is not None:
            event_payload["progress"] = progress
        add_run_event(job_id, "run.progress", message, event_payload)

    try:
        training_jobs[job_id]["status"] = "running"
        training_jobs[job_id]["started_at"] = time.time()
        update_run(job_id, status="running")
        append_run_log(job_id, "Training orchestration started")
        add_run_event(job_id, "run.started", "Training orchestration started")

        update("checking_model", "Checking if model is cached locally...")

        model_name = config["model_name"]
        hf_repo = config.get("hf_repo") or model_name
        hardware = config["hardware"]
        approach = hardware.get("training_approach", "colab")
        recommendation = config.get("recommendation") or get_training_recommendation(hardware)

        if recommendation.get("can_train_locally") is False:
            training_jobs[job_id].update(
                {
                    "status": "error",
                    "error": "colab_required",
                    "error_oom": False,
                    "message": recommendation.get(
                        "message",
                        "This device does not have enough resources for local training.",
                    ),
                    "recommendation": recommendation,
                }
            )
            update_run(job_id, status="failed", error_summary="Colab required")
            add_run_event(job_id, "run.failed", "Colab required", {"recommendation": recommendation})
            return

        if not hf_repo or "/" not in hf_repo:
            raise ValueError(
                f"Model {model_name} is not a valid HuggingFace repo ID. "
                "Please select a HuggingFace model."
            )

        if approach == "colab":
            training_jobs[job_id].update(
                {
                    "status": "error",
                    "error": "colab_required",
                    "message": (
                        "No GPU detected on your machine. "
                        "Use Google Colab for training. "
                        "Download the Colab notebook from the training page."
                    ),
                }
            )
            update_run(job_id, status="failed", error_summary="Colab required")
            add_run_event(job_id, "run.failed", "Colab required")
            return

        update("checking_cache", "Verifying model files...")

        loop = asyncio.get_event_loop()
        is_cached = await loop.run_in_executor(None, _check_hf_cache, hf_repo)

        if not is_cached:
            download_size = FALLBACK_SIZES_GB.get(hf_repo, 8)
            update(
                "downloading",
                f"Downloading {hf_repo} from HuggingFace (~{download_size} GB)...",
                progress=0,
            )

            success = await loop.run_in_executor(None, _download_hf_model, hf_repo, job_id)
            append_run_log(job_id, f"Model download {'completed' if success else 'failed'} for {hf_repo}")

            if not success:
                raise ValueError(
                    f"Failed to download {hf_repo}. "
                    "Check your internet connection and HF_TOKEN if required."
                )

        update("preparing", "Model ready. Preparing training...", progress=5)

        config_path = OUTPUT_DIR / f"train_config_{job_id}.json"
        progress_file = OUTPUT_DIR / f"train_progress_{job_id}.json"
        with config_path.open("w") as handle:
            json.dump(
                {
                    **config,
                    "hf_repo": hf_repo,
                    "job_id": job_id,
                    "progress_file": str(progress_file),
                },
                handle,
            )

        if approach == "mlx":
            script = PROJECT_ROOT / "training" / "train_mlx.py"
        elif approach in ("unsloth", "unsloth_small"):
            script = PROJECT_ROOT / "training" / "train_unsloth.py"
        else:
            raise ValueError(f"Unknown training approach: {approach}")

        update("training", "Starting fine-tuning...", progress=10)

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            str(config_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        while True:
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
                break
            except asyncio.TimeoutError:
                pass

            if progress_file.exists():
                try:
                    with progress_file.open() as handle:
                        prog = json.load(handle)
                    training_jobs[job_id].update(
                        {
                            "phase": "training",
                            "progress": prog.get("progress", 10),
                            "current_step": prog.get("step", 0),
                            "total_steps": prog.get("total_steps", 0),
                            "loss": prog.get("loss"),
                            "message": prog.get("message", "Training..."),
                        }
                    )
                    add_run_event(
                        job_id,
                        "run.progress",
                        prog.get("message", "Training..."),
                        {
                            "phase": "training",
                            "progress": prog.get("progress", 10),
                            "step": prog.get("step", 0),
                            "total_steps": prog.get("total_steps", 0),
                            "loss": prog.get("loss"),
                        },
                    )
                    append_run_log(
                        job_id,
                        (
                            f"training progress={prog.get('progress', 10)} "
                            f"step={prog.get('step', 0)}/{prog.get('total_steps', 0)} "
                            f"loss={prog.get('loss')} message={prog.get('message', 'Training...')}"
                        ),
                    )
                except Exception:
                    pass

        if process.returncode != 0:
            stderr = await process.stderr.read()
            append_run_log(job_id, stderr.decode(errors="replace")[:4000])
            raise ValueError(
                f"Training failed with exit code {process.returncode}. "
                f"Error: {stderr.decode()[:500]}"
            )

        output_path = None
        if progress_file.exists():
            with progress_file.open() as handle:
                final_prog = json.load(handle)
            output_path = final_prog.get("output_path")

        if not output_path:
            output_path = str(MODELS_DIR / config["output_name"])

        artifact_path = output_path
        if not Path(artifact_path).exists() and Path(f"{output_path}.gguf").exists():
            artifact_path = f"{output_path}.gguf"

        source_job_id = config.get("job_id")
        dataset_id = f"ds_{source_job_id}" if source_job_id else None
        if dataset_id and not get_dataset(dataset_id):
            dataset_id = None
        model_id = f"model_{config['output_name']}"
        model = create_model(
            model_id=model_id,
            display_name=config["output_name"],
            base_model_repo=hf_repo,
            training_run_id=job_id,
            dataset_id=dataset_id,
            artifact_path=artifact_path,
            model_format="gguf" if artifact_path.endswith(".gguf") else "adapter",
            readiness_status="ready",
            deployment_status="draft",
            tags=["candidate"],
        )
        try:
            evaluation = await run_model_evaluation(model["model_id"])
        except Exception as exc:
            evaluation_score = 1.0 if Path(artifact_path).exists() else 0.5
            evaluation = create_basic_evaluation(
                model_id=model["model_id"],
                dataset_id=dataset_id,
                aggregate_score=evaluation_score,
                notes=(
                    "Automatic metadata readiness check completed after training. "
                    f"Prompt evaluation could not run: {exc}"
                ),
                scores={
                    "artifact_present": 1.0 if Path(artifact_path).exists() else 0.0,
                    "training_completed": 1.0,
                    "prompt_evaluation_error": str(exc),
                },
            )

        training_jobs[job_id].update(
            {
                "status": "complete",
                "phase": "complete",
                "progress": 100,
                "message": f"Training complete! Model saved to {output_path}.gguf",
                "output_path": output_path,
                "model_id": model["model_id"],
                "evaluation_id": evaluation["evaluation_id"],
                "completed_at": time.time(),
            }
        )
        append_run_log(job_id, f"Training completed. model_id={model['model_id']} evaluation_id={evaluation['evaluation_id']}")
        update_run(
            job_id,
            status="succeeded",
            dataset_id=dataset_id,
            output_model_id=model["model_id"],
            metrics={
                "progress": 100,
                "output_path": output_path,
                "artifact_path": artifact_path,
                "evaluation_id": evaluation["evaluation_id"],
            },
        )
        add_run_event(
            job_id,
            "run.completed",
            f"Training complete. Registered model {model['model_id']}",
            {"model_id": model["model_id"], "evaluation_id": evaluation["evaluation_id"]},
        )

        for tmp in (config_path, progress_file):
            if tmp.exists():
                tmp.unlink()

    except Exception as exc:
        error_text = str(exc)
        error_oom = any(
            marker in error_text.lower()
            for marker in (
                "out of memory",
                "oom",
                "cannot allocate memory",
                "memoryerror",
            )
        )
        training_jobs[job_id].update(
            {
                "status": "error",
                "error": error_text,
                "error_oom": error_oom,
                "message": f"Training failed: {error_text}",
            }
        )
        append_run_log(job_id, f"ERROR {error_text}")
        update_run(job_id, status="failed", error_summary=error_text)
        add_run_event(job_id, "run.failed", error_text, {"error_oom": error_oom})


def _check_hf_cache(hf_repo: str) -> bool:
    """
    Synchronous check for HuggingFace model cache.
    Returns True if model files are present locally.
    """
    cache_folder = "models--" + hf_repo.replace("/", "--")
    cache_path = Path.home() / ".cache" / "huggingface" / "hub" / cache_folder
    snapshots = cache_path / "snapshots"
    if not snapshots.exists():
        return False
    for snap in snapshots.iterdir():
        if snap.is_dir():
            files = list(snap.glob("*.safetensors")) + list(snap.glob("*.bin"))
            if files:
                return True
    return False


def _download_hf_model(hf_repo: str, job_id: str) -> bool:
    """
    Download HuggingFace model synchronously.
    Uses huggingface_hub snapshot_download.
    Returns True on success, False on failure.
    Updates training_jobs[job_id] with download progress.
    """
    import os

    try:
        from huggingface_hub import snapshot_download

        token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        ignore_patterns = [
            "*.msgpack",
            "*.h5",
            "flax_model*",
            "tf_model*",
            "rust_model*",
            "*.ot",
            "*.tflite",
            "coreml*",
            "onnx*",
        ]

        training_jobs[job_id]["message"] = f"Downloading {hf_repo}..."

        snapshot_download(
            repo_id=hf_repo,
            token=token,
            ignore_patterns=ignore_patterns,
        )
        return True
    except Exception as exc:
        error_str = str(exc).lower()
        if "403" in error_str or "forbidden" in error_str:
            training_jobs[job_id].update(
                {
                    "message": (
                        f"Access denied to {hf_repo}. "
                        "You need to: "
                        "1) Accept the model license on HuggingFace.co, "
                        "2) Get a token at huggingface.co/settings/tokens, "
                        "3) Add HF_TOKEN=your_token to your .env file"
                    ),
                }
            )
        else:
            training_jobs[job_id]["message"] = f"Download failed: {str(exc)}"
        return False


def detect_hardware() -> dict:
    """
    Detect hardware without requiring any GPU library.
    """
    result = {
        "os": "unknown",
        "os_display": "Unknown OS",
        "is_mac": False,
        "is_mac_silicon": False,
        "is_windows": False,
        "is_linux": False,
        "ram_gb": None,
        "gpu_name": None,
        "vram_gb": None,
        "gpu_detected": False,
        "training_approach": "colab",
        "approach_note": "Consider Google Colab for GPU training",
        "cuda_available": False,
        "mps_available": False,
    }

    try:
        os_name = platform.system().lower()
        result["os"] = os_name
        result["is_mac"] = os_name == "darwin"
        result["is_windows"] = os_name == "windows"
        result["is_linux"] = os_name == "linux"

        if result["is_mac"]:
            result["os_display"] = "macOS"
            machine = platform.machine().lower()
            result["is_mac_silicon"] = "arm" in machine or "apple" in machine
            if result["is_mac_silicon"]:
                result["os_display"] = "macOS Apple Silicon"
        elif result["is_windows"]:
            result["os_display"] = "Windows"
        elif result["is_linux"]:
            result["os_display"] = "Linux"
    except Exception:
        pass

    try:
        import psutil

        ram = psutil.virtual_memory()
        result["ram_gb"] = round(ram.total / 1024**3, 1)
    except ImportError:
        result["ram_gb"] = None
    except Exception:
        result["ram_gb"] = None

    try:
        import torch

        if torch.cuda.is_available():
            result["cuda_available"] = True
            result["gpu_detected"] = True
            result["gpu_name"] = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory
            result["vram_gb"] = round(vram / 1024**3, 1)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            result["mps_available"] = True
            result["gpu_detected"] = True
            result["gpu_name"] = "Apple Silicon GPU (MPS)"
            if result["ram_gb"]:
                result["vram_gb"] = round(result["ram_gb"] * 0.75, 1)
    except ImportError:
        pass
    except Exception:
        pass

    if not result["gpu_detected"]:
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                result["gpu_detected"] = True
                result["gpu_name"] = gpu.name
                result["vram_gb"] = round(gpu.memoryTotal / 1024, 1)
                result["cuda_available"] = True
        except ImportError:
            pass
        except Exception:
            pass

    if not result["gpu_detected"] and not result["is_mac"]:
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                timeout=3,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            if output:
                parts = output.split(",")
                result["gpu_name"] = parts[0].strip()
                result["vram_gb"] = round(float(parts[1].strip()) / 1024, 1)
                result["gpu_detected"] = True
                result["cuda_available"] = True
        except Exception:
            pass

    if result["is_mac_silicon"]:
        result["training_approach"] = "mlx"
        result["approach_note"] = (
            "Apple Silicon detected - MLX training recommended. "
            "Fast and memory efficient on M1/M2/M3."
        )
    elif result["cuda_available"] and result["vram_gb"]:
        if result["vram_gb"] >= 8:
            result["training_approach"] = "unsloth"
            result["approach_note"] = (
                f"NVIDIA GPU with {result['vram_gb']}GB VRAM detected - "
                "Unsloth training recommended."
            )
        else:
            result["training_approach"] = "unsloth_small"
            result["approach_note"] = (
                f"NVIDIA GPU with {result['vram_gb']}GB VRAM detected - "
                "Use a smaller model (1.5B or 3B) for best results."
            )
    elif result["ram_gb"] and result["ram_gb"] >= 16:
        result["training_approach"] = "cpu"
        result["approach_note"] = (
            f"{result['ram_gb']}GB RAM available - "
            "CPU training possible but will be slow (2-4 hours). "
            "Consider Google Colab for faster results."
        )
    else:
        result["training_approach"] = "colab"
        result["approach_note"] = (
            "No GPU detected - Google Colab recommended for training. "
            "Free T4 GPU available on Colab."
        )

    return result


def get_training_recommendation(hardware: dict) -> dict:
    """
    Decide whether device can handle local training.
    Called during training config and training start.
    """
    ram = hardware.get("ram_gb") or 0
    is_mac_silicon = hardware.get("is_mac_silicon", False)
    approach = hardware.get("training_approach", "colab")
    vram = hardware.get("vram_gb") or 0

    if approach in ("unsloth", "unsloth_small") and vram >= 8:
        return {
            "can_train_locally": True,
            "confidence": "high",
            "show_colab": False,
            "colab_recommended": False,
            "message": None,
            "reason": f"NVIDIA GPU with {vram}GB VRAM detected",
        }

    if is_mac_silicon and ram >= 32:
        return {
            "can_train_locally": True,
            "confidence": "high",
            "show_colab": False,
            "colab_recommended": False,
            "message": None,
            "reason": f"Apple Silicon with {ram}GB unified memory",
        }

    if is_mac_silicon and ram >= 16:
        return {
            "can_train_locally": True,
            "confidence": "high",
            "show_colab": True,
            "colab_recommended": False,
            "message": None,
            "reason": f"Apple Silicon with {ram}GB RAM - local training works well",
        }

    if is_mac_silicon and ram >= 8:
        return {
            "can_train_locally": True,
            "confidence": "low",
            "show_colab": True,
            "colab_recommended": True,
            "message": (
                f"Your Mac has {int(ram)}GB RAM. "
                "Training a 1.5B+ model may cause your Mac to freeze. "
                "Google Colab is recommended for a smoother experience. "
                "If you train locally use the smallest model available."
            ),
            "reason": f"Apple Silicon with only {ram}GB RAM - borderline",
            "local_warning": True,
        }

    if approach in ("unsloth", "unsloth_small") and 0 < vram < 8:
        return {
            "can_train_locally": True,
            "confidence": "low",
            "show_colab": True,
            "colab_recommended": True,
            "message": (
                f"Your GPU has {vram}GB VRAM. "
                "This may not be enough for training. "
                "Use the smallest model (1.5B) and reduce batch size. "
                "Google Colab is more reliable."
            ),
            "reason": f"NVIDIA GPU with only {vram}GB VRAM",
            "local_warning": True,
        }

    return {
        "can_train_locally": False,
        "confidence": "none",
        "show_colab": True,
        "colab_recommended": True,
        "message": (
            "Your device does not have enough resources "
            "for local model training. "
            "Google Colab provides a free GPU and trains your model "
            "in 15-20 minutes."
        ),
        "reason": "No GPU detected and insufficient RAM for training",
        "colab_required": True,
    }


def get_time_estimates(hardware: dict) -> dict:
    """
    Estimate training time based on hardware.
    """
    approach = hardware["training_approach"]
    vram = hardware.get("vram_gb")
    estimates = {
        "pairs_365": "unknown",
        "pairs_1000": "unknown",
        "note": "Estimates for 3B model, 3 epochs",
    }

    if approach == "mlx":
        estimates["pairs_365"] = "15-25 minutes"
        estimates["pairs_1000"] = "40-60 minutes"
    elif approach == "unsloth":
        if vram and vram >= 16:
            estimates["pairs_365"] = "10-15 minutes"
            estimates["pairs_1000"] = "25-35 minutes"
        else:
            estimates["pairs_365"] = "15-25 minutes"
            estimates["pairs_1000"] = "40-60 minutes"
    elif approach == "unsloth_small":
        estimates["pairs_365"] = "20-35 minutes"
        estimates["pairs_1000"] = "60-90 minutes"
        estimates["note"] = "Estimates for 1.5B model, 3 epochs"
    elif approach == "cpu":
        estimates["pairs_365"] = "2-4 hours"
        estimates["pairs_1000"] = "6-10 hours"
    else:
        estimates["pairs_365"] = "15-25 min on Colab T4"
        estimates["pairs_1000"] = "40-60 min on Colab T4"

    return estimates


def get_approach_details(hardware: dict) -> dict:
    """
    Return details about the recommended training approach.
    """
    approach = hardware["training_approach"]
    details = {
        "mlx": {
            "name": "MLX",
            "description": "Apple's framework optimized for Apple Silicon",
            "install": "pip install mlx-lm",
            "docs": "https://github.com/ml-explore/mlx-lm",
            "pros": [
                "Native Apple Silicon support",
                "Memory efficient",
                "No CUDA required",
            ],
        },
        "unsloth": {
            "name": "Unsloth",
            "description": "Fast QLoRA fine-tuning for NVIDIA GPUs",
            "install": "pip install unsloth",
            "docs": "https://github.com/unslothai/unsloth",
            "pros": [
                "2x faster than standard training",
                "60% less memory usage",
                "Supports GGUF export directly",
            ],
        },
        "unsloth_small": {
            "name": "Unsloth (small model)",
            "description": "Unsloth with a smaller model for limited VRAM",
            "install": "pip install unsloth",
            "docs": "https://github.com/unslothai/unsloth",
            "pros": [
                "Works on 4-6GB VRAM",
                "Still fast with QLoRA",
            ],
        },
        "cpu": {
            "name": "CPU Training",
            "description": "Training on CPU - slow but works",
            "install": "pip install transformers trl",
            "docs": "https://huggingface.co/docs/trl",
            "pros": ["No GPU required"],
        },
        "colab": {
            "name": "Google Colab",
            "description": "Free cloud GPU for training",
            "install": "No local install needed",
            "docs": "https://colab.research.google.com",
            "pros": [
                "Free T4 GPU",
                "No local setup",
                "15-25 min training time",
            ],
        },
    }
    return details.get(approach, details["colab"])


def get_requirements(hardware: dict) -> dict:
    """
    Return package requirements based on the recommended training approach.
    """
    approach = hardware["training_approach"]
    base = ["pip install psutil"]

    if approach == "mlx":
        return {
            "packages": base + ["pip install mlx-lm"],
            "note": "MLX requires macOS 13.5+ and Apple Silicon",
        }
    if approach in ("unsloth", "unsloth_small"):
        return {
            "packages": base + [
                "pip install unsloth",
                "pip install torch torchvision torchaudio",
            ],
            "note": "Requires NVIDIA GPU with CUDA support",
        }
    if approach == "cpu":
        return {
            "packages": base + [
                "pip install transformers trl peft",
                "pip install torch --index-url https://download.pytorch.org/whl/cpu",
            ],
            "note": "CPU training is slow - consider Colab instead",
        }
    return {
        "packages": [],
        "note": "Upload training_data.jsonl to Google Colab and run the provided notebook",
    }


def resolve_training_data_file(job_id: str) -> Path | None:
    """
    Resolve the training data file for a job, falling back to output defaults.
    """
    if job_id:
        job = jobs.get(job_id)
        if job:
            output_path = job.get("output_path")
            if output_path:
                candidate = Path(output_path).expanduser()
                if candidate.exists():
                    return candidate

        job_file = OUTPUT_DIR / f"{job_id}_training_data.jsonl"
        if job_file.exists():
            return job_file

    default_file = OUTPUT_DIR / "training_data.jsonl"
    if default_file.exists():
        return default_file

    return None


def resolve_model_output_dir(raw_output_dir: str, errors: list[str]) -> Path:
    """
    Resolve and validate the folder where the trained model should be saved.
    """
    candidate = Path((raw_output_dir or "").strip()).expanduser() if raw_output_dir else MODELS_DIR
    if not str(candidate).strip():
        candidate = MODELS_DIR

    if not candidate.is_absolute():
        candidate = (MODELS_DIR / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"Cannot create output folder: {exc}")
        return MODELS_DIR

    if not candidate.is_dir():
        errors.append("Output folder must be a directory")
        return MODELS_DIR

    return candidate


def calculate_time_estimate(
    pair_count: int,
    epochs: int,
    hardware: dict,
    model_name: str,
) -> dict:
    """
    Calculate a configuration-specific training time estimate.
    """
    approach = hardware.get("training_approach", "colab")
    base_times = {
        "mlx": 20,
        "unsloth": 15,
        "unsloth_small": 25,
        "cpu": 180,
        "colab": 20,
    }
    base = base_times.get(approach, 20)
    pair_scale = pair_count / 365 if pair_count > 0 else 1
    epoch_scale = epochs / 3

    lowered_name = model_name.lower()
    if "1b" in lowered_name or "1.5b" in lowered_name:
        model_scale = 0.5
    elif "3b" in lowered_name or "mini" in lowered_name:
        model_scale = 1.0
    elif "7b" in lowered_name or "8b" in lowered_name:
        model_scale = 2.5
    elif "14b" in lowered_name:
        model_scale = 4.0
    else:
        model_scale = 1.0

    estimated_minutes = max(5, round(base * pair_scale * epoch_scale * model_scale))
    if estimated_minutes < 60:
        display = f"{estimated_minutes}-{estimated_minutes + 10} minutes"
    else:
        hours = estimated_minutes // 60
        minutes = estimated_minutes % 60
        display = f"{hours}h {minutes}m"

    return {
        "minutes": estimated_minutes,
        "display": display,
        "breakdown": {
            "pairs": pair_count,
            "epochs": epochs,
            "model": model_name,
            "approach": approach,
        },
    }


def calculate_lora_rank(pair_count: int) -> int:
    """
    Calculate a dataset-size-aware LoRA rank.
    """
    if pair_count < 200:
        return 8
    if pair_count < 500:
        return 16
    if pair_count < 1000:
        return 32
    return 64


def calculate_batch_size(hardware: dict) -> int:
    """
    Calculate a conservative batch size from the detected hardware.
    """
    vram = hardware.get("vram_gb")
    ram = hardware.get("ram_gb", 8)
    approach = hardware.get("training_approach", "colab")

    if approach == "mlx":
        if ram and ram >= 32:
            return 4
        if ram and ram >= 16:
            return 2
        return 1

    if approach in ("unsloth", "unsloth_small"):
        if vram and vram >= 16:
            return 4
        if vram and vram >= 8:
            return 2
        return 1

    return 1
