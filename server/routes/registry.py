from fastapi import APIRouter, Form, HTTPException

from server.db import db_path, init_db
from server.services.evaluation import run_model_evaluation
from server.services.registry import (
    get_dataset,
    get_evaluation,
    get_model,
    get_run,
    get_run_events,
    compare_records,
    diagnose_run,
    list_records,
    read_run_log,
    registry_summary,
    update_inference_feedback,
    update_model_status,
)

router = APIRouter(prefix="/api/registry", tags=["registry"])


@router.get("/summary")
async def summary():
    init_db()
    return {
        **registry_summary(),
        "database_path": str(db_path()),
    }


@router.get("/datasets")
async def datasets(limit: int = 100):
    return {"datasets": list_records("datasets", limit=limit)}


@router.get("/datasets/{dataset_id}")
async def dataset_detail(dataset_id: str):
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get("/runs")
async def runs(limit: int = 100):
    return {"runs": list_records("runs", order_by="updated_at DESC", limit=limit)}


@router.get("/runs/{run_id}")
async def run_detail(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        **run,
        "events": get_run_events(run_id),
        "logs": read_run_log(run_id),
        "diagnostics": diagnose_run(run, get_run_events(run_id), read_run_log(run_id)),
    }


@router.get("/runs/{run_id}/logs")
async def run_logs(run_id: str, limit: int = 500):
    if not get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "logs": read_run_log(run_id, max_lines=limit)}


@router.get("/models")
async def models(limit: int = 100):
    return {"models": list_records("models", limit=limit)}


@router.get("/models/{model_id}")
async def model_detail(model_id: str):
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    evaluations = [
        evaluation
        for evaluation in list_records("evaluations", limit=500)
        if evaluation.get("model_id") == model_id
    ]
    return {
        **model,
        "evaluations": evaluations,
    }


@router.post("/models/{model_id}/status")
async def set_model_status(
    model_id: str,
    deployment_status: str = Form(default=""),
    readiness_status: str = Form(default=""),
    tags: str = Form(default=""),
):
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    allowed_deployments = {"draft", "staging", "production", "archived", ""}
    if deployment_status not in allowed_deployments:
        raise HTTPException(status_code=400, detail="Invalid deployment status")

    tag_list = None
    if tags.strip():
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    updated = update_model_status(
        model_id,
        deployment_status=deployment_status or None,
        readiness_status=readiness_status or None,
        tags=tag_list,
    )
    return updated


@router.post("/models/{model_id}/evaluate")
async def evaluate_model(model_id: str):
    if not get_model(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        return await run_model_evaluation(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evaluations")
async def evaluations(limit: int = 100):
    return {"evaluations": list_records("evaluations", limit=limit)}


@router.get("/evaluations/{evaluation_id}")
async def evaluation_detail(evaluation_id: str):
    evaluation = get_evaluation(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


@router.get("/inference-logs")
async def inference_logs(limit: int = 100):
    return {"inference_logs": list_records("inference_logs", limit=limit)}


@router.post("/inference-logs/{log_id}/feedback")
async def inference_feedback(
    log_id: str,
    feedback: str = Form(default=""),
    flagged: bool = Form(default=False),
):
    updated = update_inference_feedback(log_id, feedback=feedback or None, flagged=flagged)
    if not updated:
        raise HTTPException(status_code=404, detail="Inference log not found")
    return updated


@router.get("/compare/models")
async def compare_models(left: str, right: str):
    left_model = get_model(left)
    right_model = get_model(right)
    if not left_model or not right_model:
        raise HTTPException(status_code=404, detail="One or both models were not found")

    fields = [
        "base_model_repo",
        "dataset_id",
        "training_run_id",
        "format",
        "size_bytes",
        "readiness_status",
        "deployment_status",
        "tags",
    ]
    differences = compare_records(left_model, right_model, fields)

    return {
        "left": left_model,
        "right": right_model,
        "differences": differences,
    }


@router.get("/compare/datasets")
async def compare_datasets(left: str, right: str):
    left_dataset = get_dataset(left)
    right_dataset = get_dataset(right)
    if not left_dataset or not right_dataset:
        raise HTTPException(status_code=404, detail="One or both datasets were not found")
    fields = [
        "source_type",
        "generation_goal",
        "quality_threshold",
        "generation_provider",
        "generation_model",
        "prompt_template_version",
        "file_count",
        "pair_count",
        "content_hash",
    ]
    return {
        "left": left_dataset,
        "right": right_dataset,
        "differences": compare_records(left_dataset, right_dataset, fields),
    }


@router.get("/compare/runs")
async def compare_runs(left: str, right: str):
    left_run = get_run(left)
    right_run = get_run(right)
    if not left_run or not right_run:
        raise HTTPException(status_code=404, detail="One or both runs were not found")
    fields = [
        "run_type",
        "status",
        "duration_seconds",
        "dataset_id",
        "base_model_id",
        "output_model_id",
        "config",
        "hardware",
        "metrics",
        "error_summary",
    ]
    return {
        "left": left_run,
        "right": right_run,
        "differences": compare_records(left_run, right_run, fields),
    }
