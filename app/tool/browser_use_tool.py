import asyncio
import base64
import json
import re
from typing import Any, Dict, Generic, List, Optional, TypeVar

from browser_use import Browser as BrowserUseBrowser
from browser_use import BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from browser_use.dom.service import DomService
from pydantic import Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from app.config import config
from app.llm import LLM
from app.llm_integration import LLMIntegration
from app.logger import logger
from app.parser.tool_parser import parse_assistant_message
from app.tool.base import BaseTool, ToolResult
from app.tool.web_search import WebSearch

_BROWSER_DESCRIPTION = """
Interact with a web browser using these tools:

Navigation Actions:
- go_to_url: Visit a URL
- go_back: Go back
- refresh: Reload page
- web_search: Search query

Element Actions:
- click_element: Click element by index
- input_text: Enter text
- scroll_down/scroll_up: Scroll page
- scroll_to_text: Scroll to text
- send_keys: Send keys
- get_dropdown_options: List dropdown
- select_dropdown_option: Select dropdown

Content Actions:
- extract_content: Extract page info with a specific goal
- get_page_content: Get and analyze current page content

Tab Actions:
- switch_tab: Switch tab
- open_tab: Open new tab
- close_tab: Close tab

Utility:
- wait: Pause for seconds
"""

Context = TypeVar("Context")


class BrowserUseTool(BaseTool, Generic[Context]):
    name: str = "browser_use"
    description: str = _BROWSER_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "go_to_url",
                    "click_element",
                    "input_text",
                    "scroll_down",
                    "scroll_up",
                    "scroll_to_text",
                    "send_keys",
                    "get_dropdown_options",
                    "select_dropdown_option",
                    "go_back",
                    "web_search",
                    "wait",
                    "extract_content",
                    "get_page_content",
                    "switch_tab",
                    "open_tab",
                    "close_tab",
                    "refresh",
                ],
                "description": "The browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL for 'go_to_url' or 'open_tab' actions",
            },
            "index": {
                "type": "integer",
                "description": "Element index for 'click_element', 'input_text', 'get_dropdown_options', or 'select_dropdown_option' actions",
            },
            "text": {
                "type": "string",
                "description": "Text for 'input_text', 'scroll_to_text', or 'select_dropdown_option' actions",
            },
            "scroll_amount": {
                "type": "integer",
                "description": "Pixels to scroll (positive for down, negative for up) for 'scroll_down' or 'scroll_up' actions",
            },
            "tab_id": {
                "type": "integer",
                "description": "Tab ID for 'switch_tab' action",
            },
            "query": {
                "type": "string",
                "description": "Search query for 'web_search' action",
            },
            "goal": {
                "type": "string",
                "description": "Extraction goal for 'extract_content' action",
            },
            "keys": {
                "type": "string",
                "description": "Keys to send for 'send_keys' action",
            },
            "seconds": {
                "type": "integer",
                "description": "Seconds to wait for 'wait' action",
            },
        },
        "required": ["action"],
        "dependencies": {
            "go_to_url": ["url"],
            "click_element": ["index"],
            "input_text": ["index", "text"],
            "switch_tab": ["tab_id"],
            "open_tab": ["url"],
            "scroll_down": ["scroll_amount"],
            "scroll_up": ["scroll_amount"],
            "scroll_to_text": ["text"],
            "send_keys": ["keys"],
            "get_dropdown_options": ["index"],
            "select_dropdown_option": ["index", "text"],
            "go_back": [],
            "web_search": ["query"],
            "wait": ["seconds"],
            "extract_content": ["goal"],
            "get_page_content": [],
            "refresh": [],
        },
    }

    lock: asyncio.Lock = Field(default_factory=asyncio.Lock)
    browser: Optional[BrowserUseBrowser] = Field(default=None, exclude=True)
    context: Optional[BrowserContext] = Field(default=None, exclude=True)
    dom_service: Optional[DomService] = Field(default=None, exclude=True)
    web_search_tool: WebSearch = Field(default_factory=WebSearch, exclude=True)

    # Context for generic functionality
    tool_context: Optional[Context] = Field(default=None, exclude=True)

    # Use both LLM (for backward compatibility) and LLMIntegration for XML-based tool calling
    llm: Optional[LLM] = Field(default_factory=lambda: LLM("openrouter"))
    llm_integration: Optional[LLMIntegration] = Field(
        default_factory=lambda: LLMIntegration("openrouter")
    )

    @field_validator("parameters", mode="before")
    def validate_parameters(cls, v: dict, info: ValidationInfo) -> dict:
        if not v:
            raise ValueError("Parameters cannot be empty")
        return v

    async def _ensure_browser_initialized(self) -> BrowserContext:
        """Ensure browser and context are initialized."""
        if self.browser is None:
            browser_config_kwargs = {"headless": False, "disable_security": True}
            
            # Log browser initialization
            logger.info(f"Initializing browser with config: {browser_config_kwargs}")

            if config.browser_config:
                from browser_use.browser.browser import ProxySettings

                # handle proxy settings.
                if config.browser_config.proxy and config.browser_config.proxy.server:
                    browser_config_kwargs["proxy"] = ProxySettings(
                        server=config.browser_config.proxy.server,
                        username=config.browser_config.proxy.username,
                        password=config.browser_config.proxy.password,
                    )

                browser_attrs = [
                    "headless",
                    "disable_security",
                    "extra_chromium_args",
                    "chrome_instance_path",
                    "wss_url",
                    "cdp_url",
                ]

                for attr in browser_attrs:
                    value = getattr(config.browser_config, attr, None)
                    if value is not None:
                        if not isinstance(value, list) or value:
                            browser_config_kwargs[attr] = value

            self.browser = BrowserUseBrowser(BrowserConfig(**browser_config_kwargs))

        if self.context is None:
            context_config = BrowserContextConfig()

            # if there is context config in the config, use it.
            if (
                config.browser_config
                and hasattr(config.browser_config, "new_context_config")
                and config.browser_config.new_context_config
            ):
                context_config = config.browser_config.new_context_config

            self.context = await self.browser.new_context(context_config)
            self.dom_service = DomService(await self.context.get_current_page())

        return self.context

    async def execute(
        self,
        action: str,
        url: Optional[str] = None,
        index: Optional[int] = None,
        text: Optional[str] = None,
        scroll_amount: Optional[int] = None,
        tab_id: Optional[int] = None,
        query: Optional[str] = None,
        goal: Optional[str] = None,
        keys: Optional[str] = None,
        seconds: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a specified browser action.

        Args:
            action: The browser action to perform
            url: URL for navigation or new tab
            index: Element index for click or input actions
            text: Text for input action or search query
            scroll_amount: Pixels to scroll for scroll action
            tab_id: Tab ID for switch_tab action
            query: Search query for Google search
            goal: Extraction goal for content extraction
            keys: Keys to send for keyboard actions
            seconds: Seconds to wait
            **kwargs: Additional arguments

        Returns:
            ToolResult with the action's output or error
        """
        async with self.lock:
            try:
                context = await self._ensure_browser_initialized()

                # Get max content length from config
                max_content_length = getattr(
                    config.browser_config, "max_content_length", 2000
                )

                # Navigation actions
                if action == "go_to_url":
                    if not url:
                        return ToolResult(
                            error="URL is required for 'go_to_url' action"
                        )
                    page = await context.get_current_page()
                    await page.goto(url)
                    await page.wait_for_load_state()
                    return ToolResult(output=f"Navigated to {url}")

                elif action == "go_back":
                    await context.go_back()
                    return ToolResult(output="Navigated back")

                elif action == "refresh":
                    await context.refresh_page()
                    return ToolResult(output="Refreshed current page")

                elif action == "web_search":
                    if not query:
                        return ToolResult(
                            error="Query is required for 'web_search' action"
                        )
                    # Execute the web search and return results directly without browser navigation
                    search_response = await self.web_search_tool.execute(
                        query=query, fetch_content=True, num_results=1
                    )
                    # Navigate to the first search result
                    if search_response.results:
                        first_search_result = search_response.results[0]
                        url_to_navigate = first_search_result.url

                        page = await context.get_current_page()
                        await page.goto(url_to_navigate)
                        await page.wait_for_load_state()
                        return search_response
                    else:
                        return ToolResult(
                            error=f"Web search for '{query}' returned no results."
                        )

                # Element interaction actions
                elif action == "click_element":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'click_element' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    download_path = await context._click_element_node(element)
                    output = f"Clicked element at index {index}"
                    if download_path:
                        output += f" - Downloaded file to {download_path}"
                    return ToolResult(output=output)

                elif action == "input_text":
                    if index is None or text is None:  # Allow empty string input
                        return ToolResult(
                            error="Index and text are required for 'input_text' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    await context._input_text_element_node(element, text)
                    return ToolResult(
                        output=f"Input '{text}' into element at index {index}"
                    )

                elif action == "scroll_down" or action == "scroll_up":
                    direction = 1 if action == "scroll_down" else -1
                    # Default scroll amount to viewport height if not provided
                    if scroll_amount is None:
                        page = await context.get_current_page()
                        viewport_size = page.viewport_size
                        amount = (
                            viewport_size["height"] if viewport_size else 500
                        )  # Default if viewport size not available
                    else:
                        amount = scroll_amount

                    await context.execute_javascript(
                        f"window.scrollBy(0, {direction * amount});"
                    )
                    return ToolResult(
                        output=f"Scrolled {'down' if direction > 0 else 'up'} by {amount} pixels"
                    )

                elif action == "scroll_to_text":
                    if not text:
                        return ToolResult(
                            error="Text is required for 'scroll_to_text' action"
                        )
                    page = await context.get_current_page()
                    try:
                        locator = page.get_by_text(
                            text, exact=False
                        ).first  # Ensure we target the first match
                        await locator.scroll_into_view_if_needed()
                        return ToolResult(output=f"Scrolled to text: '{text}'")
                    except Exception as e:
                        logger.error(f"Failed to scroll to text '{text}': {str(e)}")
                        return ToolResult(
                            error=f"Failed to scroll to text '{text}': {str(e)}"
                        )

                elif action == "send_keys":
                    if not keys:
                        return ToolResult(
                            error="Keys are required for 'send_keys' action"
                        )
                    page = await context.get_current_page()
                    await page.keyboard.press(keys)
                    return ToolResult(output=f"Sent keys: {keys}")

                elif action == "get_dropdown_options":
                    if index is None:
                        return ToolResult(
                            error="Index is required for 'get_dropdown_options' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    # Ensure the element is a select element before evaluating
                    is_select = await page.evaluate(
                        "(xpath) => document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue?.tagName === 'SELECT'",
                        element.xpath,
                    )
                    if not is_select:
                        return ToolResult(
                            error=f"Element at index {index} is not a dropdown (select element)."
                        )

                    options = await page.evaluate(
                        """
                        (xpath) => {
                            const select = document.evaluate(xpath, document, null,
                                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                            if (!select) return null;
                            return Array.from(select.options).map(opt => ({
                                text: opt.text,
                                value: opt.value,
                                index: opt.index
                            }));
                        }
                        """,
                        element.xpath,
                    )
                    return ToolResult(
                        output=f"Dropdown options: {json.dumps(options)}"
                    )  # Return as JSON string

                elif action == "select_dropdown_option":
                    if (
                        index is None or text is None
                    ):  # Allow empty string selection if needed? No, requires text.
                        return ToolResult(
                            error="Index and text are required for 'select_dropdown_option' action"
                        )
                    element = await context.get_dom_element_by_index(index)
                    if not element:
                        return ToolResult(error=f"Element with index {index} not found")
                    page = await context.get_current_page()
                    try:
                        # Use Playwright's select_option which handles various ways to select
                        await page.locator(f"xpath={element.xpath}").select_option(
                            label=text
                        )
                        return ToolResult(
                            output=f"Selected option '{text}' from dropdown at index {index}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to select dropdown option '{text}' at index {index}: {str(e)}"
                        )
                        # Try selecting by value as a fallback
                        try:
                            await page.locator(f"xpath={element.xpath}").select_option(
                                value=text
                            )
                            return ToolResult(
                                output=f"Selected option with value '{text}' from dropdown at index {index}"
                            )
                        except Exception as e2:
                            logger.error(
                                f"Failed to select dropdown option by value either: {str(e2)}"
                            )
                            return ToolResult(
                                error=f"Could not select option '{text}' by label or value at index {index}: {str(e)}"
                            )

                # Content extraction actions
                elif action == "get_page_content" or action == "extract_content":
                    # Use a default goal if this is get_page_content
                    if action == "get_page_content":
                        goal = "Extract and analyze the current page content"
                    elif not goal:
                        return ToolResult(
                            error="Goal is required for 'extract_content' action"
                        )

                    page = await context.get_current_page()

                    try:
                        # Get full HTML content and convert to markdown
                        import markdownify

                        html_content = await page.content()
                        content = markdownify.markdownify(html_content)
                    except Exception as html_error:
                        logger.warning(
                            f"Error converting HTML to markdown: {html_error}"
                        )
                        # Try direct text extraction as fallback
                        try:
                            content = await page.evaluate("document.body.innerText")
                        except Exception as text_extract_error:
                            logger.error(
                                f"Failed to extract innerText: {text_extract_error}"
                            )
                            content = "Could not extract page content."

                    # Get current page URL and title
                    page_url = page.url
                    page_title = await page.title()
                    
                    # Take a screenshot of the current page
                    screenshot = await page.screenshot(full_page=True, type="jpeg", quality=90)
                    screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                    
                    # Prepare the content for analysis
                    if len(content) > 15000:
                        # Truncate very long content to avoid overwhelming the model
                        logger.info(f"Content length {len(content)} exceeds limit, truncating to 15000 chars")
                        content = content[:15000] + "\n\n[Content truncated due to length...]\n\n"
                    
                    # Prepare prompt for the vision model
                    prompt = f"""Analyze this webpage screenshot and content. 

Goal: {goal}

Page Title: {page_title}
URL: {page_url}

Provide a detailed analysis addressing the goal. Include:
1. Overall assessment
2. Main sections/features identified
3. Content quality evaluation
4. Design and usability evaluation
5. Specific recommendations for improvement

Return your analysis as structured text."""
                    
                    logger.info(f"Sending page analysis to vision model: {page_url}")
                    
                    try:
                        # Use the vision model to analyze the page
                        vision_llm = LLM("vision")
                        analysis_result = await vision_llm.ask_with_images(
                            messages=[{"role": "user", "content": prompt}],
                            images=[{"url": f"data:image/jpeg;base64,{screenshot_b64}"}],
                            stream=False,
                            temperature=0.2
                        )
                        
                        # Return properly formatted output
                        return ToolResult(
                            output=json.dumps(
                                {
                                    "status": "success",
                                    "goal": goal,
                                    "extracted_content": {"text": analysis_result},
                                }
                            ),
                            base64_image=screenshot_b64
                        )
                    except Exception as analysis_error:
                        logger.error(f"Error analyzing page with vision model: {analysis_error}")
                        return ToolResult(
                            error=f"Error analyzing page content: {str(analysis_error)}",
                            base64_image=screenshot_b64
                        )

                # Tab management actions
                elif action == "switch_tab":
                    if tab_id is None:
                        return ToolResult(
                            error="Tab ID is required for 'switch_tab' action"
                        )
                    await context.switch_to_tab(tab_id)
                    page = await context.get_current_page()
                    await page.wait_for_load_state()
                    return ToolResult(output=f"Switched to tab {tab_id}")

                elif action == "open_tab":
                    if not url:
                        return ToolResult(error="URL is required for 'open_tab' action")
                    await context.create_new_tab(url)
                    return ToolResult(output=f"Opened new tab with {url}")

                elif action == "close_tab":
                    await context.close_current_tab()
                    return ToolResult(output="Closed current tab")

                # Utility actions
                elif action == "wait":
                    seconds_to_wait = seconds if seconds is not None else 3
                    await asyncio.sleep(seconds_to_wait)
                    return ToolResult(output=f"Waited for {seconds_to_wait} seconds")

                else:
                    return ToolResult(error=f"Unknown action: {action}")

            except Exception as e:
                logger.exception(
                    f"Browser action '{action}' failed unexpectedly."
                )  # Log full traceback
                return ToolResult(error=f"Browser action '{action}' failed: {str(e)}")

    async def get_current_state(
        self, context: Optional[BrowserContext] = None
    ) -> ToolResult:
        """
        Get the current browser state as a ToolResult.
        If context is not provided, uses self.context.
        """
        try:
            # Use provided context or fall back to self.context
            ctx = context or self.context
            if not ctx:
                # Try initializing if not available
                logger.info(
                    "get_current_state: Context not initialized, attempting to initialize."
                )
                try:
                    ctx = await self._ensure_browser_initialized()
                except Exception as init_error:
                    logger.error(
                        f"Failed to initialize browser context in get_current_state: {init_error}"
                    )
                    return ToolResult(
                        error=f"Browser context not initialized and failed to initialize: {init_error}"
                    )

            state = await ctx.get_state()

            # Create a viewport_info dictionary if it doesn't exist
            viewport_height = 0
            if hasattr(state, "viewport_info") and state.viewport_info:
                viewport_height = state.viewport_info.height
            elif hasattr(ctx, "config") and hasattr(ctx.config, "browser_window_size"):
                viewport_height = ctx.config.browser_window_size.get("height", 0)

            # Take a screenshot for the state
            page = await ctx.get_current_page()

            await page.bring_to_front()
            await page.wait_for_load_state(timeout=10000)  # Add timeout

            # First take a clean screenshot
            screenshot = await page.screenshot(
                full_page=True,
                animations="disabled",
                type="jpeg",
                quality=85,  # Reduced quality slightly
            )
            
            # Add visual overlays to the screenshot to mark clickable elements
            screenshot_with_markers = None
            if state.element_tree and state.element_tree.clickable_elements:
                try:
                    # Use JavaScript to add visual markers to the page
                    markers_script = """
                    (function() {
                        // Remove any existing markers first
                        document.querySelectorAll('.openmanus-element-marker').forEach(e => e.remove());
                        
                        // Create markers for the specified elements
                        const elements = arguments[0];
                        elements.forEach((el, index) => {
                            if (!el || !el.xpath) return;
                            
                            try {
                                // Get the element using XPath
                                const element = document.evaluate(
                                    el.xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                                ).singleNodeValue;
                                
                                if (element) {
                                    const rect = element.getBoundingClientRect();
                                    const marker = document.createElement('div');
                                    marker.className = 'openmanus-element-marker';
                                    marker.textContent = '[' + index + ']';
                                    marker.style.cssText = 'position: absolute; background-color: rgba(66, 135, 245, 0.8); color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-family: Arial; z-index: 10000; pointer-events: none; font-size: 14px;';
                                    marker.style.left = (window.scrollX + rect.left) + 'px';
                                    marker.style.top = (window.scrollY + rect.top) + 'px';
                                    document.body.appendChild(marker);
                                }
                            } catch (e) {
                                console.error('Error adding marker:', e);
                            }
                        });
                        
                        // Return true to confirm execution
                        return true;
                    })
                    """
                    
                    # Convert clickable elements to a format that can be passed to JavaScript
                    elements_for_js = []
                    for i, element in enumerate(state.element_tree.clickable_elements):
                        elements_for_js.append({
                            "index": i,
                            "xpath": element.xpath if hasattr(element, "xpath") else None,
                            "role": element.role if hasattr(element, "role") else None
                        })
                    
                    # Execute the script to add markers
                    await page.evaluate(markers_script, elements_for_js)
                    
                    # Wait a brief moment for the markers to render
                    await asyncio.sleep(0.5)
                    
                    # Take a new screenshot with the markers
                    screenshot_with_markers = await page.screenshot(
                        full_page=True,
                        animations="disabled",
                        type="jpeg",
                        quality=85
                    )
                    
                    # Clean up markers
                    await page.evaluate("""
                    document.querySelectorAll('.openmanus-element-marker').forEach(e => e.remove());
                    """)
                    
                except Exception as marker_error:
                    logger.error(f"Error adding element markers: {marker_error}")
                    # Continue with the original screenshot if there's an error

            # Use the screenshot with markers if available, otherwise use the original
            final_screenshot = screenshot_with_markers if screenshot_with_markers else screenshot
            screenshot_b64 = base64.b64encode(final_screenshot).decode("utf-8")

            # Build the state info with all required fields
            elements_list = []
            if state.element_tree and state.element_tree.clickable_elements:
                for i, element in enumerate(state.element_tree.clickable_elements):
                    element_info = {
                        "index": i,
                        "text": element.text if hasattr(element, "text") else "",
                        "type": element.role if hasattr(element, "role") else "element",
                        "is_visible": element.visible if hasattr(element, "visible") else True
                    }
                    elements_list.append(element_info)

            state_info = {
                "url": state.url,
                "title": state.title,
                "tabs": [tab.model_dump() for tab in state.tabs],
                "help": "The elements below are numbered with [0], [1], [2], etc. directly on the screenshot. Use these numbers with the click_element action to interact with them.",
                "interactive_elements": (
                    state.element_tree.clickable_elements_to_string()
                    if state.element_tree
                    else ""
                ),
                "elements": elements_list,
                "scroll_info": {
                    "pixels_above": getattr(state, "pixels_above", 0),
                    "pixels_below": getattr(state, "pixels_below", 0),
                    "total_height": getattr(state, "pixels_above", 0)
                    + getattr(state, "pixels_below", 0)
                    + viewport_height,
                },
                "viewport_height": viewport_height,
            }

            return ToolResult(
                output=json.dumps(
                    state_info, indent=2, ensure_ascii=False
                ),  # Reduced indent
                base64_image=screenshot_b64,
            )
        except Exception as e:
            logger.exception("Failed to get browser state.")  # Log full traceback
            return ToolResult(error=f"Failed to get browser state: {str(e)}")

    async def analyze_navigation_menu(self) -> Dict[str, Any]:
        """
        Analyze the website's navigation menu structure.

        Returns:
            Dictionary containing menu analysis data including:
            - Main menu items
            - Submenu structure
            - Recommendations for improvement
        """
        try:
            # Extract navigation menu
            menu_result = await self.execute(
                action="extract_content",
                goal="Find and analyze the website navigation menu. List all main menu items and their links. Identify if there are dropdown/submenu items. Describe the organization and structure of the navigation.",
            )

            if (
                not menu_result
                or not hasattr(menu_result, "output")
                or not menu_result.output
                or menu_result.error
            ):
                error_msg = (
                    menu_result.error
                    if menu_result and menu_result.error
                    else "Could not extract navigation menu"
                )
                logger.error(f"analyze_navigation_menu failed: {error_msg}")
                return {"error": error_msg}

            # Get menu text
            try:
                # Handle potential JSONDecodeError if output is not valid JSON
                output_str = menu_result.output.replace(
                    "Extracted from page:", ""
                ).strip()
                if output_str.startswith("{") and output_str.endswith("}"):
                    output_data = json.loads(output_str)
                    menu_text = output_data.get("extracted_content", {}).get("text", "")
                else:
                    # Assume plain text if not JSON
                    menu_text = output_str
            except json.JSONDecodeError:
                logger.warning(
                    "analyze_navigation_menu: Output was not valid JSON, treating as plain text."
                )
                menu_text = menu_result.output if hasattr(menu_result, "output") else ""
            except Exception as parse_error:
                logger.error(f"Error parsing menu result: {parse_error}")
                menu_text = menu_result.output if hasattr(menu_result, "output") else ""

            # Parse menu items (Improved parsing)
            menu_items = []
            # Regex to find potential menu items like "Text: http://link" or "- Text (http://link)"
            # This is a basic attempt and might need refinement based on common LLM output patterns
            link_pattern = re.compile(
                r"^\s*[-*]?\s*(.*?)\s*[:(]\s*(https?://[^\s)]+)\)?", re.MULTILINE
            )
            for match in link_pattern.finditer(menu_text):
                item_text = match.group(1).strip()
                link_url = match.group(2).strip()
                if item_text and link_url:  # Ensure both parts are found
                    menu_items.append({"text": item_text, "link": link_url})

            # Fallback parsing if regex yields few results
            if not menu_items or len(menu_items) < 2:
                logger.info(
                    "analyze_navigation_menu: Regex parsing yielded few results, trying line-based parsing."
                )
                for line in menu_text.split("\n"):
                    line = line.strip()
                    if (
                        ":" in line
                        and not line.startswith(("*", "-"))
                        and "http" in line
                    ):
                        parts = line.split(":", 1)
                        if len(parts) == 2 and parts[1].strip().startswith("http"):
                            item, link = parts
                            menu_items.append(
                                {"text": item.strip(), "link": link.strip()}
                            )

            return {
                "menu_text": menu_text,  # Keep original text for context
                "menu_items": menu_items,
                "has_submenu": "dropdown" in menu_text.lower()
                or "submenu" in menu_text.lower(),
                "menu_count": len(menu_items),
            }
        except Exception as e:
            logger.exception("Error analyzing navigation menu.")  # Log full traceback
            return {"error": f"Error analyzing navigation menu: {str(e)}"}

    async def identify_key_pages(self) -> List[Dict[str, Any]]:
        """
        Identify key pages on the website that should be analyzed.

        Returns:
            List of dictionaries with page information (title, url, priority)
        """
        try:
            # Extract links from current page
            links_result = await self.execute(
                action="extract_content",
                goal="Extract all navigation links and important page links from this website. Identify each link's purpose (e.g., Home, About, Services, Contact, etc.) and provide the full URL.",
            )

            if (
                not links_result
                or not hasattr(links_result, "output")
                or not links_result.output
                or links_result.error
            ):
                error_msg = (
                    links_result.error
                    if links_result and links_result.error
                    else "Could not extract links"
                )
                logger.error(f"identify_key_pages failed: {error_msg}")
                return []

            # Parse links
            try:
                output_str = links_result.output.replace(
                    "Extracted from page:", ""
                ).strip()
                if output_str.startswith("{") and output_str.endswith("}"):
                    output_json = json.loads(output_str)
                    links_text = output_json.get("extracted_content", {}).get(
                        "text", ""
                    )
                else:
                    links_text = output_str
            except json.JSONDecodeError:
                logger.warning(
                    "identify_key_pages: Output was not valid JSON, treating as plain text."
                )
                links_text = (
                    links_result.output if hasattr(links_result, "output") else ""
                )
            except Exception as parse_error:
                logger.error(f"Error parsing links result: {parse_error}")
                links_text = (
                    links_result.output if hasattr(links_result, "output") else ""
                )

            # Extract URLs using a more robust regex
            url_pattern = r"https?://(?:[a-zA-Z0-9\.\-]+[a-zA-Z0-9])(?::\d+)?(?:/[^\"\s<>]*)?"  # Improved regex
            urls = list(
                set(re.findall(url_pattern, links_text))
            )  # Use set to get unique URLs

            # Match URLs with descriptions
            key_pages = []
            priorities = {
                "home": 10,
                "homepage": 10,
                "index": 10,
                "contact": 10,
                "contactus": 10,
                "about": 9,
                "aboutus": 9,
                "pricing": 9,
                "rates": 9,
                "packages": 9,
                "services": 8,
                "products": 8,
                "features": 8,
                "portfolio": 7,
                "gallery": 7,
                "casestudies": 7,
                "work": 7,
                "testimonials": 7,
                "reviews": 7,
                "faq": 6,
                "help": 6,
                "support": 6,
                "blog": 5,
                "news": 5,
                "articles": 5,
            }

            # Get current URL to avoid adding it and to resolve relative links
            page = await self.context.get_current_page()
            current_url_obj = page.url
            from urllib.parse import urljoin, urlparse

            base_url = f"{urlparse(current_url_obj).scheme}://{urlparse(current_url_obj).netloc}"

            processed_urls = set()  # Keep track of processed URLs to avoid duplicates

            for url in urls:
                try:
                    # Resolve relative URLs
                    absolute_url = urljoin(base_url, url)
                    parsed_url = urlparse(absolute_url)

                    # Basic filtering: skip mailto, javascript, anchors, non-http(s)
                    if (
                        not parsed_url.scheme.startswith("http")
                        or parsed_url.path == current_url_obj
                    ):
                        continue
                    # Filter out common file extensions unless specifically requested
                    if re.search(
                        r"\.(pdf|jpg|png|gif|css|js|zip|rar|exe|mp4|mov)$",
                        parsed_url.path,
                        re.IGNORECASE,
                    ):
                        continue

                    # Normalize URL slightly (remove trailing slash)
                    normalized_url = absolute_url.rstrip("/")
                    if normalized_url in processed_urls:
                        continue
                    processed_urls.add(normalized_url)

                    # Determine page type from URL path segments
                    page_type = "other"
                    priority = 1
                    path_lower = parsed_url.path.lower()
                    # Check keywords in the last path segment first, then full path
                    path_segments = [seg for seg in path_lower.split("/") if seg]
                    check_segments = [path_segments[-1]] if path_segments else []
                    check_segments.append(path_lower)  # Check full path too

                    found_type = False
                    for segment in check_segments:
                        for key, value in priorities.items():
                            # Match whole words or common variations
                            if re.search(rf"\b{key}\b", segment):
                                page_type = key.replace("homepage", "home").replace(
                                    "us", ""
                                )  # Normalize type name
                                priority = value
                                found_type = True
                                break
                        if found_type:
                            break

                    # Assign priority based on depth (shallower pages often more important)
                    depth_priority = max(
                        0, 3 - len(path_segments)
                    )  # Add small bonus for shallower pages
                    final_priority = priority + depth_priority

                    key_pages.append(
                        {
                            "url": absolute_url,
                            "type": page_type,
                            "priority": final_priority,
                        }
                    )
                except Exception as url_proc_error:
                    logger.warning(f"Error processing URL '{url}': {url_proc_error}")

            # Sort by priority, then URL length (shorter URLs often more important)
            return sorted(key_pages, key=lambda x: (-x["priority"], len(x["url"])))

        except Exception as e:
            logger.exception("Error identifying key pages.")  # Log full traceback
            return []

    async def analyze_industry_specific(self, industry: str) -> Dict[str, Any]:
        """
        Analyze website content specific to the given industry.

        Args:
            industry: Industry name/category

        Returns:
            Industry-specific analysis results
        """
        try:
            # Customize extraction goal based on industry
            if "event" in industry.lower() or "wedding" in industry.lower():
                goal = "Analyze this event services website. Extract details about services offered, pricing information, event types covered, booking process, portfolio/gallery presence, testimonials, and contact methods."
            elif "restaurant" in industry.lower() or "food" in industry.lower():
                goal = "Analyze this food service website. Extract details about menu items, pricing, hours of operation, reservation system, delivery options, location information, and special features."
            elif "retail" in industry.lower() or "shop" in industry.lower():
                goal = "Analyze this retail website. Extract details about products offered, pricing, shopping cart functionality, payment methods, shipping information, return policy, and customer service options."
            else:
                goal = f"Analyze this {industry} website. Extract key business information including services/products offered, contact methods, pricing if available, unique selling points, and conversion elements."

            # Extract industry-specific content
            industry_result = await self.execute(action="extract_content", goal=goal)

            if (
                not industry_result
                or not hasattr(industry_result, "output")
                or not industry_result.output
                or industry_result.error
            ):
                error_msg = (
                    industry_result.error
                    if industry_result and industry_result.error
                    else f"Could not extract {industry}-specific information"
                )
                logger.error(f"analyze_industry_specific failed: {error_msg}")
                return {"error": error_msg}

            # Parse result
            try:
                output_str = industry_result.output.replace(
                    "Extracted from page:", ""
                ).strip()
                if output_str.startswith("{") and output_str.endswith("}"):
                    output_json = json.loads(output_str)
                    industry_text = output_json.get("extracted_content", {}).get(
                        "text", ""
                    )
                else:
                    industry_text = output_str
            except json.JSONDecodeError:
                logger.warning(
                    "analyze_industry_specific: Output was not valid JSON, treating as plain text."
                )
                industry_text = (
                    industry_result.output if hasattr(industry_result, "output") else ""
                )
            except Exception as parse_error:
                logger.error(f"Error parsing industry result: {parse_error}")
                industry_text = (
                    industry_result.output if hasattr(industry_result, "output") else ""
                )

            # Format results based on industry
            industry_data = {
                "analysis": industry_text,
                "industry": industry,
                "has_industry_specific_features": False,  # Added default value
                "missing_elements": [],
                "recommendations": [],
            }

            # Check for industry-specific features (Example for event industry)
            text_lower = industry_text.lower()  # Pre-lower for efficiency
            if "event" in industry.lower() or "wedding" in industry.lower():
                features = {
                    "portfolio": "portfolio" in text_lower or "gallery" in text_lower,
                    "booking": "booking" in text_lower
                    or "reservation" in text_lower
                    or "contact form" in text_lower
                    or "inquiry" in text_lower,
                    "pricing": "price" in text_lower
                    or "cost" in text_lower
                    or "package" in text_lower
                    or "rates" in text_lower,
                    "testimonials": "testimonial" in text_lower
                    or "review" in text_lower
                    or "what our clients say" in text_lower,
                }
                industry_data["features"] = features
                industry_data["has_industry_specific_features"] = any(features.values())

                # Generate recommendations
                missing = [k for k, v in features.items() if not v]
                if missing:
                    industry_data["missing_elements"] = missing
                    for element in missing:
                        if element == "portfolio":
                            industry_data["recommendations"].append(
                                "Add a portfolio/gallery showcasing past events."
                            )
                        elif element == "booking":
                            industry_data["recommendations"].append(
                                "Implement an online booking or inquiry system."
                            )
                        elif element == "pricing":
                            industry_data["recommendations"].append(
                                "Add clear pricing information or package details."
                            )
                        elif element == "testimonials":
                            industry_data["recommendations"].append(
                                "Include testimonials or reviews from past clients."
                            )

            elif "restaurant" in industry.lower() or "food" in industry.lower():
                features = {
                    "menu": "menu" in text_lower,
                    "hours": "hour" in text_lower
                    or "opening" in text_lower
                    or "open" in text_lower,
                    "location": "location" in text_lower
                    or "address" in text_lower
                    or "find us" in text_lower,
                    "reservation": "reservation" in text_lower
                    or "book a table" in text_lower,
                    "delivery": "delivery" in text_lower
                    or "takeout" in text_lower
                    or "take away" in text_lower
                    or "order online" in text_lower,
                }
                industry_data["features"] = features
                industry_data["has_industry_specific_features"] = any(features.values())
                missing = [k for k, v in features.items() if not v]
                if missing:
                    industry_data["missing_elements"] = missing
                    for element in missing:
                        if element == "menu":
                            industry_data["recommendations"].append(
                                "Add an online menu, ideally with photos and prices."
                            )
                        elif element == "hours":
                            industry_data["recommendations"].append(
                                "Clearly display opening hours."
                            )
                        elif element == "location":
                            industry_data["recommendations"].append(
                                "Add location information with an embedded map."
                            )
                        elif element == "reservation":
                            industry_data["recommendations"].append(
                                "Implement an online reservation system if applicable."
                            )
                        elif element == "delivery":
                            industry_data["recommendations"].append(
                                "Add information about delivery or takeout options if offered."
                            )

            elif "retail" in industry.lower() or "shop" in industry.lower():
                features = {
                    "products": "product" in text_lower
                    or "shop" in text_lower
                    or "catalog" in text_lower,
                    "pricing": "price" in text_lower
                    or "cost" in text_lower
                    or "$" in industry_text
                    or "£" in industry_text
                    or "€" in industry_text,  # Check for currency symbols too
                    "cart": "cart" in text_lower
                    or "basket" in text_lower
                    or "bag" in text_lower
                    or "add to cart" in text_lower,
                    "shipping": "shipping" in text_lower or "delivery" in text_lower,
                    "returns": "return" in text_lower
                    or "refund" in text_lower
                    or "exchange" in text_lower,
                }
                industry_data["features"] = features
                industry_data["has_industry_specific_features"] = any(features.values())
                missing = [k for k, v in features.items() if not v]
                if missing:
                    industry_data["missing_elements"] = missing
                    for element in missing:
                        if element == "products":
                            industry_data["recommendations"].append(
                                "Add detailed product listings with high-quality images and descriptions."
                            )
                        elif element == "pricing":
                            industry_data["recommendations"].append(
                                "Clearly display product prices."
                            )
                        elif element == "cart":
                            industry_data["recommendations"].append(
                                "Implement shopping cart functionality."
                            )
                        elif element == "shipping":
                            industry_data["recommendations"].append(
                                "Provide clear shipping information, costs, and estimated times."
                            )
                        elif element == "returns":
                            industry_data["recommendations"].append(
                                "Include a clear and easily accessible returns and refund policy."
                            )

            # Add general recommendations if none were added yet
            if not industry_data["recommendations"]:
                industry_data["recommendations"] = [
                    "Ensure content clearly communicates the value proposition for the target audience.",
                    "Include clear calls-to-action relevant to the business goals (e.g., 'Request a Quote', 'Book Now', 'Shop Now').",
                    "Consider adding testimonials or case studies to build trust.",
                ]

            return industry_data

        except Exception as e:
            logger.exception(
                f"Error performing industry-specific analysis for '{industry}'."
            )  # Log full traceback
            return {
                "error": f"Error analyzing industry specifics: {str(e)}",
                "industry": industry,
                "has_industry_specific_features": False,
            }

    async def cleanup(self) -> None:
        """Clean up browser resources safely."""
        if self.browser or self.context:
            logger.info("Cleaning up browser resources...")
            try:
                if self.context:
                    await self.context.close()
                    self.context = None
                if self.browser:
                    await self.browser.close()
                    self.browser = None
                logger.info("Browser resources cleaned up successfully.")
            except Exception as e:
                logger.error(f"Error during browser cleanup: {str(e)}")

    async def __aenter__(self):
        """Enter context manager, ensuring browser is initialized."""
        await self._ensure_browser_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager, ensuring cleanup."""
        await self.cleanup()

    async def crawl_and_analyze_website(
        self, start_url: str, industry: str = None, max_pages: int = 3
    ) -> Dict[str, Any]:
        """
        Perform a limited website crawl and analysis.

        Args:
            start_url: The starting URL for crawling.
            industry: The industry for specialized analysis (optional).
            max_pages: Maximum number of key pages to analyze (besides homepage).

        Returns:
            Dictionary with comprehensive website analysis.
        """
        logger.info(
            f"Starting website crawl and analysis for {start_url}, industry: {industry}, max_pages: {max_pages}"
        )
        results = {
            "url": start_url,
            "pages_analyzed": [],
            "navigation": {},
            "content_analysis": {},
            "industry_specific": {},
            "overall_scores": {},  # Placeholder for potential future scoring
            "recommendations": [],
            "errors": [],
        }

        try:
            async with self:  # Use async context manager for cleanup
                # Navigate to start URL
                nav_result = await self.execute(action="go_to_url", url=start_url)
                if nav_result.error:
                    results["errors"].append(
                        f"Failed to navigate to start URL {start_url}: {nav_result.error}"
                    )
                    logger.error(results["errors"][-1])
                    return results  # Cannot proceed without reaching the start URL

                await self.execute(action="wait", seconds=3)  # Allow loading

                # --- Analyze Homepage ---
                logger.info("Analyzing homepage...")
                homepage_state = await self.get_current_state()
                if homepage_state.error:
                    results["errors"].append(
                        f"Could not get state of homepage: {homepage_state.error}"
                    )
                    logger.error(results["errors"][-1])
                    # Continue analysis if possible, but note the issue
                else:
                    try:
                        homepage_info = json.loads(homepage_state.output)
                        results["pages_analyzed"].append(
                            {
                                "url": homepage_info.get("url"),
                                "title": homepage_info.get("title"),
                                "type": "homepage",
                            }
                        )
                    except Exception as e:
                        results["errors"].append(f"Could not parse homepage state: {e}")
                        logger.error(results["errors"][-1])

                # Analyze navigation
                nav_analysis = await self.analyze_navigation_menu()
                if nav_analysis.get("error"):
                    results["errors"].append(
                        f"Navigation menu analysis failed: {nav_analysis['error']}"
                    )
                    logger.warning(results["errors"][-1])
                results["navigation"] = nav_analysis

                # Analyze homepage content
                homepage_content_result = await self.execute(
                    action="extract_content",
                    goal="Analyze this homepage content. Extract the main sections (e.g., hero, services, about, testimonials, contact), key messages, calls-to-action, and assess overall content quality and clarity.",
                )
                if homepage_content_result.error:
                    results["errors"].append(
                        f"Homepage content analysis failed: {homepage_content_result.error}"
                    )
                    logger.warning(results["errors"][-1])
                else:
                    try:
                        content_json = json.loads(homepage_content_result.output)
                        results["content_analysis"]["homepage"] = content_json.get(
                            "extracted_content", {}
                        ).get("text", "Analysis unavailable")
                    except Exception as e:
                        results["errors"].append(
                            f"Could not parse homepage content analysis: {e}"
                        )
                        logger.warning(results["errors"][-1])
                        results["content_analysis"][
                            "homepage"
                        ] = homepage_content_result.output  # Store raw output

                # Industry-specific analysis on homepage
                if industry:
                    logger.info(
                        f"Performing industry-specific analysis for '{industry}' on homepage..."
                    )
                    industry_analysis = await self.analyze_industry_specific(industry)
                    if industry_analysis.get("error"):
                        results["errors"].append(
                            f"Industry analysis failed: {industry_analysis['error']}"
                        )
                        logger.warning(results["errors"][-1])
                    results["industry_specific"] = industry_analysis
                    if "recommendations" in industry_analysis:
                        results["recommendations"].extend(
                            industry_analysis["recommendations"]
                        )

                # --- Identify and Analyze Key Pages ---
                logger.info("Identifying key pages...")
                key_pages = await self.identify_key_pages()
                if not key_pages:
                    logger.warning("Could not identify key pages to crawl further.")
                else:
                    logger.info(
                        f"Identified {len(key_pages)} potential key pages. Analyzing top {max_pages}."
                    )

                pages_to_visit = key_pages[: min(max_pages, len(key_pages))]

                for page_info in pages_to_visit:
                    page_url = page_info["url"]
                    page_type = page_info.get("type", "other")
                    logger.info(f"Analyzing key page: {page_url} (Type: {page_type})")

                    try:
                        # Navigate to page
                        nav_page_result = await self.execute(
                            action="go_to_url", url=page_url
                        )
                        if nav_page_result.error:
                            results["errors"].append(
                                f"Failed to navigate to key page {page_url}: {nav_page_result.error}"
                            )
                            logger.warning(results["errors"][-1])
                            continue  # Skip this page

                        await self.execute(action="wait", seconds=2)  # Allow loading

                        # Get page state (title mainly)
                        page_state_result = await self.get_current_state()
                        page_title = "Unknown"
                        if not page_state_result.error:
                            try:
                                page_state_info = json.loads(page_state_result.output)
                                page_title = page_state_info.get("title", "Unknown")
                            except Exception as e:
                                logger.warning(
                                    f"Could not parse state for {page_url}: {e}"
                                )

                        results["pages_analyzed"].append(
                            {"url": page_url, "title": page_title, "type": page_type}
                        )

                        # Analyze content
                        page_content_result = await self.execute(
                            action="extract_content",
                            goal=f"Analyze this '{page_type}' page's content ({page_title}). Extract key information, structure, calls-to-action, and assess its quality and relevance to its purpose.",
                        )
                        if page_content_result.error:
                            results["errors"].append(
                                f"Content analysis failed for {page_url}: {page_content_result.error}"
                            )
                            logger.warning(results["errors"][-1])
                            results["content_analysis"][
                                page_type
                            ] = "Analysis unavailable due to error."
                        else:
                            try:
                                content_json = json.loads(page_content_result.output)
                                results["content_analysis"][page_type] = (
                                    content_json.get("extracted_content", {}).get(
                                        "text", "Analysis unavailable"
                                    )
                                )
                            except Exception as e:
                                results["errors"].append(
                                    f"Could not parse content analysis for {page_url}: {e}"
                                )
                                logger.warning(results["errors"][-1])
                                results["content_analysis"][
                                    page_type
                                ] = page_content_result.output  # Store raw output

                    except Exception as page_crawl_error:
                        error_msg = (
                            f"Error analyzing page {page_url}: {str(page_crawl_error)}"
                        )
                        results["errors"].append(error_msg)
                        logger.error(error_msg)

                # Optional: Return to homepage if needed, though context manager handles cleanup
                # await self.execute(action="go_to_url", url=start_url)

                logger.info(f"Finished crawl and analysis for {start_url}")
                return results

        except Exception as e:
            error_msg = f"Fatal error during website crawl and analysis for {start_url}: {str(e)}"
            results["errors"].append(error_msg)
            logger.exception(error_msg)  # Log full traceback for fatal errors
            return results
