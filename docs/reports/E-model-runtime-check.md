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

**On real JPEGs** one more difference showed up. Every variant decoded JPEGs
with Pillow's `draft` at a reduced scale (at least the target size), while the
publishers decode at full resolution. On the 16 smoke images, with draft:

| Encoder | Max pixel diff | Mean pixel diff | Embedding cosine min / mean |
|---|---|---|---|
| RAD-DINO | 2.13 | 0.0043 | 0.9984 / 0.9998 |
| ResNet-50 | 2.21 | 0.0091 | 0.9883 / 0.9944 |

Disabling draft removed the whole difference. Grayscale versus RGB contributed
nothing measurable: the 8 RGB images are gray. **`native_crop` now decodes at
full resolution**; `pad` and `pad_pstretch` keep draft decoding. On the same 16
images:

| Encoder | Max pixel diff | Mean pixel diff | Embedding cosine min / mean |
|---|---|---|---|
| RAD-DINO | 0.030 (two gray levels) | 0.00003 | 0.99999 / 1.00000 |
| ResNet-50 | 0 | 0 | 1.0 / 1.0 |

So `native_crop` is publisher-equivalent on these images. A synthetic test
checks that only `native_crop` skips draft, and the opt-in comparison includes
a large synthetic JPEG that fails if draft comes back.

## Measured tiny extraction

`scripts/extraction_smoke.py` picked 16 BTXRD images with no exact duplicates
(seed 0; centers 1/2/3: 6/5/5; 2.7 MB). It removed labels and demographics and
ran the normal bound extraction for both encoders and all three variants on MPS
with batch size 16. All six caches validated against their measured bindings.
The runner times each variant separately: model load, a cold and a warm pass,
and single-threaded decode plus preprocessing alone.

Two runs after the full-resolution change (`runs/extraction-smoke-20261024T191927Z/`
and `runs/extraction-smoke-20261024T192106Z/`; git-ignored, each with
`report.json`, `selection.csv` and six `.npz` files):

| Encoder | Variant | Warm throughput | Decode + preprocess per image | Projected full BTXRD (3,746) |
|---|---|---|---|---|
| RAD-DINO | pad | 2.5–2.6 images/s | 5–13 ms | 24–25 min |
| | pad_pstretch | 2.3–2.4 images/s | 8–10 ms | about 27 min |
| | native_crop | 2.2–2.4 images/s | 12–16 ms | 26–28 min |
| ResNet-50 | pad | 34–35 images/s | 5 ms | about 2 min |
| | pad_pstretch | 35–43 images/s | 4–6 ms | about 2 min |
| | native_crop | 31–38 images/s | 7–8 ms | about 2 min |

Full-resolution decoding costs `native_crop` a few milliseconds per image. That
is small next to RAD-DINO's roughly 400 ms per image, and the throughput
differences between variants are within run-to-run noise. Expect roughly 25–30
min per RAD-DINO variant on this laptop, matching the earlier report of about
25 min. Model load took 4–6 s for RAD-DINO the first time (about 1 s once the
file is cached) and under 2 s for ResNet-50. Measuring the image hashes for 16
images took under 0.3 s. Peak resident memory was 440–650 MB across runs. macOS
does not count MPS buffers fully in that number, so it understates total memory.
The earlier draft-decoding run stays in `runs/extraction-smoke-20261024T191018Z/`
as the before record.

## Reproduce

```sh
CW_MODEL_TESTS=1 .venv/bin/python -m unittest tests.test_model_loading -v
.venv/bin/python scripts/extraction_smoke.py
```

The real-weight tests feed only synthetic images and are skipped unless
`CW_MODEL_TESTS=1` is set, so CI and plain Python stay fast. Suite counts:
250 discovered. In the ML environment, 246 pass and the 4 opt-in tests skip;
with `CW_MODEL_TESTS=1`, all 250 pass. Plain Python passes 205 with 45 skips.

## Limits

Hashes match what was downloaded, and the weights match the publisher checksum
at that time. That is not a signature or proof of training provenance. Agreement
with the publisher processors is measured on 6 synthetic shapes and 16 real
images, not the whole release. The timing is from one laptop, small batches and
two runs per variant (plus the earlier draft-decoding run). It is an estimate, not a resource promise
for other hardware. The tests don't cover rights, labels, patient grouping,
diagnostic references or clinical validity.
