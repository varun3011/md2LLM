"""
Shared utilities for md2LLM training scripts.
Used by both train_mlx.py and train_unsloth.py.
"""

import json
from pathlib import Path


def load_config(config_path: str) -> dict:
    """Load training config from JSON file."""
    with open(config_path) as handle:
        return json.load(handle)


def write_progress(progress_file: str, data: dict):
    """
    Write training progress to a JSON file.
    The server polls this file to stream progress to the UI.
    """
    try:
        tmp = progress_file + ".tmp"
        with open(tmp, "w") as handle:
            json.dump(data, handle)
        Path(tmp).rename(progress_file)
    except Exception as exc:
        print(f"Warning: could not write progress: {exc}")


def load_jsonl_dataset(data_file: str, goal: str) -> list:
    """
    Load training pairs from JSONL file.
    Returns list of dicts ready for formatting.
    """
    pairs = []
    with open(data_file) as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    pairs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return pairs


def format_alpaca(pair: dict) -> str:
    """
    Format a knowledge/style/reasoning pair into Alpaca prompt format.
    """
    instruction = pair.get("instruction", "")
    inp = pair.get("input", "")
    output = pair.get("output", "")

    if inp:
        return (
            f"### Instruction:\n{instruction}\n\n"
            f"### Input:\n{inp}\n\n"
            f"### Response:\n{output}"
        )
    return f"### Instruction:\n{instruction}\n\n### Response:\n{output}"


def format_chatml(pair: dict) -> str:
    """
    Format a chatbot pair into ChatML format.
    """
    messages = pair.get("messages", [])
    result = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        result += f"<|im_start|>{role}\n{content}<|im_end|>\n"
    return result


def prepare_texts(pairs: list, goal: str) -> list:
    """
    Convert training pairs to formatted text strings.
    """
    texts = []
    for pair in pairs:
        if goal == "chatbot":
            texts.append(format_chatml(pair))
        else:
            texts.append(format_alpaca(pair))
    return texts


def get_hf_model_id(model_name: str) -> str:
    """
    Convert Ollama model name to HuggingFace model ID.
    """
    mapping = {
        "llama3.2:3b": "meta-llama/Llama-3.2-3B-Instruct",
        "llama3.2:1b": "meta-llama/Llama-3.2-1B-Instruct",
        "phi3:mini": "microsoft/Phi-3-mini-4k-instruct",
        "phi3:medium": "microsoft/Phi-3-medium-4k-instruct",
        "mistral:7b": "mistralai/Mistral-7B-Instruct-v0.3",
        "qwen2.5:1.5b": "Qwen/Qwen2.5-1.5B-Instruct",
        "qwen2.5:7b": "Qwen/Qwen2.5-7B-Instruct",
    }
    result = mapping.get(model_name)
    if not result:
        for key, value in mapping.items():
            if model_name.startswith(key.split(":")[0]):
                return value
    return result
