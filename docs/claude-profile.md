# Hosted Claude research profile

Inam Qasimi · October 24, 2026

The example configuration contains `claude-research`. It uses the existing
OpenAI-compatible HTTP provider, not a native Anthropic SDK. The default profile
is unchanged. Its tool-call wire format follows the publisher's documented
[compatibility endpoint](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk).
The current example model is `claude-opus-5-5`. Confirm account access before a
live test. This preparation is **not live-verified Claude integration** or
evidence of sponsor eligibility.

Set `ANTHROPIC_API_KEY` in the process environment through your normal secret
manager. Do not put its value into a profile JSON, screenshot, shell history or
committed file. `require_api_key` stops requests when it is absent. For keys
requiring workspace selection, set `ANTHROPIC_WORKSPACE_ID`. The profile's
`extra_headers_env` maps header names to environment-variable names and never
stores their values. A workspace-scoped key can omit this optional header.

The profile sets a bounded `max_tokens` and omits model-specific body options,
temperature and top-p. Compatibility does not guarantee strict tool-schema
conformance. Local toolbox validation remains active. Cross-origin redirects
are refused before credentials can be forwarded. This provider supports the
current synchronous chat/tool workflow, not the full native Claude API.

## Verified locally

Seven tests in `tests/test_hosted_profile.py` cover a two-turn function/tool
round trip against a fake local server, required-key behavior, optional workspace
headers, invalid header values, profile edit/save preservation and redirect
boundaries. They use invented test credentials. The integrated checkpoint is
155 tests discovered, 153 passed and two Torch-dependent skips.

No real key was inspected or transmitted. No hosted request or medical inference
was performed. Next, run the documented coordinator evaluation with an explicitly
selected live profile when credentials and API usage are authorized. Review the
observed trace and final answers separately before making a reasoning claim.
