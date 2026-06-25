import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.db import get_connection, init_db, rows_to_dicts
from server.config import OUTPUT_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _decode_record(record: dict) -> dict:
    decoded = dict(record)
    for key in (
        "note_stats_json",
        "config_json",
        "hardware_json",
        "metrics_json",
        "payload_json",
        "scores_json",
        "tags_json",
        "token_usage_json",
    ):
        if key in decoded:
            decoded[key.replace("_json", "")] = json_loads(decoded.pop(key), {})
    return decoded


def file_sha256(path: str | Path) -> str | None:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_jsonl_rows(path: str | Path) -> int:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return 0
    with file_path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def create_run(
    run_id: str,
    run_type: str,
    status: str = "queued",
    dataset_id: str | None = None,
    base_model_id: str | None = None,
    output_model_id: str | None = None,
    config: dict | None = None,
    hardware: dict | None = None,
    log_path: str | None = None,
    metrics: dict | None = None,
) -> dict:
    init_db()
    timestamp = now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, run_type, status, started_at, ended_at, duration_seconds,
                dataset_id, base_model_id, output_model_id, config_json,
                hardware_json, log_path, error_summary, metrics_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                run_id,
                run_type,
                status,
                timestamp if status in {"running", "succeeded", "failed"} else None,
                dataset_id,
                base_model_id,
                output_model_id,
                json_dumps(config),
                json_dumps(hardware),
                log_path,
                json_dumps(metrics),
                timestamp,
                timestamp,
            ),
        )
    add_run_event(run_id, "run.created", f"{run_type} run created", {"status": status})
    return get_run(run_id) or {}


def update_run(
    run_id: str,
    status: str | None = None,
    dataset_id: str | None = None,
    base_model_id: str | None = None,
    output_model_id: str | None = None,
    config: dict | None = None,
    hardware: dict | None = None,
    error_summary: str | None = None,
    metrics: dict | None = None,
    log_path: str | None = None,
) -> None:
    init_db()
    existing = get_run(run_id)
    if not existing:
        create_run(run_id, "unknown", status or "queued")
        existing = get_run(run_id)

    timestamp = now_iso()
    started_at = existing.get("started_at")
    ended_at = existing.get("ended_at")
    duration = existing.get("duration_seconds")

    if status == "running" and not started_at:
        started_at = timestamp
    if status in {"succeeded", "failed", "cancelled"} and not ended_at:
        ended_at = timestamp
        start_value = started_at or existing.get("created_at")
        try:
            start_dt = datetime.fromisoformat(start_value)
            end_dt = datetime.fromisoformat(ended_at)
            duration = round((end_dt - start_dt).total_seconds(), 3)
        except Exception:
            duration = None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE runs
            SET status = COALESCE(?, status),
                started_at = ?,
                ended_at = ?,
                duration_seconds = ?,
                dataset_id = COALESCE(?, dataset_id),
                base_model_id = COALESCE(?, base_model_id),
                output_model_id = COALESCE(?, output_model_id),
                config_json = COALESCE(?, config_json),
                hardware_json = COALESCE(?, hardware_json),
                log_path = COALESCE(?, log_path),
                error_summary = COALESCE(?, error_summary),
                metrics_json = COALESCE(?, metrics_json),
                updated_at = ?
            WHERE run_id = ?
            """,
            (
                status,
                started_at,
                ended_at,
                duration,
                dataset_id,
                base_model_id,
                output_model_id,
                json_dumps(config),
                json_dumps(hardware),
                log_path,
                error_summary,
                json_dumps(metrics),
                timestamp,
                run_id,
            ),
        )


def add_run_event(
    run_id: str,
    event_type: str,
    message: str = "",
    payload: dict | None = None,
) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO run_events (run_id, event_type, message, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, event_type, message, json_dumps(payload), now_iso()),
        )


def run_log_path(run_id: str) -> Path:
    log_dir = OUTPUT_DIR / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{run_id}.log"


def append_run_log(run_id: str, line: str) -> str:
    path = run_log_path(run_id)
    timestamp = now_iso()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {line.rstrip()}\n")
    update_run(run_id, log_path=str(path))
    return str(path)


def read_run_log(run_id: str, max_lines: int = 500) -> list[str]:
    run = get_run(run_id)
    log_path = Path(run.get("log_path") or run_log_path(run_id)) if run else run_log_path(run_id)
    if not log_path.exists():
        return []
    with log_path.open(encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-max_lines:]]


def diagnose_run(run: dict, events: list[dict], logs: list[str]) -> list[dict]:
    text = "\n".join(
        [
            str(run.get("error_summary") or ""),
            "\n".join(event.get("message") or "" for event in events),
            "\n".join(logs[-200:]),
        ]
    ).lower()
    checks = [
        ("out_of_memory", ("out of memory", "oom", "cannot allocate memory", "memoryerror")),
        ("missing_dependency", ("modulenotfounderror", "no module named", "importerror")),
        ("hf_token", ("403", "forbidden", "hf_token", "huggingface token", "access denied")),
        ("model_download", ("failed to download", "snapshot_download", "connection")),
        ("ollama_unavailable", ("cannot connect to ollama", "ollama not running")),
        ("cuda", ("cuda", "nvidia-smi", "cublas", "cudnn")),
    ]
    findings = []
    for code, markers in checks:
        if any(marker in text for marker in markers):
            findings.append(
                {
                    "code": code,
                    "severity": "error" if run.get("status") == "failed" else "warning",
                    "message": DIAGNOSTIC_MESSAGES[code],
                }
            )
    if not findings and run.get("status") == "failed":
        findings.append(
            {
                "code": "unknown_failure",
                "severity": "error",
                "message": "The run failed, but no known diagnostic pattern matched the logs.",
            }
        )
    return findings


DIAGNOSTIC_MESSAGES = {
    "out_of_memory": "The run appears to have run out of memory. Use a smaller model, lower batch size, or Colab.",
    "missing_dependency": "A Python dependency appears to be missing. Recheck the training dependency setup.",
    "hf_token": "The base model likely requires Hugging Face access approval or an HF_TOKEN in .env.",
    "model_download": "Model download failed or was interrupted. Check network access and model repository access.",
    "ollama_unavailable": "Ollama was unavailable during the operation. Start it with `ollama serve`.",
    "cuda": "CUDA/GPU setup appears to be involved in the failure. Verify NVIDIA drivers and CUDA-compatible PyTorch.",
}


def create_dataset(
    dataset_id: str,
    source_type: str,
    source_ref: str | None,
    generation_goal: str | None,
    note_stats: dict | None,
    quality_threshold: float | None,
    generation_provider: str | None,
    generation_model: str | None,
    prompt_template_version: str | None,
    file_count: int,
    pair_count: int,
    artifact_path: str | None,
    content_hash: str | None = None,
) -> dict:
    init_db()
    if artifact_path and not content_hash:
        content_hash = file_sha256(artifact_path)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO datasets (
                dataset_id, source_type, source_ref, generation_goal, note_stats_json,
                quality_threshold, generation_provider, generation_model,
                prompt_template_version, file_count, pair_count, artifact_path,
                content_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                source_type,
                source_ref,
                generation_goal,
                json_dumps(note_stats),
                quality_threshold,
                generation_provider,
                generation_model,
                prompt_template_version,
                file_count,
                pair_count,
                artifact_path,
                content_hash,
                now_iso(),
            ),
        )
    return get_dataset(dataset_id) or {}


def create_model(
    model_id: str,
    display_name: str,
    base_model_repo: str | None,
    training_run_id: str | None,
    dataset_id: str | None,
    artifact_path: str | None,
    model_format: str,
    readiness_status: str = "ready",
    deployment_status: str = "draft",
    tags: list[str] | None = None,
) -> dict:
    init_db()
    size_bytes = 0
    if artifact_path:
        path = Path(artifact_path)
        if path.exists() and path.is_file():
            size_bytes = path.stat().st_size
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO models (
                model_id, display_name, base_model_repo, training_run_id,
                dataset_id, artifact_path, format, size_bytes, created_at,
                readiness_status, deployment_status, tags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_id,
                display_name,
                base_model_repo,
                training_run_id,
                dataset_id,
                artifact_path,
                model_format,
                size_bytes,
                now_iso(),
                readiness_status,
                deployment_status,
                json_dumps(tags or []),
            ),
        )
    return get_model(model_id) or {}


def update_model_status(
    model_id: str,
    deployment_status: str | None = None,
    readiness_status: str | None = None,
    tags: list[str] | None = None,
) -> dict | None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE models
            SET deployment_status = COALESCE(?, deployment_status),
                readiness_status = COALESCE(?, readiness_status),
                tags_json = COALESCE(?, tags_json)
            WHERE model_id = ?
            """,
            (
                deployment_status,
                readiness_status,
                json_dumps(tags) if tags is not None else None,
                model_id,
            ),
        )
    return get_model(model_id)


def create_basic_evaluation(
    model_id: str,
    dataset_id: str | None,
    notes: str,
    aggregate_score: float,
    scores: dict | None = None,
) -> dict:
    evaluation_id = make_id("eval")
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO evaluations (
                evaluation_id, model_id, dataset_id, evaluation_suite_version,
                prompt_set_version, aggregate_score, scores_json, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                model_id,
                dataset_id,
                "basic-readiness-v1",
                "metadata-v1",
                aggregate_score,
                json_dumps(scores or {}),
                notes,
                now_iso(),
            ),
        )
    return get_evaluation(evaluation_id) or {}


def create_evaluation(
    model_id: str,
    dataset_id: str | None,
    evaluation_suite_version: str,
    prompt_set_version: str,
    aggregate_score: float | None,
    scores: dict | None,
    notes: str,
) -> dict:
    evaluation_id = make_id("eval")
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO evaluations (
                evaluation_id, model_id, dataset_id, evaluation_suite_version,
                prompt_set_version, aggregate_score, scores_json, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                model_id,
                dataset_id,
                evaluation_suite_version,
                prompt_set_version,
                aggregate_score,
                json_dumps(scores or {}),
                notes,
                now_iso(),
            ),
        )
    return get_evaluation(evaluation_id) or {}


def record_inference(
    model_name: str,
    latency_ms: float,
    success: bool,
    error_summary: str | None = None,
    model_id: str | None = None,
    token_usage: dict | None = None,
) -> dict:
    log_id = make_id("inf")
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO inference_logs (
                log_id, model_id, model_name, latency_ms, success,
                error_summary, token_usage_json, feedback, flagged, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?)
            """,
            (
                log_id,
                model_id,
                model_name,
                latency_ms,
                1 if success else 0,
                error_summary,
                json_dumps(token_usage),
                now_iso(),
            ),
        )
    return get_inference_log(log_id) or {}


def update_inference_feedback(
    log_id: str,
    feedback: str | None,
    flagged: bool | None = None,
) -> dict | None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE inference_logs
            SET feedback = COALESCE(?, feedback),
                flagged = COALESCE(?, flagged)
            WHERE log_id = ?
            """,
            (
                feedback,
                1 if flagged is True else 0 if flagged is False else None,
                log_id,
            ),
        )
    return get_inference_log(log_id)


def compare_records(left: dict, right: dict, fields: list[str]) -> dict:
    return {
        field: {
            "left": left.get(field),
            "right": right.get(field),
            "same": left.get(field) == right.get(field),
        }
        for field in fields
    }


def list_records(table: str, order_by: str = "created_at DESC", limit: int = 100) -> list[dict]:
    allowed_tables = {
        "datasets",
        "runs",
        "run_events",
        "models",
        "evaluations",
        "inference_logs",
    }
    if table not in allowed_tables:
        raise ValueError("Unknown registry table")
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM {table} ORDER BY {order_by} LIMIT ?",
            (limit,),
        ).fetchall()
    return [_decode_record(row) for row in rows_to_dicts(rows)]


def get_record(table: str, id_column: str, record_id: str) -> dict | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT * FROM {table} WHERE {id_column} = ?",
            (record_id,),
        ).fetchone()
    return _decode_record(dict(row)) if row else None


def get_dataset(dataset_id: str) -> dict | None:
    return get_record("datasets", "dataset_id", dataset_id)


def get_run(run_id: str) -> dict | None:
    return get_record("runs", "run_id", run_id)


def get_model(model_id: str) -> dict | None:
    return get_record("models", "model_id", model_id)


def get_evaluation(evaluation_id: str) -> dict | None:
    return get_record("evaluations", "evaluation_id", evaluation_id)


def get_inference_log(log_id: str) -> dict | None:
    return get_record("inference_logs", "log_id", log_id)


def get_run_events(run_id: str) -> list[dict]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM run_events
            WHERE run_id = ?
            ORDER BY created_at ASC, event_id ASC
            """,
            (run_id,),
        ).fetchall()
    return [_decode_record(row) for row in rows_to_dicts(rows)]


def registry_summary() -> dict:
    init_db()
    with get_connection() as connection:
        counts = {}
        for table in ("datasets", "runs", "models", "evaluations", "inference_logs"):
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        recent_failures = connection.execute(
            """
            SELECT * FROM runs
            WHERE status = 'failed'
            ORDER BY updated_at DESC
            LIMIT 5
            """
        ).fetchall()
    return {
        "counts": counts,
        "recent_failures": [_decode_record(row) for row in rows_to_dicts(recent_failures)],
        "generated_at": now_iso(),
    }


def monotonic_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
