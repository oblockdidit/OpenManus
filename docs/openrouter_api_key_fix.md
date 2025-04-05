# OpenRouter API Key Configuration Fix

## Issue Overview

After fixing the browser URL issue, a new error appeared:

```
Error in ask_with_tools: OpenRouter API key not found in configuration
```

This error occurred because the OpenManus system couldn't find the OpenRouter API key in the configuration, despite the key being correctly set in the `config/openrouter.toml` file.

### Root Cause

The issue was in the `get_openrouter_client` function in `app/llm/openrouter_provider.py`. It was attempting to get the API key from the main application configuration (`config.llm.get("openrouter", {}).get("api_key", None)`), but the OpenRouter settings weren't being properly loaded into the main config object.

The main configuration system (`app/config.py`) wasn't configured to load the OpenRouter TOML file, so even though the API key was present in `config/openrouter.toml`, it wasn't accessible through the main config.

### Solution

We implemented a more robust approach to API key retrieval:

1. **Direct TOML File Reading**: Added a function that reads the OpenRouter API key directly from the TOML file when it's not available through the main config system.

2. **Fallback Mechanism**: Modified the `get_openrouter_client` function to first attempt to get the API key from the main config, and if not found, to read it directly from the TOML file.

3. **Better Error Handling**: Improved error messages to help diagnose any future configuration issues.

## Code Changes

1. Added a `get_openrouter_api_key` function that directly reads and parses the TOML file:

```python
def get_openrouter_api_key():
    """Read the OpenRouter API key directly from the TOML file."""
    try:
        project_root = Path(__file__).resolve().parent.parent.parent
        config_file = project_root / "config" / "openrouter.toml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"OpenRouter config file not found at {config_file}")
        
        with open(config_file, "rb") as f:
            config = tomllib.load(f)
        
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("API key not found in OpenRouter configuration")
        return api_key
    except Exception as e:
        raise ValueError(f"Error getting OpenRouter API key: {str(e)}")
```

2. Modified the `get_openrouter_client` function to use this new approach:

```python
def get_openrouter_client(api_key: Optional[str] = None) -> OpenRouterClient:
    """Get or create the OpenRouter client instance."""
    global _client_instance
    if _client_instance is None:
        if api_key is None:
            try:
                # First try to get from app config
                from app.config import config
                api_key = config.llm.get("openrouter", {}).get("api_key", None)
                
                # If not found in config, read directly from TOML file
                if not api_key:
                    api_key = get_openrouter_api_key()
                    logger.info("Using API key from openrouter.toml file")
            except Exception as e:
                raise ValueError(f"OpenRouter API key not found: {str(e)}")
            
            if not api_key:
                raise ValueError("OpenRouter API key not found in configuration")
        _client_instance = OpenRouterClient(api_key=api_key)
    return _client_instance
```

## Testing

A test script (`test_openrouter.py`) was created to verify the fix:

1. It attempts to create an OpenRouter client, which tests the API key retrieval
2. It sends a simple completion request to OpenRouter, confirming the API key works

## Future Improvements

For a more comprehensive solution in the future, consider:

1. **Unified Configuration System**: Modify the main configuration system to explicitly load the OpenRouter TOML file, making the API key available through the standard config object.

2. **Environment Variable Support**: Add support for setting the OpenRouter API key through an environment variable as a fallback mechanism.

3. **Configuration Validation**: Add a startup validation check that verifies all required API keys are present before the application starts.

## Additional Notes

The fix preserves backward compatibility with the existing configuration system. If the OpenRouter API key is properly set in the main configuration in the future, the system will use that value instead of reading from the TOML file directly.
