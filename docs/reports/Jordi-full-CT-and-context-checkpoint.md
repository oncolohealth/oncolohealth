# Full CT and local context checkpoint — October 25, 2026

The restored MONAI RetinaNet now executes a prepared full CT scan through the same local research backend as the other specialists. It produces nodule candidate boxes and an overlay, not malignant/benign classes. The working Gemma checkpoint remains main3; no new NPS training was performed.

## Actual execution

The downloaded Apache-2.0 MONAI bundle is pinned to revision `9d6622fda0e52be0a4155fed2e0afb9c17bcd80b`. Its83,709,381-byte `models/model.pt` has SHA-256 `b5e79231466adae93a6fe8e8594029e9add142914e223b879aa0343bb2402d01`. Source data are a TCIA LIDC-IDRI CT series, patient0287, selected from the model publisher's fold0 validation list. Selection used the smallest eligible published file-size metadata for a bounded PC run; it was not an untouched test case.

One real direct-app HTTP request completed in504.828seconds. It produced three candidates with scores0.9812088,0.0623261 and0.0448366. The authenticated overlay download matched its saved SHA-256. A separately stored LPS center-size reference box was consulted only after inference. Top box IoU was0.163486; at the prespecified0.1IoU matching threshold and0.02score threshold this gives one matched detection and two unmatched candidates on this one validation scan. This does not establish medical accuracy.

The first actual Gemma tool call also completed detector execution, but its final language-model request contained4,435tokens and failed against the old4,096-token context. That failure and its successful detector receipt are retained. Final reviewed-source roundtrip results are recorded in the subsequent completion note.

## Local serving setting

The existing llama.cpp server now serves the same exact-parent Q4_K_M base and main3 F32 adapter with8,192context tokens, parallel1 and eight CPU MoE layers. A real4,824-prompt-token request completed in9.609seconds, returned `context-window-ok` and stopped normally. This verifies the old limit was actually exceeded successfully. It does not claim a larger trained context or retrained weights. Original launcher/state backups permit rollback. Sampled VRAM after the upgrade was14,636/16,303MiB.

## Preprocessing and ownership

The CT path requires explicitly calibrated HU NIfTI with mm units and reviewed regular DICOM geometry. Its separate series preparation helper requires explicit finite RescaleSlope/Intercept/Type, positive finite spacing/thickness, one regular CT series, no duplicate positions/gaps/tilt, and source slice spacing/thickness at most2.5mm. Missing calibration is not substituted with1/0/HU. The marker is a preparation contract, not proof that an arbitrary externally edited NIfTI is scientifically valid.

Serving uses float32 CPU inference, RAS orientation,0.703125×0.703125×1.25mm resampling, HU[-1024,300]→[0,1] and192×192×80 sliding windows at0.25overlap. That ROI is the publisher's training patch size, smaller than its published inference configuration. We did not reproduce the publisher's benchmark configuration or accuracy. This bounded path takes about8minutes per full scan on this PC; native Gemma continues using CUDA independently.

Every CT worker has its own600-second deadline and owning-process liveness monitor, including a Windows process handle. Exiting the app cannot leave that worker running indefinitely. Reference IDs and boxes never enter the worker command, preprocessing or detector. Results retain input/model/source identities, native boxes/scores, timing, overlay, comparison and failures.

## Verification and remaining scope

64focused local checks pass:13CT geometry/reference/worker checks,15research runtime/eligibility,5attachment,3guidance,18app and10coordinator checks. Both actual owner-exit and independent-deadline tests use subprocesses, without model weights. Initial Ubuntu CI caught a POSIX zombie/reparenting edge case; it was fixed and all eight GitHub Python3.11–3.14 push/PR checks passed. The existing full Windows suite's symlink-fixture setup errors are separate and not relabeled as passing.

Claude owns the new chat-attachment UI branch; Codex leaves its HTML/CSS/JavaScript untouched. The main Assistant redesign/streaming PR is merged. Browser control still reports disabled here; HTTP/model checks do not establish click/layout verification. Arbitrary CT/MRI preparation, whole mammography, whole-slide grading and structured CBC/clinical prediction remain unavailable without their specific verified path. Main5 majorv3 remains prepared and untrained while NPS is down. No scheduled monitor is running.

## Ready-to-upload PC files

- Scan: `C:\Users\Jordi nieves\Documents\OncoloHealth-lung-CT-full-sample-01.nii.gz` —42,862,547bytes, SHA-256 `6a31caa8f834a73f9ff56429f8fce7df5f7f7cd11648870b6fcc600c5529f4db`.
- Separate box answer key: `C:\Users\Jordi nieves\Documents\OncoloHealth-lung-CT-answer-boxes.json`.
- Full source/calibration provenance: `C:\Users\Jordi nieves\Documents\OncoloHealth-lung-CT-full-sample-01-provenance.json`.
- Direct app receipt: `C:\Users\Jordi nieves\Documents\OncoloHealth-lung-CT-actual-app-result.json`.
- First Assistant context failure: `C:\Users\Jordi nieves\Documents\OncoloHealth-lung-CT-Assistant-result.json`.
- Larger-context verification: `C:\Users\Jordi nieves\Documents\OncoloHealth-context-8192-verification.json`.

Do not upload the answer key as the scan or treat a candidate nodule score as cancer risk. The scan is publisher validation and already inspected development, not an independent medical evaluation.


## Reviewed-source completion

The actual main3 Assistant called the reviewed local detector and returned a complete final answer at8,192context tokens. Native detector preprocessing/execution/output took534.25seconds, while the app model-execution receipt including checks and worker/import overhead took601.171seconds; the whole Assistant turn took626.094seconds. It reported3actual candidates. The new receipt matches the current model manifest and inference source identities, and the authenticated overlay download matches its checksum. Exact report: `C:\Users\Jordi nieves\Documents\OncoloHealth-lung-CT-final-verification.json`.

Observed final answer:

> The specialist identified 3 pulmonary nodule candidates, with the top score being 0.981. A separate reference comparison showed 1 match at a 0.5 score threshold. This case is a publisher validation sample and does not constitute an independent test. Nodule scores are uncalibrated and are not malignancy probabilities.
