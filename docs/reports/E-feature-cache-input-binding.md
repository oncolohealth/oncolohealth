# Feature-cache image binding repair candidate

Existing feature-cache locators identify a dataset name, encoder revision prefix and preprocessing settings, but do not identify source-image bytes. This candidate keeps those locators and requires measured input bindings at consumption. Old caches are rejected; they are not silently trusted or automatically overwritten by a failed reuse attempt.

New caches carry a functional binding schema, measured image SHA-256 values aligned with unique sample IDs and a canonical mapping digest. Any declared manifest hashes must match the files. If hashes were absent, measuring the current bytes still binds the cache but does not establish curated release provenance. Absolute/escaping paths, duplicate or missing IDs, inconsistent mapping hashes and misaligned feature rows fail.

The baseline, source-shift experiment, near-duplicate ranker and legacy head-rebuild path all use the bound loader. It checks declared encoder/revision/variant/preprocessing identity and the current source files before fitting or ranking. Labels, patient groups and partitions come from the current reviewed manifest; changing them alone does not require re-encoding unchanged pixels. Their scientific truth and eligibility are not established by this check.

Extraction measures files before and after its encoder call, rejects detected changes or invalid arrays, and replaces its output only after a temporary NPZ is fully written. This detects persistent changes; it does not lock files or rule out transient edit-and-restoration races. It is not an authenticated feature store or actual weight/processor verifier. The low-level NPZ reader and direct feature-head APIs remain available; this is not a security/authorization boundary.

Twenty synthetic tests cover replaced bytes, source/hash drift, missing and duplicate IDs, malformed caches, contained paths, reordering, unchanged-pixel reuse, NPZ roundtrips, failure/mutation preservation, invalid arrays, identity mismatch and refusal in all four consumers before downstream work. No medical images, actual model weights, image-model inference, training or cluster compute were used.

Standalone verification: 126 tests discovered; plain Python passes 107 and skips 19; NumPy-enabled Python passes 115 and skips 11. Catalog validation remains 16 models and 14 datasets. Full ML/Torch execution, receiving-branch reconciliation and scientific validation remain pending. This is a local unmerged candidate against inspected main c13a74a15fdd636249899a587a239cb000107e6d.
