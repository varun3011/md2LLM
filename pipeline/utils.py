from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml


def load_environment(env_path: str = ".env") -> None:
    env_file = Path(env_path)
    load_dotenv(env_file if env_file.exists() else None)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key


def load_config(config_path: str) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
