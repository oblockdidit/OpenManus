"""
OpenRouter configuration module for OpenManus.

This module contains configurations for using OpenRouter with various models.
"""

from typing import Dict, List

# OpenRouter model IDs
OPENROUTER_MODELS = {
    # Claude models
    "claude-3-opus": "anthropic/claude-3-opus",
    "claude-3-sonnet": "anthropic/claude-3-sonnet",
    "claude-3-haiku": "anthropic/claude-3-haiku",
    "claude-3-5-sonnet": "anthropic/claude-3.5-sonnet",
    "claude-3-7-sonnet": "anthropic/claude-3.7-sonnet",
    
    # DeepSeek models
    "deepseek-chat": "deepseek/deepseek-chat",
    "deepseek-chat-v3": "deepseek/deepseek-chat-v3-0324",
    "deepseek-coder": "deepseek/deepseek-coder",
    "deepseek-r1": "deepseek/deepseek-r1",
    
    # Other models
    "mistral-large": "mistralai/mistral-large-latest",
    "llama-3-70b": "meta-llama/llama-3-70b-instruct",
    "llama-3-8b": "meta-llama/llama-3-8b-instruct",
    "gpt-4o": "openai/gpt-4o",
    "gpt-4-turbo": "openai/gpt-4-turbo",
    "qwen-32b": "qwen/qwen-32b",
    "qwen2.5-32b": "qwen/qwen2.5-32b-instruct",
    "qwen2.5-vl-32b": "qwen/qwen2.5-vl-32b-instruct",
}

# Default provider routing preferences
DEFAULT_PROVIDER_SORTING = "pricing" # Options: "pricing", "latency", "availability"

# Model capability mapping
MODEL_CAPABILITIES = {
    # Models with high context windows (16k+)
    "high_context": [
        "anthropic/claude-3-opus",
        "anthropic/claude-3-sonnet", 
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.7-sonnet",
        "openai/gpt-4o",
        "openai/gpt-4-turbo"
    ],
    
    # Models that support image inputs
    "supports_images": [
        "anthropic/claude-3-opus",
        "anthropic/claude-3-sonnet",
        "anthropic/claude-3-haiku",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.7-sonnet",
        "openai/gpt-4o",
        "openai/gpt-4-turbo"
    ],
    
    # Models that work well with XML tool calling
    "best_for_tools": [
        "anthropic/claude-3-opus",
        "anthropic/claude-3-sonnet",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.7-sonnet",
        "openai/gpt-4o",
        "openai/gpt-4-turbo"
    ],
    
    # Models that handle code well
    "code_specialized": [
        "deepseek/deepseek-coder",
        "deepseek/deepseek-r1",
        "meta-llama/llama-3-70b-instruct",
        "anthropic/claude-3-opus"
    ]
}

# Model-specific settings
MODEL_SETTINGS = {
    "deepseek/deepseek-chat": {
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 2048
    },
    "deepseek/deepseek-chat-v3-0324": {
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 2048
    },
    "deepseek/deepseek-coder": {
        "temperature": 0.5,
        "top_p": 0.95,
        "max_tokens": 2048
    },
    "deepseek/deepseek-r1": {
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 2048
    },
    "meta-llama/llama-3-70b-instruct": {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096
    },
    "meta-llama/llama-3-8b-instruct": {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096
    },
    "qwen/qwen2.5-32b-instruct": {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096
    },
    "qwen/qwen2.5-vl-32b-instruct": {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096
    }
}

# Fallback model configuration
# If a model fails, use these models as fallbacks in order
FALLBACK_MODELS = {
    "deepseek/deepseek-chat": ["anthropic/claude-3-haiku", "meta-llama/llama-3-8b-instruct"],
    "deepseek/deepseek-chat-v3-0324": ["anthropic/claude-3-haiku", "meta-llama/llama-3-8b-instruct"],
    "deepseek/deepseek-coder": ["anthropic/claude-3-haiku", "meta-llama/llama-3-8b-instruct"],
    "deepseek/deepseek-r1": ["anthropic/claude-3-haiku", "deepseek/deepseek-chat"],
    "qwen/qwen2.5-32b-instruct": ["meta-llama/llama-3-8b-instruct", "anthropic/claude-3-haiku"],
    "qwen/qwen2.5-vl-32b-instruct": ["qwen/qwen2.5-32b-instruct", "anthropic/claude-3-haiku"],
    "meta-llama/llama-3-70b-instruct": ["meta-llama/llama-3-8b-instruct", "anthropic/claude-3-haiku"],
    "default": ["anthropic/claude-3-haiku"]  # Default fallback for any model not specified
}

# System prompt enhancements for specific models
MODEL_PROMPT_ENHANCEMENTS = {
    "deepseek": "\n\nIMPORTANT: Format any tool calls using XML tags <tool_name>...</tool_name> with parameters as <param>value</param>. DO NOT use JSON format for tool calls.",
    "qwen": "\n\nIMPORTANT: When you need to use a tool, always format your response using XML tags <tool_name><param1>value1</param1><param2>value2</param2></tool_name>. DO NOT use JSON format for tools.",
    "llama": "\n\nIMPORTANT: When you need to use a tool, always format your response using XML tags like <tool_name><param>value</param></tool_name>. Never use JSON format.",
    "anthropic": "\n\nIMPORTANT: Always format tool calls using XML tags exactly as shown in the examples above. DO NOT use any other format.",
}

def get_model_settings(model_id: str) -> Dict:
    """
    Get settings for a specific model, or default settings if not specified.
    
    Args:
        model_id: The model ID
        
    Returns:
        Dict with model settings
    """
    return MODEL_SETTINGS.get(model_id, {
        "temperature": 0,  # Default to 0 for most predictable responses
        "max_tokens": 4096
    })

def get_fallback_models(model_id: str) -> List[str]:
    """
    Get fallback models for a specific model.
    
    Args:
        model_id: The model ID
        
    Returns:
        List of fallback model IDs
    """
    # First check for exact model match
    if model_id in FALLBACK_MODELS:
        return FALLBACK_MODELS[model_id]
    
    # Then check for model family match
    for family, models in FALLBACK_MODELS.items():
        if model_id.startswith(family.split('/')[0]):
            return models
    
    # Return default fallbacks if no match
    return FALLBACK_MODELS["default"]

def get_prompt_enhancement(model_id: str) -> str:
    """
    Get prompt enhancement for a specific model.
    
    Args:
        model_id: The model ID
        
    Returns:
        String with model-specific prompt enhancement
    """
    model_family = model_id.split('/')[0].lower()
    
    for family, enhancement in MODEL_PROMPT_ENHANCEMENTS.items():
        if model_family.startswith(family):
            return enhancement
    
    # Default enhancement if no match
    return "\n\nIMPORTANT: Format all tool calls using XML tags as described above."
