from app.parser.tool_parser import parse_assistant_message
import json
import re
from typing import Dict, Any
from app.logger import logger

# Improved method for analyzing page content with XML tool calling support
async def _analyze_page_content(self, browser_tool: BrowserUseTool) -> Dict[str, Any]:
    """Analyze the content of the current page."""
    try:
        # Extract content using the browser tool
        content_result = await browser_tool.execute(
            action="extract_content",
            goal="Extract the main content of the page including title, headings, paragraphs, and meta description",
        )

        if not content_result or not hasattr(content_result, "output"):
            logger.warning("No content result from browser tool")
            return {}

        # Parse the result, handling both old and new formats
        try:
            # Try to parse as JSON first (standard format)
            output_text = content_result.output.replace("Extracted from page:", "").strip()
            logger.info(f"Content extraction output length: {len(output_text)}")
            
            try:
                # Try parsing as JSON first (standard output format)
                output_json = json.loads(output_text)
                content_text = output_json.get("extracted_content", {}).get("text", "")
                logger.info("Successfully parsed content as JSON")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info("JSON parsing failed, trying XML parsing")
                text_content, tool_calls = parse_assistant_message(output_text)
                
                # If we have tool calls, use the extract_content tool call
                content_text = ""
                for tool_call in tool_calls:
                    if tool_call.name == "extract_content":
                        content_text = tool_call.parameters.get("text", "")
                        logger.info("Found extract_content tool call in XML format")
                        break
                
                # If no relevant tool calls found, use the entire text
                if not content_text and text_content:
                    content_text = text_content
                    logger.info("Using text content from XML parsing")
                elif not content_text:
                    content_text = output_text
                    logger.info("Falling back to raw output text")
        except Exception as parsing_error:
            logger.error(f"Error parsing content extraction output: {parsing_error}")
            content_text = str(content_result.output)

        # Execute script to get content metrics
        state = await browser_tool.get_current_state()

        # Combine the information
        content_analysis = {
            "text_sample": (
                content_text[:500] + "..."
                if len(content_text) > 500
                else content_text
            ),
            "title": None,
            "description": None,
            "word_count": 0,
            "has_contact_info": False,
        }

        # Extract additional info from the state
        if state and hasattr(state, "output"):
            try:
                state_data = json.loads(state.output)
                content_analysis["title"] = state_data.get("title", "")
                content_analysis["url"] = state_data.get("url", "")
            except Exception as state_error:
                logger.error(f"Error parsing state data: {state_error}")

        # Extract structured data from content text
        if "title:" in content_text.lower():
            title_match = re.search(
                r"title:\s*([^\n]+)", content_text, re.IGNORECASE
            )
            if title_match:
                content_analysis["title"] = title_match.group(1).strip()

        if "description:" in content_text.lower():
            desc_match = re.search(
                r"description:\s*([^\n]+)", content_text, re.IGNORECASE
            )
            if desc_match:
                content_analysis["description"] = desc_match.group(1).strip()

        # Estimate word count
        content_analysis["word_count"] = len(content_text.split())

        # Check for contact information
        phone_pattern = r"[(]?[0-9]{3}[)]?[-. ]?[0-9]{3}[-. ]?[0-9]{4}"
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

        has_phone = bool(re.search(phone_pattern, content_text))
        has_email = bool(re.search(email_pattern, content_text))

        content_analysis["has_contact_info"] = has_phone or has_email

        logger.info(f"Finished content analysis: title={content_analysis.get('title', 'None')}, word_count={content_analysis.get('word_count', 0)}")
        return content_analysis

    except Exception as e:
        logger.error(f"Error analyzing page content: {str(e)}")
        return {}

# Similar updates needed for these methods:
async def _analyze_seo(self, browser_tool: BrowserUseTool) -> Dict[str, Any]:
    """Analyze SEO factors of the current page with XML tool calling support."""
    try:
        # Extract SEO data
        seo_result = await browser_tool.execute(
            action="extract_content",
            goal="Analyze SEO factors including meta tags, headings, links, and more",
        )

        if not seo_result or not hasattr(seo_result, "output"):
            return {}

        # Parse the result, handling both old and new formats
        try:
            # Try to parse as JSON first (standard format)
            output_text = seo_result.output.replace("Extracted from page:", "").strip()
            
            try:
                # Try parsing as JSON
                output_json = json.loads(output_text)
                seo_text = output_json.get("extracted_content", {}).get("text", "")
                logger.info("Successfully parsed SEO data as JSON")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info("JSON parsing failed for SEO data, trying XML parsing")
                text_content, tool_calls = parse_assistant_message(output_text)
                
                # If we have tool calls, use the extract_content tool call
                seo_text = ""
                for tool_call in tool_calls:
                    if tool_call.name == "extract_content":
                        seo_text = tool_call.parameters.get("text", "")
                        logger.info("Found extract_content tool call in XML format for SEO data")
                        break
                
                # If no relevant tool calls found, use the entire text
                if not seo_text and text_content:
                    seo_text = text_content
                elif not seo_text:
                    seo_text = output_text
        except Exception as parsing_error:
            logger.error(f"Error parsing SEO extraction output: {parsing_error}")
            seo_text = str(seo_result.output)

        # Rest of the existing _analyze_seo method...
        # [Keep the remaining code from the original method]
        
    except Exception as e:
        logger.error(f"Error analyzing SEO: {str(e)}")
        return {}

async def _test_mobile_compatibility(self, browser_tool: BrowserUseTool) -> Dict[str, Any]:
    """Test mobile compatibility of the current page with XML tool calling support."""
    try:
        # Check for mobile-specific meta tags and responsive elements
        mobile_result = await browser_tool.execute(
            action="extract_content",
            goal="Analyze mobile compatibility including viewport meta tag, responsive design elements, and touch targets",
        )

        if not mobile_result or not hasattr(mobile_result, "output"):
            return {}

        # Parse the result, handling both old and new formats
        try:
            # Try to parse as JSON first (standard format)
            output_text = mobile_result.output.replace("Extracted from page:", "").strip()
            
            try:
                # Try parsing as JSON
                output_json = json.loads(output_text)
                mobile_text = output_json.get("extracted_content", {}).get("text", "")
                logger.info("Successfully parsed mobile compatibility data as JSON")
            except json.JSONDecodeError:
                # If not valid JSON, try using XML parser
                logger.info("JSON parsing failed for mobile data, trying XML parsing")
                text_content, tool_calls = parse_assistant_message(output_text)
                
                # If we have tool calls, use the extract_content tool call
                mobile_text = ""
                for tool_call in tool_calls:
                    if tool_call.name == "extract_content":
                        mobile_text = tool_call.parameters.get("text", "")
                        logger.info("Found extract_content tool call in XML format for mobile data")
                        break
                
                # If no relevant tool calls found, use the entire text
                if not mobile_text and text_content:
                    mobile_text = text_content
                elif not mobile_text:
                    mobile_text = output_text
        except Exception as parsing_error:
            logger.error(f"Error parsing mobile extraction output: {parsing_error}")
            mobile_text = str(mobile_result.output)

        # Rest of the existing _test_mobile_compatibility method...
        # [Keep the remaining code from the original method]
        
    except Exception as e:
        logger.error(f"Error testing mobile compatibility: {str(e)}")
        return {
            "mobile_score": 40,
            "issues": ["Could not fully analyze mobile compatibility"],
        }
