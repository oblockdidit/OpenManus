#!/usr/bin/env python
"""
Advanced script to navigate through navbar links on a website using element labels.
This script uses the browser_use tool's capabilities to efficiently identify and navigate
through navbar elements based on their text content.
"""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.llm.llm import LLM
from app.logger import logger
from app.tool.browser_use_tool import BrowserUseTool


class NavbarExplorer:
    """Class for exploring website navigation using browser_use tool."""

    def __init__(self, url: str):
        """Initialize the NavbarExplorer."""
        self.url = url
        self.browser_tool = BrowserUseTool()
        self.homepage_url = url
        self.visited_pages = set()
        self.page_info = {}
        self.llm = LLM()

    async def initialize(self):
        """Initialize the browser and navigate to the homepage."""
        logger.info("Initializing browser...")
        await self.browser_tool._ensure_browser_initialized()
        logger.info("Browser initialized successfully")

        # Navigate to URL
        logger.info(f"Navigating to {self.url}...")
        result = await self.browser_tool.execute(action="go_to_url", url=self.url)

        if result.error:
            logger.error(f"Navigation failed: {result.error}")
            return False

        logger.info(f"Successfully navigated to {self.url}")
        await asyncio.sleep(2)  # Wait for page to load
        return True

    async def get_page_state(self) -> Dict[str, Any]:
        """Get the current page state including all interactive elements."""
        logger.info("Getting page state...")

        # First take a screenshot to ensure we have the latest state
        context = await self.browser_tool._ensure_browser_initialized()
        page = await context.get_current_page()

        # Get the current URL
        current_url = page.url

        # Get page title
        title_result = await self.browser_tool.execute(
            action="extract_content", goal="What is the title or heading of this page?"
        )
        page_title = title_result.output if not title_result.error else "Unknown Title"

        # Get all interactive elements
        elements_result = await self.browser_tool.execute(
            action="extract_content",
            goal="List all clickable elements on the page with their text content and approximate location (top, middle, bottom, header, footer, etc.)",
        )

        # Take a screenshot for reference
        screenshot_bytes = await page.screenshot()
        screenshot_path = Path(f"screenshot_{int(time.time())}.jpg")
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)

        return {
            "url": current_url,
            "title": page_title,
            "elements": elements_result.output if not elements_result.error else "",
            "screenshot_path": str(screenshot_path),
        }

    async def identify_navbar_elements(self) -> List[Dict[str, Any]]:
        """Identify navbar elements using visual analysis and DOM structure."""
        logger.info("Identifying navbar elements...")

        # Get the current page state
        state = await self.get_page_state()

        # Take a screenshot for vision model analysis
        context = await self.browser_tool._ensure_browser_initialized()
        page = await context.get_current_page()
        screenshot_bytes = await page.screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Use vision model to identify navbar elements
        vision_llm = LLM("vision")
        prompt = (
            "Identify all navigation menu elements on this webpage. "
            "For each navigation item, provide: \n"
            "1. The exact text label\n"
            "2. Its approximate position (top, header, sidebar, etc.)\n"
            "3. Whether it appears to be a main navigation item or a sub-item\n"
            "Format your response as a JSON array of objects with properties: "
            "'label', 'position', 'is_main_nav'. Only include actual navigation menu items."
        )

        try:
            nav_analysis = await vision_llm.ask_with_images(
                messages=[{"role": "user", "content": prompt}],
                images=[{"base64": screenshot_b64}],
                stream=False,
                temperature=0.2,
            )

            # Extract JSON from the response
            nav_items = self.extract_json_from_text(nav_analysis)
            if not nav_items:
                logger.warning(
                    "Could not parse JSON from vision model response. Using fallback method."
                )
                # Fallback to text-based extraction
                nav_items = await self.extract_navbar_links_from_text(state["elements"])

            logger.info(f"Identified {len(nav_items)} navbar elements")
            return nav_items

        except Exception as e:
            logger.error(f"Error identifying navbar elements: {e}")
            # Fallback to text-based extraction
            return await self.extract_navbar_links_from_text(state["elements"])

    def extract_json_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract JSON array from text response."""
        try:
            # Find JSON-like content in the text
            start_idx = text.find("[{")
            end_idx = text.rfind("}]") + 2

            if start_idx >= 0 and end_idx > start_idx:
                json_str = text[start_idx:end_idx]
                return json.loads(json_str)

            # Try another approach if the above fails
            import re

            json_pattern = r"\[\s*{[^\[\]]*}\s*(,\s*{[^\[\]]*}\s*)*\]"
            match = re.search(json_pattern, text)
            if match:
                return json.loads(match.group(0))

            return []
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            return []

    async def extract_navbar_links_from_text(
        self, elements_text: str
    ) -> List[Dict[str, Any]]:
        """Extract navbar links from text description of elements."""
        logger.info("Extracting navbar links from text...")

        # Use LLM to identify navbar links from the elements text
        prompt = (
            f"Below is a description of elements on a webpage. "
            f"Identify which elements are likely part of the main navigation menu. "
            f"Return your answer as a JSON array of objects with properties: "
            f"'label' (the exact text of the link), 'position' (where it appears on the page), "
            f"and 'is_main_nav' (true if it's a main navigation item, false if it's a sub-item).\n\n"
            f"{elements_text}"
        )

        try:
            response = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                temperature=0.2,
            )

            # Extract JSON from the response
            nav_items = self.extract_json_from_text(response)
            if not nav_items:
                # Simple fallback if JSON extraction fails
                nav_items = []
                for line in elements_text.split("\n"):
                    if any(
                        keyword in line.lower()
                        for keyword in ["menu", "nav", "header", "link"]
                    ):
                        parts = line.split(":")
                        if len(parts) > 1:
                            label = parts[1].strip()
                            if label and label.lower() not in ["home", "homepage"]:
                                nav_items.append(
                                    {
                                        "label": label,
                                        "position": "unknown",
                                        "is_main_nav": True,
                                    }
                                )

            return nav_items

        except Exception as e:
            logger.error(f"Error extracting navbar links from text: {e}")
            return []

    async def find_element_by_text(self, text: str) -> Optional[int]:
        """Find an element by its text content and return its index."""
        logger.info(f"Finding element with text: {text}")

        # Get the current page state to see all elements with their indices
        state_result = await self.browser_tool.execute(action="get_page_content")

        if state_result.error:
            logger.error(f"Failed to get page state: {state_result.error}")
            return None

        # Parse the state to find elements with matching text
        try:
            # The state might be returned as a string that needs parsing
            if isinstance(state_result.output, str):
                # Look for elements in the output
                lines = state_result.output.split("\n")
                for line in lines:
                    if "[" in line and "]" in line and text.lower() in line.lower():
                        # Extract the index from something like [0] Element text
                        index_str = line[line.find("[") + 1 : line.find("]")]
                        try:
                            return int(index_str)
                        except ValueError:
                            continue

            # If we couldn't find it in the text output, try a more direct approach
            # Try the first 15 elements (common for navigation items)
            for i in range(15):
                # Get element text using extract_content with a specific goal
                element_text_result = await self.browser_tool.execute(
                    action="extract_content",
                    goal=f"What is the text content of element with index {i}?",
                )

                if not element_text_result.error:
                    element_text = element_text_result.output
                    if text.lower() in element_text.lower():
                        return i

            return None
        except Exception as e:
            logger.error(f"Error finding element by text: {e}")
            return None

    async def click_navbar_item(self, item: Dict[str, Any]) -> bool:
        """Click on a navbar item based on its label."""
        label = item["label"]
        logger.info(f"Attempting to click navbar item: {label}")

        # Method 1: Try to find the element by text
        element_index = await self.find_element_by_text(label)
        if element_index is not None:
            logger.info(f"Found element with index {element_index} for label '{label}'")
            click_result = await self.browser_tool.execute(
                action="click_element", index=element_index
            )

            if not click_result.error:
                logger.info(f"Successfully clicked on '{label}'")
                await asyncio.sleep(2)  # Wait for page to load
                return True

        # Method 2: Try scrolling to the text and then clicking nearby elements
        logger.info(f"Trying to scroll to text: {label}")
        scroll_result = await self.browser_tool.execute(
            action="scroll_to_text", text=label
        )

        if not scroll_result.error:
            # Try clicking elements near where we scrolled
            for i in range(5):  # Try a few elements
                click_result = await self.browser_tool.execute(
                    action="click_element", index=i
                )
                if not click_result.error:
                    await asyncio.sleep(2)  # Wait for page to load

                    # Check if we navigated to a new page
                    page = await (
                        await self.browser_tool._ensure_browser_initialized()
                    ).get_current_page()
                    current_url = page.url
                    if current_url != self.url:
                        logger.info(
                            f"Successfully navigated to new page after clicking near '{label}'"
                        )
                        return True

                    # Go back if this wasn't the right page
                    await self.browser_tool.execute(action="go_back")
                    await asyncio.sleep(1)

        # Method 3: Systematic approach - try the first 15 elements
        logger.info(f"Trying systematic approach for '{label}'")
        for i in range(15):  # Navigation elements are often among the first elements
            try:
                click_result = await self.browser_tool.execute(
                    action="click_element", index=i
                )

                if not click_result.error:
                    await asyncio.sleep(2)  # Wait for page to load

                    # Check if we're on a new page
                    page = await (
                        await self.browser_tool._ensure_browser_initialized()
                    ).get_current_page()
                    current_url = page.url
                    if current_url != self.url:
                        # Check if the page title or content contains the label
                        title_result = await self.browser_tool.execute(
                            action="extract_content",
                            goal="What is the title or heading of this page?",
                        )

                        if (
                            not title_result.error
                            and label.lower() in title_result.output.lower()
                        ):
                            logger.info(f"Successfully navigated to {label} page")
                            return True

                    # Go back if this wasn't the right page
                    await self.browser_tool.execute(action="go_back")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"Error clicking element {i}: {e}")
                continue

        logger.warning(f"Failed to click navbar item: {label}")
        return False

    async def analyze_page(self, label: str) -> str:
        """Analyze the current page and return information about it."""
        logger.info(f"Analyzing page: {label}")

        # Take a screenshot for vision model analysis
        context = await self.browser_tool._ensure_browser_initialized()
        page = await context.get_current_page()
        screenshot_bytes = await page.screenshot()
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Use vision model to analyze the page
        vision_llm = LLM("vision")
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
            info_result = await self.browser_tool.execute(
                action="extract_content",
                goal=f"Describe what this {label} page contains and its purpose.",
            )

            if not info_result.error:
                return info_result.output
            else:
                return f"Failed to analyze {label} page: {info_result.error}"

    async def explore(self):
        """Explore the website by navigating through navbar links."""
        # Initialize browser and navigate to homepage
        if not await self.initialize():
            return

        # Identify navbar elements
        navbar_items = await self.identify_navbar_elements()

        if not navbar_items:
            logger.warning("No navbar elements found. Exiting.")
            return

        logger.info(
            f"Found {len(navbar_items)} navbar items: {[item['label'] for item in navbar_items]}"
        )

        # First analyze the homepage
        homepage_info = await self.analyze_page("Homepage")
        self.page_info["Homepage"] = {"url": self.url, "info": homepage_info}

        print("\n=== HOMEPAGE ===\n")
        print(homepage_info)
        print("=================\n")

        # Navigate to each navbar item
        for item in navbar_items:
            label = item["label"]

            # Skip if this is likely the home link or we've already visited
            if label.lower() in ["home", "homepage"] or label in self.visited_pages:
                continue

            # Navigate to the homepage first (to ensure consistent starting point)
            await self.browser_tool.execute(action="go_to_url", url=self.url)
            await asyncio.sleep(2)

            # Try to click the navbar item
            if await self.click_navbar_item(item):
                self.visited_pages.add(label)

                # Analyze the page
                page_info = await self.analyze_page(label)

                # Store the page info
                page = await (
                    await self.browser_tool._ensure_browser_initialized()
                ).get_current_page()
                current_url = page.url
                self.page_info[label] = {"url": current_url, "info": page_info}

                # Print the page info
                print(f"\n=== {label.upper()} PAGE ===\n")
                print(page_info)
                print("=" * (len(label) + 11) + "\n")

                # Go back to homepage
                await self.browser_tool.execute(action="go_to_url", url=self.url)
                await asyncio.sleep(2)

        # Generate a summary of the website
        await self.generate_website_summary()

    async def generate_website_summary(self):
        """Generate a summary of the website based on all pages visited."""
        logger.info("Generating website summary...")

        # Prepare a context message with all the information gathered
        context_message = "I've analyzed the following pages of the website:\n\n"

        for page, info in self.page_info.items():
            context_message += f"{page}: {info['info']}\n\n"

        context_message += "Based on all the pages analyzed, provide a comprehensive summary of this website. "
        context_message += (
            "What is its main purpose? What services or products does it offer? "
        )
        context_message += "Who is the target audience? What is the overall design and user experience like?"

        # Use the LLM for the summary
        try:
            summary = await self.llm.ask(
                messages=[{"role": "user", "content": context_message}],
                stream=False,
                temperature=0.2,
            )

            print("\n=== WEBSITE SUMMARY ===\n")
            print(summary)
            print("======================\n")
        except Exception as e:
            logger.error(f"Error generating website summary: {e}")

    async def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up resources...")
        await self.browser_tool.cleanup()
        logger.info("Browser cleanup completed")


async def navigate_navbar(url: str = "https://example.com"):
    """Navigate through navbar links on a website using the NavbarExplorer class."""
    explorer = NavbarExplorer(url)

    try:
        await explorer.explore()

        # Keep browser open for manual inspection
        logger.info(
            "Exploration complete. Browser will remain open for manual inspection."
        )
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
        await explorer.cleanup()


if __name__ == "__main__":
    # Get URL from command line argument or use default
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"

    # Run the exploration
    asyncio.run(navigate_navbar(url))
