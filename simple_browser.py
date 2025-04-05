#!/usr/bin/env python
"""
Simple browser script that directly uses the browser_use tool without LLM integration.
This script provides a simple command-line interface for browser actions.
"""

import asyncio
import sys
import re
from app.logger import logger
from app.tool.browser_use_tool import BrowserUseTool

class SimpleBrowser:
    """Simple browser interface that directly uses the browser_use tool."""
    
    def __init__(self):
        """Initialize the simple browser."""
        self.browser_tool = BrowserUseTool()
        self.initialized = False
    
    async def initialize(self):
        """Initialize the browser."""
        if not self.initialized:
            logger.info("Initializing browser...")
            await self.browser_tool._ensure_browser_initialized()
            self.initialized = True
            logger.info("Browser initialized successfully")
    
    async def cleanup(self):
        """Clean up browser resources."""
        if self.initialized:
            logger.info("Cleaning up browser...")
            await self.browser_tool.cleanup()
            self.initialized = False
            logger.info("Browser cleanup completed")
    
    async def execute_command(self, command):
        """Execute a browser command."""
        # Initialize browser if not already initialized
        await self.initialize()
        
        # Parse command
        if command.lower().startswith("go to "):
            # Extract URL
            url = command[6:].strip()
            # Add https:// if not present
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            logger.info(f"Navigating to {url}...")
            result = await self.browser_tool.execute(action="go_to_url", url=url)
            
            if result.error:
                logger.error(f"Navigation failed: {result.error}")
                return f"Failed to navigate to {url}: {result.error}"
            else:
                logger.info(f"Successfully navigated to {url}")
                return f"Successfully navigated to {url}"
        
        elif command.lower().startswith("extract "):
            # Extract content
            goal = command[8:].strip()
            
            logger.info(f"Extracting content with goal: {goal}")
            result = await self.browser_tool.execute(action="extract_content", goal=goal)
            
            if result.error:
                logger.error(f"Content extraction failed: {result.error}")
                return f"Failed to extract content: {result.error}"
            else:
                logger.info("Content extraction successful")
                return f"Extracted content:\n{result.output}"
        
        elif command.lower().startswith("click "):
            # Extract index
            try:
                index = int(command[6:].strip())
                
                logger.info(f"Clicking element at index {index}")
                result = await self.browser_tool.execute(action="click_element", index=index)
                
                if result.error:
                    logger.error(f"Click failed: {result.error}")
                    return f"Failed to click element: {result.error}"
                else:
                    logger.info(f"Successfully clicked element at index {index}")
                    return f"Successfully clicked element at index {index}"
            except ValueError:
                return "Invalid index. Please provide a number."
        
        elif command.lower() == "back":
            # Go back
            logger.info("Going back...")
            result = await self.browser_tool.execute(action="go_back")
            
            if result.error:
                logger.error(f"Go back failed: {result.error}")
                return f"Failed to go back: {result.error}"
            else:
                logger.info("Successfully went back")
                return "Successfully went back"
        
        elif command.lower() == "refresh":
            # Refresh page
            logger.info("Refreshing page...")
            result = await self.browser_tool.execute(action="refresh")
            
            if result.error:
                logger.error(f"Refresh failed: {result.error}")
                return f"Failed to refresh: {result.error}"
            else:
                logger.info("Successfully refreshed page")
                return "Successfully refreshed page"
        
        elif command.lower().startswith("scroll "):
            # Scroll
            direction = command[7:].strip().lower()
            
            if direction == "up":
                logger.info("Scrolling up...")
                result = await self.browser_tool.execute(action="scroll_up", scroll_amount=300)
            elif direction == "down":
                logger.info("Scrolling down...")
                result = await self.browser_tool.execute(action="scroll_down", scroll_amount=300)
            else:
                return "Invalid scroll direction. Use 'scroll up' or 'scroll down'."
            
            if result.error:
                logger.error(f"Scroll failed: {result.error}")
                return f"Failed to scroll: {result.error}"
            else:
                logger.info(f"Successfully scrolled {direction}")
                return f"Successfully scrolled {direction}"
        
        elif command.lower().startswith("input "):
            # Input text
            match = re.match(r"input (\d+) (.+)", command)
            if match:
                index = int(match.group(1))
                text = match.group(2)
                
                logger.info(f"Inputting text '{text}' at index {index}")
                result = await self.browser_tool.execute(action="input_text", index=index, text=text)
                
                if result.error:
                    logger.error(f"Input failed: {result.error}")
                    return f"Failed to input text: {result.error}"
                else:
                    logger.info(f"Successfully input text at index {index}")
                    return f"Successfully input text '{text}' at index {index}"
            else:
                return "Invalid input format. Use 'input INDEX TEXT'."
        
        elif command.lower() == "help":
            # Show help
            return """
Available commands:
- go to URL: Navigate to a URL
- extract GOAL: Extract content with a specific goal
- click INDEX: Click element at index
- back: Go back
- refresh: Refresh page
- scroll up/down: Scroll page
- input INDEX TEXT: Input text at element index
- help: Show this help
- exit: Exit the program
"""
        
        else:
            return "Unknown command. Type 'help' for available commands."

async def main():
    """Main function."""
    browser = SimpleBrowser()
    
    try:
        print("Simple Browser Interface")
        print("Type 'help' for available commands, 'exit' to quit")
        
        while True:
            command = input("\nEnter command: ")
            
            if command.lower() in ["exit", "quit", "q"]:
                break
            
            result = await browser.execute_command(command)
            print(result)
    
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
    finally:
        await browser.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
