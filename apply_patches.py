#!/usr/bin/env python
"""
Script to apply the XML tool calling patches to EnhancedWebsiteAnalyzer.
This script replaces specific methods in the EnhancedWebsiteAnalyzer class
with improved versions that support XML-based tool calling.
"""

import os
import re
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

def apply_parser_patches():
    """Apply the parser patches to the EnhancedWebsiteAnalyzer file."""
    print("Applying XML tool calling patches to EnhancedWebsiteAnalyzer...")
    
    # Paths
    analyzer_path = "app/tool/webdev/enhanced_website_analyzer.py"
    parser_path = "app/tool/webdev/enhanced_website_analyzer_parser.py"
    
    # Read files
    analyzer_content = read_file(analyzer_path)
    parser_content = read_file(parser_path)
    
    # Extract methods from parser content
    analyze_page_content_pattern = r"async def _analyze_page_content.*?return \{\}\n"
    analyze_seo_pattern = r"async def _analyze_seo.*?return \{\}\n"
    test_mobile_pattern = r"async def _test_mobile_compatibility.*?\}\n"
    
    # Extract methods using regex with DOTALL flag
    analyze_page_content = re.search(analyze_page_content_pattern, parser_content, re.DOTALL)
    analyze_seo = re.search(analyze_seo_pattern, parser_content, re.DOTALL)
    test_mobile = re.search(test_mobile_pattern, parser_content, re.DOTALL)
    
    if not analyze_page_content or not analyze_seo or not test_mobile:
        print("Error: Couldn't extract all methods from parser file")
        return
    
    # Update imports first
    import_statement = "from app.parser.tool_parser import parse_assistant_message"
    if import_statement not in analyzer_content:
        # Find the last import line
        import_lines = re.findall(r"^.*import.*$", analyzer_content, re.MULTILINE)
        if import_lines:
            last_import = import_lines[-1]
            analyzer_content = analyzer_content.replace(
                last_import, 
                f"{last_import}\n{import_statement}"
            )
    
    # Replace methods in analyzer content
    analyzer_content = re.sub(
        r"async def _analyze_page_content\(.*?\}\n\s+except Exception as e\:.*?return \{\}\n",
        analyze_page_content.group(0),
        analyzer_content,
        flags=re.DOTALL
    )
    
    analyzer_content = re.sub(
        r"async def _analyze_seo\(.*?\}\n\s+except Exception as e\:.*?return \{\}\n",
        analyze_seo.group(0),
        analyzer_content,
        flags=re.DOTALL
    )
    
    analyzer_content = re.sub(
        r"async def _test_mobile_compatibility\(.*?\}\n\s+except Exception as e\:.*?\}\n",
        test_mobile.group(0),
        analyzer_content,
        flags=re.DOTALL
    )
    
    # Save updated analyzer file
    write_file(analyzer_path, analyzer_content)
    print("Successfully applied XML tool calling patches to EnhancedWebsiteAnalyzer")

if __name__ == "__main__":
    # Get the project root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Apply patches
    apply_parser_patches()
    
    print("XML tool calling implementation complete!")
    print("\nTo test your changes, run:")
    print("  python scripts/test_xml_tool_calling.py")
    print("\nTo try the full lead analyzer with the changes:")
    print("  python analyze_by_id.py 0067ee5c-f920-4982-8b5d-69fc32039624")
