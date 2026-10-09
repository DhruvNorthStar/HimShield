# Isolated future experiments

One approved experiment per uniquely named folder. Source inputs remain shared
and read-only; models, preprocessing, metadata, maps and metrics stay inside the
selected experiment. No scientific experiment was run during Stage 3.

See [artifact protection and reproducibility](../../docs/artifact_protection.md)
for activation, read-only verification, interruption recovery and the scaffold
command. Unset LSM_EXPERIMENT_ID for the established dashboard and benchmarks.

Generated experiment folders are Git-ignored. This README and the benchmark
inventory are intended to be versioned; the manifest does not replace backups.
