# Artifact protection and reproducibility (Stage 3)

The established Phase 2/Phase 3 benchmarks remain at their existing paths. The
dashboard, QGIS project, saved metrics and trained-model interfaces are unchanged.
Stage 3 changes how project commands decide to rebuild and publish results.

## Inventory and provenance

artifacts/benchmark.json is a small, reviewable JSON inventory. Every entry
records a repository-relative path, byte size, SHA-256, artifact role and Git
tracking status. It inventories existing models, preprocessing files, source
inputs, split bundle, SHAP results, district/state rasters, maps, reports and
figures without copying the large data files.

The manifest also records dependencies, relevant settings, normalized Python
source hashes, installed library versions, selected CLI options, metadata
sections and held-out prediction identities for each managed pipeline step.
Metadata completion timestamps and unrelated sections do not invalidate a step.
The actual training/test row indices and labels remain in prepared.joblib;
their hashes, 4,551 test rows and ordered 23-feature contract are recorded.

These are adopted legacy results, checked against the Stage 3 recovery baseline
and the independent preserved models. The manifest records the verified merge
commit, but does not invent a historical producer commit or claim a new training
run. Future experiments record their actual invocation, environment, source
hashes, source commit and completion time. Source hashes distinguish uncommitted
implementation changes from the recorded commit.

Run read-only checks from a properly activated Conda environment:

~~~powershell
Set-Location C:\Projects\landslide-uttarakhand
conda activate landslide
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
python -m src.provenance verify --predictions
python run_phase2.py --dry-run
python run_phase3.py --dry-run
~~~

The environment-variable removal changes only the current shell. Run activation
before invoking Python so Windows subprocesses inherit the Conda DLL directories.
Hash verification reads the large inputs and can take longer than a timestamp
check. A hash cache exists only within one planning/verification invocation.

## Overwrite protection

- With no experiment selected, managed scientific writers stop before their main
  computation. Neither --force nor LSM_REBUILD unlocks benchmark paths.
- Source downloads, sampling, raster warping and CSV construction are locked in
  this stage. Experiments reuse the existing source inputs.
- LSM_EXPERIMENT_ID redirects derived outputs into one validated experiment
  directory. IDs cannot contain path separators, traversal or Windows reserved
  names. Resolved destinations must stay inside that directory.
- A writer acquires an exclusive .writer.lock and writes into .staging/<run_id>.
  It validates required outputs, parses JSON/joblib/HTML/PNG or reads every raster
  block, and rechecks its input fingerprint before publishing.
- New files use atomic no-clobber publication on local NTFS. Explicit experiment
  replacements archive the prior files in .history/<run_id> before an atomic
  per-file replacement. The completion manifest is written last.
- Missing/corrupt output or changed dependencies invalidate completion. A changed
  mtime, Git checkout timestamp or LF/CRLF normalization alone does not.

If a step is interrupted, preserve its staging and history. Inspect its journal
and last valid manifest; do not automatically delete a stale lock or promote
partial outputs. Replacement is atomic per file, not as one multi-file database
transaction: an interruption between publications can leave a mixed set of
files, which fails manifest verification. Prior replaced files remain recoverable
in history and incomplete staging is retained.

These are application-level protections, not filesystem permissions. Manual
file edits, arbitrary imported helper calls and external QGIS/GIS tools can
bypass them. Keep the Stage 1 recovery checkpoint and verified safety copy;
the manifest detects corruption but cannot restore bytes without a backup.
Hashes are integrity records, not a cryptographic signature.

## Future experiments

The structure is prepared; Stage 3 does not perform a scientific experiment:

~~~text
outputs/experiments/
  README.md
  <experiment_id>/
    experiment.json
    models/
    processed/
    figures/
    manifest.json          created only after a completed writer
    .staging/<run_id>/     retained interruption evidence
    .history/<run_id>/     prior experiment versions when explicitly replaced
~~~

After separate approval, an empty scaffold can be created with:

~~~powershell
python -m src.provenance experiment spatial-validation-001
$env:LSM_EXPERIMENT_ID = "spatial-validation-001"
python run_phase3.py --dry-run
~~~

The scaffold copies no inputs or models. Shared factors and dataset.csv remain
read-only in data/. The selected namespace has its own models, prepared bundle,
metadata, figures, raster outputs and reports; absence of a model never causes
an automatic fallback to a benchmark model. The dashboard uses benchmarks when
LSM_EXPERIMENT_ID is unset.

New spatial validation, ablation or calibration code must declare its dependency,
settings and output specification in src/provenance.py before using
WriteTransaction. Unknown steps are rejected. Use a fresh experiment ID per
scientific configuration and label copied baseline inputs explicitly if a later
approved experiment needs them. Do not hard-link editable experiment models to
the only benchmark copy.

Existing command names remain available. A default plan reuses validated
benchmarks; missing or stale benchmarks produce a BLOCKED decision rather than
silently rebuilding. --force requests an experiment rebuild; the orchestrator
propagates that explicit permission as LSM_REBUILD=1. It cannot authorize a
benchmark replacement. Promotion/replacement needs a separately reviewed
operation and is intentionally absent from Stage 3.

## Code changes

| Files | Purpose |
|---|---|
| src/config.py | Explicit experiment paths; benchmark defaults preserved |
| src/artifacts.py | Guards, exclusive locks, staging, validation, history, publication |
| src/provenance.py | Inventory, dependency fingerprints, integrity/prediction checks |
| run_phase2.py, run_phase3.py | Content-based build planning and inherited subprocess environment |
| src/preprocess.py, src/train_svm.py, src/train_rf.py, src/train_xgboost.py | Guard entry points and stage saved model/preprocessing writes |
| src/evaluate.py, src/near_road_check.py, src/eda.py, src/explain_shap.py, src/viz.py | Guard or stage reports/figures/metadata; isolate prepared-data reads |
| src/demo_map.py, src/predict_raster_full.py, src/map_generator_full.py | Guard/stage maps and raster outputs; isolated derived paths |
| src/clean_gsi.py, src/make_stable_points.py, src/extract_points.py, src/label_categories.py, src/warp_ndvi.py, src/get_open_data.py, src/make_synthetic.py | Lock source-data construction entry points |
| src/verify_phase2.py | Read the selected namespace's prepared bundle |
| tests/test_artifact_protection.py | Disposable protection, interruption and freshness tests |
| .gitignore, outputs/experiments/README.md, README.md, this document | Keep experiment artifacts local and explain the protected workflow |
| artifacts/benchmark.json | Adopt the verified baseline without changing scientific files |

No fitting, split/sampling methodology, model parameters, metrics, dashboard code
or QGIS content changed. Legacy timestamp fields in saved SHAP/raster summaries
remain informational for compatibility; pipeline rebuild decisions use hashes.

The automated fixture suite runs with:

~~~powershell
python -m unittest discover -s tests -v
~~~

Mutable test fixtures live under .git/stage3-verification/fixtures and never use
the scientific output directories. Tests fit no models.
