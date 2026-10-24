# BTXRD: source review and local intake status

## Source evidence

The [dataset paper](https://www.nature.com/articles/s41597-024-04311-y) reports 3,746 radiographs: 1,879 normal, 1,525 benign, and 342 malignant. Source category 1 combines three hospitals; categories 2 and 3 are Radiopaedia and MedPix. Some images show different views of the same lesion. The published metadata schema includes image identifiers and diagnostic flags, with no patient identifier listed. This does not prove that an unpublished grouping map is unavailable.

The [original Figshare API record](https://api.figshare.com/v2/articles/27865398) identifies release `10.6084/m9.figshare.27865398.v1`, lists CC BY 4.0, and reports `BTXRD.zip` at 840,474,929 bytes. Its supplied MD5 is `59132a5036d030580ccade8add8f13df`. The license shown for this release is source evidence, not a blanket clearance of every downstream use.

## Independent local release audit

The original archive was downloaded into the private research workspace. Its 840,474,929-byte size and computed MD5 match the Figshare record; its computed SHA-256 is `e7c800c3b4e090262b160525a0765f9d93bcc53d639c03806a3ac47b0ded3373`. Every ZIP member passed its CRC check. This verifies transfer integrity against the published checksum, not label quality or clinical validity. The medical images stay out of the shared documents and repository.

The actual archive has `dataset.xlsx`, 3,746 JPEG radiographs, and 1,867 JSON annotation files. The paper describes a `dataset.csv`; that is a documentation/release mismatch. All 3,746 spreadsheet image IDs join to one image, and the 1,867 tumor rows join to annotation files. The class counts reproduce the paper: 1,879 normal, 1,525 benign, and 342 malignant. Center counts are 2,938 hospital-source images, 549 Radiopaedia-source images, and 259 MedPix-source images. The spreadsheet has no patient, case, lesion, or per-row diagnostic-reference field. Its other metadata fields do not repair that omission.

The reusable audit also confirms one subtype-label-set difference: `IMG001276.jpeg` has both `osteochondroma` and `synovial osteochondroma` active in the spreadsheet, while its annotation shapes name only `synovial osteochondroma`. This is a discrepancy for review, not an automatic correction or a benign/malignant class conflict.

An EXIF tag-name scan of all 3,746 source JPEGs found nonempty `GPSInfo` tags in two files, `Artist` and `XPAuthor` tags in four files each, and `DateTime` tags in 60 files. Their values were not copied into project documents or assessed for identifying content. The original archive stays private; review and strip unnecessary embedded metadata from any future permitted derivative or export. This is a release-privacy review finding, not a claim that those fields identify patients.

Byte hashing found 21 exact duplicate image pairs. Two pairs have contradictory normal/benign labels: `IMG000591.jpeg` with `IMG003456.jpeg`, and `IMG000707.jpeg` with `IMG003346.jpeg`. These four images must be excluded or adjudicated before any labeled experiment. There were no exact duplicate pairs crossing the hospital versus external-source boundary. These are file-level findings, not proof that different images represent different patients.

The dataset authors' public [classification training list](https://github.com/SHUNHANYAO/BTXRD/blob/master/classification%20task/Distribution/train.xlsx) and [validation list](https://github.com/SHUNHANYAO/BTXRD/blob/master/classification%20task/Distribution/val.xlsx) contain 2,995 and 751 image IDs. Matching by ID stem covers the release exactly, but seven of the 21 exact duplicate pairs cross those lists, including one contradictory-label pair. The lists also use `.jpeg` for 27 release files actually ending in `.jpg`. These are independently checked **list/release inconsistencies**; the repository does not establish that these exact lists produced every published paper result. They are unsuitable as a leakage-free benchmark without correction.

The [paper's methods and limitations](https://www.nature.com/articles/s41597-024-04311-y) say hospital diagnoses were confirmed either histologically **or** by two radiologists; the other sources were selected by expert keyword search. Some images show different views of one lesion. The paper acknowledges that pathology was unavailable for some images and misdiagnosis is possible. The released spreadsheet does not identify which rows have a pathology reference. The publication's random 8:2 image split is therefore not evidence of patient-independent validation.

Two newer papers are **leads, not substitutes for the missing map**. A [2026 multicenter transfer-learning study](https://link.springer.com/article/10.1186/s13244-026-02271-y) reports 471 private development patients and calls 1,867 BTXRD tumor records external patients; it does not publish an image-to-patient map and describes different reference-standard inclusion than the original open release. A [2026 preprint](https://arxiv.org/html/2609.28732v1) claims a patient-level BTXRD split but describes only a stratified random 80/10/10 split, with no published patient-identifier field or mapping procedure. Neither claim resolves the local release's patient-grouping gap. Their performance numbers must not be treated as comparable validation for our proposed three-class task.

Before a patient-independent study, ask the original data custodians for a de-identified image-to-patient and image-to-lesion/case map, a per-image reference-standard category (pathology, consensus imaging, or other), the annotation/adjudication protocol, and clarification of the two contradictory exact pairs. Ask the newer study authors how their patient counts and split were derived. These are research questions; no outreach has been sent from this audit.

The separate local OncoCopilot intake was run against this release as an **exploratory software check**, with no model training. Its first dHash grouping rule chained 814 images together and contaminated the nominal external split. The rule was corrected: only exact-byte families control partitions; dHash similarities are exported as unverified candidates. After excluding the four contradictory images, the corrected draft has 2,494 training images, 440 validation images, and 808 external-source images. Every center-2/3 image stays in the external pool, and no exact-byte family crosses partitions. The 10,372 dHash candidate pairs include 3,483 development-versus-external matches, many likely false positives; this coarse hash cannot establish patient or lesion identity. The draft remains `exploratory_only` and `ready_for_training: false`.

## Decision

Proceed with source review and offline intake development. Patient-independent training/evaluation remains blocked pending trustworthy grouping evidence, adjudication of conflicting labels and reference standards, review of visual-overlap candidates, permission review, and an agreed study protocol. Do not substitute an image filename, source category, or guessed identifier for a patient group.

The candidate first endpoint is normal/benign/malignant classification. It remains a proposal for team review. Model comparison and thresholds must be specified before test results are examined. Tumor presence, malignancy, localization, and segmentation are different endpoints.

## Working local component

The foundation now exposes `prepare_btxrd_cohort` and the `btxrd-prepare` command. It reads already-local CSV metadata with `image_id`, `center`, `tumor`, `benign`, and `malignant`. A separate case map supplies pseudonymous `patient_id`, `grouping_reference`, `sha256`, and an optional relative `file_path`.

The code rejects conflicting flags and ambiguous joins. Missing grouping/evidence/digests produce a blocked report with no partition manifest. When declarations are complete, it keeps patient and exact-digest relations together transitively, then proposes deterministic class-balanced partitions. It reports missing classes and group-size limits rather than silently splitting related images.

This is a heuristic split draft, not an optimal allocation or a verified cohort. The split-draft function does not inspect image pixels, detect near-duplicates, verify grouping assertions, adjudicate labels, measure file integrity, or clear permissions. The separate release-audit command below verifies file-level findings but does not supply missing patient identities. Synthetic tests establish software behavior only.

Run from the foundation directory, after supplying authorized local files:

```sh
python3 -m cancer_workbench btxrd-prepare metadata.csv --case-map case-map.csv
```

The current foundation suite passes 72 tests with optional Pillow installed, including 15 cohort tests and 16 release-audit tests. Without Pillow, one EXIF test skips. The synthetic grouping example contains 36 artificial metadata rows representing 18 declared groups; it proposes 24/6/6 images across training/validation/test. The release audit above read already-acquired real medical files offline; it did not train or evaluate a model or run a remote workload.

### Reproduce the release audit

The portable foundation now provides `btxrd-audit`, so the findings no longer depend on a separate local code folder. It reads a local ZIP without extracting it, accepts the reference checksum, and optionally compares CSV/XLSX split lists. With optional Pillow it counts EXIF tags without exporting their values. The [machine-readable report](BTXRD-audit.json) reproduces the original release findings and stays `ready_for_training: false`.

```sh
python3 -B -m cancer_workbench btxrd-audit BTXRD.zip --expected-md5 59132a5036d030580ccade8add8f13df --train-list train.xlsx --validation-list val.xlsx
```

Run from the foundation directory with the already-local archive and authors' split-list files supplied at the placeholder paths. Add `--inspect-exif` if Pillow is installed. The command does not infer patient groups, validate annotation geometry or diagnosis, review pixel privacy, clear permissions, split a cohort, or train a model.

### Complete the evidence handoff

The [custodian handoff](BTXRD-evidence-handoff.md) now includes a [3,746-row evidence template](BTXRD-evidence-template.csv), measured image hashes, advisory discrepancy flags and concrete unsent questions. All patient, lesion and diagnostic-reference fields are blank. The actual template was passed through the cohort helper: it remains blocked on all patient/grouping references and exports zero split rows. The helper also rejects recognized placeholders and image stems used as patient IDs. Neither this stricter input check nor a completed template can authenticate a mapping or establish medical validity.

The new [evidence-return check](BTXRD-evidence-check.json) independently matches all 3,746 template rows to the freshly read archive, detects edits to source fields/hashes and row coverage, and counts evidence/review gaps without exporting supplied identity or reference values. The actual source binding passes; the study remains blocked on all patient/lesion/reference evidence, unreviewed status and the four contradictory source copies. This checker does not approve a cohort, implement adjudication/exclusion, or run automatically inside the existing split helper.

An isolated [integration patch](BTXRD-shared-integration.md) now exposes the same utilities in the shared source snapshot through `btxrd-review`. Its actual release/evidence report matches the foundation result exactly; it remains an unmerged proposal with optional ML tests skipped. Integration does not change any scientific blocker or promote a model.

## First comparison protocol for team review

The [baseline input/provenance review](BTXRD-baseline-input-review.md) adds an execution prerequisite: bind cached features to measured source-image hashes and use provenance from the actual model-loading directory. Both defects were reproduced with synthetic fixtures in the inspected shared snapshot; no fix is applied here, and no effect on reported medical scores is established. Publisher size/normalization values agree, while padding/cropping and grayscale conversion remain explicit custom policies requiring protocol review. Patient/lesion grouping and per-row reference standards remain separate blockers.

**Status:** Proposed research protocol. The team has not agreed on the endpoint, baseline pair, or evaluation unit. This section is a specification for review, not authorization to acquire files, train, or submit a job.

A [local provenance repair candidate](BTXRD-model-provenance-fix.md) now addresses the custom-folder lookup with synthetic regression checks; it is unmerged and does not fix cache binding or authenticate weights. Scientific grouping/reference-standard requirements remain unchanged.

The separate [image-binding repair candidate](BTXRD-feature-cache-fix.md) now covers the cache issue in all four cache-consuming entry points. Its combined local suite passes 149 tests with 11 optional ML skips, using synthetic files and mocked embeddings. It remains unmerged, does not authenticate weights or resolve transient file races, and supplies no patient-grouping or diagnostic-reference evidence.

| Decision | Proposed rule and required evidence |
|---|---|
| Prediction task | Three mutually exclusive classes: normal, benign tumor, malignant tumor, using the original `tumor`, `benign`, and `malignant` fields after checking their meanings against the release and reference labels. Do not relabel an uncertain diagnosis as normal or merge localization/segmentation results into this task. |
| Eligible unit | One reviewed lesion or clinical case with one reference class, potentially represented by multiple radiographs. Record its patient, lesion/case, image, source, label, and reference evidence separately. If one patient has multiple differently labeled lesions, agree on a lesion-level protocol with patient-clustered uncertainty before inclusion; do not invent one patient label. |
| Grouping gate | Obtain and review a trustworthy mapping from every eligible image to a patient and lesion/case. Confirm it against the actual release and source records, inspect exact and near duplicates, and keep all images and lesions of one patient in one partition. If this cannot be established, the patient-independent comparison stays blocked. A filename, `center`, age, or a hash of an unverified assertion does not establish patient identity. |
| Label and source gate | Inspect the release spreadsheet and annotation/image joins; document exclusions, missingness, acquisition source, diagnostic reference standard, and any uncertain or conflicting labels. Report independent patient and lesion counts by class and source before judging feasibility. Check rights and likely pretraining overlap for each chosen model. |
| Split | After the gates pass, propose a fixed patient-grouped development/validation/test partition, starting from 70/15/15. Review class and source counts in every part before locking the test set. Never move or relabel cases after inspecting test outcomes. The local greedy split draft is a candidate allocation, not a scientifically approved split. |
| Comparable baselines | Compare two frozen image encoders with the same eligible cases, class order, linear-head objective, validation-only tuning policy, and evaluation code. Candidate A is [MedSigLIP](https://developers.google.com/health-ai-developer-foundations/medsiglip/model-card) plus a classifier, subject to its terms and access. Candidate B is an explicitly pinned conventional [ResNet-18 or ResNet-50](https://docs.pytorch.org/vision/stable/models/resnet.html) checkpoint plus the same kind of classifier. Sebastian's separate build reports ResNet-50 locally; that report does not establish which pair the team has approved. Record each encoder's own required preprocessing rather than forcing identical pixel resizing. |
| Primary measure | Macro-average class recall at the reviewed case/lesion level, so the smaller malignant class is not hidden by overall accuracy. Report class support and a confusion matrix beside it. If multiple views represent one case, average its class probabilities before assigning a case prediction; record this aggregation rule before evaluation. |
| Supporting measures | Malignant-class recall and precision, one-versus-rest precision-recall curves/area where defined, macro F1, and calibration. Show uncertainty intervals obtained by resampling independent patients, plus results by source and relevant anatomy when counts support them. State when small groups make an interval or subgroup claim unreliable. |
| Error review | Inspect malignant false negatives, benign/malignant confusions, source-specific failures, duplicate suspicions, annotation mismatches, and cases where the model depends on non-lesion image cues. Keep reviewed examples and exclusion reasons linked to their records. |
| Model selection | Use training data for fitting and validation data for hyperparameters or any probability calibration. Freeze the metric code, class mapping, case aggregation, and thresholds before a single locked-test evaluation. Report all planned baselines and seeds, including failures. Do not select a model from test results. |

The [original BTXRD article](https://www.nature.com/articles/s41597-024-04311-y) supplies the source-reported image counts and metadata fields. The [MedSigLIP card](https://developers.google.com/health-ai-developer-foundations/medsiglip/model-card) describes embeddings for downstream classifiers and explicitly requires task-specific validation; it does not report BTXRD performance. The [TorchVision ResNet documentation](https://docs.pytorch.org/vision/stable/models/resnet.html) lists the conventional architectures but does not make them bone-tumor specialists. The comparison is a research proposal until the team agrees on the task and the grouping/label evidence passes review.

## Team handoff

Inam's proposed dataset task can investigate whether a reliable grouping map can be obtained. Moshe's proposed review can define which claims remain defensible if it cannot. Sebastian can research eligible baseline artifacts while Jordi maintains the local interface. Live task claims and decisions belong in the [team hub](Team-hub.md).
