#!/usr/bin/env python
"""Test script to verify our fixes."""

import sys
import os

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that the imports work correctly."""
    try:
        # Try importing from app.llm.openrouter_provider
        from app.llm.openrouter_provider import generate_openrouter_response
        print("✅ Successfully imported from app.llm.openrouter_provider")
    except ImportError as e:
        print(f"❌ Failed to import from app.llm.openrouter_provider: {e}")
        return False

    try:
        # Try importing ToolError from app.exceptions
        from app.exceptions import ToolError
        print("✅ Successfully imported ToolError from app.exceptions")
    except ImportError as e:
        print(f"❌ Failed to import ToolError from app.exceptions: {e}")
        return False

    try:
        # Try importing from app.parser
        from app.parser import parse_assistant_message
        print("✅ Successfully imported from app.parser")
    except ImportError as e:
        print(f"❌ Failed to import from app.parser: {e}")
        return False

    return True

if __name__ == "__main__":
    print("Testing OpenManus fixes...")
    success = test_imports()
    if success:
        print("\nAll tests passed! 🎉")
        sys.exit(0)
    else:
        print("\nSome tests failed. 😞")
        sys.exit(1)
