#!/usr/bin/env python3
import asyncio
import sys

from app.llm.openrouter_provider import get_openrouter_client, generate_openrouter_response


async def test_openrouter_configuration():
    """Test the OpenRouter configuration."""
    print("Testing OpenRouter configuration...")
    
    try:
        # Test getting the client
        client = get_openrouter_client()
        print(f"✅ Successfully created OpenRouter client")
        
        # Test a simple completion
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        print("Testing OpenRouter completion...")
        response = await generate_openrouter_response(
            messages=messages,
            model_id="deepseek-chat",
            temperature=0.7,
            max_tokens=100,
            stream=False
        )
        
        # Collect the response content
        content = ""
        async for chunk in response:
            if hasattr(chunk.choices[0], 'delta') and chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
        
        print(f"✅ Successfully generated response from OpenRouter")
        print(f"Response preview: {content[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_openrouter_configuration())
    sys.exit(0 if success else 1)
