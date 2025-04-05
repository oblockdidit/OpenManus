#!/usr/bin/env python3
import asyncio
import sys
from app.tool.browser_use_tool import BrowserUseTool

async def test_browser_tool():
    """Test the fixed browser tool with a simple navigation."""
    browser_tool = BrowserUseTool()
    try:
        # Navigate to a simple test URL
        print("Navigating to a test website...")
        result = await browser_tool.execute(
            action="go_to_url",
            url="https://example.com"
        )
        print(f"Navigation result: {result.output}")
        
        # Extract content to test our fix
        print("Testing content extraction...")
        extract_result = await browser_tool.execute(
            action="extract_content",
            goal="Extract the main heading and paragraphs"
        )
        
        if extract_result.error:
            print(f"Error during extraction: {extract_result.error}")
            return False
        else:
            print("Content extraction successful!")
            print(f"Output: {extract_result.output[:100]}...")  # Print the first 100 chars
            return True
            
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
    finally:
        # Clean up
        print("Cleaning up browser resources...")
        await browser_tool.cleanup()

if __name__ == "__main__":
    success = asyncio.run(test_browser_tool())
    sys.exit(0 if success else 1)
