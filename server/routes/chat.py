from fastapi import APIRouter, Form, HTTPException

router = APIRouter(prefix="/api")


@router.post("/chat")
async def chat(
    message: str = Form(...),
    model_name: str = Form(default="my-model"),
):
    """Send a prompt to a local Ollama model and return the full response."""
    import httpx

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
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama returned {response.status_code}. Is the model loaded?",
                )

            data = response.json()
            return {
                "response": data.get("response", ""),
                "model": model_name,
                "done": data.get("done", True),
            }
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Ollama. Make sure Ollama is running: ollama serve",
        )
