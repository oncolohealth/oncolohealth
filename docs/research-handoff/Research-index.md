# Cancer AI Research

A shared research workspace for finding cancer models and datasets, checking their evidence, using specialist models, and developing reproducible new models.

## Start here

| Document or component | What it contains |
|---|---|
| [Shared team hub](Team-hub.md) | Live editable check-ins, proposed assignments, model records, AI handoffs, and decisions |
| [Shared GitHub repository](https://github.com/oncolohealth/oncolohealth) | Private collaborator codebase, progress checklist, reports, and CI |
| [Project brief](Project-brief.md) | The concise general plan |
| [Plain-language walkthrough](Project-walkthrough.md) | A guided explanation of the architecture, training paths, and useful terms |
| [Collaborator context and working prompt](Collaboration-context.md) | Self-contained research context, public sources, actual implementation status, glossary, and eight workstreams; prepared for selective sharing |
| [Project context and next steps](Project-context.md) | Accepted decisions, actual progress, open questions, and the next milestone |
| [Weekend next actions](Weekend-next-actions.md) | Immediate team decisions, evidence requests, and a bounded path to the first defensible experiment |
| [Connected chats](Connected-chats.md) | This chat and the five identified planning/access chats |
| [Product and technical design](Cancer-platform-design.md) | Researcher workflows, architecture, model reuse, evaluation, and development stages |
| [Model research](Cancer-platform-model-research.md) | Coordinator and specialist candidates, parameter counts, reuse restrictions, and training advice |
| [Prospective dataset inventory](Dataset-inventory.md) | Published dataset counts, verified BTXRD acquisition, access considerations, and priorities |
| [BTXRD readiness and intake](BTXRD-readiness.md) | Original-release integrity and label audit, unresolved patient grouping, and offline cohort preparation |
| [BTXRD machine-readable audit](BTXRD-audit.json) | Reproduced archive, joins, duplicate/split-list, annotation-label and EXIF-tag findings without image pixels or EXIF values |
| [BTXRD evidence handoff](BTXRD-evidence-handoff.md) | A 3,746-row custodian template with measured hashes, blank grouping/reference evidence, review flags, and unsent evidence questions |
| [Shared-code integration candidate](BTXRD-shared-integration.md) | Tested local patch for the shared source snapshot, application checks, exact file hashes, and remaining review limits |
| [Baseline input and provenance review](BTXRD-baseline-input-review.md) | Reproduced cache/provenance defects, pinned publisher settings, six synthetic characterization checks, and repair requirements |
| [Model-folder provenance repair](BTXRD-model-provenance-fix.md) | Local patch for the custom-folder revision bug, nine regression tests, application hashes and compatibility with the earlier audit patch |
| [Feature-cache image binding repair](BTXRD-feature-cache-fix.md) | Local patch for stale/unbound cache refusal across four consumers, 20 synthetic tests and verified composition of all three patches |
| [NPS GB300 workflow](NPS-GB300-workflow.md) | Previously inspected access, resource presets, storage, SSH/upload guidance, and unresolved checks |
| [Executable local foundation](complete-source-handoff.zip) | Registry/routing interfaces, dataset audits, experiment planning, and feature-classifier examples |
| [Software verification](complete-source-handoff.zip) | What the synthetic tests establish and what remains untested |

## Current state

The design, research notes, and executable local foundation are saved here. The foundation passed 72 synthetic software tests with optional Pillow installed, including BTXRD intake, grouped split drafts, and a reusable read-only release audit; plain Python skips one EXIF check. The separate local OncoCopilot build proposes Gemma 4 31B as its main coordinator, accepts the actual BTXRD XLSX metadata, and gates exploratory BTXRD training; its latest suite passes 84 synthetic software tests. The original BTXRD release was downloaded, checksum-verified, and audited locally. Patient grouping and per-row diagnostic evidence remain unavailable, so no patient-independent model result is established. No pretrained weights were acquired or NPS workload launched. A current snapshot of the separate shared GitHub repository passed 106 synthetic software tests with 13 optional-dependency skips; its reported exploratory medical results have not been independently reproduced here. See the [project context](Project-context.md). The shared Google Docs team hub is editable by Sebastian, Moshe, and Inam.

The six identified chats are grouped in the app sidebar under **Cancer AI Research**. This is a sidebar section. A separate ChatGPT project has not been created: its creation controls could not be reached through the available browser. Chat membership in a ChatGPT project and cloud file uploads remain uncompleted.

This index links to the existing documents and code in place so there is one maintained copy of each. The project files are local; the chat grouping does not upload them or grant shared file context automatically.
