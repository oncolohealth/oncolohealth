# Measured feature and head provenance

Inam Qasimi · October 24, 2026 · isolated `codex/demo-readiness` branch.

Replacing an image could previously leave its feature-cache name unchanged.
Both exploratory runners could reach fitting with that old cache. Separately,
an encoder configured with a custom model folder could report the default
folder's revision. These defects were reproduced at `96f2fb2` using synthetic
byte files and mocked embeddings/fitting boundaries. No medical pixels, actual
weights, training or inference were used. This does not establish that any
previous reported medical scores used incorrect inputs.

The Team Hub contains independent candidates for related repairs. Their patch
files were unavailable in the searched checkout/Documents/Downloads paths.
This branch implements and tests its own compatible repair; those candidates
are not claimed imported, and their test counts are not added to this suite.

## What is now checked

- Source identity is a canonical mapping of unique sample IDs to relative image
  paths, byte counts and measured SHA-256 values. Declared hashes, when present,
  must agree. Escaping paths and non-regular files are refused. Labels, patient
  identities and partitions remain separate manifest/protocol responsibilities.
- Encoder identity measures the actual local safetensors file and, for RAD-DINO,
  the consumed `config.json`. It includes architecture, dimension, preprocessing
  parameters/variant, loaded encoder-source hash and installed dependency versions.
  Revision metadata comes from the actual configured folder. Missing revision
  metadata stays unknown; it is never borrowed from another folder.
- New feature names include the complete input-binding digest. NPZ files retain
  the binding and a digest of the finite feature matrix, dtype, geometry and
  ordered sample IDs. Readers verify these before fitting, refitting or ranking.
  Source hashes measured by the first arm are carried into derived splits and
  later arms. Source-shift results reference their own variant's cache.
- Extraction remeasures inputs after embedding and publishes with a temporary
  file followed by atomic replacement. Detected changes or write failures leave
  an existing output intact. Review-only near-duplicate ranking reads verified
  caches and never starts extraction when a cache is missing.
- Saved run results and heads share a fingerprint of fitted arrays, class order,
  encoder context and training IDs. A missing head may be rebuilt only from a
  bound cache and must reproduce the stored validation probabilities **and**
  fitted-array identity before use. Replaced head files cannot reuse an old
  in-memory entry. Model-cache entries include the measured model identity.
- Live scoring checks model/head context and class order, measures selected image
  bytes, refuses run-linked images whose recorded hashes are missing/different,
  and checks for persistent image/model changes during work. Recorded training
  IDs are refused. Uploads have no established reference label or patient identity.

## Migration: preserve replay, regenerate explicitly

Existing result JSON, predictions, heads and legacy cache files are preserved.
Stored validation/test prediction replay remains available with the core package.
**Legacy unbound runs are replay-only on this branch.** Their live-scoring button
is disabled, and direct scoring/refitting refuses them. Near-duplicate review also
refuses legacy/unmatched caches. Do not add guessed bindings to old artifacts or
copy a current hash into an old run to make it appear verified.

After review of data/model permissions, source integrity, compute and the
exploratory protocol, an operator can explicitly generate a new run in the
supported ML environment. Inspect `python -m cancer_workbench baseline --help`
or `python -m cancer_workbench source-shift --help` before selecting the desired
encoders/endpoints/protocols. These commands perform real work; they were **not**
run on medical data for this repair. A missing matching cache in an explicitly
started baseline/source-shift run causes fresh extraction under a new bound name.
A review/scoring refusal itself never authorizes that work.

Restart the app after updating source or dependencies. Keep the old run as its
historical record. Fresh hashes establish reproducible byte identity, not a new
untouched test cohort or scientific approval. No historical metrics were rewritten.

## Verification and practical limits

Synthetic regressions cover custom/missing/malformed folder provenance, changed
images/weights/configuration/processor context, cache payload alignment, atomic
write failure, both fit runners, near-duplicate refusal before ranking, head refit,
head replacement, class order and live batch changes. A desktop browser fixture
confirmed that legacy stored predictions replay while live scoring is disabled.
Its displayed probabilities are explicitly synthetic. See `PROGRESS.md` for the
current integrated suite counts; earlier checkpoints remain separately dated.

Real-weight loading, processor agreement and a measured tiny extraction are now
recorded in `E-model-runtime-check.md`; real medical reruns remain unperformed. Hashing images and weights adds disk I/O; its cost has not
been benchmarked. Version/source identity is intentionally strict and can require
new features after software changes. Installed package versions are metadata,
not process attestation; hot-updating dependencies is unsupported.

Before/after hashing detects ordinary persistent changes. It is not a file lock
or an immutable snapshot and cannot exclude every transient edit-and-restore.
The fingerprints are local consistency records, not signatures or publisher
authentication. They do not establish rights, correct labels, authentic patient
mapping, diagnostic reference standards, pretraining independence, or clinical
validity. Training-ID refusal does not detect renamed duplicate uploads or shared
patients. Independent code/protocol review and the outstanding scientific evidence
remain necessary before stronger use or claims.
