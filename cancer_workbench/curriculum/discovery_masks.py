"""Assistant masks for the authenticated Gemma 4 template, including tool lookahead.

The renderer is preserved from the verified main3 training/coordinator/masking.py.
The CLI below checks new discovery candidates with the exact local parent tokenizer.
"""
import hashlib
import re

TEMPLATE_SHA256 = "ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4"
CONTROL = re.compile(r"<\|[^>]*>|<[^<>]*\|>")
BOUNDARY = re.compile(r"<\|turn>(system|user|model)\n|<turn\|>\n|<\|tool_response>|<tool_response\|>")


def reject_control_input(value):
    """Untrusted text cannot introduce template delimiters and spoof a loss span."""
    if isinstance(value, str) and CONTROL.search(value):
        raise ValueError("Reserved template control token in input")
    if isinstance(value, dict):
        for key, item in value.items():
            reject_control_input(key); reject_control_input(item)
    if isinstance(value, list):
        for item in value:
            reject_control_input(item)


def render_assistant_spans(tokenizer, messages, tools=None, *, thinking_mode):
    """Parse a complete pinned render; independently rendered prefixes can differ.

    Model headers are context. Assistant text, reasoning, calls and turn endings
    receive loss; complete tool-response blocks (including delimiters) never do.
    Only explicit text conversations admitted by preflight are supported.
    """
    if thinking_mode not in {"thinking", "nonthinking"}:
        raise ValueError("An explicit thinking or nonthinking mode is required")
    if not messages or messages[0].get("role") == "assistant":
        raise ValueError("A training conversation must start with a non-assistant turn")
    template = tokenizer.chat_template
    if not isinstance(template, str) or hashlib.sha256(template.encode()).hexdigest() != TEMPLATE_SHA256:
        raise ValueError("Unreviewed chat template; pinned Gemma template required")
    reject_control_input(messages); reject_control_input(tools)
    if thinking_mode == "nonthinking" and any(m.get("reasoning") or m.get("reasoning_content") for m in messages):
        raise ValueError("Nonthinking corpus must not contain reasoning fields")
    full = tokenizer.apply_chat_template(
        messages, tools=tools, tokenize=False, add_generation_prompt=False,
        enable_thinking=thinking_mode == "thinking")
    spans, role, start, in_result, results = [], None, None, False, 0
    for match in BOUNDARY.finditer(full):
        token = match.group()
        if match.group(1):
            if role is not None or in_result:
                raise ValueError("Nested or unclosed turn in template render")
            role = match.group(1)
            start = match.end() if role == "model" else None
        elif token == "<|tool_response>":
            if role != "model" or in_result or start is None:
                raise ValueError("Unexpected tool response in template render")
            if start < match.start(): spans.append((start, match.start()))
            start, in_result = None, True
            results += 1
        elif token == "<tool_response|>":
            if not in_result or role != "model":
                raise ValueError("Unmatched tool response ending")
            start, in_result = match.end(), False
        else:
            if role is None or in_result:
                raise ValueError("Unexpected turn ending")
            if role == "model" and start is not None and start < match.end():
                spans.append((start, match.end()))
            role, start = None, None
    if role is not None or in_result or not spans:
        raise ValueError("Incomplete render or no supervised assistant spans")
    if results != sum(m.get("role") == "tool" for m in messages):
        raise ValueError("Tool result coverage differs from source messages")
    if full.count("<|tool_call>") != sum(len(m.get("tool_calls") or []) for m in messages):
        raise ValueError("Tool call coverage differs from source messages")
    return full, spans


def encode(tokenizer, row, max_length=4096):
    if not tokenizer.is_fast:
        raise ValueError("A fast local tokenizer with inspectable offsets is required")
    if any(m.get("reasoning") or m.get("reasoning_content") or m.get("thinking") for m in row["messages"]):
        raise ValueError("Discovery examples must not contain hidden reasoning")
    text, spans = render_assistant_spans(tokenizer, row["messages"], row["tools"], thinking_mode="nonthinking")
    enc = tokenizer(text, return_offsets_mapping=True, add_special_tokens=False, truncation=False)
    if len(enc["input_ids"]) > max_length:
        raise ValueError("Overlength trajectory refused; never truncate a tool trace")
    if len(enc["input_ids"]) != len(enc["offset_mapping"]):
        raise ValueError("Tokenizer offsets mismatch")
    labels = []
    for token, (start, end) in zip(enc["input_ids"], enc["offset_mapping"]):
        if not 0 <= start <= end <= len(text):
            raise ValueError("Invalid tokenizer offsets")
        overlaps = [(a, b) for a, b in spans if end > a and start < b]
        if overlaps and not any(start >= a and end <= b for a, b in overlaps):
            raise ValueError("Token crosses assistant boundary")
        labels.append(token if end > start and overlaps else -100)
    if not any(t != -100 for t in labels):
        raise ValueError("No supervised assistant tokens")
    return {"input_ids": enc["input_ids"], "labels": labels}


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True, trust_remote_code=False)
    rows = [json.loads(line) for line in args.data.read_text(encoding="utf-8").splitlines() if line.strip()]
    checked = []
    for row in rows:
        x = encode(tokenizer, row)
        checked.append({"case_id": row["case_id"], "tokens": len(x["input_ids"]), "supervised_tokens": sum(t != -100 for t in x["labels"])})
    result = {"state": "TOKEN_MASKS_VERIFIED_CONTENT_RIGHTS_ADMISSION_PENDING", "rows": checked,
              "template_sha256": TEMPLATE_SHA256, "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
              "truncation": False, "optimizer_run": False}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
