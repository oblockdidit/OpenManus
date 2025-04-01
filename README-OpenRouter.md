# Using OpenRouter with OpenManus

This guide explains how to use OpenRouter with OpenManus, including how to use DeepSeek and other models through the OpenRouter API.

## Overview

OpenManus now includes a robust OpenRouter integration that:

1. Uses XML-based tool calling that works with any model (even those without native tool call support)
2. Includes adaptive rate limiting to prevent quota errors
3. Provides model fallbacks when specific models fail
4. Automatically formats prompts specifically for each model family
5. Offers comprehensive error handling and retry mechanisms

## Setup

### 1. Get an OpenRouter API Key

1. Go to [OpenRouter](https://openrouter.ai/) and create an account
2. Generate an API key from the dashboard
3. Copy the API key

### 2. Configure OpenRouter in OpenManus

Edit the `config/openrouter.toml` file and add your API key:

```toml
# OpenRouter Configuration
api_key = "your-openrouter-api-key-here"
default_model = "deepseek-chat"
```

### 3. Test the Integration

Use the included test script to verify your setup:

```bash
# Navigate to the OpenManus directory
cd /path/to/OpenManus

# Test with DeepSeek
python scripts/test_openrouter.py --model deepseek-chat --prompt "Write a Python function to calculate Fibonacci numbers"

# List available models
python scripts/test_openrouter.py --list-models
```

## Available Models

You can use any model available on OpenRouter, but the following models are specifically configured:

- **Claude Models**: `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`, `claude-3-5-sonnet`, `claude-3-7-sonnet`
- **DeepSeek Models**: `deepseek-chat`, `deepseek-coder`, `deepseek-r1`
- **Other Models**: `mistral-large`, `llama-3-70b`, `llama-3-8b`, `gpt-4o`, `gpt-4-turbo`, `qwen-32b`

## Using in OpenManus

### Method 1: Configure Default LLM

To use OpenRouter as your default LLM, edit your main `config/config.toml` file:

```toml
[llm]
api_type = "openrouter"
model = "deepseek-chat"  # Or any other model shortname
api_key = "your-openrouter-api-key-here"
max_tokens = 4096
temperature = 0.7
```

### Method 2: Use in Code

To use OpenRouter in your code:

```python
from app.llm_integration import LLMIntegration
from app.llm.openrouter_provider import generate_openrouter_response

# Method 1: Using the LLM integration layer
llm_integration = LLMIntegration(config_name="openrouter")
response = await llm_integration.ask_with_tools(
    messages=[{"role": "user", "content": "Write a Python function"}],
    system_msgs=[{"role": "system", "content": "You are a helpful assistant"}]
)

# Method 2: Using the OpenRouter provider directly
response = await generate_openrouter_response(
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Write a Python function"}
    ],
    model_id="deepseek-chat",
    temperature=0.7
)
```

## Using DeepSeek Models

DeepSeek models have specific settings for optimal performance:

### DeepSeek Chat

Good for general conversational tasks and simpler coding tasks:

```python
response = await generate_openrouter_response(
    messages=messages,
    model_id="deepseek-chat",
    temperature=0.7,
    top_p=0.95
)
```

### DeepSeek Coder

Specialized for programming tasks:

```python
response = await generate_openrouter_response(
    messages=messages,
    model_id="deepseek-coder",
    temperature=0.5,  # Lower temperature for more deterministic outputs
    top_p=0.95
)
```

### DeepSeek R1

Advanced reasoning capabilities:

```python
response = await generate_openrouter_response(
    messages=messages,
    model_id="deepseek-r1",
    temperature=0.7,
    top_p=0.95
)
```

## Troubleshooting

### Rate Limit Errors

The integration includes adaptive rate limiting that automatically adjusts based on errors. If you encounter rate limit errors, the system will:

1. Reduce the request rate
2. Implement exponential backoff
3. Retry the request with increasing delays

### Model Endpoint Errors

If a model returns an endpoint error (e.g., "No endpoints found that support tool use"), the system will:

1. Add the model to a blocked list
2. Automatically fall back to alternative models
3. Log the error for troubleshooting

To view detailed logs:

```bash
# From the OpenManus directory
tail -f logs/openrouter.log
```

## Advanced Configuration

You can customize the fallback behavior and other settings in `config/openrouter_config.py`:

- **Model Fallbacks**: Change the fallback model order
- **Provider Sorting**: Adjust provider preferences (pricing, latency, availability)
- **Model-Specific Settings**: Customize temperature, max_tokens, and top_p per model

For advanced users, you can also modify the prompt enhancements for each model family to optimize tool calling performance.
