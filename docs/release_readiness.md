# Release readiness

**Final audit, 24 October 2026: PARTIAL for portable/public release.** The existing local application passes fresh automated and browser checks; [the final audit](final_release_audit.md) lists the exact remaining blockers. GitHub was confirmed **PUBLIC** by authenticated and unauthenticated API requests. No push or visibility change was performed. A follow-up classified the real CSV blobs as local Codex checkpoint trees, not branch commits; the three checked public branch histories did not contain them. The earlier broad history warning below is not evidence of a public CSV leak.

**24 October 2026 update:** returned spatial/control results passed independent verification and are integrated as aggregate-only presentation. See [scientific results and limitations](spatial_validation_results.md). Original models, maps and metrics are preserved. The Stage 6A audit below is historical; its pending-results statements describe 11 October, not the now verified experiment. Public district publication/redistribution, code licensing, fresh-machine installation, native zoom/touch/assistive-technology checks and historical-data review still require attention. Six-page/four-viewport browser checks have since passed; they are not physical-device or full accessibility certification.

## Archived Stage 6A audit — 11 October 2026

Audited 11 October 2026 on `codex/phase3-integration`, starting from `a2cd0d204be7c097b02314eb4db7fd4a6d2c6bdd`. Documentation/rehearsal is not approval to package, publish, push or promote to `main`.

## Readiness decision

The existing local academic application is suitable for artifact-backed rehearsal, subject to manual browser sign-off. A portable/public release is **not yet cleared**: code omits saved artifacts, and official district publication/redistribution rights remain unresolved.

| Finding | Status / next action |
| --- | --- |
| Models, six pages, map modes | Require fresh regression checks, benchmark prediction parity and hashes before docs commit |
| All 13 districts | Matching private 2025 inputs, original RF class raster and loopback session; identities/counts/NoData verified separately |
| Spatial validation | Infrastructure ready; new results pending review; frozen protocol and teammate package unchanged |
| Setup dependencies | Windows base lock plus Phase 3 overlay; pip requirements incomplete; fresh download/solver and second-machine install not performed |
| Browser/accessibility | Desktop/mobile, 200% zoom, focus, touch, map interaction and chart/table visual sign-off pending; AppTest is not browser certification |
| Code licence | No repository-level LICENSE/LICENCE file; owner must choose a licence before reusable public release |
| QGIS portability | Tracked project contains absolute datasource paths; review privately before shipping; current edits excluded from commit |
| Historical real CSVs | Reachable history includes dataset.csv (~2.61 MiB) and dataset_raw.csv (~3.11 MiB). Untracked now does not erase history. Review rights/privacy before distributing Git history; no rewrite performed |
| Large history blobs | None exceeds 10 MiB in focused audit; largest observed 3,257,405-byte dataset_raw.csv |
| Secret patterns | No provider-token/private-key matches in current tracked text; heuristic scan is not a full historical secret/security audit |
| Private official assets | No ABDB vectors tracked; retain inputs/recovery evidence outside public packages |

## Official district policy

[Survey of India guidelines](https://onlinemaps.surveyofindia.gov.in/GeospatialGuidelines.aspx), clause xiii, describe permissible digital display/printing of standard boundaries. Its [copyright policy](https://surveyofindia.gov.in/pages/copyright-policy) also sets reproduction/attribution conditions. Both were checked on 11 October 2026; neither is represented as a product-specific permission letter or blanket clearance.

The project's approved scope remains **local academic use only** for the validated feature. Public hosting, official screenshot publication, sharing derived images and original/transformed/simplified vector redistribution remain on hold pending applicable-rights clarification. Attribution: **Source: Survey of India, Government of India.** Image-only payloads avoid vector exposure but do not independently grant redistribution rights. See [local implementation constraints](local_district_views.md).

A later approved package must exclude private Git contents, downloaded ABDB, derived geometry, recovery evidence, local datasets, credentials, temporary uploads and user-specific QGIS settings. Original map HTML also needs source/attribution review before public redistribution. Use an explicit reviewed allowlist and exact-artifact fresh-machine rehearsal, not a ZIP of the entire development folder. No package is created here.

## Acceptance checks

Use [Windows setup](windows_setup.md) and [runbook](demo_runbook.md). Before committing these docs, require:

- Dashboard, district, protection/CLI and spatial fixture tests pass without unexpected skips.
- Six pages, presets/snapshots, saved figure choices, 13 scopes and map modes pass available automated checks.
- All 217 preservation records retain hashes/sizes/mtimes; all 216 inventory entries and 18 dependency checks pass.
- SVM/RF/XGBoost class/score identities match the 4,551-point benchmark.
- Activated native setup/Phase 3 imports work; dry runs exit successfully without fitting/scientific publication.
- Current-document links/paths and command syntax resolve; only approved Markdown staged; whitespace checks pass.
- Frozen spatial code/config, environment files, Phase 2, ABDB, QGIS and untracked CSVs unchanged.

Keep recovery copies: manifests detect damage but do not restore bytes. Never silence failures by changing hashes, rewriting reports, generating rasters or retraining. Do not run the scheduled training pipeline; stop on a critical failure.

## Stage 6A verification outcome

The current run passed 132 automated tests with zero failures, errors or skips: 32 dashboard, 17 district, 45 protection/CLI and 38 spatial synthetic-fixture tests. All six pages and all 13 local district selections passed available AppTest checks, including map modes and dedicated Rudraprayag products. Synthetic test fitting did not use the real dataset or alter saved models.

All 217 protected files retained their hashes, sizes and modification times; all 216 inventory entries and 18 dependency checks passed. Saved SVM, RF and XGBoost predictions matched the preserved 4,551 benchmark points exactly. The manifest, private ABDB, Phase 2, frozen code/configuration and local QGIS/CSV records remained unchanged.

The installed setup checker finished READY with zero warnings; Phase 3 imports, Streamlit CLI and all three dry runs succeeded in activated Conda. Legacy plans skipped 13 Phase 2 and five Phase 3 artifact-producing steps; read-only checks were permitted. A diagnostic server passed 10 HTTP checks and was terminated. Conda create/update help was checked for syntax only: no new environment, dependency installation, second-machine test or real-browser verification was performed.

Documentation checks resolved 59 internal links and 44 project paths, parsed 10 PowerShell blocks, matched 18 displayed metric cells to saved metadata and confirmed all four archived handoff bodies were preserved. Final staging is restricted to the reviewed Markdown allowlist; private verification evidence is outside the commit.

## Documentation corrections

README describes three-model HimShield rather than a two-model Phase 2-only project. Status/contributor instructions reflect integration, without automatic pushes/main commits. September handoffs carry archive notices with historical results retained. Setup distinguishes base/overlay, DLL propagation, missing pip dependencies, private inputs and artifact restoration. Architecture separates random benchmarks from pending spatial performance; runbook supplies tour/fallback/error instructions.

This stage changes no code, environment definition, model, metric, dataset, saved map, QGIS content or teammate training protocol/package. It selects no licence, rewrites no history, builds no package, installs no dependency, runs no real training, pushes nothing and does not merge into `main`.
