# Working with HimShield

Current development is on `codex/phase3-integration` in the original repository. Isolated demo/handoff folders are not its replacement. `main` retains Phase 2. Preserve both existing branches, QGIS edits, untracked CSVs and recovery copies. Do not push or promote to `main` without separate approval.

## Review and commit the approved change

```powershell
git branch --show-current
git status --short
git diff --check
```

Inspect the intended diff and name each approved file when staging. Check `git diff --cached --name-only`, `git diff --cached --check` and `git diff --cached` before committing. Never use `git add .`: both real CSVs are untracked and excluded by exact `.gitignore` rules, but QGIS still has intentional tracked local modifications and unrelated files may be present. Ignore rules are not a substitute for reviewing the index.

A local commit is not permission to push, merge, delete branches or rewrite history. Keep unrelated files outside it. Historical automatic-push/main-branch instructions are superseded.

## Scientific artifacts and experiments

Read [artifact protection](docs/artifact_protection.md) before invoking writers. Benchmark destinations are protected; `--force` does not authorize replacement. A manifest is not a backup. Manual edits/external GIS tools can bypass guards; keep recovery copies.

Restore trusted saved artifacts for demos instead of retraining. Only load trusted pickle/joblib files with compatible versions. New approved science is isolated under `outputs/experiments/<experiment_id>/`; it must not silently replace benchmark metrics.

The teammate's portable training package and the frozen [spatial protocol](docs/spatial_validation_protocol.md) are separate work. Do not modify either for dashboard/release documentation. The returned spatial/control results have been [independently verified and integrated as aggregates](docs/spatial_validation_results.md); future results still require review before incorporation. The deployed benchmark models remain unchanged.

## Setup and tests

Use [Windows setup](docs/windows_setup.md), including Conda activation and the Phase 3 overlay. `requirements.txt` is a historical Phase 2 fallback, not a complete current installer.

Run relevant tests from the [runbook](docs/demo_runbook.md). Tests can fit tiny synthetic fixtures; they do not retrain benchmark models or run real spatial experiments. Phase 2 compatibility remains required.

Keep notebook logic in `src/` and avoid scratch/output-heavy commits. `nbstripout --install` is optional developer Git-filter setup, not required to launch a dashboard. Do not alter shared repository filters merely for a demo.

## Packaging and history

Keep credentials, private ABDB inputs/derived geometry, recovery evidence, local datasets and temporary files out of commits/packages. `.gitignore` does not validate rights or erase history. HimShield-owned code uses [MIT](LICENSE); external data retains the terms in [third-party notices](THIRD_PARTY_NOTICES.md). See [release readiness](docs/release_readiness.md) for the distinction between private local CSV checkpoints and branch history. Historical VRTs contain machine-specific source references; the QGIS path warning was corrected in the later audit.

Do not ZIP the entire working folder. A separately approved release needs an explicit reviewed allowlist, source attribution and a fresh-machine rehearsal. No package is created here. Use descriptive commit messages and inspect both versions of conflicts; never discard local work to make verification pass.
