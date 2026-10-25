# OncoloHealth: backend contract for Claude's interface update

Jordi asked Claude to own the interface. Codex is leaving the shared HTML, CSS and JavaScript alone and implementing/testing the local execution path. Preserve the existing source edits from all contributors.

The main app is `http://127.0.0.1:8765`. Its verified Python runtime is `K:\oncolohealth-runtime\research-venv\Scripts\python.exe`, repository `K:\oncolohealth`. Launch with `C:\Users\Jordi nieves\Documents\OncoloHealth-start-local-app.ps1`. The native Gemma server stays on `127.0.0.1:8080`; do not restart or replace its protected main3 checkpoint for a UI change.

## Normal user flow: keep it inside Assistant

Put an attachment control, input preview and plain-language input/task choice in the chat composer. Do not make a user copy an input ID, choose a technical model name or move to another screen. The Research page remains an optional direct/debug workflow.

1. `POST /api/research/upload` with `{name, data}` (`data` is base64), using the existing `X-CW-Token`. Returns `{id, format, shape, sha256, ...}`. JPEG/PNG, NIfTI, DICOM/series ZIP and CSV/JSON are validated. The limit is 128 MB. Accepted upload **does not** imply an installed model; show unsupported tasks honestly.
2. `GET /api/research` returns actual verified models, uploaded inputs, reserved examples (`samples`) and exact unavailable-task blockers. Render a plain task label; keep model IDs under details. The initial five models are bone X-ray, breast ultrasound patch, colorectal tissue patch, dermoscopy patch and 3D CT nodule patch. Four use small 28-pixel logistic baselines, not deep clinical specialists. Bone uses frozen ResNet-50 plus a trained head.
3. `GET /api/research/preview/<input_id>` returns validated input metadata and optional relative `media`. Display media at `/media/<media>?t=<CW token>`. Volumes receive a voxel-index preview, not an inferred clinical orientation.
4. `POST /api/coordinator/ask` supports `attachments: [{input_id, workflow_id}]` alongside the existing question/profiles/histories/synthetic_demo fields. `workflow_id` is the selected model ID under the hood. Empty text plus a selected attachment is allowed. The server resolves the stable ID, validates the selected task/format/preprocessing, and adds grounded execution context. It refuses a remote coordinator endpoint for attachments. A real `run_specialist` call processes actual bytes; no text/filename/label substitution.
5. Show the actual specialist output in the same conversation: prediction and class scores, or segmentation counts/overlay when a segmentation backend is available, execution time, and any separate reference comparison. Keep the complete envelope under expandable details. Failures stay visible. `steps[].finish_reason` is preserved and `stopped="response_limit"` means the assistant answer is incomplete, even when there is partial text. Do not style that as a completed answer.

## Direct path and separate references

- `POST /api/research/run`: `{model_id,input_id}` returns a saved observed receipt, including failed runs. `GET /api/research/results` lists recent receipts.
- `POST /api/research/reference`: classification references use `{model_id,input_id,label,source}`. Labels are saved outside model inputs and read only after inference. Changing the reference does not change prediction; this was tested through the actual app endpoints.
- Do not include reference labels, expected classes or diagnosis-bearing answer keys in the inference request, attachment context or a model's feature vector.
- The existing re-encoded BTXRD mirror has legacy ID `62c12500810db32f`; the full SHA-ID after import is `62c12500810db32fb99f564c0df6f3576a0875ba3e6cf474b5ad0f880f94b287`. Its observed prediction was **benign**, while the separately stored dataset reference is **malignant**. Display the disagreement; do not fix it by substituting the label.
- The CT patch example also disagreed with its reference. Ultrasound, tissue and dermoscopy example agreement is not medical validation. Every sample comes from reserved test data; exact duplicate checks and known grouping limitations are recorded.

## Dataset page: fix the CSV-only blind spot

`GET /api/datasets/installed` returns actual on-PC files, byte totals, source/license information, NPZ array shapes (including train/val/test image counts), and CSV manifests. At this checkpoint **eight dataset directories contain real files**: BTXRD, BreastMNIST, PathMNIST, DermaMNIST, NoduleMNIST3D, one LIDC-IDRI patient, one CBIS-DDSM patient, and BloodMNIST. The catalog has 16 models and 18 datasets. The prior `/api/manifests` dropdown only sees CSVs; it is not the installed-dataset inventory.

Show downloaded vs runnable independently. BloodMNIST contains normal cell images, not structured CBC profiles or a leukemia classifier. A mammography/CT patient subset is data, not a trained detector. MRI integration is being verified separately; use current `/api/research` state rather than assuming every source file is ready.

## Verification boundary

The actual backend app endpoints have run all five initial specialists and five Gemma-driven specialist calls, with saved receipts and reference comparisons. Initial bone prose was truncated; a compact tool output and explicit response-limit reporting now address that serving issue, pending fresh live checks. Browser control still reports disabled in Work settings, so Codex has **not** verified clicks, layout or screenshots. Claude should perform that visible interface check and report any failure with the exact request/console response.

API authentication, loopback binding and path/identity checks stay in place. Inputs and inference stay local. NPS is only for training/evaluation/downloads. Keep the working Gemma checkpoint, previous failures and remote files. Do not claim medical validation or complete support based on a button/configuration alone.

## Latest integration checkpoint

The branch is rebased onto main808dcc6, retaining main's no-limit storage implementation and peach theme. The user-specific200GB environment setting can still opt into a cap. Claude owns the separate-worktree UI and JSON-lines streaming endpoint. Codex owns this specialist/data/attachment backend. For streaming, share the attachment validation and loopback guard before provider invocation, run the same specialist handler, retain real step observations, and distinguish response_limit from answered. Do not send labels or raw pixels to a remote LLM. Six model-driven attachment paths now have actual local HTTP evidence, including MRI segmentation and authenticated mask/overlay download. Nine datasets are installed; use `/api/datasets/installed`. New classification/segmentation output kinds and evaluation_eligibility must render honestly.

The source branch contains no trained weights or medical sample files. Documentation/checkpoint claims are backend/API/model observations; visible UX remains unverified by Codex. The previousMRIverification failure caused by WindowsLF→CRLF rebase conversion is preserved; LF-normalized source matches its original verified checksum and a full post-rebase MRI attachment run succeeded.
