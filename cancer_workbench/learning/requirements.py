"""Research training requirements, not installation or execution assertions."""


def get_training_requirements(task):
    common = {"task": task, "scope": "Preparation only; no download, optimizer, job or model promotion is executed.",
              "always_required": ["Specific prediction target and source-backed labels", "Reviewed rights and input/preprocessing schema", "Patient/case/slide grouping before splits", "Train-only preprocessing, validation-only selection and reserved evaluation", "Saved/reloaded artifact checks and actual app acceptance before promotion"]}
    recipes = {
        "coordinator_tools": {
            "kind": "text tool-use LoRA candidate preparation",
            "inputs": ["Observed live tool trajectories", "Current tool schemas", "Exact compatible parent tokenizer", "Corpus-bound content/rights review", "Reserved workflow acceptance cases"],
            "commands": ["python scripts/prepare_discovery_training.py --output NEW_CANDIDATE.jsonl",
                         "python -m cancer_workbench.curriculum.discovery_masks --data NEW_CANDIDATE.jsonl --tokenizer LOCAL_BASE --output NEW_MASK_REPORT.json"],
            "next": "Merge only reviewed source-disjoint examples into the existing protected main5 workflow. This does not train on scans or patient profiles; no new checkpoint is claimed."},
        "tabular_profile": {
            "kind": "numeric-profile research baseline; no trained blood model supplied",
            "inputs": ["CSV with sample_id, genuine patient_id, partition containing train/val/test, and a target column", "JSON schema uses the exact keys features (column-to-unit object), classes (ordered labels), target, target_description, label_reference, split_reference and source_url", "Finite numeric values; missingness and unit conversions must be reviewed upstream"],
            "schema_example_illustrative_only": {"features": {"REVIEWED_COLUMN": "SOURCE_UNIT"}, "classes": ["LABEL_A", "LABEL_B"], "target": "REVIEWED_TARGET_COLUMN", "target_description": "Specify the actual prediction question", "label_reference": "Reviewed label provenance", "split_reference": "Reviewed patient-disjoint partition policy", "source_url": "Actual source record"},
            "commands": ["python -m cancer_workbench.learning.tabular --csv REVIEWED.csv --schema REVIEWED_SCHEMA.json --out NEW_CANDIDATE_DIR"],
            "next": "The output remains a candidate. Validate label/source quality and external performance, then implement/review its runtime adapter. TCGA clinical or genomic data is not automatically a CBC table."},
        "bone_xray": {
            "kind": "existing exploratory frozen-encoder classifier",
            "inputs": ["Verified BTXRD release and manifest", "Pinned encoder weights", "Explicit endpoint and duplicate/grouping policy", "Full ml extra"],
            "commands": ["python -m cancer_workbench btxrd manifest", "python -m cancer_workbench baseline --encoder resnet50-a1-in1k --endpoint three_class"],
            "next": "This reproduces the existing exploratory image-level protocol; absent patient IDs prevent a patient-independent claim. Reserve a new cohort before improving on inspected tests."},
        "mammography": {
            "kind": "full-image specialist development still required", "commands": [],
            "inputs": ["CBIS-DDSM images joined to pathology/ROI CSVs by verified patient and lesion IDs", "Regroup official splits where the same participant crosses them", "Mammography-specific preprocessing, architecture and training/evaluation implementation"],
            "next": "BreastMNIST ultrasound heads cannot be reused as mammography classifiers. Downloading images alone does not supply this missing implementation."},
        "whole_slide": {
            "kind": "slide-level specialist development still required", "commands": [],
            "inputs": ["Eligible TCGA/PANDA/CAMELYON slide files and reviewed case-level target join", "Verified tile extraction/tissue QC and slide/case grouping", "Licensed pathology encoder plus trained slide aggregation/head", "Reserved slide/case evaluation"],
            "next": "PathMNIST patch classification is not whole-slide inference; raw slides do not automatically supply the prediction target."},
        "volume_specialist": {
            "kind": "publisher-model adaptation or independently evaluated reuse", "commands": [],
            "inputs": ["A specific CT detection or MRI segmentation target", "Matched masks/boxes and patient grouping", "Publisher-compatible calibration, orientation, spacing and channels", "A model-specific fine-tuning recipe, measured resources and reserved patient cohort"],
            "next": "Use current installed-model evidence for the actual runnable CT/MRI path. Restoration of pretrained weights is different from local training or independent benchmark reproduction."},
    }
    if task not in recipes:
        raise ValueError("Choose an explicit task: " + ", ".join(recipes))
    return common | recipes[task]
