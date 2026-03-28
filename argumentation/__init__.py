"""
Argumentation package for the Route Explanation System.

Implements a Dung-style Abstract Argumentation Framework (AF) with
strength-weighted grounded semantics for formal route recommendation
and explanation generation.

Public API:
    build_argumentation_framework(routes, cbr_cases_per_route) → ArgumentationFramework
    generate_argument_explanation(af, chosen_route, all_routes, pref_summary) → str
    build_ollama_prompt_from_af(af, chosen_route, all_routes) → str
"""

from .framework import Argument, Attack, ArgumentationFramework
from .generator import build_argumentation_framework, reload_params
from .explainer import generate_argument_explanation, build_ollama_prompt_from_af

__all__ = [
    "Argument",
    "Attack",
    "ArgumentationFramework",
    "build_argumentation_framework",
    "reload_params",
    "generate_argument_explanation",
    "build_ollama_prompt_from_af",
]
