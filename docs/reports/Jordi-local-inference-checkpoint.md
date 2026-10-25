# Local inference integration checkpoint — October 24, 2026

The review branch extends the shared app with real local specialist execution and a backend contract for Claude's independent Assistant/streaming redesign. It does not claim a finished visible UI or medical validation.

## Verified execution

The main app at `http://127.0.0.1:8765` uses an isolated research environment. Native Gemma/main3 remains at port8080, independently of NPS. All five initial classifiers were executed through app HTTP endpoints and through actual Gemma `run_specialist` calls. After compacting tool output, five attachment requests completed with short final answers, including honest reference disagreements. MRI then completed via the actual attachment API after rebase; its 24,806-byte overlay and 60,606-byte NIfTI mask downloaded through authenticated media routes with exact hashes. This is API/model evidence; browser-click and layout verification is pending Claude's UI work.

| Task | Actual artifact and result | Limits |
|---|---|---|
| Bone X-ray | Frozen pinned timm ResNet-50 + locally fitted three-class head; 225 train /61val /62test. Sample IMG000001 mirror predicted benign0.542, reference malignant. | 62.7% balanced accuracy,0.785macroAUROC on a small image-level split; missing patient/lesion IDs, source label/overlap issues. Sample and declared exact duplicates reserved. Re-encoded mirror provenance is unmatched by byte hash and disclosed. |
| Breast ultrasound | Newly fitted 28px BreastMNIST pixel logistic baseline; supplied test sample predicted malignant0.528, matches release label. | Not a deep specialist or a full-resolution clinical model; grouped patient independence unavailable. |
| Colorectal pathology patch | Newly fitted 28px PathMNIST pixel baseline; supplied test patch predicted adipose0.657, matches release label. | Tissue classification only; no whole-slide grading or prognosis. |
| Skin dermoscopy patch | Newly fitted 28px DermaMNIST pixel baseline; supplied test sample predicted actinic-keratoses/intraepithelial-carcinoma0.360, matches release label. | Not ordinary phone-photo analysis; uncalibrated scores, weak simple baseline. |
| Lung CT patch | Newly fitted 28³ NoduleMNIST3D pooled-pixel baseline; test patch predicted malignant0.524, reference benign. | Source radiologist rating classes, not pathology-confirmed cancer or whole-scan detection. |
| Brain MRI | Restored pinned MONAI SegResNet; aligned1mm T1ce,T1,T2,FLAIR NIfTI; saved mask region counts WT83,945/TC3,467/ET2,980. Fresh-process mask SHA-256 `07ebfc69e28a905824e4ea291267f2577422e0f82a223d71f45b26addccc0361` matched. | One MSD/BraTS case may overlap model training. Post-inference Dice agreement WT0.897/TC0.835/ET0.832 is a demonstration, not independent performance. Arbitrary MRI/DICOM preparation unavailable. |

## Input/reference and local execution boundaries

Registered stable IDs resolve checked bytes. Classifier references and MRI answer masks are stored separately and consulted after inference. Changing a reference leaves classifier predictions unchanged. Known training inputs are refused, validation inputs disclosed, test/unmatched provenance distinguished. Remote coordinator URLs are refused before any question/tool result is sent. A language-model answer ending at the token budget is `response_limit`, not a completed answer.

JPEG/PNG, bounded NIfTI, DICOM objects/series ZIPs and CSV/JSON can be validated. Accepting an input format does not establish a runnable specialist. Mammography, whole-CT detection, whole-slide pathology and structured blood/clinical prediction remain visibly unavailable without trained verified artifacts and matched preprocessing. BloodMNIST is normal cell imagery, not a blood-profile classifier.

Nine catalog dataset directories now contain real files: BTXRD, BreastMNIST, PathMNIST, DermaMNIST, NoduleMNIST3D, BloodMNIST, a LIDC-IDRI patient subset, a CBIS-DDSM patient subset plus reference CSVs, and one prepared MSD brain-MRI case. Catalog16models/18datasets. `/api/datasets/installed` exposes real file counts and NPZ split shapes; the old CSV-manifest selector was not the installed-data inventory.

## Verification and remaining work

New relevant fixture suites pass:14research-runtime/eligibility,5MRI,5attachment and3guidance checks. The rebased core suite discovered335tests:237passed,94optional-dependency/opt-in skips,4setup errors because Windows denied symlink creation(WinError1314) in existing path-escape fixtures. The original failure logs are preserved; no all-suite-pass claim. All eight GitHub push/PR Ubuntu checks for Python3.11–3.14 subsequently passed before merge. JavaScript syntax and whitespace checks pass. The MRI source uses LF in `.gitattributes` to retain its pinned implementation hash across a Windows rebase.

Current main3 checkpoints and all remote originals are protected. Main4 remains unpromoted. Main5v2 has437 reviewed constructed workflow rows, source-bound masks and preserved development exclusions; its input/launch ZIPs are local in Documents. It has not been submitted/trained because NPS is down. A major-checkpoint acceptance expansion must add MRI/attachment/streaming/result-kind checks, not claim an improvement from a larger rank or step count. No recurring schedule is active.

## Claude integration

Claude reports a fresh worktree frommain, another app port against the same local model, and a streaming JSON-lines endpoint. Its UI/streaming work remains separate. Preserve this branch's attachment context, loopback policy, shared `research.predict` path, reference isolation and response-limit semantics in the streaming endpoint. Do not duplicate specialist code or start another model server/training job. Detailed API contract: [Jordi-Claude-inference-handoff.md](Jordi-Claude-inference-handoff.md).

All medical samples, weights, raw observation receipts and per-file provenance stay uncommitted in this PC's Documents/data/models/runs folders. Upstream credits and source-linked154-row resource register plus supplement are saved in Documents. MIT-related research/collaborators are attributed as upstream work; institutional endorsement is not implied.

## Published and follow-up status

PR#7 is merged as `0ec2045`; no branch protection or security controls were bypassed. A live structured JSON check exposed a payload/metadata filename collision; the correction and a byte-preserving regression were included before merge and verified against the main app afterward. The earlier failed receipt stays preserved.

Main5 major-checkpointv3 now preserves the same437 reviewed training examples while expanding the bounded recipe to384steps/3000seconds and the required acceptance contract. Input ZIP138,772bytes SHA256 `b40ff0e119ec027da22c89a47b382573fc6de46ddc92577b6d4bac7a424f5292`; launch ZIP146,048bytes SHA256 `c6fe1eefc0ad15b608c2322b0e7ae8fbc60cd10904e3573f80cc33b808b1746d`. These are prepared local packages, not a trained checkpoint. Their snapshot predates the final JSON correction; refreshed source/acceptance checks after Claude's integration are mandatory before NPS execution. Current-source runtime checks must not be silently inferred from an older source-bound receipt.
