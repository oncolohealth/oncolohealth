"""Reviewed tool-use examples for possible coordinator adaptation. Owner: Workstream D. STUB.

export_curriculum(records) -> list[dict]
    Export only records marked reviewed whose tool results were OBSERVED (e.g.
    TurnRecord.steps from coordinator.loop), pairing every call with its result
    and validating arguments against the tool schema. Include rejections,
    failures and abstentions. Never include invented results or hidden reasoning.
"""
