#!/usr/bin/env python
"""
Direct script to navigate through navbar links on a website.
This version uses a more direct approach with Playwright's built-in methods.
"""

import asyncio
import sys
import time
import base64
from pathlib import Path

from app.logger import logger
from app.tool.browser_use_tool import BrowserUseTool
from app.llm.llm import LLM

async def explore_navbar(url: str = "https://example.com"):
    """Explore navbar links on a website using direct Playwright methods."""
    logger.info(f"Exploring navbar links on: {url}")
    
    # Create browser tool
    browser_tool = BrowserUseTool()
    
    try:
        # Initialize browser
        logger.info("Initializing browser...")
        context = await browser_tool._ensure_browser_initialized()
        logger.info("Browser initialized successfully")
        
        # Navigate to URL
        logger.info(f"Navigating to {url}...")
        result = await browser_tool.execute(action="go_to_url", url=url)
        
        if result.error:
            logger.error(f"Navigation failed: {result.error}")
            return
        
        logger.info(f"Successfully navigated to {url}")
        await asyncio.sleep(2)  # Wait for page to load
        
        # Get the current page
        page = await context.get_current_page()
        
        # Take a screenshot for vision model analysis
        screenshot_bytes = await page.screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        # Save screenshot to file for reference
        screenshot_path = Path(f"screenshot_{int(time.time())}.jpg")
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        logger.info(f"Screenshot saved to {screenshot_path}")
        
        # Use vision model to identify navbar elements
        vision_llm = LLM("vision")
        prompt = (
            "Identify all navigation menu elements on this webpage. "
            "For each navigation item, provide its exact text label. "
            "Format your response as a simple numbered list with just the link text. "
            "Only include main navigation menu items."
        )
        
        try:
            nav_analysis = await vision_llm.ask_with_images(
                messages=[{"role": "user", "content": prompt}],
                images=[{"base64": screenshot_b64}],
                stream=False,
                temperature=0.2,
            )
            
            # Parse links from the result
            links = []
            for line in nav_analysis.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line[0] in ['•', '-', '*']):
                    # Remove numbering or bullet points
                    link_text = line.split('.', 1)[-1] if '.' in line[:3] else line
                    link_text = link_text.strip()
                    # Remove any bullet points
                    for char in ['•', '-', '*']:
                        if link_text.startswith(char):
                            link_text = link_text[1:].strip()
                    if link_text and link_text.lower() not in ['home', 'homepage']:
                        links.append(link_text)
            
            logger.info(f"Found links: {links}")
            
            # First analyze the homepage
            homepage_info = await analyze_page_with_vision(vision_llm, "Homepage", screenshot_b64)
            print("\n=== HOMEPAGE ===\n")
            print(homepage_info)
            print("=================\n")
            
            # Navigate to each link using direct Playwright methods
            for link in links:
                logger.info(f"Attempting to navigate to: {link}")
                
                # Try to find and click the link directly using Playwright
                try:
                    # Find all links on the page
                    all_links = await page.query_selector_all("a")
                    
                    # Look for a link with matching text
                    link_found = False
                    for link_element in all_links:
                        text_content = await link_element.text_content()
                        if link.lower() in text_content.lower():
                            logger.info(f"Found link with text: {text_content}")
                            
                            # Click the link
                            await link_element.click()
                            await page.wait_for_load_state()
                            await asyncio.sleep(2)  # Wait for page to load
                            
                            # Take a screenshot of the new page
                            page_screenshot = await page.screenshot()
                            page_screenshot_b64 = base64.b64encode(page_screenshot).decode("utf-8")
                            
                            # Analyze the page
                            page_info = await analyze_page_with_vision(vision_llm, link, page_screenshot_b64)
                            
                            # Print the page info
                            print(f"\n=== {link.upper()} PAGE ===\n")
                            print(page_info)
                            print("=" * (len(link) + 11) + "\n")
                            
                            # Go back to homepage
                            await page.goto(url)
                            await page.wait_for_load_state()
                            await asyncio.sleep(2)
                            
                            link_found = True
                            break
                    
                    if not link_found:
                        logger.warning(f"Could not find link with text: {link}")
                        
                        # Try using browser_use's extract_content to get more info
                        elements_result = await browser_tool.execute(
                            action="extract_content",
                            goal="List all clickable elements on the page with their text content"
                        )
                        
                        if not elements_result.error:
                            logger.info(f"Page elements: {elements_result.output[:200]}...")
                
                except Exception as e:
                    logger.error(f"Error navigating to {link}: {e}")
            
        except Exception as e:
            logger.error(f"Error analyzing navigation: {e}")
        
        # Keep browser open for manual inspection
        logger.info("Exploration complete. Browser will remain open for manual inspection.")
        logger.info("Press Ctrl+C to exit...")
        
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Exploration interrupted by user.")
            
    except KeyboardInterrupt:
        logger.info("Exploration interrupted by user.")
    except Exception as e:
        logger.error(f"Exploration failed with exception: {str(e)}")
    finally:
        # Clean up browser
        logger.info("Cleaning up browser...")
        await browser_tool.cleanup()
        logger.info("Browser cleanup completed")

async def analyze_page_with_vision(vision_llm, label, screenshot_b64):
    """Analyze a page using the vision model."""
    logger.info(f"Analyzing page: {label}")
    
    prompt = f"This is the {label} page of a website. Describe what this page contains, its purpose, and key information or features visible on the page."
    
    try:
        analysis = await vision_llm.ask_with_images(
            messages=[{"role": "user", "content": prompt}],
            images=[{"base64": screenshot_b64}],
            stream=False,
            temperature=0.2,
        )
        
        return analysis
    except Exception as e:
        logger.error(f"Error analyzing page: {e}")
        return f"Failed to analyze {label} page: {e}"

if __name__ == "__main__":
    # Get URL from command line argument or use default
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    
    # Run the exploration
    asyncio.run(explore_navbar(url))
