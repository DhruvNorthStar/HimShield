"""Transactional artifact writers. Verified benchmark paths are never writable."""
import contextvars
import functools
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import config

_ACTIVE = contextvars.ContextVar("artifact_transaction", default=None)


class ProtectionError(RuntimeError):
    """A write would overwrite a benchmark or escape the selected experiment."""


def validate_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Empty/missing staged artifact: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        json.loads(path.read_text(encoding="utf-8"))
    elif suffix in (".pkl", ".joblib"):
        import joblib
        joblib.load(path)
    elif suffix in (".tif", ".tiff"):
        import rasterio
        with rasterio.open(path) as raster:
            if raster.count < 1 or raster.width < 1 or raster.height < 1 or raster.crs is None:
                raise ValueError("Invalid staged raster header")
            for _, window in raster.block_windows(1):
                raster.read(1, window=window)
    elif suffix == ".png":
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
    elif suffix in (".txt", ".html", ".csv"):
        text = path.read_text(encoding="utf-8")
        if suffix == ".html" and "<html" not in text.lower():
            raise ValueError("Staged map is not an HTML document")


class WriteTransaction:
    """Validate the whole step, then publish files and its completion manifest.

    Publication is atomic per file, not across multiple files. Prior experiment
    versions and incomplete staging directories are retained for recovery.
    """
    def __init__(self, step: str, *, allow_replace: bool = False):
        self.step, self.allow_replace = step, allow_replace
        self.paths = {}
        self.run_id = uuid.uuid4().hex
        self.token = self.lock = None

    def __enter__(self):
        if not config.EXPERIMENT_DIR:
            raise ProtectionError("Verified benchmarks are read-only. Select a new LSM_EXPERIMENT_ID; --force cannot unlock benchmarks.")
        self.root = config.EXPERIMENT_DIR.resolve()
        if self.root != config.experiment_directory(config.EXPERIMENT_ID).resolve():
            raise ProtectionError("Experiment root does not match its validated ID.")
        if _ACTIVE.get() is not None:
            raise ProtectionError("Nested transactions are not supported.")
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = self.root / ".writer.lock"
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ProtectionError(f"Another writer or an interrupted run owns {self.lock}; inspect it rather than automatically removing it.")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "run_id": self.run_id, "step": self.step}))
        self.staging = self.root / ".staging" / self.run_id
        try:
            self.staging.mkdir(parents=True)
            from src import provenance
            self.input_snapshot = provenance.input_snapshot(self.step)
            for path in provenance.expected_outputs(self.step):
                self.stage_path(path)  # reject escapes/existing results before computation
            self.token = _ACTIVE.set(self)
        except BaseException:
            self.lock.unlink()
            raise
        return self

    def stage_path(self, destination: Path) -> Path:
        destination = Path(destination).resolve()
        if not destination.is_relative_to(self.root):
            raise ProtectionError(f"Write outside the selected experiment is blocked: {destination}")
        if destination == self.root or destination.name in {"manifest.json", "experiment.json", ".writer.lock"} or destination.is_relative_to(self.root / ".staging") or destination.is_relative_to(self.root / ".history"):
            raise ProtectionError(f"Reserved transaction path: {destination}")
        if destination.exists() and destination != config.METADATA_PATH.resolve() and not self.allow_replace:
            raise ProtectionError(f"Existing experiment artifact is protected: {destination}")
        if destination not in self.paths:
            staged = self.staging / destination.relative_to(self.root)
            staged.parent.mkdir(parents=True, exist_ok=True)
            self.paths[destination] = staged
        return self.paths[destination]

    def read_path(self, destination: Path) -> Path:
        staged = self.paths.get(Path(destination).resolve())
        return staged if staged is not None and staged.exists() else Path(destination)

    def publish(self):
        from src import provenance
        if not self.paths:
            raise ValueError("No artifacts produced; no completion entry recorded.")
        for destination in provenance.expected_outputs(self.step):
            if destination.resolve() not in self.paths:
                raise ValueError(f"Step did not stage its required output: {destination}")
        for staged in self.paths.values():
            validate_file(staged)
        if provenance.input_snapshot(self.step) != self.input_snapshot:
            raise ProtectionError("Dependencies changed during computation; staged output was not published.")
        for destination in self.paths:
            if destination.exists() and destination != config.METADATA_PATH.resolve() and not self.allow_replace:
                raise ProtectionError(f"Destination appeared during computation: {destination}")
        journal = {"step": self.step, "run_id": self.run_id, "status": "validated",
                   "files": [str(p.relative_to(self.root)) for p in self.paths]}
        (self.staging / "transaction.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
        for destination, staged in self.paths.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                backup = self.root / ".history" / self.run_id / destination.relative_to(self.root)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
                os.replace(staged, destination)
            else:
                os.link(staged, destination)  # atomic no-clobber publication on NTFS
                staged.unlink()
        provenance.record_step(self.step, self.input_snapshot, list(self.paths), self.run_id)
        journal["status"] = "complete"
        (self.staging / "transaction.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")

    def __exit__(self, kind, value, trace):
        try:
            if kind is None:
                self.publish()
        finally:
            if self.token is not None:
                _ACTIVE.reset(self.token)
            if self.lock is not None:
                self.lock.unlink()
        return False


def output_path(path: Path) -> Path:
    transaction = _ACTIVE.get()
    if transaction is None:
        raise ProtectionError("Writes require a WriteTransaction in a selected experiment.")
    return transaction.stage_path(Path(path))


def read_output(path: Path) -> Path:
    transaction = _ACTIVE.get()
    return transaction.read_path(path) if transaction else Path(path)


def protected_step(step: str):
    def decorate(function):
        @functools.wraps(function)
        def guarded(*args, **kwargs):
            import sys
            help_modules = {"src.clean_gsi", "src.make_stable_points", "src.label_categories",
                            "src.warp_ndvi", "src.get_open_data"}
            # python -m executes as __main__; its ModuleSpec retains the real name.
            module_spec = function.__globals__.get("__spec__")
            module_name = getattr(module_spec, "name", None) or function.__module__
            if "--help" in sys.argv and (step in {"state", "shap", "map", "demo_map"}
                                         or (step == "source-data" and module_name in help_modules)):
                return function(*args, **kwargs)
            if step == "state" and "--estimate-only" in sys.argv:
                return function(*args, **kwargs)
            if step == "source-data":
                raise SystemExit("Source-data generation is locked. Experiments reuse existing inputs; source updates require separate approval.")
            selected = step
            from src.provenance import argument
            if step == "demo_map" and argument("--model", "rf") == "svm":
                selected = "demo_map_svm"
            if step == "state" and argument("--district") is not None:
                selected = "district_raster"
            try:
                with WriteTransaction(selected, allow_replace=os.environ.get("LSM_REBUILD") == "1"):
                    result = function(*args, **kwargs)
                    if result not in (None, 0):
                        raise ProtectionError(f"Step returned {result}; partial output was not published.")
                    return result
            except ProtectionError as error:
                raise SystemExit(str(error)) from error
        return guarded
    return decorate


def update_metadata(section: str, payload: dict[str, Any]) -> None:
    data: dict[str, Any] = {}
    current = read_output(config.METADATA_PATH)
    if current.exists():
        data = json.loads(current.read_text(encoding="utf-8"))
    data.setdefault("random_seed", config.RANDOM_STATE)
    data["data_source"] = config.DATA_SOURCE
    data["dataset_file"] = config.DATASET_CSV.name
    data["experiment_id"] = config.EXPERIMENT_ID
    data[section] = payload
    data.setdefault("written", {})[section] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output_path(config.METADATA_PATH).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def save_feature_names(names: list[str]) -> None:
    output_path(config.FEATURE_NAMES_PATH).write_text(json.dumps(names, indent=2), encoding="utf-8")


def load_feature_names() -> list[str]:
    if not config.FEATURE_NAMES_PATH.exists():
        raise SystemExit(f"{config.FEATURE_NAMES_PATH} not found. Run approved experiment preprocessing first.")
    return json.loads(config.FEATURE_NAMES_PATH.read_text(encoding="utf-8"))
