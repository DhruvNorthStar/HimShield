"""
Shared writers for the Phase 2 exit artifacts.

Phase 3 loads these by name, so each step adds its own section to one metadata
file instead of overwriting it. Steps run in order (preprocess, train_svm,
train_rf, evaluate) and each merges its part.
"""
import json
from datetime import datetime, timezone
from typing import Any

from src import config


def update_metadata(section: str, payload: dict[str, Any]) -> None:
    """Merge one section into models/metadata.json, keeping what other steps wrote."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if config.METADATA_PATH.exists():
        data = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
    data.setdefault("random_seed", config.RANDOM_STATE)
    data["data_source"] = config.DATA_SOURCE  # synthetic or real: never lose track of which
    data["dataset_file"] = config.DATASET_CSV.name
    data[section] = payload
    data.setdefault("written", {})[section] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    config.METADATA_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def save_feature_names(names: list[str]) -> None:
    """The contract between phases: feature order at predict time must equal train time."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    config.FEATURE_NAMES_PATH.write_text(json.dumps(names, indent=2), encoding="utf-8")


def load_feature_names() -> list[str]:
    if not config.FEATURE_NAMES_PATH.exists():
        raise SystemExit(f"{config.FEATURE_NAMES_PATH} not found. Run `python -m src.preprocess` first.")
    return json.loads(config.FEATURE_NAMES_PATH.read_text(encoding="utf-8"))
