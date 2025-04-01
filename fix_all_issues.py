#!/usr/bin/env python3
import os
import sys

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the fix functions
from fix_functions import fix_website_analyzer, fix_browser_use_tool, fix_tool_parser, fix_llm_integration

def main():
    print("Fixing OpenManus issues...")

    # Fix the EnhancedWebsiteAnalyzer
    fix_website_analyzer()

    # Fix the BrowserUseTool
    fix_browser_use_tool()

    # Ensure the tool parser is correct
    fix_tool_parser()

    # Ensure the LLM integration is correct
    fix_llm_integration()

    print("All fixes applied successfully!")

if __name__ == "__main__":
    main()
