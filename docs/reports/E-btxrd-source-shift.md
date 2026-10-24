# BTXRD source-shift check and near-duplicate search

**Exploratory, image-level software result. Not medical performance.** Run October 24, 2026 on the local laptop. It follows up the drop found in [E-btxrd-exploratory-baseline.md](E-btxrd-exploratory-baseline.md).

**Centers 2 and 3 are not an untouched test set.** The first baseline run already reported results on them, and the drop it showed there is why these variants were tried. Choosing each variant on center-1 validation data keeps the test centers out of the choice itself, but not out of the idea. So a better score on centers 2 and 3 is a hint, not evidence that a variant handles new sources better. Checking that needs images from a source nobody has looked at, which the T03 protocol already asks for.

## Summary

Neither change closes the gap between center 1 and centers 2 + 3. On center-1 validation data, the per-image contrast stretch never beat the current padding, and the native center crop helped ResNet-50 but not RAD-DINO. With the native crop, ResNet-50's test ROC-AUC rose from 0.623 to 0.690 for benign vs malignant and from 0.609 to 0.637 for the three-class endpoint. It stayed at 0.62 for tumor vs normal. The confidence intervals overlap, and they resample images, so they are too narrow. Test performance stays far below center-1 validation (0.84 to 0.94).

The near-duplicate search found one more same-image pair beyond the 21 byte-identical ones, plus pairs that look like separate images of the same patient. Several of those sit on both sides of the image-stratified split.

## Variants

All other settings match the baseline: frozen encoders, logistic-regression head, C chosen on val, Youden threshold on val for binary endpoints, split seed 0.

| Variant | Preprocessing |
|---|---|
| `pad` (baseline) | Grayscale, pad to square with black, bicubic resize (RAD-DINO 518, ResNet-50 288) |
| `pad_pstretch` | Grayscale, per-image 1st–99th percentile contrast stretch, then as `pad` |
| `native_crop` | Grayscale, bicubic resize of the shortest edge, center crop to square: RAD-DINO's processor and timm's ResNet-50 test config. It can cut off part of a long radiograph |

Split: `source_holdout`, center 1 split 85 / 15 into train / val (2,495 / 439 images; 1,142 / 201 for benign vs malignant), centers 2 + 3 as test (808; 522).

## Selection on center-1 validation data

Macro ROC-AUC on center-1 val at each head's chosen C. Test data was not used in this step. Ties go to `pad`.

| Endpoint | Encoder | pad | pad_pstretch | native_crop | Selected |
|---|---|---|---|---|---|
| three_class | RAD-DINO | 0.875 | 0.872 | 0.862 | pad |
| three_class | ResNet-50 | 0.859 | 0.840 | 0.881 | native_crop |
| tumor_vs_normal | RAD-DINO | 0.877 | 0.875 | 0.866 | pad |
| tumor_vs_normal | ResNet-50 | 0.843 | 0.831 | 0.856 | native_crop |
| benign_vs_malignant | RAD-DINO | 0.915 | 0.909 | 0.885 | pad |
| benign_vs_malignant | ResNet-50 | 0.920 | 0.883 | 0.943 | native_crop |

## Test (centers 2 + 3), baseline and selected variant only

| Endpoint | Encoder | Variant | Test n | ROC-AUC (95% CI) | At val threshold (binary) or argmax |
|---|---|---|---|---|---|
| three_class | RAD-DINO | pad (selected) | 808 | 0.602 (0.567–0.635) macro | balanced acc 0.43; recall normal 0.36, benign 0.57, malignant 0.35 |
| three_class | ResNet-50 | pad | 808 | 0.609 (0.580–0.642) macro | balanced acc 0.45; recall normal 0.40, benign 0.48, malignant 0.46 |
| three_class | ResNet-50 | native_crop (selected) | 808 | 0.637 (0.605–0.669) macro | balanced acc 0.46; recall normal 0.40, benign 0.59, malignant 0.41 |
| tumor_vs_normal | RAD-DINO | pad (selected) | 808 | 0.616 (0.576–0.656) | sensitivity 0.76, specificity 0.40 |
| tumor_vs_normal | ResNet-50 | pad | 808 | 0.621 (0.579–0.662) | sensitivity 0.80, specificity 0.38 |
| tumor_vs_normal | ResNet-50 | native_crop (selected) | 808 | 0.623 (0.583–0.662) | sensitivity 0.80, specificity 0.34 |
| benign_vs_malignant | RAD-DINO | pad (selected) | 522 | 0.598 (0.535–0.663) | sensitivity 0.64, specificity 0.53 |
| benign_vs_malignant | ResNet-50 | pad | 522 | 0.623 (0.563–0.681) | sensitivity 0.67, specificity 0.51 |
| benign_vs_malignant | ResNet-50 | native_crop (selected) | 522 | 0.690 (0.634–0.744) | sensitivity 0.60, specificity 0.67 |

Positive class: tumor for `tumor_vs_normal`, malignant for `benign_vs_malignant`. The `pad` rows reproduce the first baseline run's test numbers exactly, so the new pre-fit checks and the refactor did not change results for valid inputs.

## What this does and does not show

- **Contrast stretch.** It did not help either encoder on center-1 val, so it was never tested on centers 2 + 3. Differences in overall brightness and contrast do not look like the main cause of the drop.
- **Native crop.** It helped ResNet-50 on center-1 val for every endpoint and was the only variant to reach test. The test gains for benign vs malignant and three-class have overlapping intervals with the baseline, and the test centers were already seen, so this is a reason to keep the crop in mind, not a finding. Cropping can remove a lesion at the edge of a long image; that was not checked image by image.
- **Gap.** Every test ROC-AUC (0.60 to 0.69) stays far below center-1 val (0.84 to 0.94). Most of the drop remains unexplained. It could come from acquisition, cropping, annotation marks or case mix in the teaching-file sources, or from same-patient images inflating center-1 val (see below). These cannot be separated without patient identifiers.
- **Not shown.** Patient-level performance, results on a new source, calibration on a new population, or any clinical usefulness.

## Near-duplicate candidates

`python -m cancer_workbench near-duplicates` scores every pair of the 3,746 images by the lower of its two cosine similarities: RAD-DINO and ResNet-50 features, each centered on the dataset mean. Both encoders have to agree. It writes the top 300 pairs to `runs/btxrd-near-duplicates-<stamp>/candidates.csv` for review and changes no split or duplicate group.

- **Calibration.** All 21 byte-identical pairs score 1.0. Only one other pair scores above 0.95, and two more score above 0.90. Below that, scores fall off gradually.
- **Top new pairs, inspected by eye:**
  - Rank 22 (IMG002677 / IMG002686, score 0.992): the same shoulder radiograph, one copy with an added text label. They are on opposite sides of the image-stratified split.
  - Rank 23 (IMG000155 / IMG000157, 0.917): the same hip radiograph re-saved with a slightly different crop.
  - Ranks 24 and 25 (IMG002882 / IMG002884, IMG001939 / IMG001940): separate exposures of the same hand and the same shoulder, with matching age and sex. These look like the same patient, not the same image.
- **Top 279 new pairs overall:** 131 sit on both sides of the image-stratified split. 61 sit on both sides of the source hold-out split: 52 between train and val inside center 1, and 9 between a center-1 image and a center-2 (Radiopaedia) test image. 59 have different labels. 63 have IDs within 5 of each other and 69 share age and sex.
- **The 9 center-1 / center-2 pairs.** If any were the same image, the source hold-out's test set would overlap its training data. All score about 0.78, and one Radiopaedia image (IMG003536) appears in four of them. The two highest, checked by eye, are different images: a left and a right hand, and two different pelvises. No cross-center copy was found among the top 300 pairs, but pairs below 0.78 were not reviewed.

Many candidates are probably separate images of one patient. That supports what the baseline report suspected: same-patient images inflate the image-stratified numbers and center-1 val. Hub decision D04 rules out building patient groups from similarity or adjacent IDs, so the list stays for review. The confirmed same-image pairs (ranks 22 and 23) could join a `duplicate_group` after a person checks them, and the list belongs in the inquiry to the maintainers (Hub Q01).

## Reproducibility

| Item | Value |
|---|---|
| Commands | `.venv/bin/python -m cancer_workbench source-shift`; `.venv/bin/python -m cancer_workbench near-duplicates` |
| Runs | `runs/btxrd-source-shift-20261024T071226Z/`, `runs/btxrd-near-duplicates-20261024T071231Z/` (local, gitignored) |
| Code | run from `7a45668` plus the uncommitted changes recorded as `-dirty`; committed together with this report |
| Feature extraction | Apple MPS. RAD-DINO 25 min each for `pad_pstretch` and `native_crop`; ResNet-50 1.5 min each. Six feature files, 123 MB in total |
| Environment | Python 3.12.13, torch 2.14.1, numpy 2.5.3, scikit-learn 1.9.1 |
| CIs | 95 %, 1,000 bootstrap resamples by image |

## Next steps

- Review the top near-duplicate candidates and add confirmed same-image pairs to `duplicate_group`.
- Include the candidate list and the conflicting-label pairs in the maintainer inquiry (Q01).
- A fair test of the native crop needs a source that none of this work has looked at.
