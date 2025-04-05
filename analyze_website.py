#!/usr/bin/env python
"""
Direct website analysis script that bypasses the LLM.
This script directly uses the browser_use tool to analyze a website.
"""

import asyncio
import base64
import re
import sys
import time
import traceback
from pathlib import Path

from app.llm.llm import LLM
from app.logger import logger
from app.tool.browser_use_tool import BrowserUseTool


async def take_screenshot(browser_tool):
    """Take a screenshot of the current page."""
    context = await browser_tool._ensure_browser_initialized()
    page = await context.get_current_page()
    screenshot_bytes = await page.screenshot()
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    # Save screenshot to file for debugging
    timestamp = int(time.time())
    screenshot_path = Path(f"screenshot_{timestamp}.jpg")
    with open(screenshot_path, "wb") as f:
        f.write(screenshot_bytes)
    logger.info(f"Screenshot saved to {screenshot_path}")

    return screenshot_b64


async def analyze_page_with_vision(vision_llm, screenshot_b64, prompt):
    """Analyze a page using the vision model."""
    try:
        analysis_result = await vision_llm.ask_with_images(
            messages=[{"role": "user", "content": prompt}],
            images=[{"base64": screenshot_b64}],
            stream=False,
            temperature=0.2,
        )
        return analysis_result
    except Exception as e:
        logger.error(f"Vision model analysis failed: {e}")
        return f"Error: {str(e)}"


async def extract_links(vision_llm, screenshot_b64):
    """Extract links from the navigation menu."""
    prompt = "Extract all navigation menu links from this webpage. For each link, provide the exact text label and what section of the website it likely leads to. Format your response as a numbered list with each item having the format: 'Link text: Purpose'. Only include main navigation links, not footer or sidebar links."

    try:
        result = await vision_llm.ask_with_images(
            messages=[{"role": "user", "content": prompt}],
            images=[{"base64": screenshot_b64}],
            stream=False,
            temperature=0.2,
        )

        # Parse the links from the result
        links = []
        for line in result.split("\n"):
            line = line.strip()
            if ":" in line and any(char.isdigit() for char in line[:3]):
                # Extract the link text (before the colon)
                link_text = line.split(":", 1)[0]
                # Remove any numbering or bullet points
                link_text = re.sub(r"^\d+\.\s*", "", link_text)
                link_text = link_text.strip()
                if link_text:
                    links.append(link_text)

        return links
    except Exception as e:
        logger.error(f"Link extraction failed: {e}")
        return []


async def click_link(browser_tool, link_text, current_url=None):
    """Click a link with the given text."""
    logger.info(f"Attempting to click link: {link_text}")

    try:
        # First try to find elements with text content
        context = await browser_tool._ensure_browser_initialized()
        page = await context.get_current_page()

        # Method 1: Try to find the link by text content
        elements = await page.query_selector_all("a")
        for i, element in enumerate(elements):
            text_content = await element.text_content()
            if link_text.lower() in text_content.lower():
                logger.info(f"Found link '{link_text}' at index {i}")
                await element.click()
                await page.wait_for_load_state()
                logger.info(f"Clicked on link: {link_text}")
                return True

        # Method 2: Try to find the link by using browser_tool's click_element action
        logger.info(f"Trying alternative method to click {link_text}...")
        # First get all clickable elements
        elements_result = await browser_tool.execute(
            action="extract_content",
            goal="List all clickable elements on the page with their text content",
        )

        if not elements_result.error:
            # Try to find the element index using the browser_use tool
            for i in range(10):  # Try the first 10 elements
                try:
                    # Try clicking each element
                    click_result = await browser_tool.execute(
                        action="click_element", index=i
                    )
                    if not click_result.error:
                        # Wait for page to load
                        await asyncio.sleep(1)

                        # Check if we're on a new page
                        new_url = await page.url()
                        if current_url and new_url != current_url:
                            logger.info(f"Successfully clicked element at index {i}")
                            return True

                        # Go back if needed
                        await browser_tool.execute(action="go_back")
                        await asyncio.sleep(0.5)
                except Exception as click_error:
                    logger.warning(f"Error clicking element {i}: {click_error}")
                    continue

        # Method 3: Try to use the navigation menu directly
        logger.info(f"Trying to navigate to {link_text} using menu...")
        nav_selector = "nav, header, .menu, .navigation, .navbar"
        nav_elements = await page.query_selector_all(nav_selector)

        for nav in nav_elements:
            links = await nav.query_selector_all("a")
            for link in links:
                text = await link.text_content()
                if link_text.lower() in text.lower():
                    await link.click()
                    await page.wait_for_load_state()
                    logger.info(f"Clicked on navigation link: {link_text}")
                    return True

        logger.warning(f"Could not find link with text: {link_text}")
        return False
    except Exception as e:
        logger.error(f"Error clicking link: {e}")
        return False


async def analyze_website(url: str = "https://example.com"):
    """Comprehensively analyze a website by navigating through its pages."""
    logger.info(f"Analyzing website: {url}")

    # Create browser tool
    browser_tool = BrowserUseTool()

    # Dictionary to store analysis results
    analysis_results = {}

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

        # Create vision LLM
        vision_llm = LLM("vision")
        logger.info(f"Using vision model: {vision_llm.model}")

        # Analyze homepage
        logger.info("Analyzing homepage...")
        homepage_screenshot = await take_screenshot(browser_tool)

        # Extract basic information
        logger.info("Extracting basic information...")
        basic_prompt = "Describe this webpage. What is the main content and purpose of this site? Extract key information."
        basic_info = await analyze_page_with_vision(
            vision_llm, homepage_screenshot, basic_prompt
        )

        print("\n=== HOMEPAGE CONTENT ===")
        print(basic_info)
        print("=======================\n")

        analysis_results["homepage"] = {"url": url, "basic_info": basic_info}

        # Extract navigation menu
        logger.info("Analyzing navigation menu...")
        nav_prompt = "Focus on the navigation menu of this website. List all main menu items and their purpose. What are the main sections of this website?"
        nav_info = await analyze_page_with_vision(
            vision_llm, homepage_screenshot, nav_prompt
        )

        print("\n=== NAVIGATION MENU ===")
        print(nav_info)
        print("=======================\n")

        analysis_results["navigation"] = nav_info

        # Extract contact information
        logger.info("Extracting contact information...")
        contact_prompt = "Focus on finding contact information on this webpage. Extract any phone numbers, email addresses, physical addresses, contact forms, or social media links."
        contact_info = await analyze_page_with_vision(
            vision_llm, homepage_screenshot, contact_prompt
        )

        print("\n=== CONTACT INFORMATION ===")
        print(contact_info)
        print("===========================\n")

        analysis_results["contact"] = contact_info

        # Extract links from the navigation menu
        logger.info("Extracting navigation links...")
        nav_links = await extract_links(vision_llm, homepage_screenshot)
        logger.info(f"Found navigation links: {nav_links}")

        # Navigate to each link and analyze the page
        for link in nav_links:
            if link.lower() in [
                "home",
                "homepage",
            ]:  # Skip home link as we've already analyzed it
                continue

            logger.info(f"Navigating to {link} page...")
            if await click_link(browser_tool, link, current_url=url):
                # Wait for page to load
                await asyncio.sleep(2)

                # Take screenshot of the page
                page_screenshot = await take_screenshot(browser_tool)

                # Analyze the page
                logger.info(f"Analyzing {link} page...")
                page_prompt = f"This is the {link} page of the website. Describe what this page contains and its purpose. Extract key information."
                page_info = await analyze_page_with_vision(
                    vision_llm, page_screenshot, page_prompt
                )

                print(f"\n=== {link.upper()} PAGE ===")
                print(page_info)
                print("=" * (len(link) + 11) + "\n")

                analysis_results[link.lower()] = {"info": page_info}

                # Go back to homepage
                logger.info("Returning to homepage...")
                await browser_tool.execute(action="go_to_url", url=url)
                await asyncio.sleep(1)
            else:
                logger.warning(f"Failed to navigate to {link} page")

        # Generate a summary of the website
        logger.info("Generating website summary...")
        summary_prompt = "Based on all the pages analyzed, provide a comprehensive summary of this website. What is its main purpose? What services or products does it offer? Who is the target audience? What is the overall design and user experience like?"

        # Prepare a context message with all the information gathered
        context_message = "I've analyzed the following pages of the website:\n\n"
        for page, info in analysis_results.items():
            if page == "homepage":
                context_message += f"Homepage: {info['basic_info']}\n\n"
            elif page == "navigation":
                context_message += f"Navigation: {info}\n\n"
            elif page == "contact":
                context_message += f"Contact Information: {info}\n\n"
            else:
                context_message += f"{page.capitalize()} Page: {info['info']}\n\n"

        context_message += summary_prompt

        # Use the LLM (not vision model) for the summary
        llm = LLM()
        summary = await llm.ask(
            messages=[{"role": "user", "content": context_message}],
            stream=False,
            temperature=0.2,
        )

        print("\n=== WEBSITE SUMMARY ===")
        print(summary)
        print("======================\n")

        # Keep browser open for manual inspection
        logger.info(
            "Analysis complete. Browser will remain open for manual inspection."
        )
        logger.info("Press Ctrl+C to exit...")

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Analysis interrupted by user.")

    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user.")
    except Exception as e:
        logger.error(f"Analysis failed with exception: {str(e)}")
        traceback.print_exc()
    finally:
        # Clean up browser
        logger.info("Cleaning up browser...")
        await browser_tool.cleanup()
        logger.info("Browser cleanup completed")


if __name__ == "__main__":
    # Get URL from command line argument or use default
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    # Run the analysis
    asyncio.run(analyze_website(url))
