import sqlite3
from pathlib import Path
from typing import Iterable

from server.config import OUTPUT_DIR

DB_PATH = OUTPUT_DIR / "md2llm.sqlite3"


def get_connection() -> sqlite3.Connection:
    OUTPUT_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_ref TEXT,
                generation_goal TEXT,
                note_stats_json TEXT,
                quality_threshold REAL,
                generation_provider TEXT,
                generation_model TEXT,
                prompt_template_version TEXT,
                file_count INTEGER DEFAULT 0,
                pair_count INTEGER DEFAULT 0,
                artifact_path TEXT,
                content_hash TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                duration_seconds REAL,
                dataset_id TEXT,
                base_model_id TEXT,
                output_model_id TEXT,
                config_json TEXT,
                hardware_json TEXT,
                log_path TEXT,
                error_summary TEXT,
                metrics_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            );

            CREATE TABLE IF NOT EXISTS run_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS models (
                model_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                base_model_repo TEXT,
                training_run_id TEXT,
                dataset_id TEXT,
                artifact_path TEXT,
                format TEXT,
                size_bytes INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                readiness_status TEXT NOT NULL,
                deployment_status TEXT NOT NULL,
                tags_json TEXT,
                FOREIGN KEY(training_run_id) REFERENCES runs(run_id),
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                dataset_id TEXT,
                evaluation_suite_version TEXT NOT NULL,
                prompt_set_version TEXT NOT NULL,
                aggregate_score REAL,
                scores_json TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(model_id) REFERENCES models(model_id),
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            );

            CREATE TABLE IF NOT EXISTS inference_logs (
                log_id TEXT PRIMARY KEY,
                model_id TEXT,
                model_name TEXT NOT NULL,
                latency_ms REAL,
                success INTEGER NOT NULL,
                error_summary TEXT,
                token_usage_json TEXT,
                feedback TEXT,
                flagged INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(model_id) REFERENCES models(model_id)
            );

            CREATE INDEX IF NOT EXISTS idx_runs_type_status
                ON runs(run_type, status);
            CREATE INDEX IF NOT EXISTS idx_run_events_run
                ON run_events(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_models_dataset
                ON models(dataset_id);
            CREATE INDEX IF NOT EXISTS idx_inference_model_time
                ON inference_logs(model_name, created_at);
            """
        )


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def db_path() -> Path:
    return DB_PATH
