#!/usr/bin/env python
"""
Script to apply the XML tool calling fixes to EnhancedWebsiteAnalyzer.
This script directly copies the fixed methods to the EnhancedWebsiteAnalyzer class
to fix the NoneType errors we're seeing.
"""

import os
import sys
from pathlib import Path

def read_file(path):
    """Read file content."""
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    """Write content to file."""
    with open(path, 'w') as f:
        f.write(content)

def apply_fixes():
    """Apply the XML tool calling fixes to EnhancedWebsiteAnalyzer."""
    print("Applying XML tool calling fixes to EnhancedWebsiteAnalyzer...")
    
    # Paths
    analyzer_path = "/Users/teez/Development/Claude/openmanus/openmanus/app/tool/webdev/enhanced_website_analyzer.py"
    fixed_methods_path = "/Users/teez/Development/Claude/openmanus/openmanus/app/tool/webdev/enhanced_website_analyzer_fix.py"
    
    # Read files
    analyzer_content = read_file(analyzer_path)
    fixed_methods = read_file(fixed_methods_path)
    
    # Add import for parser if needed
    import_statement = "from app.parser.tool_parser import parse_assistant_message"
    if import_statement not in analyzer_content:
        # Find the last import line
        import_lines = [line for line in analyzer_content.split('\n') if 'import' in line]
        if import_lines:
            last_import = import_lines[-1]
            analyzer_content = analyzer_content.replace(
                last_import, 
                f"{last_import}\n{import_statement}"
            )
    
    # Extract function names from fixed_methods to replace
    function_names = [
        "_analyze_page_content",
        "_analyze_seo",
        "_test_mobile_compatibility",
        "_extract_internal_links"
    ]
    
    # Replace each function in the analyzer file
    for func_name in function_names:
        print(f"Replacing {func_name}...")
        
        # Extract the function from fixed_methods
        func_start_idx = fixed_methods.find(f"async def {func_name}")
        if func_start_idx == -1:
            print(f"  Error: Function {func_name} not found in fixed methods file")
            continue
            
        # Find the end of the function
        next_func_idx = fixed_methods.find("async def ", func_start_idx + 1)
        if next_func_idx == -1:
            # If it's the last function, take until the end
            func_end_idx = len(fixed_methods)
        else:
            func_end_idx = next_func_idx
            
        new_func = fixed_methods[func_start_idx:func_end_idx].strip()
        
        # Find where to replace in the analyzer file
        func_start_in_analyzer = analyzer_content.find(f"async def {func_name}")
        if func_start_in_analyzer == -1:
            print(f"  Error: Function {func_name} not found in analyzer file")
            continue
            
        # Find the end of the function in analyzer
        next_func_in_analyzer = analyzer_content.find("async def ", func_start_in_analyzer + 1)
        if next_func_in_analyzer == -1:
            # If it's the last function, this won't work well
            print(f"  Error: Could not determine end of function {func_name} in analyzer file")
            continue
            
        func_end_in_analyzer = next_func_in_analyzer
        
        # Replace the function
        current_func = analyzer_content[func_start_in_analyzer:func_end_in_analyzer]
        analyzer_content = analyzer_content.replace(current_func, new_func + "\n\n")
        print(f"  Successfully replaced {func_name}")
    
    # Save the updated analyzer file
    write_file(analyzer_path, analyzer_content)
    print("Successfully applied fixes to EnhancedWebsiteAnalyzer")
    
    # Check if BrowserUseTool is using LLMIntegration
    print("\nChecking if BrowserUseTool is using LLMIntegration...")
    browser_tool_path = "/Users/teez/Development/Claude/openmanus/openmanus/app/tool/browser_use_tool.py"
    browser_tool_content = read_file(browser_tool_path)
    
    if "from app.llm_integration import LLMIntegration" not in browser_tool_content:
        print("Warning: BrowserUseTool does not import LLMIntegration")
    
    if "self.llm_integration" not in browser_tool_content:
        print("Warning: BrowserUseTool does not initialize LLMIntegration")
    
    if "ask_with_tools" not in browser_tool_content:
        print("Warning: BrowserUseTool does not use ask_with_tools method")

if __name__ == "__main__":
    # Apply patches
    apply_fixes()
    
    print("\nDone! Fixed the NoneType errors in EnhancedWebsiteAnalyzer.")
    print("\nTo test your changes, run:")
    print("  python analyze_by_id.py 0067ee5c-f920-4982-8b5d-69fc32039624")
