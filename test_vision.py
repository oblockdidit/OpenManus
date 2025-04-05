#!/usr/bin/env python
"""
Test script for the vision model functionality.
This script tests the ask_with_images method in the LLM class.
"""

import asyncio
import base64
import sys
from pathlib import Path
from app.logger import logger
from app.llm.llm import LLM
from app.tool.browser_use_tool import BrowserUseTool

async def test_vision_model(url: str = "https://example.com"):
    """Test the vision model functionality."""
    logger.info(f"Testing vision model with URL: {url}")
    
    # Create browser tool
    browser_tool = BrowserUseTool()
    
    try:
        # Initialize browser
        logger.info("Initializing browser...")
        await browser_tool._ensure_browser_initialized()
        logger.info("Browser initialized successfully")
        
        # Navigate to URL
        logger.info(f"Navigating to {url}...")
        result = await browser_tool.execute(action="go_to_url", url=url)
        
        if result.error:
            logger.error(f"Navigation failed: {result.error}")
            return
        
        logger.info(f"Successfully navigated to {url}")
        
        # Take screenshot
        logger.info("Taking screenshot...")
        context = await browser_tool._ensure_browser_initialized()
        page = await context.get_current_page()
        screenshot_bytes = await page.screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        logger.info("Screenshot taken successfully")
        
        # Save screenshot to file for debugging
        screenshot_path = Path("screenshot.jpg")
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        logger.info(f"Screenshot saved to {screenshot_path}")
        
        # Create vision LLM
        logger.info("Creating vision LLM...")
        vision_llm = LLM("vision")
        logger.info(f"Vision model: {vision_llm.model}")
        
        # Prepare prompt
        prompt = "Describe what you see on this webpage. What is the main content and purpose of this site?"
        
        # Call ask_with_images
        logger.info("Calling ask_with_images...")
        try:
            analysis_result = await vision_llm.ask_with_images(
                messages=[{"role": "user", "content": prompt}],
                images=[{"base64": screenshot_b64}],
                stream=False,
                temperature=0.2
            )
            
            logger.info("Vision model analysis successful")
            print("\n=== VISION MODEL ANALYSIS ===")
            print(analysis_result)
            print("============================\n")
        except Exception as e:
            logger.error(f"Vision model analysis failed: {e}")
            print(f"Error: {e}")
            
    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
    finally:
        # Clean up browser
        logger.info("Cleaning up browser...")
        await browser_tool.cleanup()
        logger.info("Browser cleanup completed")

if __name__ == "__main__":
    # Get URL from command line argument or use default
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    
    # Run the test
    asyncio.run(test_vision_model(url))
