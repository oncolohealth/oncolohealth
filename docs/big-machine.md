# Coordinator runtime guidance

The selected coordinator is now Gemma 4 26B A4B. Read [the current Gemma desktop/large-memory profiles and acceptance checks](gemma-coordinator.md). The default example targets quantized local inference; larger-memory serving, tuning and cluster workloads require separate verification and execution scope.

The following Qwen material is a historical optional-provider guide. It does not describe the selected coordinator or authorize acquisition or execution.

# Running the Qwen coordinator on the GPU machine

The laptop develops against any OpenAI-compatible endpoint. The GPU machine serves Qwen.

## 1. Pick the weights from available VRAM

Check with `nvidia-smi --query-gpu=name,memory.total --format=csv`.

| Variant | Catalog id | Weights | Fits (approx.) |
|---|---|---|---|
| BF16 | `qwen3.8-27b` | 55.6 GB | one 80 GB GPU, or 2+ GPUs with tensor parallel |
| FP8 (official) | `qwen3.8-27b-fp8` | 30.9 GB | one 40–48 GB GPU at modest context; FP8 kernels need a recent GPU generation |

KV cache for long contexts needs extra memory on top of the weights. Limit the context length (`--max-model-len`) to what the workflows need. Before relying on FP8, compare it against BF16 on the coordinator evaluation set (Workstream D).

## 2. Fetch (optional: vLLM/SGLang can also pull from the Hub directly)

```fish
set -x CW_MODELS_DIR /path/with/space
python -m cancer_workbench fetch plan qwen3.8-27b-fp8
python -m cancer_workbench fetch get qwen3.8-27b-fp8 --allow-big
```

The fetch is pinned to the catalog revision, and every shard is verified against its Hub sha256.

## 3. Serve

Follow the official recipe for the exact flags, including the tool-call parser. Don't guess them:

- vLLM: https://recipes.vllm.ai/Qwen/Qwen3.8-27B
- SGLang: https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.8-27B

Enable tool calling on the server and set an API key if the port is reachable by anyone else.

## 4. Point the coordinator at it

```fish
cp configs/coordinator.example.json configs/coordinator.json   # then edit
set -x CW_QWEN_BASE_URL http://<gpu-host>:8000/v1
set -x CW_QWEN_API_KEY <key>
python -m cancer_workbench coordinator ping qwen-fp8-vllm
python -m cancer_workbench coordinator ask "Which models could segment a 4-sequence brain MRI?" --profile qwen-fp8-vllm --profile qwen-fp8-no-thinking
```

Add more profiles for other models or servers; each one is just `base_url` + `model`. Repeat `--profile` to compare models on the same question.
