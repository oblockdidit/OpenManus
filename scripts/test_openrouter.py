#!/usr/bin/env python
"""
Test script for OpenRouter integration with OpenManus.

This script allows you to test OpenRouter with various models, including DeepSeek.
Usage:
    python test_openrouter.py --model deepseek-chat --prompt "Write a function to calculate Fibonacci numbers"
"""

import argparse
import asyncio
import os
import sys
import tomllib
from pathlib import Path

# Add the OpenManus directory to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.llm.openrouter_provider import (
    generate_openrouter_response, 
    get_openrouter_model_list,
    get_openrouter_client
)
from app.parser.tool_parser import parse_assistant_message
from config.openrouter_config import OPENROUTER_MODELS


async def test_openrouter(model: str, prompt: str, temperature: float = 0.7, stream: bool = True):
    """Test OpenRouter with the specified model and prompt."""
    # Load the OpenRouter configuration
    config_path = Path(__file__).resolve().parent.parent / "config" / "openrouter.toml"
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return

    # Get the API key from the configuration
    api_key = config.get("api_key", os.environ.get("OPENROUTER_API_KEY"))
    if not api_key or api_key == "your-openrouter-api-key-here":
        print("Error: OpenRouter API key not found in configuration")
        print("Please edit config/openrouter.toml and add your API key")
        return
    
    # Initialize the OpenRouter client
    client = get_openrouter_client(api_key)
    
    # Setup the messages with a system prompt that includes XML tool instructions
    system_prompt = """You are a helpful assistant with coding expertise.
When using tools, format your response using XML tags like this:

<tool_name>
<parameter1>value1</parameter1>
<parameter2>value2</parameter2>
</tool_name>

Available tools:
- execute_command: Run shell commands
- read_file: Read a file's contents
- write_to_file: Create or modify a file

Example:
<read_file>
<path>file.txt</path>
</read_file>
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    # Check if model exists in our mapping
    if model in OPENROUTER_MODELS:
        full_model_id = OPENROUTER_MODELS[model]
        print(f"Using model: {model} (ID: {full_model_id})")
    else:
        # Check if it's a full model ID
        if "/" in model:
            full_model_id = model
            print(f"Using model: {model}")
        else:
            print(f"Model '{model}' not found. Using default fallback model.")
            full_model_id = OPENROUTER_MODELS.get("claude-3-haiku")
    
    print(f"\nGenerating response to: '{prompt}'")
    print("=" * 80)
    
    try:
        # Generate the response
        if stream:
            # Handle streaming response
            complete_response = ""
            response = await generate_openrouter_response(
                messages=messages,
                model_id=full_model_id,
                temperature=temperature,
                stream=True
            )
            
            print("\nStreaming response:\n")
            
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    complete_response += content
                    print(content, end="", flush=True)
            
            print("\n\n" + "=" * 80)
            
            # Parse for tool calls
            text_content, tool_calls = parse_assistant_message(complete_response)
            
            if tool_calls:
                print("\nDetected Tool Calls:")
                for i, tool in enumerate(tool_calls):
                    print(f"\nTool {i+1}: {tool.name}")
                    print(f"Parameters: {tool.parameters}")
                    print(f"Is partial: {tool.partial}")
        else:
            # Handle non-streaming response
            collected_chunks = []
            response = await generate_openrouter_response(
                messages=messages,
                model_id=full_model_id,
                temperature=temperature,
                stream=True  # We'll still use streaming but collect all chunks
            )
            
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    collected_chunks.append(content)
            
            complete_response = "".join(collected_chunks)
            print(complete_response)
            
            # Parse for tool calls
            text_content, tool_calls = parse_assistant_message(complete_response)
            
            if tool_calls:
                print("\nDetected Tool Calls:")
                for i, tool in enumerate(tool_calls):
                    print(f"\nTool {i+1}: {tool.name}")
                    print(f"Parameters: {tool.parameters}")
                    print(f"Is partial: {tool.partial}")
        
        # Get client stats
        stats = client.get_model_stats()
        print("\nModel Stats:")
        for model_id, stats_data in stats.items():
            print(f"- {model_id}:")
            print(f"  - Usage count: {stats_data['usage_count']}")
            print(f"  - Success rate: {stats_data['success_rate']:.2f}%")
            print(f"  - Is blocked: {stats_data['is_blocked']}")
    
    except Exception as e:
        print(f"\nError generating response: {e}")


async def list_models():
    """List available models from OpenRouter."""
    # Load the OpenRouter configuration
    config_path = Path(__file__).resolve().parent.parent / "config" / "openrouter.toml"
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return

    # Get the API key from the configuration
    api_key = config.get("api_key", os.environ.get("OPENROUTER_API_KEY"))
    if not api_key or api_key == "your-openrouter-api-key-here":
        print("Error: OpenRouter API key not found in configuration")
        print("Please edit config/openrouter.toml and add your API key")
        return
    
    # Get list of models
    try:
        models = await get_openrouter_model_list()
        
        print("Available Models:")
        print("=" * 80)
        
        # Print shorthand models from our config
        print("\nShorthand Model Names (recommended):")
        for shortname, model_id in OPENROUTER_MODELS.items():
            print(f"- {shortname} → {model_id}")
        
        # Print all models from OpenRouter API
        if models:
            print("\nAll Available Models from OpenRouter:")
            for model in models:
                print(f"- {model.get('id')}: {model.get('name', 'Unknown')}")
        
    except Exception as e:
        print(f"Error listing models: {e}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Test OpenRouter integration with OpenManus")
    parser.add_argument("--model", default="deepseek-chat", help="Model to use (default: deepseek-chat)")
    parser.add_argument("--prompt", default="Tell me how to write a Python function to calculate Fibonacci numbers.", 
                      help="Prompt to send to the model")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature (default: 0.7)")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming")
    parser.add_argument("--list-models", action="store_true", help="List available models")
    
    args = parser.parse_args()
    
    if args.list_models:
        asyncio.run(list_models())
    else:
        asyncio.run(test_openrouter(
            model=args.model,
            prompt=args.prompt,
            temperature=args.temperature,
            stream=not args.no_stream
        ))


if __name__ == "__main__":
    main()
