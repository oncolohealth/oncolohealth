# Cancer AI Research: plain-language walkthrough

## The idea

I’m building a workspace that helps cancer researchers find useful datasets and AI models, compare methods, and create new models. Many existing tools focus on one narrow problem. The goal is to make them easier to discover and use together.

A model is software that has learned patterns from examples. A specialist model handles a particular task, such as locating a lung nodule in a CT scan or outlining a tumor in an MRI. Different specialists need different inputs and produce different kinds of results.

## How the pieces fit together

A general reasoning assistant would coordinate the work. Google Gemma is the selected model family to investigate: the 31B model for large-machine experiments and a smaller quantized version for local use. It would research papers with citations, help write code, select compatible specialists, and explain their outputs. These capabilities still need end-to-end testing in this project.

For example, a researcher could ask: “Help me build and evaluate a bone X-ray model.” The assistant would help define the prediction task, find suitable data, check its labels and permissions, suggest existing models, prepare an experiment, and explain the comparison.

The model registry would be the catalog behind those choices: what each model does, which files it accepts, how to prepare them, what its outputs mean, and what evidence supports its performance.

## Three ways to use existing models

- **Run a specialist directly.** This is inference: applying an already trained model to new inputs.

- **Adapt an existing model.** Training adjusts a model using examples. Fine-tuning means continuing the training of an existing model for a particular task. Another option is to keep its learned image features fixed and train a small classifier on top.

- **Learn from a stronger model.** Distillation teaches a smaller student model using a stronger teacher’s outputs, alongside reference labels where available. We would check the source model’s permissions and measure the student’s performance on independent examples.

## Why the data work matters

A dataset is a collection of examples and associated information. Labels describe the target we want the model to learn, such as a reviewed diagnosis or an expert-drawn tumor outline. We need to examine how those labels were established, rather than assume every label is correct.

The platform would help check provenance (where data came from), duplicates, missing information, population coverage, and permitted uses. It would also check for data leakage: information from the evaluation cases accidentally entering training. Images from the same patient appearing on both sides can make results look better than they really are.

## The first build and what exists today

We would start with one bone X-ray experiment: audit a public dataset, compare two baseline approaches, and evaluate them on held-out patients—patients kept separate from model development. A baseline is a reference method that helps us judge whether a change actually improves results.

NPS’s GB300 would provide the GPU computing for specifically authorized experiments. GPUs are processors suited to the repeated numerical calculations used by AI models. We would track the settings, data splits, results, and saved model checkpoints so the work can be reproduced.

The initial local software foundation exists and has passed tests using synthetic examples. Real medical data, specialist weights, a live assistant, and cluster training still need integration. The immediate goal is a useful, reproducible research workflow. Any claim about cancer-detection performance will need independent evaluation.

