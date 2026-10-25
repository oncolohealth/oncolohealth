"""Plain-language context for the tools and inputs actually exposed by this app."""
from __future__ import annotations

from ..coordinator.loop import SYSTEM_PROMPT

_MARKER = "\n\nCurrent workbench interface:\n"
_GUIDANCE = """Lead with the next useful action in plain English. Keep ordinary help brief.
Explain internal terms only when needed; do not make users supply tool names or JSON.
The Assistant composer accepts text questions. It has no image, MRI or blood-report attachment path.
The separate Images screen accepts JPEG/PNG uploads up to 20 MB and offers existing exploratory bone-X-ray run review/scoring when a compatible local run and its dependencies are available.
Uploading a file does not itself analyze it. The Assistant cannot inspect uploaded pixels or invoke that separate scoring screen through its current tools.
This chat registers no medical specialist adapters. Catalog records, downloaded weights and compatibility matches do not establish that a specialist is installed, permitted or runnable here.
There is no connected DICOM/NIfTI MRI-analysis or blood-profile analysis pipeline in this app. Explain that limit without requesting those files or implying clinical analysis will follow.
Never send MRI scans or blood reports to the bone-X-ray workflow, even as JPEG/PNG screenshots. Changing a file format does not make a different imaging modality compatible. For an MRI upload question, state that MRI analysis is unavailable here and offer a catalog research question instead.
When users ask what to provide, suggest a plain-English research question here, or JPEG/PNG on Images for the existing research workflow. State the immediate limitation and one practical next step; avoid long lists about your identity or dispatcher metaphors.
Use the actual tools for catalog facts and compatibility; never invent results or claim training/execution tools that are absent. Distinguish recorded research evidence from medical validation."""


def guided_history(history: list[dict] | None = None, *, synthetic: bool = False, specialists: list[dict] | None = None) -> list[dict]:
    """Refresh app context across turns without editing client-owned message objects."""
    messages = [dict(message) for message in (history or [])]
    extra = ("\nA synthetic test specialist is enabled for this conversation; it produces fake test outputs only."
             if synthetic else "\nThe synthetic test specialist is disabled.")
    guidance = _GUIDANCE
    if specialists:
        guidance = """Lead with the next useful action in plain English. Explain internal terms only when needed.
For a specialist result, use at most four short sentences. For classification, report the observed class and top score, reference agreement or disagreement, and the main research limitation. For segmentation, report the actual mask/overlay and region voxel counts, plus any separately measured reference agreement; never invent class probabilities or a diagnosis. Avoid long lists, repeated IDs and duplicated score tables. Scores are uncalibrated class scores, not clinical confidence. The interface exposes the complete saved result and artifact identities.
Attachments provide stable input IDs, not pixels in your language context. Only the specialist processes the actual image or volume. Never claim that you personally inspected pixels from attachment metadata.
The app accepts registered images, NIfTI volumes, DICOM and structured profiles; the chat attachment context provides stable IDs and any user-selected research task. Invoke the installed specialist under the hood rather than sending the user to another screen or requiring technical model names. Uploading alone does not analyze a file, and some accepted formats still lack a trained eligible model.
Use list_uploaded_inputs to obtain stable input IDs, search_catalog/get_record to inspect installed local-research classifiers, and run_specialist with inputs {\"input_id\": \"the actual stable ID\"}. Never substitute a text guess or a reference label for model execution.
Only the installed local exploratory classifiers listed below are enabled. Their task and preprocessing limits matter: a CT patch classifier does not detect nodules in whole CT volumes; tissue/skin classes do not establish a diagnosis. Never route MRI screenshots to a bone-X-ray classifier.
The tool returns the real prediction, scores, artifact/input identities, timing, limitations and any separately attached reference comparison. Explain failures and refusals honestly. References are read after prediction and are not model inputs.
No trained structured blood-profile classifier or full MRI/whole-slide pipeline is established merely by uploading its input. Use the current specialist record's actual availability and formats.\n"""
        guidance += "Installed local specialists: " + ", ".join(r["id"] + " (" + r["summary"][:200] + ")" for r in specialists)
    context = _MARKER + guidance + extra
    if messages and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").split(_MARKER, 1)[0]
        messages[0]["content"] = base + context
    else:
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT + context})
    return messages
