# Research evidence review

Inam Qasimi · October 24, 2026. Source/document review only. No medical execution.

## Primary-source checks

The [BTXRD dataset paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11739492/)
reports 3,746 images: 1,879 normal, 1,525 benign and 342 malignant. Center 1 pools
three hospitals; centers 2 and 3 are Radiopaedia and MedPix. They are not three
independent hospitals. The paper acknowledges multiple views of a lesion and
mixed histology/expert confirmation, including absent pathology for some images.
Its published metadata table does not supply patient/lesion identity. The local
inventory's missing identity finding remains the operative limitation. Source
separation therefore cannot certify patient independence. This last conclusion
is our interpretation, not a reported new experimental result.

The paper's article license and the separate dataset license must be treated
separately. The publisher's [Figshare API record](https://api.figshare.com/v2/articles/27865398)
was re-read through a direct HTTP request after the web reader failed. It reports
version 1 and CC BY 4.0, consistent with the catalog. No new rights approval for
other sources or uses is inferred from this metadata check.

The [CLAIM 2024 checklist](https://rsna.github.io/claim/checklist.html) calls for
explicit reference-standard methods, partition assignment and disjointness,
model selection, uncertainty, failures and limitations. It is a reporting guide,
not an approval or certification. We use it to identify the following gaps.

## Evidence still needed

| Question | Current evidence | Concrete next artifact |
|---|---|---|
| What is the primary task? | Three exploratory endpoints, no approved primary endpoint | Dated endpoint and intended-use decision before a new confirmatory evaluation |
| What supports each label? | Mixed confirmation reported; per-image method unresolved | Reference-standard provenance and disagreement/adjudication log |
| Are patients independent? | No genuine IDs in the release inventory | Maintainer mapping or a defensible independent cohort; never infer IDs from demographics |
| Are repeated images resolved? | Team reports 21 exact pairs, two conflicting-label pairs; near-duplicate candidates | Reviewed pair/group ledger, exclusions and a new manifest/split version |
| Was the test untouched? | Baseline and source-shift results already viewed | Freeze development choices, then use a new untouched evaluation |
| Did pretraining include evaluation cases? | Provenance review remains partial | Named inventories, identifiers/hashes, coverage and unresolved matches |
| Does the workflow help users? | Proposed research community, no documented study | Observed task session and completion/effort/understanding measures |

## Corrections made during this pass

The baseline report previously treated overlapping confidence intervals as
support for no encoder difference and suggested source holdout removes
same-patient overlap. Those conclusions are not established. The report now
describes the observed estimates and explicitly leaves equivalence and patient
independence unresolved. Historical scores, predictions, thresholds and runs
are unchanged. The presentation uses the same qualified interpretation.

The next scientific deliverable requires real protocol/cohort evidence, not
more software tests. The software can enforce declared identities and preserve
provenance, but cannot supply missing clinical labels or identities.
