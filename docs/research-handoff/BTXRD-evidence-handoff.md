# BTXRD evidence handoff

The [evidence template](BTXRD-evidence-template.csv) is a local review file for the team and data custodians. It contains 3,746 source image IDs, normalized original diagnostic flags, source-center codes, and measured SHA-256 image hashes. It contains no images, demographics, EXIF values, patient identities, or invented groups. Every patient/lesion/reference field is blank and every row is `unreviewed`.

The input is the [original BTXRD release](https://doi.org/10.6084/m9.figshare.27865398.v1), whose archive MD5 matches the [published checksum](https://api.figshare.com/v2/articles/27865398). The [release audit](BTXRD-audit.json) preserves the file-level findings and source references. The template's SHA-256 is `97891aa3d6c9cf051bd5876cc79d80c3520320368a64cec0903971e4c94c272f`.

## Fields to complete with real evidence

| Field | Meaning and required handling |
|---|---|
| `image_id`, `center`, `tumor`, `benign`, `malignant` | Source identifiers and diagnostic flags. Preserve them as the original record; record adjudication separately. The 27 `.jpg` image extensions are retained. |
| `sha256` | Measured identity of the image bytes in the audited archive. Equal bytes establish an exact duplicate, not a patient identity. |
| `patient_id` | A consistent de-identified identifier supplied or confirmed by the data custodian, shared by all images and lesions from one patient. Do not enter a filename, filename stem, row number, demographic combination, or similarity cluster. |
| `grouping_reference` | A reviewable de-identified source reference that establishes the mapping. A nonempty string alone is not proof; the team must inspect its basis. |
| `lesion_id` | A custodian-supported identifier for one lesion or clinical case, linked to the patient. Multiple views of the same lesion must share it. |
| `reference_standard` | The actual basis for the diagnosis, such as pathology or expert imaging consensus. Keep uncertainty explicit; do not claim pathology when only an imaging opinion is available. |
| `reference_evidence` | A secure de-identified evidence reference sufficient for authorized review. Do not paste names, hospital identifiers, or identifiable clinical text into this file. |
| `review_status`, `review_flags` | Handoff records. Status starts at `unreviewed`; flags identify review work. They are advisory and do not automatically filter rows or attest that a diagnosis is correct. |

The current split helper consumes source flags, `patient_id`, `grouping_reference`, and `sha256`. It rejects blank or recognized placeholder grouping values and patient IDs equal to the image filename or stem. It does **not** independently verify the mapping, enforce the lesion/reference fields, or interpret `review_status` and `review_flags`. A completed template still needs a reviewed cohort, permissions, diagnostic evidence, and study protocol before scientific execution.

The separate `btxrd-evidence-check` command now checks a returned template directly against the local archive. It requires the original row coverage and template columns, compares source flags/hashes/review flags, counts unresolved patient/lesion/reference fields and review status, and flags inconsistent patient assignments for exact copies or conflicting source labels within one declared lesion. It accepts equivalent numeric/boolean flag encodings, hash capitalization and review-flag ordering. It never exports supplied patient IDs or reference values, authenticates their truth, filters a cohort, or starts training. The source-copy label conflicts remain blockers even if a row is marked `reviewed`; a corrected release or an explicit reviewed adjudication/exclusion workflow is still needed.

## Review queue already marked

- **Four images in two contradictory exact pairs:** IMG000591.jpeg / IMG003456.jpeg and IMG000707.jpeg / IMG003346.jpeg. Each pair has normal versus benign source labels. Exclude or adjudicate them under the agreed protocol; do not choose a label from model predictions.
- **38 images in 19 other exact-byte pairs:** keep their exact-digest relations together in any future partitions. This does not resolve other same-patient views or re-encoded duplicates.
- **One subtype-label-set difference:** IMG001276.jpeg has both osteochondroma and synovial osteochondroma spreadsheet flags, while its annotations name only synovial osteochondroma. Review the intended meaning; this alone is not a benign/malignant class contradiction.

All 3,746 rows still lack patient/lesion mapping and per-image diagnostic-reference evidence. No row is certified eligible merely because its review-flags cell is empty. The source images' EXIF and pixel privacy review also remains open; no image export has been prepared.

## Questions ready for the data custodians

No request has been sent. A concise evidence request can ask:

1. Can you provide a de-identified mapping from every released image ID to its patient and lesion/case, with enough provenance to check that the mapping belongs to this release?
2. For each image or case, which diagnosis was established by pathology, imaging consensus, or another method, and which remain uncertain? Can those reference categories and reviewable evidence references be linked to the mapping?
3. How should the two contradictory exact-byte pairs above be labeled or excluded? What does the two-subtype record at IMG001276.jpeg mean?
4. Is there an official patient-grouped split or release correction? The public classification lists cover the image stems, but seven exact pairs cross training/validation, and 27 list extensions differ from the released files. Were those exact lists used for the publication's classification results?
5. Is there a corrected or recommended metadata-clean release, and what downstream reuse/sharing conditions apply to the hospital, Radiopaedia, and MedPix images?

These are requests for evidence and clarification, not assertions that every listed inconsistency is a clinical labeling error.

## Reproduce and check locally

From the foundation directory, with the already-local archive at the placeholder path:

```sh
python3 -B -m cancer_workbench btxrd-evidence-template BTXRD.zip --expected-md5 59132a5036d030580ccade8add8f13df > evidence-template.csv
python3 -B -m cancer_workbench btxrd-evidence-check BTXRD.zip evidence-template.csv --expected-md5 59132a5036d030580ccade8add8f13df
python3 -B -m cancer_workbench btxrd-prepare evidence-template.csv --case-map evidence-template.csv
```

The exporter audits and hashes local files without extracting or acquiring data. It omits input paths and authoring timestamps. The [actual evidence-check report](BTXRD-evidence-check.json) matches all 3,746 source rows and measured image hashes to the archive, but remains `blocked`: every patient/lesion/reference field and review status is unresolved, and four source images have conflicting exact-copy labels. Its `evidence_content_sha256` hashes the sorted logical records, so it differs from the CSV-file checksum above. Neither a `true` source-binding flag nor complete declared fields establishes medical validity.

The cohort command also currently returns `blocked`: all 3,746 patient/grouping references are missing, the measured digest fields pass format checks, and no split rows are exported. These are actual local software/data checks, not medical validation or permission to train.
