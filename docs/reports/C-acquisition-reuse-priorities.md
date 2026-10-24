# Model and dataset priorities for the next round

Sebastian · October 24, 2026, written with Claude Code. Ordered by value for
the next Gemma coordinator round and the bone X-ray milestone. Each item states
why it earns its place and what blocks it. Cards for the records marked ✓ are
in `catalog/cards.json`.

| # | Record | Action | Why it earns its place | Blocker / cost |
|---|---|---|---|---|
| 1 | ✓ rad-dino, ✓ resnet50-a1-in1k | Done: runnable specialists | The two matched arms of the first comparison; real call path for the coordinator | Adaptation/redistribution terms unreviewed |
| 2 | ✓ medsiglip-448 | Acquire after terms are accepted | The Hub's primary medical encoder candidate (Q03) and a third arm on the same adapter pattern | A named person must accept HAI-DEF terms; 3.5 GB |
| 3 | dinov2-base (on disk) | Add an adapter | Separates "medical pretraining" from "self-supervised ViT" in the RAD-DINO comparison (RAD-DINO is fine-tuned from it); same `Dinov2Model` code path | Terms review (Apache-2.0), processor check at 224 |
| 4 | ✓ btxrd | Review near-duplicate candidates, send the custodian request | Every BTXRD claim depends on grouping and the reference standard | Human review; outreach decision |
| 5 | ✓ cbis-ddsm | Fetch a small patient subset (labels already fetch with it) | The only cataloged cancer set with verified patient grouping and lesion-level pathology labels: teaches grouped splits and split auditing | No encoder accepts `mammography`; that is a catalog decision. 163 GB total, so subsets only |
| 6 | ✓ lidc-idri-sample + LIDC XML reads | Fetch the radiologist annotations | Turns the 3-patient sample into a detector smoke test with a reference; demonstrates a detector's box output | Detector adapter (item 7); still not evaluation data |
| 7 | ✓ monai-lung-nodule-ct-detection (on disk) | Adapter over `models/model.ts` (TorchScript, instead of the arbitrary-code pickle `model.pt`) | Gives the coordinator a real non-encoder output (boxes) to explain | MONAI dependency check; terms review |
| 8 | soft-tissue-sarcoma | Review ROI names and outcome columns before fetching | Sarcoma-relevant, open, 51 patients with clinical spreadsheet | ROI/outcome review; about 190 MB per patient |

Not prioritized now: BiomedCLIP (on disk, but its weights are a pickle and
need open_clip), MURA (registration-gated and "abnormal" is not cancer),
pathology foundation models (no slide workflow on this laptop yet).
