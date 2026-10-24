# Prospective cancer research data

## Published scale

These are source-reported collection sizes except where the BTXRD release is explicitly marked as locally verified. Counts use different units and must not be added into a single training-sample total.

| Candidate | Published amount | Published storage | Intended role and checks |
|---|---|---|---|
| [BTXRD](https://www.nature.com/articles/s41597-024-04311-y.pdf) | 3,746 bone radiographs, including 1,879 normal and 1,867 tumor images; locally verified | 840,474,929-byte original ZIP, locally verified | First bone X-ray candidate. The archive and joins were audited locally; patient grouping and per-row reference evidence remain unavailable. See [BTXRD readiness](BTXRD-readiness.md). The [original release](https://api.figshare.com/v2/articles/27865398) lists CC BY 4.0. |
| [LIDC-IDRI](https://www.cancerimagingarchive.net/collection/lidc-idri/) | 1,010 subjects and 244,527 DICOM images, with radiologist annotations | 133.15 GB listed for images | Lung imaging branch. Distinguish nodules and radiologist assessments from confirmed cancer diagnoses. |
| [LUNA16](https://luna16.grand-challenge.org/Procedure/) | 888 CT scans selected from LIDC-IDRI | Not independently verified here | Nodule-detection benchmark. It overlaps LIDC-IDRI and cannot serve as independent external validation against it. |
| [BraTS-PEDs](https://www.cancerimagingarchive.net/collection/brats-peds/) | 457 subjects in the listed pediatric brain-tumor collection | 32.7 GB | Possible pediatric MRI branch. Confirm release-specific input channels, labels, partitions, access, and intended population. The full collection count is not a count of labeled training cases available for every task. |
| [PANDA](https://www.nature.com/articles/s41591-021-01620-2) | 10,616 digitized prostate biopsies from 2,113 patients in the development set | Not verified here | Pathology branch. The publication describes noncommercial research availability under CC BY-NC-SA 4.0. Keep biopsies from the same patient together. |
| [TCGA](https://www.cancer.gov/ccg/research/genome-sequencing/tcga) | More than 20,000 primary tumor and matched normal samples across 33 cancer types | More than 2.5 PB generated across molecular data types | Future genomics/multimodal research. Select the required processed data and matched cohorts rather than treating the archive as one model-ready dataset. |

GDC has both open and controlled data. Controlled access requires the appropriate authorization; open availability of one data type does not establish access to every linked file. See [GDC access processes](https://gdc.cancer.gov/access-data/data-access-processes-and-tools).

## Three separate data collections for the platform

1. **Specialist research data:** images, molecular measurements, annotations, and task-specific reference labels.
2. **Retrievable research knowledge:** papers, model documentation, dataset records, and benchmark evidence with citations and reuse terms.
3. **Coordinator training examples:** reviewed examples of model selection, dataset auditing, training assistance, and interpretation of actual observed tool results.

Keep their purposes and evidence separate. A paper or teacher prediction is not an independently confirmed patient label. Specialist datasets do not need to be merged into one multimodal pool to support a useful coordinator.

## Acquisition order and storage allowance

The original BTXRD release has been acquired locally for an offline audit. Catalog broader sources before storing them, and acquire model weights only for a defined, permitted experiment.

The initial planning allowance is roughly **200 GB** for the first prototype, including model weights, processing, caches, logs, and checkpoints. A later **1–2 TB** allowance could support selected imaging cohorts and additional models. These are provisional budgets, not measured requirements, verified NPS allocations, or capacity for the full TCGA archive. Revise them after choosing artifacts and measuring a small run.

Useful data volume depends on independent patients, trustworthy labels, cohort coverage, permissions, and compatibility with the selected task. Multiple images or extracted tiles from one patient do not create additional independent patients.

## Acquisition status

The original BTXRD archive has been downloaded, checksum-verified, and inspected locally. No other medical dataset or pretrained model weights have been downloaded in this workspace. No NPS upload, workload, or training run has been started. The [BTXRD readiness record](BTXRD-readiness.md) describes the audit and blockers.
