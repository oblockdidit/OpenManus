#!/usr/bin/env python
"""
Run the MCP server for OpenManus.
"""

import asyncio
import importlib
import logging
import os
import sys

# Ensure correct paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)

# Import the MCP server module
from app.mcp.server import MCPServer
from app.tool.browser_use_tool import BrowserUseTool
from app.tool.terminate import Terminate
from app.tool.webdev.enhanced_website_analyzer import WebsiteAnalyzer


def main():
    """Main entry point for running the MCP server."""
    # Create and run server
    server = MCPServer()

    # Explicitly register WebsiteAnalyzer and other important tools
    server.register_tool(WebsiteAnalyzer())
    server.register_tool(BrowserUseTool())
    server.register_tool(Terminate())

    # Run server in stdio mode (for communication with clients)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
