"""Local researcher app: `python3 -m cancer_workbench app`. Owner: Workstream G.

server.py   stdlib HTTP server on 127.0.0.1 with a per-launch token
api.py      JSON endpoints wrapping registry, routing, acquisition, datasets, coordinator
jobs.py     background downloads with progress and cancel
static/     index.html, app.js, style.css (no build step, no external assets)
"""
