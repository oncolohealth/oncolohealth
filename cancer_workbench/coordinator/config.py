"""Load named coordinator profiles.

Lookup order: explicit path > configs/coordinator.json (local, gitignored) >
configs/coordinator.example.json. Pick a profile by name, CW_COORDINATOR_PROFILE,
or the file's `default_profile`. Fields starting with `_` are comments.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..common.paths import CONFIG_DIR
from .providers import OpenAICompatibleProvider

_PROVIDER_FIELDS = {"base_url", "model", "api_key_env", "timeout_s", "default_params", "extra_body", "supports_tools"}


def config_path(path: Path | None = None) -> Path:
    if path:
        return path
    local = CONFIG_DIR / "coordinator.json"
    return local if local.exists() else CONFIG_DIR / "coordinator.example.json"


def load_profiles(path: Path | None = None) -> tuple[dict[str, dict], str | None]:
    cfg = json.loads(config_path(path).read_text())
    profiles = {name: p for name, p in cfg["profiles"].items() if not name.startswith("_")}
    return profiles, cfg.get("default_profile")


def make_provider(profile: str | None = None, path: Path | None = None) -> OpenAICompatibleProvider:
    profiles, default = load_profiles(path)
    name = profile or os.environ.get("CW_COORDINATOR_PROFILE") or default
    if name not in profiles:
        raise KeyError(f"unknown coordinator profile {name!r}; available: {sorted(profiles)}")
    p = profiles[name]
    if p.get("type", "openai_compatible") != "openai_compatible":
        raise ValueError(f"profile {name!r}: unsupported type {p.get('type')!r}")
    url_env = p.get("base_url_env")
    base_url = os.environ.get(url_env, p.get("base_url")) if url_env else p.get("base_url")
    kwargs = {k: v for k, v in p.items() if k in _PROVIDER_FIELDS}
    kwargs["base_url"] = base_url
    return OpenAICompatibleProvider(profile=name, **kwargs)
