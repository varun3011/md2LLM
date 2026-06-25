import time
from statistics import mean

import httpx

from server.evaluation.prompts import (
    EVALUATION_SUITE_VERSION,
    PROMPT_SET,
    PROMPT_SET_VERSION,
)
from server.services.registry import create_evaluation, get_model


def _score_response(dimension: str, response_text: str, latency_ms: float, success: bool) -> float:
    if not success:
        return 0.0

    text = response_text.strip()
    word_count = len(text.split())
    lowered = text.lower()

    if dimension == "latency":
        if latency_ms <= 3000:
            return 1.0
        if latency_ms <= 8000:
            return 0.7
        if latency_ms <= 15000:
            return 0.4
        return 0.2

    if dimension == "hallucination_control":
        if "i do not know" in lowered or "not sure" in lowered or "do not have" in lowered:
            return 0.9
        if word_count <= 80:
            return 0.7
        return 0.45

    if word_count < 8:
        return 0.25
    if word_count <= 180:
        return 0.85
    return 0.65


async def run_model_evaluation(model_id: str) -> dict:
    model = get_model(model_id)
    if not model:
        raise ValueError("Model not found")

    model_name = model.get("display_name") or model_id
    prompt_results = []

    async with httpx.AsyncClient(timeout=90.0) as client:
        for item in PROMPT_SET:
            start = time.perf_counter()
            success = False
            response_text = ""
            error = None

            try:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model_name,
                        "prompt": item["prompt"],
                        "stream": False,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    response_text = data.get("response", "")
                    success = True
                else:
                    error = f"Ollama returned {response.status_code}"
            except httpx.ConnectError:
                error = "Cannot connect to Ollama"
            except Exception as exc:
                error = str(exc)

            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            score = _score_response(item["dimension"], response_text, latency_ms, success)
            prompt_results.append(
                {
                    "prompt_id": item["id"],
                    "dimension": item["dimension"],
                    "latency_ms": latency_ms,
                    "success": success,
                    "score": score,
                    "error": error,
                    "response_preview": response_text[:500],
                }
            )

    successful_scores = [result["score"] for result in prompt_results if result["success"]]
    aggregate_score = round(mean(successful_scores), 3) if successful_scores else 0.0
    dimension_scores = {}
    for result in prompt_results:
        dimension_scores.setdefault(result["dimension"], []).append(result["score"])
    dimension_scores = {
        dimension: round(mean(scores), 3)
        for dimension, scores in dimension_scores.items()
    }

    failures = [result for result in prompt_results if not result["success"]]
    notes = (
        f"Evaluated {len(prompt_results)} starter prompts through Ollama. "
        f"{len(failures)} prompt(s) failed."
    )

    return create_evaluation(
        model_id=model_id,
        dataset_id=model.get("dataset_id"),
        evaluation_suite_version=EVALUATION_SUITE_VERSION,
        prompt_set_version=PROMPT_SET_VERSION,
        aggregate_score=aggregate_score,
        scores={
            "aggregate": aggregate_score,
            "dimensions": dimension_scores,
            "prompts": prompt_results,
        },
        notes=notes,
    )
