# Spatial validation infrastructure (Stage 4B)

The original benchmarks, preprocessing script, models and dashboard remain unchanged.
This infrastructure plans by default. Stage 4B permits saving split records and
testing with tiny generated fixtures; it does not authorize fitting real-data models.

The explicit protocol is in `configs/spatialcv-10km-buffer2km-v1.json`. It anchors
the verified Stage 3 checkpoint, feature schema, seeds, grouping, buffers, tuning
budget and laptop limits. Changes to it invalidate experiment fingerprints.

## Membership and leakage controls

- Five outer folds, 10,000 m squares, fixed UTM origin (0,0), EPSG:32644.
- Assign samples by 30 m DEM cell centres; conservatively union blocks with repeated
  event identifiers. Never change sample coordinates, labels or event records.
- Remove spatial training samples within 2,000 m of held-out block rectangles and
  actual test locations. Rectangles include any sampled coordinate extending beyond
  a cell-centre square. The polygon buffer is deliberately more conservative than
  point-only buffering. Points on the boundary are removed.
- Three buffered spatial inner folds are constructed within each retained outer
  training set. Buffered-out outer samples cannot re-enter tuning. Every outer
  training row has exactly one inner validation membership.
- The random-group control uses a seeded random outer assignment of cell/event
  groups. Its outer buffer is explicitly **zero**: geographic proximity is the
  comparison condition. It uses the same three buffered spatial inner folds policy
  as the spatial protocol, holding the tuning policy constant. Its outer folds do
  not claim a 2 km guarantee. A random-inner-CV ablation is not implemented here.
- All three models read the same saved memberships; no model-specific resplitting.

CSV/GIS row identity, fixed categorical code mappings, projected CRS and shared input
hashes are checked before planning. Coordinates and IDs never become predictors.
The established water exclusion is a fixed eligibility rule, not learned from folds.

For each inner fit, learn numeric medians, categorical modes/rare mapping/reference
levels, encoding, constant-feature removal, VIF filtering and scaling on that inner
training partition only. Apply SMOTE after scaling to its training rows only.
Fit fresh transformations on retained outer training when refitting the selected
candidate. Unknown categories map to the training-defined Other encoding if present,
otherwise to the all-zero/reference representation; held-out categories never create
new columns. All-missing numeric training features and insufficient class support
fail rather than borrowing values from held-out data.

Four predefined candidates per model, three inner folds, ROC-AUC selection. SVM RBF
uses decision margins and probability=False; no hidden random probability calibration.
RF/XGBoost each use one native thread. XGBoost does not early-stop on outer test data.
After tuning, additional inner OOF predictions select the largest finite threshold
maximizing Youden J. Threshold APIs reject outer-test IDs, duplicate/missing OOF rows
and predictions without the inner-validation origin. Outer labels are used only for
final scoring after tuning/refitting/threshold selection.

Report ROC-AUC, average precision, balanced accuracy, precision, recall, specificity,
F1 and confusion counts by outer fold. Do not pool SVM margins across different fits
into one AUC. Calibration and spatial confidence intervals are separate work.

## Safe commands

Run from the original repository with the Conda environment activated, including its
DLL PATH; selecting python.exe alone is insufficient on Windows.

~~~powershell
Set-Location C:\Projects\landslide-uttarakhand
conda activate landslide
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
python -m src.run_spatial_experiment --dry-run
~~~

No directories/files are created by the default action or --dry-run, even when RAM
is insufficient for training. Class counts, distances, membership hash and the
resource warning are printed. No model/scaler fitting, resampling, tuning or raster
sampling/generation occurs. Only existing point exports and the DEM header are read.

Stage 4B-approved membership publication:

~~~powershell
python -m src.run_spatial_experiment --prepare
python -m src.run_spatial_experiment --prepare --resume
~~~

The second command verifies an already completed design and changes no bytes or
timestamps. Existing invalid/different records cannot be overwritten, even through
LSM_REBUILD. Use a separately reviewed version/ID for changed science/configuration.

## Isolated records and preservation

~~~text
outputs/experiments/spatialcv-10km-buffer2km-v1/
  experiment.json
  manifest.json
  processed/
    design.json          exact outer/inner row IDs, buffer removals, counts and spec
    samples.csv          point IDs, coordinates, labels, cell/block/event groups
    membership.csv       protocol, outer/inner fold, row ID and role
  pilot/<protocol>/fold_01/    future fixed-parameter timing only, no test evaluation
  results/<protocol>/fold_01/  future pipelines, receipts, test predictions, logs
  .staging/<run_id>/
  .history/<run_id>/
~~~

No GIS copies, benchmark models, benchmark metadata or dashboard metrics are stored
in the design. Pipeline files contain their own per-fold preprocessing. Receipts
record training IDs, feature contracts, VIF drops, threshold origin, candidate
scores, fit timing and the common membership fingerprint. Stage 3 manifests record
source code/config/data hashes, library versions, actual producer commit and invocation.
The code hashes distinguish uncommitted implementation from the checkpoint commit.

All scientific output publication uses the existing WriteTransaction guard, staging
validation, input recheck, no-clobber publication and manifest-last completion.
New experiment specifications do not make benchmark destinations writable.
Legacy provenance fingerprint compatibility updates, if needed, affect code hashes
only after verification; benchmark inventory, metrics and prediction identity remain
unchanged. A hash manifest detects damage but is not a backup.

## Resume and cancellation

Completed model jobs are skipped only with --resume and matching input/code/config/
environment/output hashes. An incomplete job without published outputs can restart
after a graceful interruption; its prior staging is retained. Invalid partially
published outputs, mismatched dependencies and a remaining .writer.lock stop execution
and require inspection. There is no automatic overwrite, stale-lock removal or cleanup.

A file named CANCEL at the experiment root requests cooperative cancellation before
the next fit or publication. Retain/rename that control file after inspection before
resuming. Ctrl+C or a supervisor time/memory breach terminates the worker; a hard stop
can leave its lock. Inspect retained staging, journal and PID before any separately
approved lock recovery. Limits are enforced by the parent, so native fitting cannot
silently run beyond the wall-clock budget. Publication is atomic per file, not as a
multi-file database transaction: incomplete publication fails manifest verification.

## Future timed pilot — NOT RUN during Stage 4B

After separate training approval and freeing RAM, this explicit command fits one
frozen outer fold for each model with predefined pilot parameters. It performs no
grid search, no inner fitting and no outer-test evaluation:

~~~powershell
python -m src.run_spatial_experiment --timed-pilot --approve-training --protocol spatial --outer-fold 1 --model all --max-seconds 600 --max-memory-mb 2048
~~~

One supervised worker at a time, one native thread, 256 MiB SVM cache, at least
3,072 MiB available RAM and 2,048 MiB free storage. Total pilot wall-clock budget is
600 seconds including worker startup and input/split verification; each worker is
monitored for 2,048 MiB aggregate resident memory. Timer/memory caps can be lowered.
No GPU, parallel grids, raster generation or automatic full-data refit is used.
psutil and threadpoolctl are required; both are already in the activated environment.

The separate --train --approve-training action is future-only and also requires a
verified prepared design. It runs jobs serially, with a 600 s per-job limit, and
supports selecting a protocol/fold/model and verified resume. The limited full
comparison is 480 fits: 240 per protocol, including inner OOF threshold fitting.
Successful jobs remain isolated and do not promote a model to the dashboard.

The 10 km/2 km scales are a feasible pilot, not proven independence ranges. Retain the
Stage 4A road/pseudo-absence/coordinate limitations and plan larger-region sensitivity
checks before making strong regional-generalization claims.
