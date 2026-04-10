import asyncio
from pathlib import Path

from pipeline.data_generator import generate_training_data_async
from pipeline.vault_reader import read_vault

from server.state import jobs


async def run_generation(
    job_id: str,
    vault_path: str,
    goal: str,
    min_quality: float,
    output_path: str,
    checkpoint_path: str,
) -> None:
    """Background task that runs the pipeline and updates in-memory job state."""
    try:
        jobs[job_id]["status"] = "reading_vault"
        jobs[job_id]["message"] = "Reading vault and scoring notes..."

        loop = asyncio.get_running_loop()
        notes = await loop.run_in_executor(None, read_vault, vault_path, min_quality)

        jobs[job_id]["total"] = len(notes)
        jobs[job_id]["message"] = (
            f"Found {len(notes)} quality notes. Generating training pairs..."
        )
        jobs[job_id]["status"] = "generating"

        def progress_callback(
            completed: int,
            total: int,
            pairs_so_far: int,
            current_note: str,
        ) -> None:
            jobs[job_id]["progress"] = completed
            jobs[job_id]["total"] = total
            jobs[job_id]["pairs"] = pairs_so_far
            jobs[job_id]["message"] = f"Processing: {current_note[:50]}"

        await generate_training_data_async(
            notes=notes,
            goal=goal,
            output_path=output_path,
            checkpoint_path=checkpoint_path,
            resume=True,
            progress_callback=progress_callback,
        )

        pair_count = 0
        if Path(output_path).exists():
            with open(output_path, encoding="utf-8") as handle:
                pair_count = sum(1 for _ in handle)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = jobs[job_id]["total"]
        jobs[job_id]["pairs"] = pair_count
        jobs[job_id]["message"] = f"Done! Generated {pair_count} training pairs."

    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["message"] = f"Error: {str(exc)}"
