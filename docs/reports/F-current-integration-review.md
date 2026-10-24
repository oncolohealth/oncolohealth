# Current-source integration and independent processor checks

Prepared by Inam Qasimi, 2026-10-24. Software integration and review evidence;
no clinical validation or new medical experiment.

## Source and attribution

`codex/research-integration-followup` combines Inam's published-evidence panel
(`7405810`), the published identity guard (`a7f8ff4`), Gemma profile selection
(`3e369d6`) and experiment execution-review summary (`072bac2`) with main through
`94f99eb9b42829961a1c767be51b417735ec9ccf`. The pre-report/test integration
commit is `50f024f`; the final review commit is recorded in the delivery metadata
and PR. The corresponding draft PRs #2–4 remain separate pending reviews.
Their inclusion here is an integration candidate, not approval of those changes.

Original commits and authors are retained. Sebastian's processor binding,
rounding, full-resolution JPEG, subset acquisition and network fixes come from
main. Only appended progress records conflicted during these merges; both sides
were retained. The user's BETA_TEST checkout and shared main were not modified
by this work. Canonical source remains the repository root.

## Independent checks completed here

An isolated CPU environment now satisfies all eight exact `ml` dependency pins:
NumPy 2.5.3, Pillow 12.3.0, Torch 2.14.1+cpu, Torchvision 0.29.1+cpu, timm 1.0.30,
transformers 5.19.0, safetensors 0.8.0 and scikit-learn 1.9.1. The `+cpu` builds
satisfy the declared public-version equality pins. Torch/Torchvision wheels came
from the official CPU index; their SHA-256 hashes matched that index. Actual
Dinov2Model, BitImageProcessor, timm and Torchvision imports succeed. This closes
the earlier local optional-dependency gap without changing the user's global
Python installation. CUDA is unavailable in this runtime.

- Full suite on the combined source: **305 discovered, 301 pass, four skips**.
  The skips are the four opt-in actual-weight tests; they were not enabled here.
- System Python: **305 discovered, 257 pass, 48 optional-ML/weight skips**.
- Catalog: **16 models, 17 datasets** valid after Sebastian's subset additions.
- JavaScript syntax and Git whitespace checks pass.
- All **eight scripted coordinator smoke cases** pass against the current
  catalog. These are scripted tool traces; reasoning/quality scores remain null.

No actual model weights were downloaded or loaded here. A public RAD-DINO
processor JSON was fetched from the catalog's pinned revision, with SHA-256
`c537fc995c30e2353f07253899618d60e9eae3d5f82473778602c007c6523b56`, matching
Sebastian's recorded file. This is not weight authentication. Sebastian's own
MPS/CPU weight loading and 16-image timing record remains attributed to him in
`E-model-runtime-check.md`; it was not independently reproduced on this machine.

## Three independent preprocessing regressions

`tests/test_processor_equivalence.py` compares native-crop output with actual
timm/transformers implementations using synthetic configurations and six
invented grayscale images. Fixtures cover both orientations, odd margins,
square images, upsampling, sharp edges and a 1600×1100 JPEG. No network, weights
or medical images are used by these tests.

1. ResNet-50 agrees with timm within `1e-6` after normalization.
2. RAD-DINO agrees with the transformers PIL backend within 1.01 gray levels
   before normalization, on these fixtures.
3. The default transformers Torchvision backend differs by up to two gray
   levels on a sharp synthetic edge; the test bounds this fixture set at 2.01
   levels. This is a backend/quantization observation, not universal or exact
   publisher equivalence.

The initial one-gray-level bound for the default backend was too strict on the
sharp-edge fixture. Testing an alternative PIL conversion did not remove the
difference; that experimental adapter edit was reverted. No production encoder
change is included in this follow-up. The retained tests document the actual
comparison scope instead of claiming an unmeasured numerical identity.

As a characterization, the same three final tests were run against `66562ea`
(before the full-resolution native-crop JPEG fix). All three deliberately fail
on the large JPEG, while the current source passes. The separately labeled
expected-failure log demonstrates that this coverage detects the draft-decoding
regression; it is not a failure of the current suite.

## Browser and handoff

The evidence panel and experiment review/history coexist in the merged UI.
Synthetic preview/save/reload/reopen was exercised at `903f1d2`. After updating
to `50f024f` and restarting the backend, the evidence panel loads and the same
persisted draft reopens with its original source revision, saved-snapshot warning,
execution unauthorized and dispatch unavailable. No console warnings/errors
were observed. Current desktop screenshots accompany the delivery. The earlier
390×844 dark/light evidence-panel checks are a separate preceding checkpoint;
they are not a fresh full-app mobile pass after the acquisition changes.

Blank CSV contents are verified through the API/library tests. A completed
browser download was not independently inspected. No medical archive was read
by this browser pass; temporary data/model roots held only synthetic QA records.

Two new handoff documents reduce the remaining coordination work:

- `A-custodian-request-draft.md`: an **unsent**, unaddressed request for genuine
  pseudonymous grouping/reference evidence and clarification of source conflicts.
- `F-scientific-review-decisions.md`: a decision worksheet for a named reviewer,
  distinguishing proposed reporting metrics from the implemented tuning objective.

## Remaining decisions

Team review/merge of this integration and the pending PR chain remains open.
For patient-independent BTXRD evaluation, authentic grouping and per-row
diagnostic references remain unavailable; similarity does not supply them.
A named scientific reviewer must settle the endpoint, evaluation unit, exclusions,
split and primary metric. A live coordinator needs an approved real endpoint and
an actual tool round trip; the 26B profile is configuration only. Any new medical
extraction/training or cloud workload needs its specific reviewed scope/resources.
None was dispatched here, and no external outreach was sent.
