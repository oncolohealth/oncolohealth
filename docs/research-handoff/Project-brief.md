# Cancer AI Research: project brief

## Goal

Create one place where researchers can find cancer models and datasets, ask evidence-backed questions, compare methods, and develop new models.

A Gemma-based reasoning assistant is the proposed coordinator: it would search research sources with citations, write code, select compatible specialist models, call them, and explain their results and limitations. Gemma 4 31B is the large-machine candidate; a smaller quantized Gemma is the local-computer candidate. The assistant should retain its general reasoning and coding ability as oncology capabilities are added. Neither deployment nor retained capability has been verified.

## Three ways to reuse existing models

1. **Use specialists directly.** Connect existing cancer models as tools and teach the assistant when and how to use each one.
2. **Adapt pretrained models.** Reuse learned features or fine-tune eligible checkpoints on suitable datasets for new tasks.
3. **Train smaller models from stronger teachers.** Where permissions allow, combine teacher outputs with reference labels and evaluate the smaller model on independent data.

## Dataset quality and training support

Help researchers discover and assess datasets: provenance, label evidence, licensing, duplicates, patient overlap, class balance, population coverage, and suitability for the intended task. Report what the evidence supports and what still needs expert review.

Prepare reproducible experiments, compare baselines, launch specifically authorized training jobs, and track metrics, checkpoints, and resource use. Keep model requirements, permissions, preprocessing, versions, and validation evidence searchable.

## First milestone

Complete one bone X-ray research workflow: audit a public dataset, compare two baseline approaches using the same patient-separated splits, and produce a reproducible evaluation. Add that working specialist to the assistant's registry. Expand into other modalities after the first workflow is reliable.

## Status and success criteria

An initial local software foundation exists and passed tests using synthetic data. Real medical data, specialist weights, a live assistant, internet retrieval, and cluster execution still need integration.

Success means useful, reproducible research workflows and measured performance on each supported task. Cancer-detection claims require appropriate reference labels, independent evaluation, and comparison with strong existing methods.
