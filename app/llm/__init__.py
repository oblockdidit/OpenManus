"""
OpenManus LLM integration package
"""

# Import LLM from the local module
from app.llm.llm import LLM

# Make openrouter_provider importable
from app.llm.openrouter_provider import (
    generate_openrouter_response,
    get_openrouter_model_list,
    get_openrouter_client
)

__all__ = [
    "LLM",
    "generate_openrouter_response",
    "get_openrouter_model_list",
    "get_openrouter_client",
]
