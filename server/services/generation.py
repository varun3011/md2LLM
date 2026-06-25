import asyncio
from pathlib import Path

from pipeline.data_generator import generate_training_data_async
from pipeline.vault_reader import read_vault

from server.services.registry import add_run_event, append_run_log, create_dataset, update_run
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
        update_run(job_id, status="running")
        append_run_log(job_id, "Reading vault and scoring notes")
        add_run_event(job_id, "run.started", "Reading vault and scoring notes")

        loop = asyncio.get_running_loop()
        notes = await loop.run_in_executor(None, read_vault, vault_path, min_quality)

        jobs[job_id]["total"] = len(notes)
        jobs[job_id]["message"] = (
            f"Found {len(notes)} quality notes. Generating training pairs..."
        )
        jobs[job_id]["status"] = "generating"
        append_run_log(job_id, f"Found {len(notes)} quality notes")
        add_run_event(
            job_id,
            "run.progress",
            f"Found {len(notes)} quality notes",
            {"total_notes": len(notes)},
        )

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
            append_run_log(
                job_id,
                f"progress completed={completed} total={total} pairs={pairs_so_far} note={current_note[:120]}",
            )
            add_run_event(
                job_id,
                "run.progress",
                f"Processing: {current_note[:80]}",
                {
                    "completed": completed,
                    "total": total,
                    "pairs": pairs_so_far,
                    "current_note": current_note,
                },
            )

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
        append_run_log(job_id, f"Generated {pair_count} training pairs at {output_path}")

        dataset_id = f"ds_{job_id}"
        job = jobs[job_id]
        dataset = create_dataset(
            dataset_id=dataset_id,
            source_type=job.get("source_type") or "vault",
            source_ref=vault_path,
            generation_goal=goal,
            note_stats=job.get("scan_stats")
            or {
                "total_found": job.get("md_files_found", 0),
                "passed_filter": len(notes),
            },
            quality_threshold=min_quality,
            generation_provider="openai",
            generation_model="gpt-4o-mini",
            prompt_template_version="default-v1",
            file_count=len(notes),
            pair_count=pair_count,
            artifact_path=output_path,
        )
        job["dataset_id"] = dataset["dataset_id"]
        update_run(
            job_id,
            status="succeeded",
            dataset_id=dataset["dataset_id"],
            metrics={
                "notes_used": len(notes),
                "pair_count": pair_count,
                "artifact_path": output_path,
            },
        )
        add_run_event(
            job_id,
            "artifact.created",
            f"Dataset {dataset['dataset_id']} created",
            {"dataset_id": dataset["dataset_id"], "artifact_path": output_path},
        )

    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["message"] = f"Error: {str(exc)}"
        append_run_log(job_id, f"ERROR {exc}")
        update_run(job_id, status="failed", error_summary=str(exc))
        add_run_event(job_id, "run.failed", str(exc))
