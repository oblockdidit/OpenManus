"""
This is a temporary fix for the OpenRouter provider.
It adds direct TOML file reading for the OpenRouter API key.
"""

import os
import tomllib
from pathlib import Path


def get_openrouter_config():
    """Read the OpenRouter configuration from the TOML file directly."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_file = project_root / "config" / "openrouter.toml"
    
    if not config_file.exists():
        raise FileNotFoundError(f"OpenRouter config file not found at {config_file}")
    
    with open(config_file, "rb") as f:
        config = tomllib.load(f)
    
    return config


def get_openrouter_api_key():
    """Get the OpenRouter API key from the configuration."""
    try:
        config = get_openrouter_config()
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("API key not found in OpenRouter configuration")
        return api_key
    except Exception as e:
        raise ValueError(f"Error getting OpenRouter API key: {str(e)}")
