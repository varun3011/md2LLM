import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import AsyncGenerator

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from server.config import OUTPUT_DIR, PROJECT_ROOT, UPLOAD_DIR
from server.services.generation import run_generation
from server.services.registry import create_dataset, create_run
from server.state import jobs
from pipeline.vault_reader import (
    EXCLUDED_FOLDERS,
    parse_note,
    read_vault,
    score_note,
)

router = APIRouter(prefix="/api")


def _new_upload_job_paths() -> tuple[str, Path, Path]:
    job_id = str(uuid.uuid4())[:8]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_id, job_dir, job_dir / "vault"


def _new_job_id() -> str:
    return str(uuid.uuid4())[:8]


def _init_job(
    job_id: str,
    vault_path: str | None,
    md_count: int,
    message: str,
    source_type: str,
) -> dict:
    job = {
        "id": job_id,
        "status": "ready",
        "progress": 0,
        "total": 0,
        "pairs": 0,
        "message": message,
        "error": None,
        "output_path": None,
        "output_dir": str(OUTPUT_DIR),
        "vault_path": vault_path,
        "goal": None,
        "md_files_found": md_count,
        "scan_stats": None,
        "source_type": source_type,
    }
    jobs[job_id] = job
    return job


def _validate_training_data_line(record: dict, line_number: int) -> None:
    if "messages" in record:
        messages = record.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid training data on line {line_number}: messages must contain at least 2 entries",
            )
        first_two = messages[:2]
        if any(not isinstance(message, dict) for message in first_two):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid training data on line {line_number}: messages must be JSON objects",
            )
        if first_two[0].get("role") != "user" or first_two[1].get("role") != "assistant":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid training data on line {line_number}: "
                    "messages must start with user then assistant"
                ),
            )
        if not str(first_two[0].get("content", "")).strip() or not str(
            first_two[1].get("content", "")
        ).strip():
            raise HTTPException(
                status_code=400,
                detail=f"Invalid training data on line {line_number}: message content cannot be empty",
            )
        return

    instruction = str(record.get("instruction", "")).strip()
    output = str(record.get("output", "")).strip()
    if not instruction or not output:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid training data on line {line_number}: "
                "expected instruction/output fields or messages"
            ),
        )


def _parse_training_jsonl(raw_text: str) -> tuple[list[str], int]:
    lines = raw_text.splitlines()
    valid_lines: list[str] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON on line {line_number}: {exc.msg}",
            ) from exc

        if not isinstance(record, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid training data on line {line_number}: each line must be a JSON object",
            )

        _validate_training_data_line(record, line_number)
        valid_lines.append(json.dumps(record, ensure_ascii=False))

    if not valid_lines:
        raise HTTPException(status_code=400, detail="Training file is empty")

    return valid_lines, len(valid_lines)


def _get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _resolve_job_vault(job_id: str) -> Path:
    job = _get_job(job_id)
    vault_path = job.get("vault_path")
    if not vault_path:
        raise HTTPException(status_code=400, detail="Vault is not registered for this job")
    root = Path(vault_path).expanduser().resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail="Vault path is no longer available")
    return root


def _count_markdown_files(root: Path) -> int:
    return sum(1 for _ in root.rglob("*.md"))


def _resolve_output_dir(output_dir: str | None) -> Path:
    raw_value = (output_dir or "").strip()
    if not raw_value:
        raise HTTPException(status_code=400, detail="Choose an output folder before starting generation")

    candidate = Path(raw_value).expanduser()
    resolved = candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)
    resolved = resolved.resolve()
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot create output folder: {exc}") from exc
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Output folder must be a directory")
    return resolved


def _safe_relative_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/").strip("/")
    relative_path = Path(normalized)
    if (
        not normalized
        or relative_path.is_absolute()
        or ".." in relative_path.parts
        or normalized.startswith(".")
    ):
        raise HTTPException(status_code=400, detail="Invalid folder entry path")
    return relative_path


@router.post("/upload")
async def upload_vault(file: UploadFile = File(...)):
    """Accept a zip file of an Obsidian vault and extract it for processing."""
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a zip file of your vault folder",
        )

    job_id, job_dir, vault_path = _new_upload_job_paths()
    zip_path = job_dir / "vault.zip"

    try:
        async with aiofiles.open(zip_path, "wb") as handle:
            content = await file.read()
            await handle.write(content)

        shutil.unpack_archive(str(zip_path), str(vault_path))
        zip_path.unlink()

        md_count = _count_markdown_files(vault_path)
        _init_job(
            job_id=job_id,
            vault_path=str(vault_path),
            md_count=md_count,
            message=f"Vault uploaded successfully. Found {md_count} markdown files.",
            source_type="zip_upload",
        )

        return {
            "job_id": job_id,
            "md_files_found": md_count,
            "message": f"Vault uploaded successfully. Found {md_count} markdown files.",
        }
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract vault: {str(exc)}")


@router.post("/upload-folder")
async def upload_vault_folder(files: list[UploadFile] = File(...)):
    """Accept a full vault folder upload and reconstruct it on disk."""
    if not files:
        raise HTTPException(status_code=400, detail="No folder files were uploaded")

    job_id, job_dir, vault_path = _new_upload_job_paths()

    try:
        md_count = 0
        for file in files:
            raw_relative_path = file.filename or ""
            relative_path = _safe_relative_path(raw_relative_path)
            destination = vault_path / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(destination, "wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    await handle.write(chunk)

            if destination.suffix.lower() == ".md":
                md_count += 1

        _init_job(
            job_id=job_id,
            vault_path=str(vault_path),
            md_count=md_count,
            message=f"Vault uploaded successfully. Found {md_count} markdown files.",
            source_type="folder_upload",
        )

        return {
            "job_id": job_id,
            "md_files_found": md_count,
            "message": f"Vault uploaded successfully. Found {md_count} markdown files.",
        }
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to save vault folder: {exc}")
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to save vault folder: {exc}")


@router.post("/upload-training-data")
async def upload_training_data(file: UploadFile = File(...)):
    """Accept an existing training_data.jsonl file and register it as a completed job."""
    filename = file.filename or ""
    if not filename.lower().endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="Please upload a .jsonl training data file")

    try:
        raw_bytes = await file.read()
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Training file must be UTF-8 encoded") from exc

    valid_lines, pair_count = _parse_training_jsonl(raw_text)

    job_id = _new_job_id()
    output_path = OUTPUT_DIR / f"{job_id}_training_data.jsonl"
    async with aiofiles.open(output_path, "w", encoding="utf-8") as handle:
        await handle.write("\n".join(valid_lines) + "\n")

    job = _init_job(
        job_id=job_id,
        vault_path=None,
        md_count=0,
        message=f"Training data uploaded successfully. Found {pair_count} training pairs.",
        source_type="imported_jsonl",
    )
    job.update(
        {
            "status": "complete",
            "progress": pair_count,
            "total": pair_count,
            "pairs": pair_count,
            "output_path": str(output_path),
            "output_dir": str(output_path.parent),
            "goal": None,
        }
    )

    dataset_id = f"ds_{job_id}"
    create_dataset(
        dataset_id=dataset_id,
        source_type="imported_jsonl",
        source_ref=filename,
        generation_goal=None,
        note_stats={"total_found": 0, "passed_filter": 0},
        quality_threshold=None,
        generation_provider="import",
        generation_model=None,
        prompt_template_version=None,
        file_count=0,
        pair_count=pair_count,
        artifact_path=str(output_path),
    )
    job["dataset_id"] = dataset_id

    return {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "pair_count": pair_count,
        "output_path": str(output_path),
        "message": f"Training data uploaded successfully. Found {pair_count} training pairs.",
    }


@router.post("/register-vault")
async def register_vault(vault_path: str = Form(...)):
    """Register a local vault path with a server-side job id."""
    root = Path(vault_path).expanduser().resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Vault path not found: {vault_path}")
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="Vault path must be a directory")

    job_id = str(uuid.uuid4())[:8]
    md_count = _count_markdown_files(root)
    _init_job(
        job_id=job_id,
        vault_path=str(root),
        md_count=md_count,
        message=f"Vault registered successfully. Found {md_count} markdown files.",
        source_type="vault",
    )

    return {
        "job_id": job_id,
        "md_files_found": md_count,
        "message": f"Vault registered successfully. Found {md_count} markdown files.",
    }


@router.post("/generate")
async def generate(
    job_id: str = Form(...),
    goal: str = Form(default="knowledge"),
    min_quality: float = Form(default=0.4),
    output_dir: str = Form(...),
):
    """Start training data generation as a background job."""
    valid_goals = ["knowledge", "style", "reasoning", "chatbot"]
    if goal not in valid_goals:
        raise HTTPException(status_code=400, detail=f"Goal must be one of {valid_goals}")

    job = _get_job(job_id)
    vault_path = str(_resolve_job_vault(job_id))

    resolved_output_dir = _resolve_output_dir(output_dir)
    output_path = str(resolved_output_dir / f"{job_id}_training_data.jsonl")
    checkpoint_path = str(resolved_output_dir / f"{job_id}_checkpoint.json")

    job.update(
        {
            "status": "starting",
            "progress": 0,
            "total": 0,
            "pairs": 0,
            "message": "Starting pipeline...",
            "error": None,
            "output_path": output_path,
            "output_dir": str(resolved_output_dir),
            "goal": goal,
            "min_quality": min_quality,
        }
    )

    create_run(
        run_id=job_id,
        run_type="dataset_generation",
        status="running",
        config={
            "goal": goal,
            "min_quality": min_quality,
            "output_path": output_path,
            "checkpoint_path": checkpoint_path,
            "source_type": job.get("source_type"),
            "vault_path": vault_path,
        },
        metrics={
            "md_files_found": job.get("md_files_found", 0),
        },
    )

    asyncio.create_task(
        run_generation(job_id, vault_path, goal, min_quality, output_path, checkpoint_path)
    )

    return {
        "job_id": job_id,
        "status": "started",
        "message": "Generation started. Connect to /progress/{job_id} for live updates.",
    }


@router.post("/scan")
async def scan_vault(
    job_id: str = Form(...),
    min_quality: float = Form(default=0.4),
):
    """Run vault_reader and return notes list without generating data."""
    job = _get_job(job_id)
    root = _resolve_job_vault(job_id)
    vault_path = str(root)

    loop = asyncio.get_running_loop()
    notes = await loop.run_in_executor(None, read_vault, vault_path, min_quality)

    total_found = 0
    skipped_short = 0
    skipped_draft = 0
    skipped_low_quality = 0
    quality_scores: list[float] = []

    for file_path in root.rglob("*.md"):
        relative_parts = file_path.relative_to(root).parts
        if any(part in EXCLUDED_FOLDERS for part in relative_parts[:-1]):
            continue
        if file_path.stem.lower().startswith("template"):
            continue

        total_found += 1
        note = parse_note(str(file_path))
        score = score_note(note)
        quality_scores.append(score)

        status = str(note.frontmatter.get("status", "")).strip().lower()
        normalized_tags = {tag.lower() for tag in note.tags}
        if status in {"draft", "raw"} or {"draft", "raw"} & normalized_tags:
            skipped_draft += 1
            continue
        if note.word_count < 50:
            skipped_short += 1
            continue
        if score < min_quality:
            skipped_low_quality += 1

    stats = {
        "total_found": total_found,
        "passed_filter": len(notes),
        "skipped_short": skipped_short,
        "skipped_draft": skipped_draft,
        "skipped_low_quality": skipped_low_quality,
        "average_quality": round(sum(quality_scores) / len(quality_scores), 2)
        if quality_scores
        else 0,
    }
    job["scan_stats"] = stats
    job["message"] = f"Vault scanned. {len(notes)} notes passed the quality filter."

    return {
        "notes": [
            {
                "title": note.title,
                "path": note.path,
                "word_count": note.word_count,
                "quality_score": round(note.quality_score, 2),
                "tags": note.tags[:5],
                "wikilinks": note.wikilinks[:5],
                "body_preview": note.body[:200].replace("\n", " ").strip(),
            }
            for note in notes
        ],
        "stats": stats,
    }


@router.get("/progress/{job_id}")
async def progress(job_id: str):
    """Stream job progress as server-sent events."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        while True:
            job = jobs.get(job_id, {})
            yield f"data: {json.dumps(job)}\n\n"

            if job.get("status") in ("complete", "error"):
                break

            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Return current state of a job as plain JSON."""
    return _get_job(job_id)


@router.get("/jobs")
async def list_jobs():
    """Return all jobs."""
    return list(jobs.values())


@router.get("/download/{job_id}")
async def download(job_id: str):
    """
    Download the training data JSONL for a specific job.
    Used by the Colab flow so user can get their data file.
    """
    output_path = None

    if job_id in jobs:
        job = jobs[job_id]
        if job.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Job not complete yet")
        if job.get("output_path"):
            output_path = Path(job["output_path"])

    if not output_path or not output_path.exists():
        output_path = OUTPUT_DIR / f"{job_id}_training_data.jsonl"

    if not output_path.exists():
        output_path = OUTPUT_DIR / "training_data.jsonl"

    if not output_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Training data file not found. Generate training data first.",
        )

    return FileResponse(
        path=str(output_path),
        filename="md2LLM_training_data.jsonl",
        media_type="application/octet-stream",
    )
