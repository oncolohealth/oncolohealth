# T02: Candidate model cards and adapter contract

Status: first pass, October 23, 2026. Software and study-design work only. Neither model has a validated bone-tumor result; an exploratory run is in [E-btxrd-exploratory-baseline.md](E-btxrd-exploratory-baseline.md).

## Decision recorded (Hub Q03)

The first comparison is **frozen RAD-DINO + linear head** against **frozen ResNet-50 + linear head**, both already downloaded and checksum-verified. MedSigLIP joins as a second medical arm once its gated terms are accepted. ResNet-50 replaces the ResNet-18 in the Hub's model register because it is the backbone already obtained; ResNet-18 remains an option if the team prefers a smaller baseline.

## Card 1: RAD-DINO (medical encoder arm)

| Field | Value |
|---|---|
| Artifact | `microsoft/rad-dino` at revision `110cbc18d5133582e320b43d53bf5c44e410c936`; `model.safetensors` (sha256 verified against Hugging Face LFS) |
| Kind | Image encoder (ViT-B/14, DINOv2 architecture, 86.6 M parameters) |
| Pretraining data | 882,775 chest X-rays from MIMIC-CXR, CheXpert, NIH-CXR, PadChest and BRAX (model card). No musculoskeletal radiographs |
| Native input | 3 channels, shortest edge resized to 518 then 518 × 518 center crop; mean 0.5307, std 0.2583 per channel (`preprocessor_config.json`) |
| Native output | 768-d CLS embedding after the final layer norm (`pooler_output`); also 37 × 37 patch tokens, unused here |
| License and terms | MIT license file; the model card says "shared for research purposes only" and "not meant to be used for clinical practice" |
| Inference / adaptation / distillation | Research inference and linear probing fit the card's stated uses. Distilling from it, or shipping a derived head outside research, needs review of the research-only statement |
| Overlap with BTXRD | None expected: chest-only pretraining. Not verified, because `training_images.csv` was not downloaded |
| Evidence state | Catalog: `cataloged` (promotion needs a reviewed change). Locally: the adapter runs and produced features for all 3,746 BTXRD images |
| Open question | Chest-only pretraining may transfer poorly to bone; that is what the comparison measures |

## Card 2: ResNet-50 (conventional arm)

| Field | Value |
|---|---|
| Artifact | `timm/resnet50.a1_in1k` at revision `767268603ca0cb0bfe326fa87277f19c419566ef`; `model.safetensors` (sha256 verified) |
| Kind | Convolutional image backbone (25.6 M parameters; 23.6 M without the ImageNet classifier) |
| Pretraining data | ImageNet-1k natural images, "ResNet Strikes Back" A1 recipe |
| Native input | 3 channels; 224 px train / 288 px test resolution; ImageNet mean (0.485, 0.456, 0.406) and std (0.229, 0.224, 0.225) |
| Native output | 2,048-d global-average-pooled features (classifier removed) |
| License and terms | Apache-2.0, commercial use allowed |
| Inference / adaptation / distillation | Allowed under Apache-2.0 |
| Overlap with BTXRD | None: natural-image pretraining |
| Evidence state | Catalog: `cataloged`. Locally: the adapter runs and produced features for all 3,746 BTXRD images |

## Pending card: MedSigLIP-448

`google/medsiglip-448` at revision `9cea28a1a1195f665105faa6e8544c112fd960a4`. Gated under the Health AI Developer Foundations terms, which someone on the team must accept with their own Hugging Face account. Native input is 448 px. Not acquired, so no preprocessing, rights or overlap checks have been run. Its pretraining data must be checked for overlap with BTXRD sources (Radiopaedia and MedPix are centers 2 and 3) before any comparison.

## Adapter contract (as implemented)

Code: `cancer_workbench/adapters/encoder.py` (`FrozenEncoderAdapter`), following the `Adapter` protocol in `adapters/base.py`.

**Input.** `{"image_path": "<file>"}`, plus optional `input_refs` on the request. `validate` rejects a missing or non-string path and a file that does not exist.

**Preprocessing (one policy for both arms).**
1. JPEG decode at reduced scale (never below the target size).
2. Convert to grayscale; colour radiographs from public sources are converted too.
3. Pad to a square with black, so the whole radiograph is kept. This departs from RAD-DINO's center crop, which could cut off a lesion near the edge.
4. Bicubic resize to the encoder's size (RAD-DINO 518, ResNet-50 288).
5. Replicate to 3 channels, scale to [0, 1], normalize with the encoder's mean and std.

The policy, size, mean and std are hashed; feature files carry that hash and the weight revision, and stale features are refused.

**Variants for the source-shift check** (`encoder.VARIANTS`; `pad` above stays the default everywhere, so its hash and cached features are unchanged):
- `pad_pstretch`: after grayscale, a per-image 1st–99th percentile contrast stretch (`ImageOps.autocontrast`, cutoff 1 %), then the same padding and resize.
- `native_crop`: after grayscale, bicubic resize of the shortest edge to the input size, then a center crop to a square. This matches RAD-DINO's processor (shortest edge 518, crop 518) and timm's test config for ResNet-50 (288 px, `test_crop_pct` 1.0). It can cut off part of a long radiograph, including a lesion near the edge.

**Weights.** Loaded only from the local `model.safetensors` (no pickles, no network).

**Output.** `run` returns `{"type": "embedding", "dim", "embedding", "encoder", "revision", "preprocessing", "note"}` inside the standard `ResultEnvelope`. `embed(paths)` returns an N × dim array for batches. An embedding is a representation, not a diagnosis.

**Head contract.** `learning/heads.py` takes features with ordered classes, labels, partitions and the encoder reference. Before any fit, `validate_head_inputs` refuses misaligned or non-finite inputs, repeated sample ids, a train or val partition missing a class, and any patient or duplicate group that spans partitions. It fits on TRAIN only, chooses regularization on VAL only, and `evaluate_head` refuses rows that were trained on, shared patients, a different encoder reference or a different class order. Output is per-class probabilities in the declared class order.

## Open questions

- **Rights.** RAD-DINO's research-only statement alongside an MIT license file needs a team reading before anything derived from it leaves research use.
- **Preprocessing.** Pad-to-square versus each model's native crop is untested. A small ablation would show whether it matters.
- **BTXRD authors' model.** Inam's T01 notes say the authors' notebook trains `yolov8n-cls` while the paper names YOLOv8s-cls, and their repository has no LICENSE file. That repository is outside this session's access, so the discrepancy and checkpoint permissions are still open. Their checkpoint is not a candidate until both are resolved.
- **MedSigLIP access.** Who accepts the gated terms, and whether its pretraining overlaps Radiopaedia or MedPix.
