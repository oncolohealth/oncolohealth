# Run OncoloHealth on your own machine

This gets the workbench, the local assistant and the research specialists running on one PC, the way the demo machine runs them. Everything stays on the machine: the app refuses model servers that aren't on `localhost`.

## What you need

| | Minimum | Demo machine |
|---|---|---|
| OS | Windows 10/11, Linux or macOS | Windows 10 |
| Python | 3.11+ (3.12 recommended) | 3.12 via `uv` |
| GPU, for the local assistant | 16 GB VRAM (NVIDIA, CUDA 12.8+ driver) | RTX 5070 Ti, 16 GB |
| RAM | 32 GB | 32 GB |
| Disk | ~80 GB free for models and the starter datasets | 2 TB data drive |

Without a GPU you can still use the catalog, audits, datasets screens and the specialists (they run on CPU); only the assistant chat needs the model server.

## 1. Get the code and a Python environment

```bash
git clone https://github.com/oncolohealth/oncolohealth.git
cd oncolohealth
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[ml,imaging]"
```

On Windows, put the cache on a roomy drive first: `set UV_CACHE_DIR=K:\.uv-cache`. Check the core install with `.venv/bin/python -m unittest discover -s tests` (Windows: `.venv\Scripts\python`). Four symlink tests error on Windows unless Developer Mode is on (WinError 1314); that is expected.

## 2. Data and specialist models

- Starter datasets and open weights: `python -m cancer_workbench fetch list`, then `python -m cancer_workbench fetch get <id>`. The default storage is unlimited; set `CW_STORAGE_BUDGET_GB` to cap it.
- The trained research specialists (bone X-ray head, MedMNIST baselines, restored MONAI brain-MRI and lung-CT bundles) and their reserved samples live under `models/` and `data/`. They are not in git. Copy them from the demo machine (`models/research-specialists/`, `models/monai-*`, `data/research-*`) or ask Codex's runbook in `docs/reports/Jordi-local-inference-checkpoint.md` for how each was produced.
- Keep data, models and runs outside the checkout if you like: `CW_DATA_DIR`, `CW_MODELS_DIR`, `CW_RUNS_DIR`.

## 3. The local assistant (Gemma 4 26B + the OncoloHealth adapter)

1. **Model server:** an official llama.cpp release built for your CUDA version (the demo uses `b11870`, `win-cuda-13.4-x64` plus its `cudart` zip).
2. **Base model:** Google's `gemma-4-26B-A4B-it`, quantized to Q4_K_M GGUF (about 16.8 GB). The exact files, hashes and conversion steps are in `docs/reports/Jordi-local-inference-checkpoint.md`.
3. **Adapter:** the main3 LoRA, `oncolo-adapter-main3-F32.gguf`, from the team (it is not in git).
4. **Start it** on port 8080 with the alias the app expects:

   ```bash
   llama-server --model gemma-4-26B-A4B-it-4d7ae498-Q4_K_M.gguf --lora oncolo-adapter-main3-F32.gguf \
     --alias oncolo-main3-gemma4-26b-q4km --host 127.0.0.1 --port 8080 --ctx-size 8192 --parallel 1 \
     --jinja --gpu-layers all --n-cpu-moe 8 --fit on --fit-target 1536
   ```

   `--n-cpu-moe 8` keeps 8 expert layers on the CPU so the model fits in 16 GB. With more VRAM, lower it, and consider `--ctx-size 16384` for longer chats.

5. **Point the app at it:** copy `configs/coordinator.example.json` to `configs/coordinator.json` (gitignored) and add:

   ```json
   "oncolo-main3-local": {
     "type": "openai_compatible", "base_url": "http://127.0.0.1:8080/v1",
     "model": "oncolo-main3-gemma4-26b-q4km", "timeout_s": 600, "supports_tools": true,
     "default_params": {"temperature": 0, "max_tokens": 1024},
     "extra_body": {"chat_template_kwargs": {"enable_thinking": false}}
   }
   ```

   and set `"default_profile": "oncolo-main3-local"`.

## 4. Run the app

```bash
python -X utf8 -m cancer_workbench app --port 8765 --no-browser
```

Open http://127.0.0.1:8765. The Assistant's model picker should say **Ready**. If it says **Not reachable**, the model server isn't up on 8080 (it may also just be busy: it serves one request at a time).

## 5. Check it works

- **Assistant:** click **Guided demo** on the welcome screen; four steps run against the real model and specialists.
- **Research:** pick a specialist and click **Run on sample**.
- **Datasets:** "Installed on this PC" lists what is actually on disk.

## Ground rules

Research software only: results are not diagnoses. No Qwen base models. Keep `license` and `commercial_ok` on every data row, never invent patient IDs, and never send credentialed data (PhysioNet etc.) to hosted APIs.
