from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=None)
def load_prompts() -> dict:
    path = Path(__file__).parents[2] / "config" / "prompts.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
