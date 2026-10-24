# Verified spatial-validation results

Independently verified and integrated on 24 October 2026. This is a separate evaluation of the frozen `spatialcv-10km-buffer2km-v1` experiment. It does not replace the three deployed benchmark models, original 4,551-point random held-out metrics, saved SHAP figures, rasters or maps.

## Provenance and independent verification

The return ZIP is `HimShield-standalone-20261024T114050732Z-b77a5e-PASS.zip`, SHA-256:

```text
fd69c3b0c36d7d4bcd9ad3eeb39de136703c3fe7c9b31c233742b2d130aeafc7
```

Its 1,047 files were safely extracted outside the repository; CRC reads and the 1,045-file transfer inventory passed. Original scientific inputs, configuration, scientific source and checkpoint outputs matched. Portable provenance changes add origin tracking; resource wrappers change admission/monitoring rather than fitting methods. The original configuration and frozen protocol remain unchanged.

Using the original data and planner reproduced all 484,534 membership records and the design digest:

```text
b55f24bef5a0ced68ff540512f2403fe4a1cc1488f2c527356a32856757875c6
```

All 30 final jobs were checked individually: four candidates × three inner fits, three selected-candidate OOF fits, and one final outer refit = 16 completed fit phases per job, 480 total. Candidate means/selection, resource audits, single-thread records, output fingerprints and progress events matched. Separate pilots/interrupted histories are not added to this completed-planned-fit count. Verification did not rerun training. Logs/receipts attest inner fitting; individual tuning estimators are not all retained for independent inference.

All 30 final pipelines loaded. Outer-test scores/classes reproduced: RF double scores matched exactly, XGBoost float32 scores matched bitwise after decoding their shortest CSV decimals into the original dtype, and SVM margin differences were at most 8.74e-11; classification decisions matched exactly. No saved CSV or model was rewritten. Metrics, training-only threshold records and complete outer OOF coverage were independently checked, rather than accepting PASS labels.

Each model scores every one of the 15,169 eligible samples exactly once per protocol, without missing/duplicate outer predictions. Original model prediction identities on 4,551 points, 216 inventory entries and 18 dependency checks also passed before integration. Today's 217 preservation records include the user's already edited QGIS state; no historical QGIS rollback was imposed.

Only the 35 KB aggregate summary is committed. Row/event IDs, point coordinates, fold models, detailed receipts and private machine paths remain in the external review; no official ABDB geometry is added. The reader pins the summary checksum with LF/CRLF normalization and checks internal statistics and frozen-configuration identity before displaying it.

## Evaluation design

- Five outer folds, 10 km blocks in EPSG:32644, 30 m raster-cell-centre grouping and conservative repeated-event grouping; identical memberships across all three models within a protocol.
- Spatial outer exclusions cover test locations and held-out block rectangles at 2 km. Retained training sizes are 9,793–10,179, with 1,943–2,323 samples removed. Minimum point separation is 2,022.12 m and minimum block distance is 2,000.09 m.
- Random-group outer control has zero buffer, training sizes 12,132–12,138 and nearest-point distances as small as 6.90 m. This is intentional, not a spatial-buffer failure. Cell/event groups still do not cross train/test.
- Both protocols use three buffered spatial inner folds; all inner training/validation point minima exceed 2 km. This control is not ordinary random inner CV.
- Imputation, categorical decisions, encoding, constant/VIF filtering, scaling and SMOTE are training-fold-contained. Final pipeline medians, vocabularies, VIF/scaler state and training/SMOTE row identities were checked against allowed training rows.
- Selection maximizes mean inner ROC-AUC across four fixed candidates. Thresholds use inner-validation OOF Youden J only, excluding outer labels. SVM uses uncalibrated margins; RF/XGBoost use uncalibrated model scores.

## Five-fold results

Unweighted means ± sample SD (ddof=1), on a percentage scale. SD is expressed in percentage points and **is not a confidence interval**. Accuracy/precision/recall/F1 use fold-specific training-selected thresholds. AP is average precision, not trapezoidal PR-AUC.

| Protocol | Model | ROC-AUC | Average precision | Accuracy | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Buffered spatial CV | SVM (RBF) | 93.73 ± 0.71 | 87.54 ± 1.74 | 86.59 ± 0.74 | 75.26 ± 1.12 | 88.92 ± 1.59 | 81.52 ± 0.99 |
| Buffered spatial CV | Random Forest | 95.54 ± 0.88 | 91.03 ± 1.19 | 88.19 ± 1.56 | 77.81 ± 3.84 | 90.59 ± 2.11 | 83.64 ± 1.71 |
| Buffered spatial CV | XGBoost | 95.76 ± 0.67 | 91.98 ± 0.90 | 88.95 ± 1.07 | 79.65 ± 2.79 | 89.87 ± 1.57 | 84.41 ± 1.21 |
| Random-group control | SVM (RBF) | 94.17 ± 0.24 | 88.41 ± 0.62 | 86.50 ± 0.45 | 74.32 ± 1.53 | 90.83 ± 1.41 | 81.73 ± 0.45 |
| Random-group control | Random Forest | 96.18 ± 0.16 | 92.03 ± 0.44 | 89.25 ± 0.90 | 79.52 ± 2.38 | 91.32 ± 1.61 | 84.98 ± 0.79 |
| Random-group control | XGBoost | 96.18 ± 0.09 | 92.59 ± 0.42 | 89.21 ± 0.56 | 80.18 ± 1.80 | 89.82 ± 1.42 | 84.70 ± 0.44 |

## Control minus spatial differences

Descriptive differences between complete protocol means; positive values mean control scored higher. Protocol memberships and retained training sizes differ, so these differences do not isolate a causal buffer effect and matching fold numbers are not paired geographic regions.

| Model | ROC-AUC gap (pp) | AP gap (pp) | Accuracy gap (pp) | F1 gap (pp) |
| --- | ---: | ---: | ---: | ---: |
| SVM (RBF) | +0.4377 | +0.8704 | -0.0934 | +0.2134 |
| Random Forest | +0.6447 | +0.9925 | +1.0624 | +1.3364 |
| XGBoost | +0.4276 | +0.6082 | +0.2580 | +0.2900 |

## Evidence and interpretation

**Observed:** all three control mean ROC-AUC/AP values exceed spatial values. Spatial ROC-AUC ranges are 92.8838–94.5103% (SVM), 94.0767–96.1393% (RF), and 94.7228–96.3063% (XGBoost). Spatial AUC fold SDs are larger than control SDs. Spatial RF fold 4 is notably lower (94.08%) than its first three folds (about 96.03–96.14%).

**Observed:** both ensembles exceed SVM ROC-AUC in every outer fold of both protocols. XGBoost exceeds RF in four of five spatial folds and two of five control folds. Its spatial mean AUC advantage is about 0.22 pp; control means are almost identical (RF 96.18424%, XGBoost 96.18400%). These observations do not establish a statistically superior model or equivalence.

**Observed:** not every classification metric falls under spatial CV. Spatial SVM accuracy/precision are slightly higher than control, while recall is lower. Fold-specific thresholds create tradeoffs; avoid saying every metric or every model deteriorates uniformly.

**Interpretation:** blocked/buffered evaluation reveals greater geographic fold variability and modest descriptive ranking degradation within this sampled study region. The outer folds contain dispersed held-out blocks, not entirely unseen districts/regions. High AUC therefore supports only this evaluation setting, not universal geographic transfer or event prediction.

**Remaining bias/leakage limits:** the original pseudo-absence cohort was generated globally using the whole known inventory before folding. Historical feature/design choices were informed by the same study dataset. Fold-contained learning prevents the checked preprocessing/threshold leakage, but does not undo study-level selection, road-survey bias, pseudo-absence conditioning, coarse coordinates or missing inventory events. Two kilometres is not a proven independence range; coarse factors and residual spatial dependence can extend farther.

The original random 70/30 benchmark differs in held-out cohort, random versus grouped outer split, training size, preprocessing timing, search budgets and threshold selection. Its saved AUCs remain 94.04%/96.04%/96.16%. A single held-out bootstrap interval and a five-fold SD quantify different things; neither should be substituted for the other. Do not attribute legacy-to-new differences solely to geographic buffering.

## Per-fold variation

The following are metrics from independently checked outer predictions. Training counts exclude outer buffer removals; all models share each protocol/fold's memberships.

| Protocol | Model | Fold | Train | Test | ROC-AUC (%) | AP (%) | Accuracy (%) | Precision (%) | Recall (%) | F1 (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Buffered spatial CV | SVM (RBF) | 1 | 9793 | 3053 | 93.7912 | 88.1687 | 86.7999 | 76.1945 | 87.8073 | 81.5898 |
| Buffered spatial CV | Random Forest | 1 | 9793 | 3053 | 96.0259 | 91.5377 | 90.2391 | 83.8831 | 87.5123 | 85.6593 |
| Buffered spatial CV | XGBoost | 1 | 9793 | 3053 | 96.3063 | 92.5254 | 90.4356 | 84.1659 | 87.8073 | 85.9480 |
| Buffered spatial CV | SVM (RBF) | 2 | 10152 | 3018 | 94.5103 | 88.6852 | 86.4811 | 74.2041 | 90.8092 | 81.6712 |
| Buffered spatial CV | Random Forest | 2 | 10152 | 3018 | 96.1393 | 91.9017 | 88.3366 | 77.2003 | 92.0080 | 83.9562 |
| Buffered spatial CV | XGBoost | 2 | 10152 | 3018 | 96.0796 | 92.5642 | 88.8337 | 78.3761 | 91.6084 | 84.4772 |
| Buffered spatial CV | SVM (RBF) | 3 | 10114 | 3017 | 94.3340 | 89.3879 | 87.1064 | 75.8679 | 89.6000 | 82.1641 |
| Buffered spatial CV | Random Forest | 3 | 10114 | 3017 | 96.1248 | 91.9974 | 88.9957 | 78.7931 | 91.4000 | 84.6296 |
| Buffered spatial CV | XGBoost | 3 | 10114 | 3017 | 96.2354 | 92.7943 | 89.5592 | 80.4444 | 90.5000 | 85.1765 |
| Buffered spatial CV | SVM (RBF) | 4 | 10034 | 3034 | 93.1394 | 86.1732 | 87.2116 | 76.1383 | 89.5833 | 82.3154 |
| Buffered spatial CV | Random Forest | 4 | 10034 | 3034 | 94.0767 | 89.1588 | 86.3217 | 74.5244 | 89.3849 | 81.2810 |
| Buffered spatial CV | XGBoost | 4 | 10034 | 3034 | 94.7228 | 90.8776 | 87.9038 | 77.9425 | 88.6905 | 82.9698 |
| Buffered spatial CV | SVM (RBF) | 5 | 10179 | 3047 | 92.8838 | 85.2751 | 85.3627 | 73.8912 | 86.8240 | 79.8373 |
| Buffered spatial CV | Random Forest | 5 | 10179 | 3047 | 95.3310 | 90.5715 | 87.0364 | 74.6434 | 92.6254 | 82.6678 |
| Buffered spatial CV | XGBoost | 5 | 10179 | 3047 | 95.4380 | 91.1500 | 88.0210 | 77.3032 | 90.7571 | 83.4916 |
| Random-group control | SVM (RBF) | 1 | 12137 | 3032 | 94.4924 | 89.1678 | 86.4116 | 73.5804 | 92.3762 | 81.9140 |
| Random-group control | Random Forest | 1 | 12137 | 3032 | 96.2350 | 91.9548 | 90.0396 | 81.2169 | 91.1881 | 85.9142 |
| Random-group control | XGBoost | 1 | 12137 | 3032 | 96.1197 | 92.2599 | 89.6108 | 81.2781 | 89.4059 | 85.1485 |
| Random-group control | SVM (RBF) | 2 | 12135 | 3034 | 94.2044 | 88.6255 | 86.9150 | 76.4950 | 88.9855 | 82.2689 |
| Random-group control | Random Forest | 2 | 12135 | 3034 | 96.4403 | 92.5954 | 88.5300 | 77.8138 | 92.8502 | 84.6696 |
| Random-group control | XGBoost | 2 | 12135 | 3034 | 96.3210 | 93.2306 | 89.1233 | 80.5724 | 89.7585 | 84.9177 |
| Random-group control | SVM (RBF) | 3 | 12138 | 3031 | 93.9536 | 87.7883 | 86.6051 | 73.7274 | 91.2602 | 81.5622 |
| Random-group control | Random Forest | 3 | 12138 | 3031 | 96.0281 | 91.6988 | 90.2013 | 82.2535 | 89.0244 | 85.5051 |
| Random-group control | XGBoost | 3 | 12138 | 3031 | 96.1824 | 92.6866 | 89.8713 | 82.0853 | 88.0081 | 84.9436 |
| Random-group control | SVM (RBF) | 4 | 12134 | 3035 | 93.9093 | 87.7474 | 86.7875 | 75.1873 | 89.7614 | 81.8305 |
| Random-group control | Random Forest | 4 | 12134 | 3035 | 96.0966 | 92.3323 | 89.3245 | 79.8599 | 90.6561 | 84.9162 |
| Random-group control | XGBoost | 4 | 12134 | 3035 | 96.0807 | 92.6079 | 88.9951 | 79.5255 | 89.9602 | 84.4216 |
| Random-group control | SVM (RBF) | 5 | 12132 | 3037 | 94.2875 | 88.7133 | 85.7754 | 72.6060 | 91.7659 | 81.0692 |
| Random-group control | Random Forest | 5 | 12132 | 3037 | 96.1213 | 91.5482 | 88.1462 | 76.4706 | 92.8571 | 83.8710 |
| Random-group control | XGBoost | 5 | 12132 | 3037 | 96.2162 | 92.1677 | 88.4425 | 77.4436 | 91.9643 | 84.0816 |

## Research/manuscript readiness

A defensible contribution is a reproducible audit and controlled comparison of random-group versus buffered spatial evaluation for this inventory, with quantified fold variation and sampling limitations. Do not claim a novel algorithm, a universal winning model, unbiased population risk, calibrated probabilities, or publication readiness solely from these scores.

Before stronger claims: review source/data publication rights, map permissions, code licensing and dataset-history privacy; add independently approved distance/block sensitivity or new-region/temporal validation; justify dependence scales and pseudo-absence design; assess calibration if probabilities are wanted; and plan uncertainty analysis respecting shared training data. None of those additional experiments was run in this integration.

Spatially structured evaluation should match the prediction task; see [Roberts et al. (2017)](https://doi.org/10.1111/ecog.02881) and [Valavi et al. (2019)](https://doi.org/10.1111/2041-210X.13107). These motivate validation design, not the numerical results or a claim that HimShield uses the blockCV R implementation.

See [the frozen protocol](spatial_validation_protocol.md), [architecture](architecture.md), [data provenance](data_sources_log.md), [local district restrictions](local_district_views.md) and [release readiness](release_readiness.md). Public district-boundary/image redistribution remains on hold. No main merge, history rewrite or push is included.
