# Two-minute demo script

For presenting OncoloHealth live. Pair it with the slide deck; the demo replaces slides 6–8 if time is short.

## Before you start (5 minutes ahead)
- Model server up: the Assistant's picker says **Ready**. It serves one request at a time, so nothing else should be using it.
- Open http://127.0.0.1:8765/#assistant, click **New chat**, and set the window to full screen.
- Do one warm-up question so the model and the bone X-ray specialist are loaded (the first specialist call takes a few seconds longer).
- Light theme (the default peach) reads best on projectors.

## The run (click **Guided demo**, then **Next** each time)

| Time | Step | What happens on screen | What to say |
|---|---|---|---|
| 0:00 | Open | Welcome screen | "Every cancer model today starts from zero: its own data hunt, its own cleaning, its own evaluation. This is one place where that work is shared." |
| 0:15 | **1. Search the catalog** | Lookups stream in one by one, then an answer with a license table | "Watch it work: each lookup and its real result appears as it happens. It's answering from a catalog of datasets and their licenses, not from memory." |
| 0:40 | **2. Bone X-ray specialist** | The X-ray attaches; a result card shows score bars and **Differs from the reference** | "That's a real model running on this laptop. It says benign; the dataset says malignant, and we show the disagreement instead of hiding it." |
| 1:05 | **3. Brain MRI** | Tumor overlay, region table, Dice ≈ 0.90 against the expert mask | "Segmentation from a pretrained MONAI model, compared to the expert's mask after the prediction, never before." |
| 1:35 | **4. Ask for something that isn't there** | A plain "no": only a patch classifier exists, no whole-slide pipeline | "And when the evidence isn't there, it says so. That honesty is the point." |
| 1:50 | Close | Open **Datasets** for a second | "Nine datasets on disk, seven specialists, all local. The next researcher starts where the last one stopped." |

## If something goes wrong
- **"Not reachable · retry"**: the model server is busy or down. Click retry; if it stays down, fall back to the **Research** screen and click **Run on sample**, which needs no language model.
- **A step takes long:** the MRI step takes 20–30 s on this machine; talk over the streaming steps.
- **"This chat is longer than the model can hold":** click **New chat** and continue the demo from that step; the guided demo keeps each step short to avoid it.
- **CT detection** takes 8–10 minutes on CPU, too long for a live demo. Show a saved result from the Research screen's **Recent runs** instead.

## Facts you may be asked
- Assistant: Google's Gemma 4 26B, fine-tuned by us on an NVIDIA DGX GB300 (via NPS), running locally at about 40–60 tokens/s on a 16 GB RTX 5070 Ti.
- Specialists: 7. Four are deliberately simple baselines; the MRI and CT models are restored MONAI bundles; the bone model is a ResNet-50 with our trained head.
- Nothing is validated for clinical use. The MRI and CT samples may overlap the original models' training data.
