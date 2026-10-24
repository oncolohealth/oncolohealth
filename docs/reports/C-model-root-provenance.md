# Model-root provenance repair candidate

When an encoder adapter was configured with a custom models directory, it loaded from that directory but looked up result revision metadata under the default models directory. This candidate makes `revision` accept an optional model root and makes adapter results use their configured root. Existing one-argument helper calls retain their default-root behavior.

Missing provenance in the requested custom folder remains unknown (`None`); the helper does not borrow the default folder's identity. Malformed custom JSON raises before an embedding call. Assertions in a provenance file still do not authenticate weight bytes, permissions, model eligibility or a scientifically valid result.

The candidate changes only the adapter helper/result path, nine synthetic tests, this report and the candidate progress record. Tests use temporary JSON and mocked vectors; no weights, medical images, live inference, training or remote resources are involved. They cover default compatibility, custom Path/string roots, missing/malformed custom metadata, result identities, pre-call refusal and separate encoder folders.

Verification on this candidate: 115 tests discovered, 102 passed, 13 optional ML checks skipped; catalog validation stays at 16 models and 14 datasets. Full ML/Torch execution and independent receiving-branch review remain pending. The image-content/cache-binding defect, custom preprocessing review, missing patient/lesion mapping and per-row diagnostic references remain unresolved. This isolated source candidate is unmerged and unpushed.
