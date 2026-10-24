"""Coordinator: swappable LLM providers (any OpenAI-compatible endpoint), tools, and the tool loop.

Owner: Workstream D. Multiple models/endpoints are configured as named profiles in
configs/coordinator.example.json (copy to configs/coordinator.json).
"""
from .config import load_profiles, make_provider
from .loop import SYSTEM_PROMPT, TurnRecord, run_turn
from .providers import ChatResult, OpenAICompatibleProvider, Provider, ProviderError, ScriptedProvider, ToolCall
from .tools import Tool, ToolBox, default_toolbox

__all__ = [
    "ChatResult", "OpenAICompatibleProvider", "Provider", "ProviderError", "SYSTEM_PROMPT", "ScriptedProvider",
    "Tool", "ToolBox", "ToolCall", "TurnRecord", "default_toolbox", "load_profiles", "make_provider", "run_turn",
]
