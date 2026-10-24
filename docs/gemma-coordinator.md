# Gemma 4 26B A4B coordinator

The selected coordinator base is **`google/gemma-4-26B-A4B-it`**, replacing the earlier 31B choice. The deployment target is an RTX 5070 Ti with 16 GB VRAM, a Ryzen 9 CPU and 32 GB system RAM. This is a model/configuration decision. No checkpoint has been downloaded, served, fine-tuned or validated here.

## Two runtime profiles

| Profile | Intended use | Model identity in API requests |
|---|---|---|
| `gemma-26b-local` (example default) | Quantized local text coordinator through an already configured llama.cpp server | `gemma-4-26b-a4b-local`, an explicit server alias that must match `/v1/models` |
| `gemma-26b-vllm` | Same selected family on separately approved large-memory compute | `google/gemma-4-26B-A4B-it` |

The local quantized starting candidate is Google's [QAT Q4_0 GGUF](https://huggingface.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf). Record its actual revision, file size and measured hash if acquisition is later authorized. The alias is not evidence of which file is loaded. A future fine-tuned export is a different artifact and must record its parent, adapter/merge identity, conversion and quantization identity; do not label an untouched QAT checkpoint as the trained model.

The old `gemma-31b-vllm` profile remains available for explicit comparisons. No fallback is automatic. Existing local `configs/coordinator.json`, environment selections and named profiles retain precedence; changing the shipped example does not overwrite a user's local configuration or start a server. Other contributor profiles and the catalog remain intact; no model evidence state or reuse permission is promoted.

## Memory and desktop limits

Google's [memory guidance](https://ai.google.dev/gemma/docs/core) lists approximate loading memory of **57.7 GB BF16 / 28.8 GB SFP8 / 14.4 GB Q4_0** for 26B A4B. Its table includes loading overhead but excludes additional context and serving memory. These are publisher estimates, not local measurements. The MoE activates about 4B parameters per token, but all 26B parameters still need memory for fast access. [NVIDIA specifies 16 GB](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/) for the desktop 5070 Ti.

Q4_0 therefore leaves a narrow GPU margin. A 32 GB RAM machine may support partial CPU offload, but usable RAM, the exact Ryzen 9, operating system, display load and backend matter. Start with one request slot, a 4096-token total context and a 1024-token response cap; these are conservative trial settings, not a measured fit or speed guarantee. The prompt, tool schemas, results and generated tokens all occupy that context. Increase limits only after measuring actual GPU/RAM headroom. The [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) exposes automatic layer placement and `--n-cpu-moe N` for CPU expert placement; choose offload from actual measurements rather than assuming 4B memory use. Latency may increase. BF16 and fine-tuning do not inherit the Q4 inference estimate.

## Prepared connection, no execution performed

The example speaks the existing OpenAI-compatible API. `CW_GEMMA_LOCAL_BASE_URL` optionally selects the local endpoint; `CW_GEMMA_LOCAL_API_KEY` supplies an existing key if configured. It sends the explicit alias, a bounded output cap and `chat_template_kwargs.enable_thinking: true`. General reasoning, coding and tool-result feedback remain in the existing coordinator; changing a profile proves none of the model's capabilities.

After separate permission for actual model loading, an existing compatible llama.cpp build can be configured using an already-local authorized file, with the following **unexecuted example**. `GEMMA_GGUF` must identify that reviewed file; the example has no acquisition flag:

```sh
llama-server --model "$GEMMA_GGUF" --offline \
  --alias gemma-4-26b-a4b-local --jinja \
  --ctx-size 4096 --parallel 1 --n-gpu-layers auto \
  --chat-template-kwargs '{"enable_thinking":true}' \
  --host 127.0.0.1 --port 8080
```

Confirm the installed build supports these flags and the exact Gemma 4 template before using it. Keep localhost binding unless a separately reviewed access design is required. [llama.cpp's function-calling documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md) requires Jinja tool formatting; request compatibility must be tested on the exact quantized model/build. The [vLLM Gemma recipe](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html) documents the `gemma4` reasoning/tool parsers, automatic tool choice and matching chat template for the large-memory profile. No launcher, dependency installation, endpoint ping or model request ran during this change.

## Acceptance before relying on the model

1. Record exact model/quantization/template/runtime identities, GPU/CPU/RAM and free storage. Measure peak GPU/RAM and latency at the trial context. Stop on OOM, swapping or a malformed/unavailable parser; retain logs and cancel cleanly. No throughput estimate is established here.
2. On an explicitly authorized local endpoint, verify one ordinary reasoning answer, one coding task, a nested tool argument round trip, faithful result feedback, unavailable/malformed-tool refusal, and source-grounded citations. Use only synthetic/public inputs. A scripted fixture cannot verify a Gemma parser or reasoning quality.
3. Run the existing bounded coordinator development evaluation under explicit model-execution scope, then human-review answers against the observed tool results. Freeze a separate unseen workflow suite before measuring generalization. Evaluate the actual quantized deployment artifact, as well as any trained parent. Keep errors and refusals in the report.
4. Treat training as a later decision based on measured recurring failures. Review training data rights, teacher-output/distillation permission, retention of general reasoning/coding and specialist behavior, and a bounded resource/checkpoint/cancellation plan before any SFT/LoRA or cluster job. The retained 31B profile is not teacher authorization.

Patient/lesion mapping, per-row diagnostic references, contradictory-label adjudication and protocol review remain unresolved for BTXRD. Coordinator configuration does not establish cancer accuracy or authorize medical execution.

## Offline verification

Profile construction/default parsing, endpoint environment override and preservation of the existing provider fields pass. The combined suite discovers 253 tests: 213 pass and 40 optional ML checks skip. All eight existing scripted coordinator development cases pass; trace rate and reasoning-quality score remain null. Catalog: 16 model and 14 dataset records valid; whitespace check passes. No model, endpoint ping or parser execution is represented by these software results.

## Claude work inspected

Claude's visible existing conversation reports an isolated `oncomodel` workspace with 11 tools, an HTTP service and rewards tested against recorded responses (76 tests reported), plus a training recipe and a 26B A4B specification change. These remain **Claude-reported**: those container source files and test execution were not independently obtained here. The visible activity stops at checking browser tabs for cluster access and shows an account usage limit. It does not establish any cluster workload or model acquisition. No message was sent to Claude and no usage credits were purchased.

The shared checkout separately contains contributor commit `aedd36aa14e3c35f3ea22199e3b5a165d9bb4650` on `d/pubmed-retrieval`: opt-in PubMed search and citation-ID checking, with fake-response tests and no successful live NCBI call claimed. That work is preserved; this change uses a linked Git review worktree based on `a7f8ff4` so it neither switches nor overwrites the contributor's checked-out branch. No second application is created. Review the existing source and evidence contracts before selecting any useful Claude component for integration.
