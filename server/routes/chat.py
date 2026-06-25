from fastapi import APIRouter, Form, HTTPException

from server.services.registry import monotonic_ms, record_inference

router = APIRouter(prefix="/api")


def _record_inference_safely(**kwargs):
    try:
        return record_inference(**kwargs)
    except Exception:
        return None


@router.post("/chat")
async def chat(
    message: str = Form(...),
    model_name: str = Form(default="my-model"),
):
    """Send a prompt to a local Ollama model and return the full response."""
    import time

    import httpx

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": message,
                    "stream": False,
                },
            )

            if response.status_code != 200:
                error_summary = f"Ollama returned {response.status_code}"
                _record_inference_safely(
                    model_name=model_name,
                    latency_ms=monotonic_ms(start),
                    success=False,
                    error_summary=error_summary,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"{error_summary}. Is the model loaded?",
                )

            data = response.json()
            inference_log = _record_inference_safely(
                model_name=model_name,
                latency_ms=monotonic_ms(start),
                success=True,
                token_usage={
                    "prompt_eval_count": data.get("prompt_eval_count"),
                    "eval_count": data.get("eval_count"),
                },
            )
            return {
                "response": data.get("response", ""),
                "model": model_name,
                "done": data.get("done", True),
                "inference_log_id": inference_log["log_id"] if inference_log else None,
            }
    except httpx.ConnectError:
        _record_inference_safely(
            model_name=model_name,
            latency_ms=monotonic_ms(start),
            success=False,
            error_summary="Cannot connect to Ollama",
        )
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Ollama. Make sure Ollama is running: ollama serve",
        )
    except httpx.TimeoutException:
        _record_inference_safely(
            model_name=model_name,
            latency_ms=monotonic_ms(start),
            success=False,
            error_summary="Ollama request timed out",
        )
        raise HTTPException(status_code=504, detail="Ollama request timed out")
    except HTTPException:
        raise
    except Exception as exc:
        _record_inference_safely(
            model_name=model_name,
            latency_ms=monotonic_ms(start),
            success=False,
            error_summary=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
