# BTXRD exploratory frozen-encoder baseline

**Exploratory, image-level software result. Not medical performance.** BTXRD has no patient identifiers, the images come from one dataset release, and no external cohort was used. Run October 23, 2026, after authorization for an exploratory local run.

## Summary

Frozen RAD-DINO and frozen ResNet-50 features with a linear head have image-level ROC-AUC estimates of 0.83 to 0.86 when train and test images come from the same sources, and 0.60 to 0.62 when trained on center 1 and tested on centers 2 and 3. The confidence intervals overlap, but this does not establish equivalence or the absence of an encoder benefit. The source protocols use different test cohorts. Their descriptive contrast is the main observation; it does not establish patient-independent performance or isolate a causal effect of source shift.

## Setup

| Item | Value |
|---|---|
| Data | BTXRD figshare 27865398 v1, `data/btxrd/manifest.csv` (3,746 images; 4 unlabeled because of duplicate conflicts, see below) |
| Encoders | `rad-dino@110cbc18`, `resnet50-a1-in1k@76726860`, frozen; preprocessing in [C-model-cards.md](C-model-cards.md) |
| Head | Logistic regression on standardized features, balanced class weights; C from {1e-4 … 1} chosen by val ROC-AUC; fit on train only |
| Binary threshold | Youden's J on val, applied unchanged to test |
| Endpoints | `three_class` (normal / benign / malignant), `tumor_vs_normal`, `benign_vs_malignant`. Q02 is still open; all three are shown so the choice can be made with them in view |
| `image_stratified` | 70 / 15 / 15 split stratified by three-class label, seed 0. Exact-duplicate pairs kept together |
| `source_holdout` | Center 1 (three hospitals) split 85 / 15 into train / val; centers 2 (Radiopaedia) and 3 (MedPix) are test (286 normal, 415 benign, 107 malignant) |
| CIs | 95 %, 1,000 bootstrap resamples **by image**: too narrow if images share patients, which they likely do |
| Code | commit `bd6d3b1`; run `runs/btxrd-baseline-20261024T054518Z/` (local, gitignored) with splits, predictions, `results.json` and one `ExperimentRecord` per row |
| Environment | Python 3.12.13, torch 2.14.1, scikit-learn 1.9.1, Apple MPS; features took 23 min (RAD-DINO) and 1.4 min (ResNet-50) |

## Results on test

| Protocol | Endpoint | Encoder | Test n | ROC-AUC (95 % CI) | At val threshold (binary) or argmax |
|---|---|---|---|---|---|
| image_stratified | three_class | RAD-DINO | 559 | 0.834 (0.801–0.863) macro | balanced acc 0.68; recall normal 0.78, benign 0.62, malignant 0.65 |
| image_stratified | three_class | ResNet-50 | 559 | 0.835 (0.805–0.864) macro | balanced acc 0.67; recall normal 0.77, benign 0.66, malignant 0.59 |
| image_stratified | tumor_vs_normal | RAD-DINO | 559 | 0.846 (0.814–0.877) | sensitivity 0.73, specificity 0.79 |
| image_stratified | tumor_vs_normal | ResNet-50 | 559 | 0.834 (0.800–0.866) | sensitivity 0.71, specificity 0.83 |
| image_stratified | benign_vs_malignant | RAD-DINO | 278 | 0.837 (0.772–0.896) | sensitivity 0.71, specificity 0.82 |
| image_stratified | benign_vs_malignant | ResNet-50 | 278 | 0.862 (0.803–0.915) | sensitivity 0.71, specificity 0.84 |
| source_holdout | three_class | RAD-DINO | 808 | 0.602 (0.567–0.635) macro | balanced acc 0.43; recall normal 0.36, benign 0.57, malignant 0.35 |
| source_holdout | three_class | ResNet-50 | 808 | 0.609 (0.580–0.642) macro | balanced acc 0.45; recall normal 0.40, benign 0.48, malignant 0.46 |
| source_holdout | tumor_vs_normal | RAD-DINO | 808 | 0.616 (0.576–0.656) | sensitivity 0.76, specificity 0.40 |
| source_holdout | tumor_vs_normal | ResNet-50 | 808 | 0.621 (0.579–0.662) | sensitivity 0.80, specificity 0.38 |
| source_holdout | benign_vs_malignant | RAD-DINO | 522 | 0.598 (0.535–0.663) | sensitivity 0.64, specificity 0.53 |
| source_holdout | benign_vs_malignant | ResNet-50 | 522 | 0.623 (0.563–0.681) | sensitivity 0.67, specificity 0.51 |

Positive class: tumor for `tumor_vs_normal`, malignant for `benign_vs_malignant`. Under `source_holdout`, validation ROC-AUC on held-out center-1 images was 0.84 to 0.92, so the fall to about 0.6 happens between center 1 and centers 2 + 3, not between train and val.

## What this does and does not show

- **Encoders.** Point estimates are similar in these exploratory comparisons. Overlapping marginal intervals do not test a paired difference or establish equivalence. The effect of pretraining is unresolved by this comparison.
- **Source shift.** Centers 2 and 3 are teaching-file collections, which may differ from hospital images in acquisition, cropping, annotation marks and case mix. Holding sources apart does not verify that patients or lesions are disjoint. Source differences and unrecorded overlap cannot be separated without additional identity/provenance evidence.
- **Thresholds.** Thresholds chosen on center-1 validation data transfer poorly: specificity falls to about 0.4 on the other sources.
- **Image-level optimism.** The `image_stratified` numbers are likely optimistic, because several views of one lesion can fall on both sides of the split.
- **Not shown.** Patient-level performance, external validity, calibration on a new population, or any clinical usefulness.

## Data findings from this run

- **21 pairs of byte-identical images.** Feature extraction showed identical embeddings; the manifest confirmed identical file hashes. Each pair now shares a `duplicate_group` and is kept within one partition.
- **2 duplicate pairs carry conflicting labels.** IMG000591 is labeled benign but is identical to IMG003456 (normal), and IMG000707 (benign) is identical to IMG003346 (normal). All four images are unlabeled in the manifest. Several other pairs disagree on age or sex. This is direct evidence of label or metadata errors in the release; a question for the maintainers (Hub Q01).
- Near-duplicates (same image re-saved or cropped) were not searched for here. The follow-up search is in [E-btxrd-source-shift.md](E-btxrd-source-shift.md).

## Next steps

- Agree the endpoint (Q02) with these numbers and their limits in view.
- Ask the maintainers about patient grouping and the conflicting duplicate labels (Q01).
- Done October 24: the changes the source shift suggested, chosen on center-1 validation data only (per-image intensity normalization, the native center crop instead of padding), and a near-duplicate search with feature similarity. See [E-btxrd-source-shift.md](E-btxrd-source-shift.md); neither change closes the gap.
- Add MedSigLIP as a second medical arm once its gated terms are accepted.
