
import os
import sys
import shutil
from pathlib import Path

def read_file(path):
    \"\"\"Read file content.\"\"\"
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    \"\"\"Write content to file.\"\"\"
    with open(path, 'w') as f:
        f.write(content)

def get_project_root():
    \"\"\"Get the project root directory.\"\"\"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return script_dir

def fix_enhanced_website_analyzer():
    \"\"\"Apply null safety fixes to EnhancedWebsiteAnalyzer methods.\"\"\"
    print(\"Fixing EnhancedWebsiteAnalyzer null safety issues...\")

    enhanced_website_analyzer_path = os.path.join(get_project_root(), \"app/tool/webdev/enhanced_website_analyzer.py\")
    fixed_methods_path = os.path.join(get_project_root(), \"app/tool/webdev/enhanced_website_analyzer_fix.py\")

    # Read the website analyzer file
    analyzer_content = read_file(enhanced_website_analyzer_path)

    # Add import for parser if needed
    import_statement = \"from app.parser.tool_parser import parse_assistant_message\"
    if import_statement not in analyzer_content:
        # Find the last import line
        import_lines = analyzer_content.split('\
')
        last_import_idx = 0
        for i, line in enumerate(import_lines):
            if 'import' in line and not line.startswith('#'):
                last_import_idx = i

        # Insert the import after the last import line
        import_lines.insert(last_import_idx + 1, import_statement)
        analyzer_content = '\
'.join(import_lines)

    # Update the file with the enhanced null-checking methods
    if os.path.exists(fixed_methods_path):
        print(\"Using existing fixed methods file\")
        fixed_methods_content = read_file(fixed_methods_path)
    else:
        print(\"Creating fixed methods file with enhanced null-checking...\")
        fixed_methods_content = \"\"\"from app.parser.tool_parser import parse_assistant_message
import json
import re
from typing import Dict, Any, List
from app.logger import logger

# Improved _extract_internal_links method with better null-checking
async def _extract_internal_links(self, browser_tool, domain: str) -> List[str]:
    \\\"\\\"\\\"Extract internal links from the current page with better null-checking.\\\"\\\"\\\"
    try:
        # Extract all links using JavaScript
        page_info = await browser_tool.execute(
            action=\"extract_content\",
            goal=\"Extract all links (a href) from the page\",
        )

        # Return empty list if no result or error in result
        if not page_info or hasattr(page_info, \"error\") and page_info.error:
            logger.warning(f\"No content to extract links from or error occurred: {getattr(page_info, 'error', 'Unknown error')}\")
            return []

        # Handle missing output attribute
        if not hasattr(page_info, \"output\") or not page_info.output:
            logger.warning(\"No output attribute in page_info\")
            return []

        # Parse the result, handling multiple formats
        content_text = \"\"
        try:
            # Try to parse as JSON first
            output_text = page_info.output.replace(\"Extracted from page:\", \"\").strip()

            try:
                output_json = json.loads(output_text)
                content_text = output_json.get(\"extracted_content\", {}).get(\"text\", \"\")
                logger.info(f\"Successfully parsed links content as JSON: {len(content_text)} chars\")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info(\"JSON parsing failed for links, trying XML parsing\")
                text_content, tool_calls = parse_assistant_message(output_text)

                # If we have tool calls, use the extract_content tool call
                for tool_call in tool_calls:
                    if tool_call.name == \"extract_content\":
                        content_text = tool_call.parameters.get(\"text\", \"\")
                        logger.info(f\"Found extract_content tool call in XML format for links: {len(content_text)} chars\")
                        break

                # If no relevant tool calls found, use the text content or raw output
                if not content_text and text_content:
                    content_text = text_content
                    logger.info(f\"Using text content from XML parsing: {len(content_text)} chars\")
                elif not content_text:
                    content_text = output_text
                    logger.info(f\"Falling back to raw output text for links: {len(output_text)} chars\")

        except Exception as parsing_error:
            logger.error(f\"Error parsing links content: {parsing_error}\")
            # Fallback to raw output or empty string
            content_text = str(page_info.output) if page_info.output else \"\"
            logger.info(f\"Using fallback content for links: {len(content_text)} chars\")

        # Make sure content_text is a string
        if not isinstance(content_text, str):
            logger.warning(f\"content_text is not a string: {type(content_text)}\")
            content_text = str(content_text)

        # Use regex to extract URLs
        url_pattern = r\"https?://(?:[-\\w.]|(?:%[\\da-fA-F]{2}))+\"
        urls = re.findall(url_pattern, content_text)

        # Filter for internal links only
        internal_links = [url for url in urls if domain in url]

        # Remove duplicates
        unique_links = list(set(internal_links))
        logger.info(f\"Found {len(unique_links)} unique internal links\")

        return unique_links

    except Exception as e:
        logger.error(f\"Error extracting links: {str(e)}\")
        return []

# Improved _analyze_page_content method with better null-checking
async def _analyze_page_content(self, browser_tool) -> Dict[str, Any]:
    \\\"\\\"\\\"Analyze the content of the current page with better null-checking.\\\"\\\"\\\"
    try:
        # Extract content using the browser tool
        content_result = await browser_tool.execute(
            action=\"extract_content\",
            goal=\"Extract the main content of the page including title, headings, paragraphs, and meta description\",
        )

        # Return empty dict if no result or error in result
        if not content_result or hasattr(content_result, \"error\") and content_result.error:
            logger.warning(f\"No content or error occurred: {getattr(content_result, 'error', 'Unknown error')}\")
            return {}

        # Handle missing output attribute
        if not hasattr(content_result, \"output\") or not content_result.output:
            logger.warning(\"No output attribute in content_result\")
            return {}

        # Parse the result, handling multiple formats
        content_text = \"\"
        try:
            # Try to parse as JSON first (standard format)
            output_text = content_result.output.replace(\"Extracted from page:\", \"\").strip()
            logger.info(f\"Content extraction output length: {len(output_text)}\")

            try:
                # Try parsing as JSON first (standard output format)
                output_json = json.loads(output_text)
                content_text = output_json.get(\"extracted_content\", {}).get(\"text\", \"\")
                logger.info(\"Successfully parsed content as JSON\")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info(\"JSON parsing failed, trying XML parsing\")
                text_content, tool_calls = parse_assistant_message(output_text)

                # If we have tool calls, use the extract_content tool call
                for tool_call in tool_calls:
                    if tool_call.name == \"extract_content\":
                        content_text = tool_call.parameters.get(\"text\", \"\")
                        logger.info(\"Found extract_content tool call in XML format\")
                        break

                # If no relevant tool calls found, use the entire text
                if not content_text and text_content:
                    content_text = text_content
                    logger.info(\"Using text content from XML parsing\")
                elif not content_text:
                    content_text = output_text
                    logger.info(\"Falling back to raw output text\")

        except Exception as parsing_error:
            logger.error(f\"Error parsing content extraction output: {parsing_error}\")
            # Fallback to raw output or empty string
            content_text = str(content_result.output) if content_result.output else \"\"
            logger.info(f\"Using fallback content: {len(content_text)} chars\")

        # Make sure content_text is a string
        if not isinstance(content_text, str):
            logger.warning(f\"content_text is not a string: {type(content_text)}\")
            content_text = str(content_text)

        # Execute script to get content metrics
        state = await browser_tool.get_current_state()

        # Combine the information
        content_analysis = {
            \"text_sample\": (
                content_text[:500] + \"...\"
                if len(content_text) > 500
                else content_text
            ),
            \"title\": None,
            \"description\": None,
            \"word_count\": 0,
            \"has_contact_info\": False,
        }

        # Extract additional info from the state
        if state and hasattr(state, \"output\"):
            try:
                state_data = json.loads(state.output)
                content_analysis[\"title\"] = state_data.get(\"title\", \"\")
                content_analysis[\"url\"] = state_data.get(\"url\", \"\")
            except Exception as state_error:
                logger.error(f\"Error parsing state data: {state_error}\")

        # Extract structured data from content text
        if content_text and \"title:\" in content_text.lower():
            title_match = re.search(
                r\"title:\\s*([^\
]+)\", content_text, re.IGNORECASE
            )
            if title_match:
                content_analysis[\"title\"] = title_match.group(1).strip()

        if content_text and \"description:\" in content_text.lower():
            desc_match = re.search(
                r\"description:\\s*([^\
]+)\", content_text, re.IGNORECASE
            )
            if desc_match:
                content_analysis[\"description\"] = desc_match.group(1).strip()

        # Estimate word count
        content_analysis[\"word_count\"] = len(content_text.split())

        # Check for contact information
        phone_pattern = r\"[(]?[0-9]{3}[)]?[-. ]?[0-9]{3}[-. ]?[0-9]{4}\"
        email_pattern = r\"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}\"

        has_phone = bool(re.search(phone_pattern, content_text))
        has_email = bool(re.search(email_pattern, content_text))

        content_analysis[\"has_contact_info\"] = has_phone or has_email

        logger.info(f\"Finished content analysis: title={content_analysis.get('title', 'None')}, word_count={content_analysis.get('word_count', 0)}\")
        return content_analysis

    except Exception as e:
        logger.error(f\"Error analyzing page content: {str(e)}\")
        return {}

# Improved _analyze_seo method with better null-checking
async def _analyze_seo(self, browser_tool) -> Dict[str, Any]:
    \\\"\\\"\\\"Analyze SEO factors of the current page with better null-checking.\\\"\\\"\\\"
    try:
        # Extract SEO data
        seo_result = await browser_tool.execute(
            action=\"extract_content\",
            goal=\"Analyze SEO factors including meta tags, headings, links, and more\",
        )

        # Return empty dict if no result or error in result
        if not seo_result or hasattr(seo_result, \"error\") and seo_result.error:
            logger.warning(f\"No SEO content or error occurred: {getattr(seo_result, 'error', 'Unknown error')}\")
            return {}

        # Handle missing output attribute
        if not hasattr(seo_result, \"output\") or not seo_result.output:
            logger.warning(\"No output attribute in seo_result\")
            return {}

        # Parse the result, handling multiple formats
        seo_text = \"\"
        try:
            # Try to parse as JSON first
            output_text = seo_result.output.replace(\"Extracted from page:\", \"\").strip()

            try:
                output_json = json.loads(output_text)
                seo_text = output_json.get(\"extracted_content\", {}).get(\"text\", \"\")
                logger.info(f\"Successfully parsed SEO data as JSON: {len(seo_text)} chars\")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info(\"JSON parsing failed for SEO data, trying XML parsing\")
                text_content, tool_calls = parse_assistant_message(output_text)

                # If we have tool calls, use the extract_content tool call
                for tool_call in tool_calls:
                    if tool_call.name == \"extract_content\":
                        seo_text = tool_call.parameters.get(\"text\", \"\")
                        logger.info(f\"Found extract_content tool call in XML format for SEO: {len(seo_text)} chars\")
                        break

                # If no relevant tool calls found, use the text content or raw output
                if not seo_text and text_content:
                    seo_text = text_content
                    logger.info(f\"Using text content from XML parsing for SEO: {len(text_content)} chars\")
                elif not seo_text:
                    seo_text = output_text
                    logger.info(f\"Falling back to raw output text for SEO: {len(output_text)} chars\")

        except Exception as parsing_error:
            logger.error(f\"Error parsing SEO content: {parsing_error}\")
            # Fallback to raw output or empty string
            seo_text = str(seo_result.output) if seo_result.output else \"\"
            logger.info(f\"Using fallback content for SEO: {len(seo_text)} chars\")

        # Make sure seo_text is a string
        if not isinstance(seo_text, str):
            logger.warning(f\"seo_text is not a string: {type(seo_text)}\")
            seo_text = str(seo_text)

        # State for additional info
        state = await browser_tool.get_current_state()

        # Build SEO analysis
        seo_analysis = {
            \"has_title\": False,
            \"title_length\": 0,
            \"has_meta_description\": False,
            \"meta_description_length\": 0,
            \"has_h1\": False,
            \"has_exactly_one_h1\": False,
            \"images_with_alt_text_percent\": 0,
            \"has_mobile_viewport\": False,
            \"is_https\": False,
            \"has_social_tags\": False,
            \"issues\": [],
        }

        # Get page URL from state
        if state and hasattr(state, \"output\"):
            try:
                state_data = json.loads(state.output)
                url = state_data.get(\"url\", \"\")
                seo_analysis[\"is_https\"] = url.startswith(\"https://\")
            except Exception:
                pass

        # Extract data from SEO text
        if seo_text and \"title:\" in seo_text.lower():
            title_match = re.search(r\"title:\\s*([^\
]+)\", seo_text, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
                seo_analysis[\"has_title\"] = bool(title)
                seo_analysis[\"title_length\"] = len(title)

        if seo_text and \"description:\" in seo_text.lower():
            desc_match = re.search(
                r\"description:\\s*([^\
]+)\", seo_text, re.IGNORECASE
            )
            if desc_match:
                desc = desc_match.group(1).strip()
                seo_analysis[\"has_meta_description\"] = bool(desc)
                seo_analysis[\"meta_description_length\"] = len(desc)

        if seo_text and \"h1\" in seo_text.lower():
            seo_analysis[\"has_h1\"] = (
                \"h1\" in seo_text.lower() and not \"no h1\" in seo_text.lower()
            )
            seo_analysis[\"has_exactly_one_h1\"] = (
                \"exactly one h1\" in seo_text.lower()
                or \"single h1\" in seo_text.lower()
            )

        if seo_text and \"viewport\" in seo_text.lower():
            seo_analysis[\"has_mobile_viewport\"] = (
                \"viewport\" in seo_text.lower()
                and not \"no viewport\" in seo_text.lower()
            )

        if seo_text and (\"og:\" in seo_text.lower() or \"open graph\" in seo_text.lower()):
            seo_analysis[\"has_social_tags\"] = True

        # Generate SEO issues
        issues = []

        if not seo_analysis[\"has_title\"] or seo_analysis[\"title_length\"] < 10:
            issues.append(\"Missing or too short page title\")
        elif seo_analysis[\"title_length\"] > 70:
            issues.append(\"Page title too long (over 70 characters)\")

        if not seo_analysis[\"has_meta_description\"]:
            issues.append(\"Missing meta description\")
        elif seo_analysis[\"meta_description_length\"] < 50:
            issues.append(\"Meta description too short (under 50 characters)\")
        elif seo_analysis[\"meta_description_length\"] > 160:
            issues.append(\"Meta description too long (over 160 characters)\")

        if not seo_analysis[\"has_h1\"]:
            issues.append(\"Missing H1 heading\")
        elif not seo_analysis[\"has_exactly_one_h1\"]:
            issues.append(\"Multiple H1 headings (should have exactly one)\")

        if not seo_analysis[\"has_mobile_viewport\"]:
            issues.append(\"Missing mobile viewport meta tag\")

        if not seo_analysis[\"is_https\"]:
            issues.append(\"Not using HTTPS\")

        if not seo_analysis[\"has_social_tags\"]:
            issues.append(\"Missing social media meta tags (Open Graph/Twitter)\")

        seo_analysis[\"issues\"] = issues

        return seo_analysis

    except Exception as e:
        logger.error(f\"Error analyzing SEO: {str(e)}\")
        return {}

# Improved _test_mobile_compatibility method with better null-checking
async def _test_mobile_compatibility(self, browser_tool) -> Dict[str, Any]:
    \\\"\\\"\\\"Test mobile compatibility of the current page with better null-checking.\\\"\\\"\\\"
    try:
        # Check for mobile-specific meta tags and responsive elements
        mobile_result = await browser_tool.execute(
            action=\"extract_content\",
            goal=\"Analyze mobile compatibility including viewport meta tag, responsive design elements, and touch targets\",
        )

        # Return default dict if no result or error in result
        if not mobile_result or hasattr(mobile_result, \"error\") and mobile_result.error:
            logger.warning(f\"No mobile compatibility content or error occurred: {getattr(mobile_result, 'error', 'Unknown error')}\")
            return {
                \"mobile_score\": 40,
                \"issues\": [\"Could not fully analyze mobile compatibility\"],
            }

        # Handle missing output attribute
        if not hasattr(mobile_result, \"output\") or not mobile_result.output:
            logger.warning(\"No output attribute in mobile_result\")
            return {
                \"mobile_score\": 40,
                \"issues\": [\"Could not fully analyze mobile compatibility\"],
            }

        # Parse the result, handling multiple formats
        mobile_text = \"\"
        try:
            # Try to parse as JSON first
            output_text = mobile_result.output.replace(\"Extracted from page:\", \"\").strip()

            try:
                output_json = json.loads(output_text)
                mobile_text = output_json.get(\"extracted_content\", {}).get(\"text\", \"\")
                logger.info(f\"Successfully parsed mobile compatibility data as JSON: {len(mobile_text)} chars\")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info(\"JSON parsing failed for mobile data, trying XML parsing\")
                text_content, tool_calls = parse_assistant_message(output_text)

                # If we have tool calls, use the extract_content tool call
                for tool_call in tool_calls:
                    if tool_call.name == \"extract_content\":
                        mobile_text = tool_call.parameters.get(\"text\", \"\")
                        logger.info(f\"Found extract_content tool call in XML format for mobile: {len(mobile_text)} chars\")
                        break

                # If no relevant tool calls found, use the text content or raw output
                if not mobile_text and text_content:
                    mobile_text = text_content
                    logger.info(f\"Using text content from XML parsing for mobile: {len(text_content)} chars\")
                elif not mobile_text:
                    mobile_text = output_text
                    logger.info(f\"Falling back to raw output text for mobile: {len(output_text)} chars\")

        except Exception as parsing_error:
            logger.error(f\"Error parsing mobile content: {parsing_error}\")
            # Fallback to raw output or empty string
            mobile_text = str(mobile_result.output) if mobile_result.output else \"\"
            logger.info(f\"Using fallback content for mobile: {len(mobile_text)} chars\")

        # Make sure mobile_text is a string
        if not isinstance(mobile_text, str):
            logger.warning(f\"mobile_text is not a string: {type(mobile_text)}\")
            mobile_text = str(mobile_text)

        # Build mobile compatibility analysis
        mobile_analysis = {
            \"has_viewport_meta\": False,
            \"has_responsive_design\": False,
            \"uses_media_queries\": False,
            \"has_touch_friendly_elements\": False,
            \"mobile_score\": 0,
            \"issues\": [],
        }

        # Extract mobile compatibility data from text if we have text
        if mobile_text:
            if \"viewport\" in mobile_text.lower():
                mobile_analysis[\"has_viewport_meta\"] = (
                    \"viewport\" in mobile_text.lower()
                    and not \"no viewport\" in mobile_text.lower()
                )

            if \"responsive\" in mobile_text.lower():
                mobile_analysis[\"has_responsive_design\"] = (
                    \"responsive\" in mobile_text.lower()
                    and not \"not responsive\" in mobile_text.lower()
                )

            if \"media queries\" in mobile_text.lower() or \"@media\" in mobile_text:
                mobile_analysis[\"uses_media_queries\"] = True

        # Generate mobile issues
        issues = []

        if not mobile_analysis[\"has_viewport_meta\"]:
            issues.append(\"Missing viewport meta tag\")

        if not mobile_analysis[\"has_responsive_design\"]:
            issues.append(\"No responsive design elements detected\")

        if not mobile_analysis[\"uses_media_queries\"]:
            issues.append(\"No CSS media queries detected for responsive layouts\")

        # Calculate mobile score (0-100)
        score = 0
        if mobile_analysis[\"has_viewport_meta\"]:
            score += 40
        if mobile_analysis[\"has_responsive_design\"]:
            score += 40
        if mobile_analysis[\"uses_media_queries\"]:
            score += 20

        mobile_analysis[\"mobile_score\"] = score
        mobile_analysis[\"issues\"] = issues

        return mobile_analysis

    except Exception as e:
        logger.error(f\"Error testing mobile compatibility: {str(e)}\")
        return {
            \"mobile_score\": 40,
            \"issues\": [\"Could not fully analyze mobile compatibility\"],
        }\"\"\"

        # Create the file
        os.makedirs(os.path.dirname(fixed_methods_path), exist_ok=True)
        write_file(fixed_methods_path, fixed_methods_content)

    # Method names to replace
    method_names = [
        \"_analyze_page_content\",
        \"_analyze_seo\",
        \"_test_mobile_compatibility\",
        \"_extract_internal_links\"
    ]

    # Find and replace each method
    for method_name in method_names:
        print(f\"Replacing method: {method_name}\")

        # Find the method in the fixed content
        method_start_pattern = f\"async def {method_name}\"
        method_start_idx = fixed_methods_content.find(method_start_pattern)

        if method_start_idx == -1:
            print(f\"  Could not find method {method_name} in fixed content\")
            continue

        # Find the end of the method
        next_method_idx = fixed_methods_content.find(\"async def \", method_start_idx + 1)
        if next_method_idx == -1:
            method_end_idx = len(fixed_methods_content)
        else:
            method_end_idx = next_method_idx

        # Extract the fixed method
        fixed_method = fixed_methods_content[method_start_idx:method_end_idx].strip()

        # Find the method in the analyzer content
        method_pattern = f\"async def {method_name}.*?return.*?\
\\s*except Exception as e:.*?return.*?\
\"
        import re
        analyzer_method_match = re.search(method_pattern, analyzer_content, re.DOTALL)

        if not analyzer_method_match:
            print(f\"  Could not find method {method_name} in analyzer content\")
            continue

        # Replace the method
        analyzer_content = analyzer_content.replace(analyzer_method_match.group(0), fixed_method + \"\
\
\")
        print(f\"  Successfully replaced method {method_name}\")

    # Save the updated analyzer content
    write_file(enhanced_website_analyzer_path, analyzer_content)
    print(\"Successfully applied fixes to EnhancedWebsiteAnalyzer\")

def update_browser_use_tool():
    \"\"\"Update BrowserUseTool to use LLMIntegration.\"\"\"
    print(\"Updating BrowserUseTool to use LLMIntegration...\")

    browser_tool_path = os.path.join(get_project_root(), \"app/tool/browser_use_tool.py\")

    # Read the browser tool file
    browser_tool_content = read_file(browser_tool_path)

    # Add import for LLMIntegration if needed
    import_statement = \"from app.llm_integration import LLMIntegration\"
    if import_statement not in browser_tool_content:
        # Add the import after the LLM import
        browser_tool_content = browser_tool_content.replace(
            \"from app.llm import LLM\",
            \"from app.llm import LLM\
from app.llm_integration import LLMIntegration\"
        )

    # Add parser import
    parser_import = \"from app.parser.tool_parser import parse_assistant_message\"
    if parser_import not in browser_tool_content:
        # Add the import after the LLM import
        browser_tool_content = browser_tool_content.replace(
            \"from app.llm import LLM\",
            \"from app.llm import LLM\
from app.parser.tool_parser import parse_assistant_message\"
        )

    # Add LLMIntegration field
    llm_integration_field = \"llm_integration: Optional[LLMIntegration] = Field(\
        default_factory=lambda: LLMIntegration(\\\"openrouter\\\")\
    )\"
    if \"llm_integration\" not in browser_tool_content:
        # Add the field after the LLM field
        browser_tool_content = browser_tool_content.replace(
            \"llm: Optional[LLM] = Field(default_factory=LLM)\",
            \"llm: Optional[LLM] = Field(default_factory=lambda: LLM(\\\"openrouter\\\"))\
    \" + llm_integration_field
        )

    # Update the extract_content method to use LLMIntegration
    extract_content_pattern = r\"async def _extract_content\\(.*?\\)\\:\"
    extract_content_match = re.search(extract_content_pattern, browser_tool_content, re.DOTALL)

    if not extract_content_match:
        print(\"  Could not find _extract_content method\")
    else:
        # Find the method body to replace
        method_start = extract_content_match.start()

        # Find where the extract_content method ends (start of next method)
        next_method_pattern = r\"async def _\"
        next_method_match = re.search(next_method_pattern, browser_tool_content[method_start + 10:], re.DOTALL)

        if next_method_match:
            method_end = method_start + 10 + next_method_match.start()

            # Extract the current method
            current_method = browser_tool_content[method_start:method_end]

            # Check if the method is already using LLMIntegration
            if \"self.llm_integration.ask_with_tools\" in current_method:
                print(\"  _extract_content method is already using LLMIntegration\")
            else:
                print(\"  Updating _extract_content method to use LLMIntegration\")

                # Replace the method with a version that uses LLMIntegration
                new_method = \"\"\"async def _extract_content(self, goal: str = None):
        \\\"\\\"\\\"Extract content from the current page using XML-based tool calling.\\\"\\\"\\\"
        if not self.browser_state:
            return {\\\"error\\\": \\\"Browser not initialized. Call go_to_url first.\\\"}

        logger.info(f\\\"Extracting content with goal: {goal}\\\")

        try:
            # Get the page content
            page = await self.context.get_current_page()
            import markdownify
            content = markdownify.markdownify(await page.content())

            # Max content length from config or default
            max_content_length = getattr(
                config.browser_config, \"max_content_length\", 2000
            )

            # Use XML-based tool calling for content extraction
            system_message = f\\\"\\\"\\\"\\\\
You are a helpful browser assistant that extracts content from web pages.
Your task is to analyze the content of a web page and extract information based on the user's goal.

Current page URL: {await page.url()}
Current page title: {await page.title()}

IMPORTANT: When providing extracted information, format your response using XML tags:
<extract_content>
<text>The extracted information here...</text>
</extract_content>

For example, if asked to extract a phone number, respond like:
<extract_content>
<text>I found the phone number: 555-123-4567</text>
</extract_content>

DO NOT use any other format for providing the extracted content.
\\\"\\\"\\\"

            user_message = f\\\"Extract the following information from the current page: {goal}\\\
\\\
Page content:\\\
{content[:max_content_length]}\\\"

            messages = [
                {\\\"role\\\": \\\"system\\\", \\\"content\\\": system_message},
                {\\\"role\\"
}
