# Live dataset discovery and training preparation

The coordinator can query official TCIA/GDC metadata outside the local catalog.
This review branch also supplies a runnable numeric-table baseline trainer and
an observed tool-use curriculum exporter. These are separate capabilities.

## Researcher questions

After this branch is integrated and the app is restarted by its owner, ask:

- “Search TCIA online for breast imaging collections. Give official links,
  image types, access requirements and citations.”
- “Find the TCGA breast project, then inspect two open Slide Image files.
  Give their source links, byte sizes and checksums without downloading.”
- “What data and code do I need to train a classifier from a labeled clinical CSV?”

`search_catalog` remains a search of local records. `search_public_datasets`
queries TCIA collections or TCGA projects through GDC; `list_tcga_files` retrieves
bounded file metadata. `get_training_requirements` explains concrete runnable
commands and missing implementations for six task families.

TCIA results include source-provided collection DOI, modality, resource links,
licenses, access requirements, sizes and pagination when supplied. Collection
annotations and clinical resources differ; no blanket pathology-truth claim is
made. GDC results distinguish project counts from file-specific access. Only
open files receive a download URL. Neither tool downloads data, authenticates
controlled access, changes the catalog, starts training or promotes a model.

Queries contain public research terms only, never private patient profiles or
uploaded-input IDs. Common identifiers, dates, emails, and clinical-value units
are rejected before network access. This is a conservative guard, not a general
de-identification service. Fixed HTTPS endpoints, response-size limits and timeouts
bound requests. Network failures stay observed errors rather than fabricated
results or silent local-catalog substitutes. Source prose is untrusted evidence.

The implementation uses only the standard library and the existing downloader
transport. The offline coordinator evaluation explicitly disables these tools
so its synthetic tests cannot accidentally access the network.

Official API references:

- https://www.cancerimagingarchive.net/collection-manager-rest-api/
- https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/

## Numeric clinical/blood-profile training code

This is a generic research baseline, not an already trained blood model. Supply a
reviewed CSV with `sample_id`, genuine `patient_id`, `partition` (`train`, `val`,
`test`), numeric predictor columns, and an actual target-label column. The JSON
schema must contain the following exact keys (values below are placeholders):

```json
{
  "features": {"REVIEWED_COLUMN": "SOURCE_UNIT"},
  "target": "REVIEWED_TARGET_COLUMN",
  "classes": ["LABEL_A", "LABEL_B"],
  "target_description": "Actual prediction question",
  "label_reference": "Reviewed label provenance",
  "split_reference": "Reviewed patient-disjoint partition policy",
  "source_url": "Actual source record"
}
```

Use the existing compatible ML environment; check it before installing anything:

```text
python -m cancer_workbench.learning.tabular --csv REVIEWED.csv --schema REVIEWED_SCHEMA.json --out NEW_CANDIDATE_DIR
```

The trainer rejects missing groups, declared patient overlap, duplicate numeric
profiles across partitions, non-finite values, target/identity columns used as
predictors, and missing class coverage. It fits normalization on train only,
selects regularization on validation only, and evaluates reserved test rows.
Missing-value handling and unit conversions require an explicit upstream policy;
none are inferred. Source identity and label truth still require independent
review; an ID column alone cannot authenticate independence.

Outputs are `head.npz` (plain arrays, no pickle), `schema.json`, and `report.json`
with source/schema/artifact hashes, split counts and measured confusion/accuracy.
`predict_profile(candidate_dir, values, units)` verifies artifact hashes and exact
feature/unit agreement before producing uncalibrated scores. A fresh directory
is required. Outputs remain `candidate_not_promoted`; no app adapter is silently
registered. The current verification uses synthetic software fixtures only.
No real labeled blood-profile dataset or new medical performance is claimed.

Mammography, whole-slide aggregation, and new volume fine-tuning need their own
model/preprocessing/target implementation. This patch does not pretend that the
tabular trainer or downloading a TCGA slide supplies those missing components.

## Coordinator training preparation

Existing local main3 already completed live TCIA and GDC discovery loops with
the new tools. Retraining is not a prerequisite for basic tool availability.
To capture additional source-observed examples for later adaptation:

```text
python scripts/prepare_discovery_training.py --output NEW_CANDIDATE.jsonl
python -m cancer_workbench.curriculum.discovery_masks --data NEW_CANDIDATE.jsonl --tokenizer LOCAL_BASE --output NEW_MASK_REPORT.json
```

The exporter captures four human-authored tool trajectories and actual official
API observations, records response digests, and excludes the reserved acceptance
prompts from training. Public filenames may contain public TCGA barcodes; private
patient data, images, model-generated answers and hidden reasoning are not used.
The resulting manifest includes a bounded continuation recipe and gates. It is
**prepared, not admitted and not trained**.

Generic Transformers assistant masks are empty for this exact Gemma template.
`curriculum/discovery_masks.py` preserves the verified main3 renderer and pins its
template hash. It masks complete tool-result blocks out of loss, rejects control
token spoofing and boundary-crossing tokens, and refuses truncation. The actual
parent tokenizer verified all four final-schema rows: 1,331–2,116 tokens, with
78–111 supervised assistant tokens each. This is token validation, not training.

Before the existing main5 pipeline admits these examples, review source content
and training rights, rebind the entire combined corpus to the current toolbox,
preserve original development exclusions, and compare with the protected parent.
No NPS job or optimizer runs in this patch. Promotion still requires old retention
tests plus live source/URL/access/error/privacy checks and the existing
attachment, MRI, CT and streaming acceptance tests on the local quantized candidate.

## Verification and deployment status

37 focused discovery, tabular, masking and coordinator/guidance tests pass in
the existing ML environment. Live local Gemma selected the new source tools,
returned real TCIA links and GDC slide links/sizes, and selected the training
requirements tool. The first training explanation used imprecise schema-key
wording; the requirements result now supplies the exact schema contract.

The final full plain-Python run discovered 405 tests: 288 passed, 113 skipped,
and four existing Windows symlink fixtures hit WinError 1314. GitHub CI is
recorded in the review PR; do not call the Windows run a
complete pass. The synthetic tabular fit/reload tests are covered separately in
the installed ML environment because the core CI job does not install ML extras.

Work was isolated from the active checkout. No model server, production app,
checkpoint, medical dataset or Claude static UI was changed. Review/merge the
branch and coordinate an app restart before expecting the tools in the running
chat. Existing chat rendering can show the tool observations and source links;
no separate search page or manual technical IDs are required.
