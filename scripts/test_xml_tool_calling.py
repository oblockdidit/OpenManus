#!/usr/bin/env python
"""
Test script for XML-based tool calling with OpenRouter.
This script tests the BrowserUseTool with XML tool calling for content extraction.
"""

import asyncio
import os
import sys
import json

# Add the current directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tool.browser_use_tool import BrowserUseTool
from app.logger import logger

async def test_browser_tool():
    """Test the BrowserUseTool with XML-based tool calling."""
    print("\n========== Testing BrowserUseTool with XML Tool Calling ==========\n")
    
    browser_tool = BrowserUseTool()
    
    # Test navigation
    print("Testing browser navigation...")
    result = await browser_tool.execute(action="go_to_url", url="https://example.com")
    print(f"Navigation result: {result.output if not result.error else f'Error: {result.error}'}\n")
    
    # Test content extraction with XML tool calling
    print("Testing content extraction with XML tool calling...")
    extract_result = await browser_tool.execute(
        action="extract_content", 
        goal="Extract the main heading and first paragraph"
    )
    
    print(f"Extraction result:")
    if not extract_result.error:
        print(extract_result.output)
    else:
        print(f"Error: {extract_result.error}")
    
    # Cleanup browser resources
    await browser_tool.cleanup()
    print("\n========== Test completed ==========\n")

if __name__ == "__main__":
    asyncio.run(test_browser_tool())
