# BTXRD custodian evidence request — unsent draft

Prepared by Inam Qasimi for team review. This document has not been emailed,
submitted or represented as an accepted request. Confirm the corresponding
research contact from the official paper/release before addressing it.

**Subject:** BTXRD v1: pseudonymous grouping and diagnostic-reference evidence

Dear BTXRD research team,

We are building a research workbench and reviewing the original BTXRD v1 release
(DOI: https://doi.org/10.6084/m9.figshare.27865398.v1). Our team’s structural audit
reconciles 3,746 metadata/image rows. The published metadata does not supply a
patient/lesion mapping or a per-image diagnostic-reference record. We would like
to understand which evaluation units and claims the available evidence supports.

Could you provide, or explain whether you can provide:

1. A mapping from original image IDs to stable **pseudonymous** patient, study and
   lesion groups, including links across different views and source collections?
   Please describe how the grouping was established and its completeness.
2. Per-image diagnostic-reference categories, such as pathology-supported,
   expert-image interpretation, other documented method, or unknown, with a
   non-identifying evidence reference and review status? We do not need clinical
   reports, demographics or identifiable patient details.
3. Clarification of the identical image copies with normal/benign disagreement:
   `IMG000591.jpeg` / `IMG003456.jpeg`, and `IMG000707.jpeg` / `IMG003346.jpeg`?
   We are preserving original values and treating these as unresolved rather
   than choosing a label from software similarity alone.
4. Clarification of the subtype-label-set difference at `IMG001276.jpeg`, whose
   metadata lists two subtypes while its annotation contains one?
5. Any documented patient/study/lesion grouping behind the published training
   and validation lists, and guidance on the seven exact-copy pairs crossing
   those lists? We will not infer patients from filename order or demographics.
6. The applicable source-rights/attribution evidence for contributed collections
   and any recommended controls for redistributing derived images/metadata?

Our blank evidence template preserves public release image IDs, source flags,
measured image hashes and review flags. Its patient/lesion/reference fields are
blank; it creates no cohort and grants no training permission. We can adapt the
handoff format to your existing de-identified records. Please do not send names,
contact information, dates of birth, identifying clinical records or raw EXIF
values. If the requested evidence is unavailable, a statement of that limitation
would still help us report the evaluation scope accurately.

Thank you,
Inam Qasimi
Oncolohealth research project

## Team review before any send

Verify the recipient/contact, project affiliation/signature and exact attachment.
Use only the blank public-source template; do not attach source medical images,
returned private evidence or weights. No external message has been sent by this
work. Sending requires a direct instruction naming the intended recipient.

## Basis and response handling

The questions follow the published team artifacts in
`docs/research-handoff/BTXRD-audit.json`, `BTXRD-evidence-check.json` and
`BTXRD-evidence-template.csv`. They are structural observations, not independent
adjudication of clinical labels. The original source flags/hashes remain intact.
If evidence is returned, run the explicit offline checker, retain source identity
and report missing/contradictory declarations. Independent reviewers must still
assess the truth/completeness of grouping and diagnostic references; a passing
format/source check alone cannot authenticate them or approve a study.
