"""Offline software demo. Every successful prediction is explicitly SYNTHETIC.

Run from the repo root: python3 scripts/demo_observed_results.py
No network, medical images, model weights, credentials or ML packages needed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cancer_workbench.adapters import SYNTHETIC_MODEL_RECORD, SyntheticThresholdAdapter
from cancer_workbench.coordinator import ChatResult, ScriptedProvider, ToolCall, default_toolbox, run_turn
from cancer_workbench.registry import load_catalog


def main() -> int:
    catalog = load_catalog()
    box = default_toolbox(catalog, {"synthetic-threshold": SyntheticThresholdAdapter()},
                          extra_models=[SYNTHETIC_MODEL_RECORD])
    requests = [
        ("catalog_lookup", "get_record", {"id": "rad-dino"}),
        ("unsupported_medical_execution", "run_specialist", {
            "model_id": "monai-brats-mri-segmentation", "task": "brain_tumor_segmentation",
            "modality": "mri", "anatomy": "brain", "inputs": {}}),
        ("invalid_tool_arguments", "route_models", {
            "task": "feature_extraction", "modality": "xray", "anatomy": "bone", "channels": True}),
        ("synthetic_success", "run_specialist", {
            "model_id": "synthetic-threshold-model", "task": "synthetic_classification",
            "modality": "synthetic", "anatomy": "any", "inputs": {"signal": 0.8}}),
    ]
    cases = [{"case": label, "tool": tool, "observed": box.call(tool, json.dumps(args))}
             for label, tool, args in requests]
    failure_box = default_toolbox(catalog, {"synthetic-threshold": SyntheticThresholdAdapter(fail=True)},
                                  extra_models=[SYNTHETIC_MODEL_RECORD])
    cases.append({"case": "synthetic_execution_failure", "tool": "run_specialist",
                  "observed": failure_box.call("run_specialist", json.dumps(requests[-1][2]))})
    provider = ScriptedProvider([
        ChatResult(content=None, tool_calls=[ToolCall("lookup", "get_record", '{"id":"rad-dino"}')],
                   finish_reason="tool_calls", model="scripted", profile="offline-demo"),
        ChatResult(content="The catalog record is available. It does not establish eligibility to execute the model.",
                   tool_calls=[], finish_reason="stop", model="scripted", profile="offline-demo"),
    ])
    turn = run_turn(provider, box, "Show the RAD-DINO record and its evidence state.")
    # Assert the behavior promised by the demo instead of printing a success
    # narrative when an integration regression changes the actual outputs.
    assert cases[1]["observed"]["result"]["status"] == "rejected"
    assert "error" in cases[2]["observed"]
    assert cases[3]["observed"]["result"]["status"] == "ok"
    assert cases[3]["observed"]["result"]["synthetic"] is True
    assert cases[4]["observed"]["result"]["status"] == "failed"
    observed_message = json.loads(provider.calls[1]["messages"][-1]["content"])
    assert observed_message == turn.steps[0]["tool_calls"][0]["observed"]
    print(json.dumps({"scope": "SYNTHETIC SOFTWARE DEMO. No live LLM or medical inference.",
                      "catalog": {"models": len(catalog.models), "datasets": len(catalog.datasets)},
                      "cases": cases, "scripted_coordinator": {
                          "observed_result_fed_back": True, "steps": turn.steps, "final": turn.final}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
