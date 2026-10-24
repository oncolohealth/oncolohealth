# Model files, loading and a measured tiny extraction

Sebastian · October 24, 2026 · main, written with Claude Code.

This checks the real local RAD-DINO and ResNet-50 files: what they are, whether
they load completely, whether the code's preprocessing matches each publisher's
processor, and how long extraction takes on this laptop. It is a software and
runtime record. No labels were used, nothing was fitted or scored, and nothing
here is a medical result.

## Environment

macOS on Apple silicon (MPS), 8 GB. `.venv` with Python 3.12, torch 2.14.1,
timm 1.0.30, transformers 5.19.0, safetensors 0.8.0, Pillow 12.3.0, numpy 2.5.3.

## File identity

Every file in both model folders was hashed and compared with its
`PROVENANCE.json`. All match. Both weight files also match the publisher
checksum recorded at download (`integrity: publisher_checksum`). The config
files were recorded as `size_only` at download, so their hashes below are
measured local identities, not publisher-verified.

| Model | Revision | File | SHA-256 | Bytes |
|---|---|---|---|---|
| rad-dino | `110cbc18d513…` | model.safetensors | `dbfb9f54459c38773505de64a6ab7807bdcb392610fe1e697166342e43fb91ae` | 346,345,912 |
| | | config.json | `89daf9751d9576d586dedf9543c1083211611fa3a36908db7a799b3ce7c68ede` | 879 |
| | | preprocessor_config.json | `c537fc995c30e2353f07253899618d60e9eae3d5f82473778602c007c6523b56` | 756 |
| resnet50-a1-in1k | `767268603ca0…` | model.safetensors | `773525d5821de224f8f30c33377b7a795d7863e08522698200d3217d3f2a41bb` | 102,469,840 |
| | | config.json (timm `pretrained_cfg`) | `ff00d936f02c3b5f9f80a169d651ed28f9b6dc9cb1fd0464f92da4761caaac50` | 756 |

## Binding change

`model_identity` measured the weights (and RAD-DINO's `config.json`) but not the
processor file whose values the code hard-codes. It now also measures each
encoder's processor file (`preprocessor_config.json` for RAD-DINO, `config.json`
for ResNet-50). It parses the same bytes it hashed and refuses when size, mean,
std, bicubic interpolation or the native crop settings disagree with
`ENCODERS`. The parsed values are kept in the identity as
`publisher_preprocessing`.

Every model fingerprint changes as a result, as does every binding digest. The
six caches in `runs/features` predate input binding, so they were already
replay-only and nothing is lost. Earlier result files are unchanged.

## Weight loading

- RAD-DINO through `Dinov2Model.from_pretrained`: no missing, unexpected or
  shape-mismatched keys and no load errors; 86,580,480 parameters.
- ResNet-50 through timm with `strict=True`: the stored keys equal the model's
  keys except `fc.weight` and `fc.bias`, the classifier this code drops on purpose.
- CPU embeddings are finite, have the expected dimension (768 and 2048) and
  agree across batch sizes. MPS and CPU embeddings agree (cosine > 0.9999).

## Preprocessing against the publisher processors

`native_crop` is meant to reproduce each publisher's own resize and crop. On
synthetic PNGs it did for RAD-DINO but not for ResNet-50. The worst normalized
pixel difference was 3.4, caused by two rounding mismatches:

- Both publishers truncate the resized long edge; the code rounded it.
- transformers floors the center-crop offset; torchvision (timm) rounds it. The
  code always floored, so odd crop margins shifted ResNet-50's crop by one pixel.

Fixed in `load_image`: the long edge uses the publishers' own expression, and
each encoder declares its crop offset rounding. On six synthetic shapes,
ResNet-50 now matches timm exactly. RAD-DINO matches transformers to within one
8-bit gray level, because transformers rescales after its own uint8 resize.
`pad` and `pad_pstretch` are unaffected. The native-crop preprocessing hash now
includes the crop offset.

**On real JPEGs** a remaining difference appears. All pipelines decode JPEGs
with Pillow's `draft` at a reduced scale (at least the target size), which is
the documented policy. The publishers decode at full resolution. On the 16
smoke images:

| Encoder | Max pixel diff | Mean pixel diff | Embedding cosine min / mean | Max diff without draft |
|---|---|---|---|---|
| RAD-DINO | 2.13 | 0.0043 | 0.9984 / 0.9998 | 0.030 |
| ResNet-50 | 2.21 | 0.0091 | 0.9883 / 0.9944 | 0.000 |

With draft disabled, the difference disappears (two gray levels at most for
RAD-DINO). Grayscale versus RGB contributes nothing measurable: the 8 RGB images
are gray. So `native_crop` is publisher-equivalent except for draft decoding.
Whether to drop draft for that variant (slower decode of large JPEGs) is open.

## Measured tiny extraction

`scripts/extraction_smoke.py` picked 16 BTXRD images with no exact duplicates
(seed 0; centers 1/2/3: 6/5/5; 2.7 MB). It removed labels and demographics and
ran the normal bound extraction for both encoders and all three variants on MPS
with batch size 16. All six caches validated against their measured bindings.
Output: `runs/extraction-smoke-20261024T191018Z/` (git-ignored; `report.json`,
`selection.csv`, six `.npz` files of 71 to 153 KB).

| Encoder | Model load | Warm throughput | Bound extraction, 16 images, incl. load | Projected full BTXRD (3,746) |
|---|---|---|---|---|
| RAD-DINO | 4.2 s | 2.6 images/s | 7.8–7.9 s | about 24 min |
| ResNet-50 | 0.9 s | 36 images/s | 1.3–1.7 s | about 2 min |

An earlier identical run measured 2.1 images/s for RAD-DINO (about 29 min), so
expect roughly 25–30 min per RAD-DINO variant on this laptop. This matches the
earlier report of about 25 min. Measuring the image hashes for 16 images took
under 0.3 s. The process peaked at about 610 MB of resident memory. macOS does
not count MPS buffers fully in that number, so it understates total memory.

## Reproduce

```sh
CW_MODEL_TESTS=1 .venv/bin/python -m unittest tests.test_model_loading -v
.venv/bin/python scripts/extraction_smoke.py
```

The real-weight tests feed only synthetic images and are skipped unless
`CW_MODEL_TESTS=1` is set, so CI and plain Python stay fast. Suite counts:
249 discovered. In the ML environment, 245 pass and the 4 opt-in tests skip;
with `CW_MODEL_TESTS=1`, all 249 pass. Plain Python passes 205 with 44 skips.

## Limits

Hashes match what was downloaded, and the weights match the publisher checksum
at that time. That is not a signature or proof of training provenance. Agreement
with the publisher processors is measured on 6 synthetic shapes and 16 real
images, not the whole release. The timing is from one laptop, small batches and
one run each (plus the earlier run). It is an estimate, not a resource promise
for other hardware. The tests don't cover rights, labels, patient grouping,
diagnostic references or clinical validity.
