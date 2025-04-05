#!/usr/bin/env python
"""
Simple script to navigate through navbar links on a website.
This version focuses on the core functionality and uses a more direct approach.
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
    """Explore navbar links on a website."""
    logger.info(f"Exploring navbar links on: {url}")
    
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
        await asyncio.sleep(2)  # Wait for page to load
        
        # Take a screenshot for vision model analysis
        context = await browser_tool._ensure_browser_initialized()
        page = await context.get_current_page()
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
            homepage_info = await analyze_page(browser_tool, vision_llm, "Homepage", screenshot_b64)
            print("\n=== HOMEPAGE ===\n")
            print(homepage_info)
            print("=================\n")
            
            # Navigate to each link
            for link in links:
                logger.info(f"Attempting to navigate to: {link}")
                
                # Try to click the link using the browser_use tool
                if await click_link_by_text(browser_tool, link):
                    logger.info(f"Successfully navigated to {link} page")
                    
                    # Take a screenshot of the page
                    page = await context.get_current_page()
                    page_screenshot = await page.screenshot()
                    page_screenshot_b64 = base64.b64encode(page_screenshot).decode("utf-8")
                    
                    # Analyze the page
                    page_info = await analyze_page(browser_tool, vision_llm, link, page_screenshot_b64)
                    
                    # Print the page info
                    print(f"\n=== {link.upper()} PAGE ===\n")
                    print(page_info)
                    print("=" * (len(link) + 11) + "\n")
                    
                    # Go back to homepage
                    await browser_tool.execute(action="go_to_url", url=url)
                    await asyncio.sleep(2)
                else:
                    logger.warning(f"Failed to navigate to {link} page")
            
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

async def analyze_page(browser_tool, vision_llm, label, screenshot_b64):
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
        
        # Fallback to text-based extraction
        info_result = await browser_tool.execute(
            action="extract_content",
            goal=f"Describe what this {label} page contains and its purpose."
        )
        
        if not info_result.error:
            return info_result.output
        else:
            return f"Failed to analyze {label} page: {info_result.error}"

async def click_link_by_text(browser_tool, link_text):
    """Click a link with the given text."""
    logger.info(f"Clicking link with text: {link_text}")
    
    # Method 1: Try using scroll_to_text and then clicking
    scroll_result = await browser_tool.execute(
        action="scroll_to_text", 
        text=link_text
    )
    
    if not scroll_result.error:
        logger.info(f"Successfully scrolled to text: {link_text}")
        
        # Try clicking elements after scrolling
        for i in range(5):  # Try a few elements
            click_result = await browser_tool.execute(
                action="click_element", 
                index=i
            )
            
            if not click_result.error:
                # Wait for page to load
                await asyncio.sleep(2)
                
                # Check if we navigated to a new page by extracting the title
                title_result = await browser_tool.execute(
                    action="extract_content",
                    goal="What is the title or heading of this page?"
                )
                
                if not title_result.error:
                    title = title_result.output
                    logger.info(f"Page title: {title}")
                    
                    if link_text.lower() in title.lower():
                        return True
                
                # Go back if this wasn't the right page
                await browser_tool.execute(action="go_back")
                await asyncio.sleep(1)
    
    # Method 2: Systematic approach - try the first 10 elements
    logger.info(f"Trying systematic approach for '{link_text}'")
    
    # Get page content to see all elements
    content_result = await browser_tool.execute(
        action="extract_content",
        goal="List all clickable elements on the page with their text content"
    )
    
    if not content_result.error:
        content = content_result.output
        logger.info(f"Page content: {content[:200]}...")
        
        # Try clicking elements that might be the link
        for i in range(10):
            try:
                # Try clicking each element
                click_result = await browser_tool.execute(
                    action="click_element", 
                    index=i
                )
                
                if not click_result.error:
                    # Wait for page to load
                    await asyncio.sleep(2)
                    
                    # Check if we navigated to a new page by extracting the title
                    title_result = await browser_tool.execute(
                        action="extract_content",
                        goal="What is the title or heading of this page?"
                    )
                    
                    if not title_result.error:
                        title = title_result.output
                        logger.info(f"Page title: {title}")
                        
                        if link_text.lower() in title.lower():
                            return True
                    
                    # Go back if this wasn't the right page
                    await browser_tool.execute(action="go_back")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"Error clicking element {i}: {e}")
    
    logger.warning(f"Failed to click link: {link_text}")
    return False

if __name__ == "__main__":
    # Get URL from command line argument or use default
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    
    # Run the exploration
    asyncio.run(explore_navbar(url))
