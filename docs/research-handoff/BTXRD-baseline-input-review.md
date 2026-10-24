# BTXRD baseline input and provenance review

The inspected shared baseline has two reproducibility defects to address before relying on a rerun: cached features are not bound to source-image bytes, and a custom model directory can report provenance from the default directory. Its preprocessing settings match the pinned publishers' sizes and normalization, but its custom image pipeline has not been shown equivalent to either publisher's processor.

This review applies to inspected shared commit `c13a74a15fdd636249899a587a239cb000107e6d`. It does not inspect Inam's unavailable unpushed branch or establish that the same issues remain there. No shared source was changed. The [source fingerprints and publisher configurations](BTXRD-baseline-input-review.json) and [offline characterization checks](BTXRD-baseline-input-checks.py) make the observations reproducible.

## Verified findings

| Finding | Evidence and practical implication |
|---|---|
| Source-image replacement can reuse stale features | `learning/features.py:cache_path` includes dataset/model IDs, a revision prefix and a preprocessing hash, but no image-content identity. Neither exploratory experiment's cache guard checks source hashes. With synthetic input bytes changed under the same ID, the cache name stays identical and both actual guard expressions accept the old identity fields. This demonstrates a missing check; it does not show that any reported experiment used stale features. |
| Custom-folder provenance can describe another model directory | `FrozenEncoderAdapter` accepts `models_dir`, but its result calls the module-global `revision()`, which reads the default model directory. A synthetic adapter call with mocked embeddings and two different provenance files returns the default revision while its configured root points at the custom folder. No weights were loaded. |
| Basic publisher settings agree | RAD-DINO's 518-pixel size, mean `[0.5307, 0.5307, 0.5307]` and standard deviation `[0.2583, 0.2583, 0.2583]` match the pinned config. ResNet-50's 288-pixel test size and ImageNet normalization also match its pinned config. This does not verify acquired weight files, tensor outputs or end-to-end processor equivalence. |
| `native_crop` is a custom pipeline | The inspected code forces grayscale and uses a reduced JPEG decode before resize/crop. RAD-DINO's publisher config requests RGB conversion. A synthetic red input becomes grayscale in the source's PIL stage. A synthetic marker near the end of a long image survives padding but is discarded by center cropping. Cropping is a deliberate field-of-view tradeoff; the marker test is not evidence of a missed tumor or measured medical harm. |

The cache-guard check extracts and evaluates the existing rejection expression from each experiment without running its job. The pixel checks execute the inspected function's PIL stage, stopping before tensor creation. The custom-directory check mocks the embedding result. These are bounded software observations, not full ML runtime tests.

## Exact candidates and primary evidence

- **RAD-DINO:** `microsoft/rad-dino`, revision `110cbc18d5133582e320b43d53bf5c44e410c936`. Its [pinned processor configuration](https://huggingface.co/microsoft/rad-dino/blob/110cbc18d5133582e320b43d53bf5c44e410c936/preprocessor_config.json) specifies shortest-edge resizing and a 518 × 518 center crop. Its [pinned model card](https://huggingface.co/microsoft/rad-dino/blob/110cbc18d5133582e320b43d53bf5c44e410c936/README.md) describes a chest-radiograph encoder, research use and five named pretraining collections. Bone classification requires a fitted head and task-specific evaluation. Dataset names alone cannot prove absence of pretraining overlap.
- **Conventional comparator:** `timm/resnet50.a1_in1k`, revision `767268603ca0cb0bfe326fa87277f19c419566ef`. Its [pinned configuration](https://huggingface.co/timm/resnet50.a1_in1k/blob/767268603ca0cb0bfe326fa87277f19c419566ef/config.json) records 224-pixel training and 288-pixel test inputs, bicubic interpolation and a test crop fraction of 1.0. Its [model card](https://huggingface.co/timm/resnet50.a1_in1k/blob/767268603ca0cb0bfe326fa87277f19c419566ef/README.md) describes ImageNet training and pooled feature extraction. That source does not establish cancer accuracy.

Only small public text/configuration references were retrieved. No model weights, training-image lists, medical datasets or medical pixels were acquired or read for this review. Acquisition/checksum claims about the team's weight files remain repository reports until those actual files are independently inspected.

## Required repair and acceptance behavior

1. Bind feature rows to unique sample IDs and measured image SHA-256 values. Check that mapping against the current source files before reusing cached features. A missing, changed or duplicate identity must fail before head fitting. A changed file under an unchanged ID must be detected.
2. Bind the cache to the full encoder identity, actual weight digest and preprocessing implementation/configuration. Keep relevant runtime details as scientific provenance. A declared revision alone does not authenticate weights. For unchanged pixels, label or partition changes need a reviewed current manifest rather than needless image re-encoding.
3. Read and report provenance from the same resolved model directory used for loading. Test two folders with different asserted identities, missing provenance and altered local weights; do not fall back to another folder's identity.
4. Reject legacy caches lacking the new bindings. Recompute features only after explicit authorized execution. Prevent source-file changes during extraction from being silently recorded as matching the measured input.
5. Describe padding and cropping as explicit custom policies until an authorized comparison against pinned reference processors establishes equivalence where intended. Preserve the field-of-view choice, interpolation, rounding, color conversion and decode behavior in the protocol. Select changes using development data; already-examined centers 2 and 3 cannot become an untouched test set.

Review/rebase these changes against the receiving branch before integration. A separate [model-folder provenance repair candidate](BTXRD-model-provenance-fix.md) now addresses the custom-folder lookup on the inspected base, with nine regression tests and clean composition with the earlier audit patch. It remains local and unmerged; cache binding, actual weight authentication and processor equivalence remain open. The original characterization tests and source fingerprints in this review continue to describe the original inspected source, not the repaired candidate.

A subsequent [feature-cache image-binding candidate](BTXRD-feature-cache-fix.md) now addresses cache/source-byte consistency in all four consumers with 20 synthetic tests. All three local patches compose in all six orders on the inspected base. Actual weight/processor authentication and receiving-branch reconciliation remain open; the original source observations and characterization script above are unchanged.

## Checks actually performed

With optional Pillow installed, all **six characterization tests passed**. Plain Python passed four and skipped the two pixel checks. Both source cache guards were examined, and changing the encoder revision was correctly rejected by their existing checks. The harness refuses source fingerprints different from those in the manifest; this refusal was also checked. These tests confirm the described limitations, not repaired behavior. They are separate from the foundation's 72-test suite and the integration candidate's 131 discovered tests.

Run with a checkout matching the recorded source fingerprints:

```sh
python3 -B BTXRD-baseline-input-checks.py shared-checkout
```

Keep the script and its sibling JSON manifest together. The command performs no downloads, model loading, training or remote work. Pillow is optional and is not installed automatically.

Patient/lesion grouping, per-row diagnostic reference standards, contradictory-label adjudication, rights/privacy review and an agreed protocol remain scientific blockers. Repairing reproducibility defects cannot establish those facts or medical validity.
