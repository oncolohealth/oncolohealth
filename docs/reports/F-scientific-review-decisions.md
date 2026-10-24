# First experiment: decisions awaiting scientific review

Prepared by Inam Qasimi. **Draft for a named reviewer; no decision is approved by
this document.** Existing exploratory scores and software tests do not fill in
these decisions. Use `F-evaluation-protocol.md` for the fuller method proposal.

| Decision | Current source behavior / evidence | Reviewer needs to record |
|---|---|---|
| Study scope | BTXRD lacks genuine patient/lesion mapping and per-row diagnostic references. Centers 2/3 have already been examined. | Explicit exploratory image-level scope, or a suitable independently grouped/evidenced cohort; intended claims and limits. |
| Endpoint and class order | Runner supports `three_class` → normal/benign/malignant; `tumor_vs_normal` → normal/tumor; `benign_vs_malignant` → benign/malignant. | One first endpoint, positive class where binary, eligibility denominator and label/reference definition. |
| Primary metric | The fuller proposal discusses malignant one-vs-rest AP for three classes; existing head selection uses validation macro-AUROC. | Primary/secondary metrics and whether the selection objective stays as implemented. A proposed reporting metric is not an approved change to tuning. |
| Eligibility/exclusions | Four contradictory exact-copy rows are quarantined by the exploratory manifest policy; other duplicate/view/reference gaps remain. | Reviewed exclusions/adjudication policy, retained source values and counts; handling of missing labels and failed inputs. |
| Grouping and split | Runner has image-stratified and source-holdout exploratory protocols; declared groups are checked. Similarity and source labels cannot establish patients. | Evaluation unit and genuine grouping source, split version and overlap assessment. No new patient identity inferred by software. |
| Preprocessing and model pair | Frozen RAD-DINO and ResNet-50 with linear heads. New processor/decode fixes change fingerprints; old unbound caches stay replay-only. | Chosen variant and exact model/processor/source identities. Fresh extraction needs explicit scope; no hashes retrofitted to old features. |
| Development choices | C grid is fixed in `learning/heads.py`; binary thresholds are chosen from validation data. Source-shift variants were selected using center-1 validation. | Frozen search/seed/threshold/calibration/abstention rules and which choices were already explored. No selection on final evaluation data. |
| Uncertainty and comparison | Grouped/paired utilities exist, but authentic patient groups are unavailable. Different test cohorts do not support a paired comparison or an equivalence claim. | Supported uncertainty unit, cohort matching and comparison plan; unsupported patient-level intervals withheld. |
| Execution and resources | Saved drafts are non-authorizing. Sebastian reports actual model loading and tiny extraction on his MPS laptop; this environment’s CPU checks are software-only. | Exact workload, operator/runtime, permitted artifacts, storage/time cap, logs/checkpoints/cancellation and failure policy. No transfer of timing claims to unmeasured hardware. |
| Independent review | Dataset and source checks can verify declarations/bytes but not medical truth or permissions. | Named reviewer, evidence reviewed, dated decision record and remaining conditions. |

## Review outcome to complete

- Reviewer and decision reference: **unassigned / pending**.
- Approved endpoint, evaluation unit and primary metric: **pending**.
- Cohort/source/split/protocol versions: **pending**.
- Approved execution scope and resources: **pending**.
- Unresolved evidence, exclusions and restrictions: **retain explicitly**.

A reviewer may reject or amend this proposal. Preserve the earlier exploration
history and record amendments before new work. No table cell here authorizes a
medical run, makes an unavailable mapping authentic or converts examined sources
into an untouched final test. No clinical accuracy or utility is established.
