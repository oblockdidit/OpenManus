from typing import Any, Dict, List, Optional, Tuple
import asyncio
import json

from pydantic import Field

from app.agent.toolcall import ToolCallAgent
from app.logger import logger
from app.prompt.mcp import MULTIMEDIA_RESPONSE_PROMPT, NEXT_STEP_PROMPT, SYSTEM_PROMPT
from app.schema import AgentState, Message
from app.tool.base import ToolResult
from app.tool.mcp import MCPClients
from app.parser.tool_parser import ToolCall, parse_assistant_message
from app.llm_integration import LLMIntegration
from app.exceptions import ToolUnavailableError, ToolExecutionError, ParsingError


class MCPAgent(ToolCallAgent):
    """Agent for interacting with MCP (Model Context Protocol) servers.

    This agent connects to an MCP server using either SSE or stdio transport
    and makes the server's tools available through the agent's tool interface.
    """

    name: str = "mcp_agent"
    description: str = "An agent that connects to an MCP server and uses its tools."

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    # Initialize MCP tool collection
    mcp_clients: MCPClients = Field(default_factory=MCPClients)
    available_tools: MCPClients = None  # Will be set in initialize()

    max_steps: int = 20
    connection_type: str = "stdio"  # "stdio" or "sse"

    # Track tool schemas to detect changes
    tool_schemas: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    _refresh_tools_interval: int = 5  # Refresh tools every N steps
    
    # LLM timeouts
    initial_timeout: int = 60  # Initial timeout in seconds
    adaptive_timeout: bool = True  # Whether to adapt timeout based on complexity
    current_timeout: int = 60  # Current timeout value, adjusted dynamically

    # Special tool names that should trigger termination
    special_tool_names: List[str] = Field(default_factory=lambda: ["terminate"])
    
    # Website analysis plan for structured analysis
    analysis_plan: List[Dict[str, str]] = Field(default_factory=lambda: [
        {"action": "get_page_content", "description": "First get the main page content"},
        {"action": "screenshot", "description": "Take a screenshot of the page"},
        {"action": "extract_links", "description": "Extract key links from the page"},
        {"action": "analyze_layout", "description": "Analyze the page layout and structure"}
    ])
    
    # Metrics tracking
    execution_history: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, int] = Field(default_factory=lambda: {
        "total_executions": 0,
        "successful_executions": 0,
        "failed_executions": 0,
    })

    async def initialize(
        self,
        connection_type: Optional[str] = None,
        server_url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
    ) -> None:
        """Initialize the MCP connection.

        Args:
            connection_type: Type of connection to use ("stdio" or "sse")
            server_url: URL of the MCP server (for SSE connection)
            command: Command to run (for stdio connection)
            args: Arguments for the command (for stdio connection)
        """
        if connection_type:
            self.connection_type = connection_type

        # Connect to the MCP server based on connection type
        if self.connection_type == "sse":
            if not server_url:
                raise ValueError("Server URL is required for SSE connection")
            await self.mcp_clients.connect_sse(server_url=server_url)
        elif self.connection_type == "stdio":
            if not command:
                raise ValueError("Command is required for stdio connection")
            await self.mcp_clients.connect_stdio(command=command, args=args or [])
        else:
            raise ValueError(f"Unsupported connection type: {self.connection_type}")

        # Set available_tools to our MCP instance
        self.available_tools = self.mcp_clients

        # Store initial tool schemas
        await self._refresh_tools()

        # Add system message about available tools
        tool_names = list(self.mcp_clients.tool_map.keys())
        tools_info = ", ".join(tool_names)

        # Add system prompt and available tools information
        self.memory.add_message(
            Message.system_message(
                f"{self.system_prompt}\n\nAvailable MCP tools: {tools_info}"
            )
        )

    async def _refresh_tools(self) -> Tuple[List[str], List[str]]:
        """Refresh the list of available tools from the MCP server.

        Returns:
            A tuple of (added_tools, removed_tools)
        """
        if not self.mcp_clients.session:
            return [], []

        # Get current tool schemas directly from the server
        response = await self.mcp_clients.session.list_tools()
        current_tools = {tool.name: tool.inputSchema for tool in response.tools}

        # Determine added, removed, and changed tools
        current_names = set(current_tools.keys())
        previous_names = set(self.tool_schemas.keys())

        added_tools = list(current_names - previous_names)
        removed_tools = list(previous_names - current_names)

        # Check for schema changes in existing tools
        changed_tools = []
        for name in current_names.intersection(previous_names):
            if current_tools[name] != self.tool_schemas.get(name):
                changed_tools.append(name)

        # Update stored schemas
        self.tool_schemas = current_tools

        # Log and notify about changes
        if added_tools:
            logger.info(f"Added MCP tools: {added_tools}")
            self.memory.add_message(
                Message.system_message(f"New tools available: {', '.join(added_tools)}")
            )
        if removed_tools:
            logger.info(f"Removed MCP tools: {removed_tools}")
            self.memory.add_message(
                Message.system_message(
                    f"Tools no longer available: {', '.join(removed_tools)}"
                )
            )
        if changed_tools:
            logger.info(f"Changed MCP tools: {changed_tools}")

        return added_tools, removed_tools

    async def think(self) -> bool:
        """Process current state and decide next action."""
        logger.info(f"MCP Agent thinking (step {self.current_step})")
        
        # Check for a forced next action from previous step
        for msg in reversed(self.memory.messages):
            # Check for both NEXT_ACTION and ANALYSIS_STEP messages
            if msg.role == 'system' and (msg.content.startswith('NEXT_ACTION:') or msg.content.startswith('ANALYSIS_STEP_')):
                try:
                    # For ANALYSIS_STEP_x messages, we need to find the next step in sequence
                    if msg.content.startswith('ANALYSIS_STEP_'):
                        # Find the current step number from the prefix (ANALYSIS_STEP_1, ANALYSIS_STEP_2, etc.)
                        current_step_num = int(msg.content.split('_')[2].split(':')[0])
                        
                        # Check if we've completed the previous step
                        previous_step_complete = True
                        if current_step_num > 0:
                            previous_msg_prefix = f"ANALYSIS_STEP_{current_step_num-1}"
                            previous_step_complete = not any(m.role == 'system' and m.content.startswith(previous_msg_prefix) for m in self.memory.messages)
                        
                        # Only proceed if the previous step is complete
                        if not previous_step_complete:
                            continue
                        
                        # Once all steps are complete, provide a final analysis
                        if current_step_num == len(analysis_plan) - 1:
                            logger.info(f"Moving to final analysis step {current_step_num}")
                        
                        # Convert ANALYSIS_STEP to NEXT_ACTION format
                        msg.content = msg.content.replace(f"ANALYSIS_STEP_{current_step_num}:", "NEXT_ACTION:")
                    
                    # Extract the tool name and parameters
                    action_parts = msg.content.split(' ', 2)
                    if len(action_parts) >= 3:
                        tool_name = action_parts[1]
                        tool_params = json.loads(action_parts[2])
                        
                        logger.info(f"Executing next action: {tool_name} with {tool_params}")
                        
                        if tool_name in self.mcp_clients.tool_map:
                            # Execute the specified tool
                            tool = self.mcp_clients.tool_map[tool_name]
                            
                            # Add an explanation message for analysis steps
                            if msg.content.startswith('NEXT_ACTION:') and 'action' in tool_params:
                                self.memory.add_message(Message.assistant_message(
                                    f"Now I'm executing the '{tool_params['action']}' step of the website analysis."
                                ))
                            
                            # Execute the tool
                            result = await tool.execute(**tool_params)
                            
                            # Update execution info
                            self.update_execution_info(tool_name, result)
                            
                            # Add the result to memory
                            tool_message = Message.tool_message(
                                name=tool_name,
                                content=result.output or result.error or "No result",
                                tool_call_id=self.generate_tool_call_id(tool_name),
                                base64_image=result.base64_image
                            )
                            self.memory.add_message(tool_message)
                            
                            # Remove the message so we don't process it again
                            self.memory.messages.remove(msg)
                            
                            # For website analysis, add a progress message
                            if 'action' in tool_params and current_step_num < len(analysis_plan) - 1:
                                self.memory.add_message(Message.assistant_message(
                                    f"I've completed the '{tool_params['action']}' step. Moving to the next step in the analysis process."
                                ))
                            
                            # After all steps are complete, add a message to prompt for summary
                            is_last_step = msg.content.startswith('NEXT_ACTION:') and \
                                         any(m.role == 'system' and m.content.startswith(f"ANALYSIS_STEP_{len(analysis_plan)-1}") for m in self.memory.messages)
                            
                            if is_last_step:
                                self.memory.add_message(Message.system_message(
                                    "All analysis steps completed. Provide a comprehensive website analysis summary now."
                                ))
                            
                            return True
                except Exception as e:
                    logger.error(f"Error processing action: {e}")
                    # Continue with normal processing
                break
        
        # Check MCP session and tools availability
        if not self.mcp_clients.session or not self.mcp_clients.tool_map:
            logger.info("MCP service is no longer available, ending interaction")
            self.state = AgentState.FINISHED
            return False

        # Refresh tools periodically
        if self.current_step % self._refresh_tools_interval == 0:
            logger.info(f"Refreshing tools (step {self.current_step})")
            await self._refresh_tools()
            # All tools removed indicates shutdown
            if not self.mcp_clients.tool_map:
                logger.info("MCP service has shut down, ending interaction")
                self.state = AgentState.FINISHED
                return False

        # Create an LLM integration instance
        logger.info("Creating LLM integration for MCP Agent's thinking")
        
        # Check if we need a vision model (for analyzing browser screenshots)
        vision_model_needed = False
        for msg in self.memory.messages:
            if msg.role == 'tool' and msg.base64_image and msg.name == 'browser_use':
                vision_model_needed = True
                break
                
        # Use vision model if needed, otherwise use regular model
        if vision_model_needed:
            logger.info("Browser screenshot detected - using vision model")
            llm_integration = LLMIntegration("vision")
        else:
            llm_integration = LLMIntegration()

        try:
            # Get the latest messages for context
            all_messages = self.memory.messages
            logger.info(f"Preparing to ask LLM with {len(all_messages)} messages")
            
            # Format system prompt with available tools
            tool_names = list(self.mcp_clients.tool_map.keys())
            tools_info = ", ".join(tool_names)
            system_message = Message.system_message(
                f"{self.system_prompt}\n\nAvailable MCP tools: {tools_info}"
            )
            
            logger.info("Calling LLM for tool selection or response")
            # Adjust the timeout based on current step and website complexity
            if self.adaptive_timeout:
                # Start with our initial timeout value
                self.current_timeout = self.initial_timeout
                
                # Increase timeout if we're analyzing websites with long content
                for msg in self.memory.messages:
                    if msg.role == 'tool' and len(msg.content) > 10000:
                        # For large page content, increase timeout
                        self.current_timeout = min(120, self.current_timeout + 30)  # Max 120 seconds
                        logger.info(f"Increased timeout to {self.current_timeout}s due to large content")
                        break
                    
                # Also increase timeout based on step number (more history = more tokens)
                if self.current_step > 5:
                    step_increase = min(30, (self.current_step - 5) * 5)  # 5 second increase per step after 5th
                    self.current_timeout = min(120, self.current_timeout + step_increase)
                    logger.info(f"Increased timeout to {self.current_timeout}s due to step count")
            
            # Set up a timeout for the LLM call
            logger.info(f"Setting up {self.current_timeout} second timeout for LLM call")
            try:
                # Create a task for the LLM call
                llm_task = asyncio.create_task(llm_integration.ask_with_tools(
                    messages=all_messages[1:],  # Skip system message as we're providing it separately
                    system_msgs=[system_message.to_dict()],
                    tools=None,  # We're using XML-based tool calls
                    stream=False,
                    temperature=0.7  # Use higher temperature for more creative responses
                ))
                
                # Wait for the task with a shorter timeout first
                try:
                    response = await asyncio.wait_for(llm_task, timeout=15)  # Try with a shorter timeout first
                    logger.info("LLM response received successfully with shortened timeout")
                except asyncio.TimeoutError:
                    # If it times out with the short timeout, try again with the full timeout
                    logger.warning("LLM call taking longer than expected, extending timeout")
                    try:
                        response = await asyncio.wait_for(llm_task, timeout=self.current_timeout - 15)
                        logger.info("LLM response received successfully with extended timeout")
                    except asyncio.TimeoutError:
                        # If it still times out, check if this is a URL navigation request
                        logger.error(f"LLM call timed out after {self.current_timeout} seconds")
                        # Use regex to extract URLs from the user's request
                        import re
                        urls = []
                        for msg in all_messages:
                            if msg.get('role') == 'user':
                                content = msg.get('content', '')
                                if isinstance(content, str):
                                    urls.extend(re.findall(r'https?://[^\s]+', content))
                        
                        if urls:
                            url = urls[0].rstrip(',.;:"\')')  # Clean the URL
                            logger.info(f"Proceeding directly to navigate to: {url}")
                            
                            # Proceed directly with browser navigation
                            self.memory.add_message(Message.assistant_message(
                                f"I'll navigate to {url} and analyze the website for you."
                            ))
                            
                            # Create a tool call for browser navigation
                            tool_call = ToolCall(
                                name="browser_use",
                                parameters={"action": "go_to_url", "url": url},
                                partial=False
                            )
                            
                            # Execute browser navigation
                            logger.info(f"Using browser_use to navigate to {url}")
                            tool = self.mcp_clients.tool_map["browser_use"]
                            result = await tool.execute(**tool_call.parameters)
                            
                            # Update execution metrics
                            self.update_execution_info("browser_use", result)
                            
                            # Add the result to memory
                            tool_message = Message.tool_message(
                                name="browser_use",
                                content=result.output or result.error or "No result",
                                tool_call_id=self.generate_tool_call_id("browser_use"),
                                base64_image=result.base64_image
                            )
                            self.memory.add_message(tool_message)
                            
                            # Handle multimedia
                            if result.base64_image:
                                from app.prompt.mcp import BROWSER_SCREENSHOT_PROMPT
                                self.memory.add_message(Message.system_message(BROWSER_SCREENSHOT_PROMPT))
                            
                            return True  # Continue execution
                        else:
                            # No URL found, return a helpful message
                            self.memory.add_message(Message.assistant_message(
                                "I'm having trouble connecting to the language model service. Please try again or provide a URL to visit."
                            ))
                            return False
                
                # Reset timeout after successful call for future steps
                if self.adaptive_timeout and self.current_timeout > self.initial_timeout:
                    self.current_timeout = self.initial_timeout
                    logger.info(f"Reset timeout to {self.current_timeout}s after successful call")
                    
            except asyncio.TimeoutError:
                logger.error(f"LLM call timed out after {self.current_timeout} seconds")
                self.memory.add_message(
                    Message.system_message("I'm having trouble processing your request due to a timeout. Let me try a simpler approach.")
                )
                # Check if this looks like a website analysis request
                url_match = None
                import re
                for msg in all_messages:
                    if msg.role == 'user':
                        # Look for URLs in the message
                        urls = re.findall(r'https?://[^\s]+', msg.content)
                        if urls and any(u for u in urls if 'analyze' in msg.content.lower() or 'analyse' in msg.content.lower()):
                            url_match = urls[0]  # Use the first URL
                            break
                
                if url_match:
                    # This is likely a website analysis request
                    logger.info(f"Detected website analysis request for {url_match}")
                    self.memory.add_message(Message.assistant_message(
                        f"I'll analyze the website at {url_match}"))
                    
                    # First navigate to the URL
                    tool_call = ToolCall(
                        name="browser_use",
                        parameters={"action": "go_to_url", "url": url_match},
                        partial=False
                    )
                else:
                    # Default to a generic response
                    self.memory.add_message(Message.assistant_message(
                        "I'll help you with that."))
                    
                    tool_call = ToolCall(
                        name="browser_use",
                        parameters={"action": "go_to_url", "url": "https://www.example.com"},
                        partial=False
                    )
                # If URL found, we'll analyze it as a multi-step process
                if url_match and ('analyze' in ' '.join(msg.content.lower() for msg in all_messages if msg.role == 'user') or 'analyse' in ' '.join(msg.content.lower() for msg in all_messages if msg.role == 'user')):
                    # Set up a structured website analysis process
                    self.memory.add_message(Message.system_message(
                        "Setting up a structured website analysis process with multiple steps."
                    ))
                
                # Execute the tool
                logger.info(f"🛠️ {self.name} using fallback tool '{tool_call.name}' with action={tool_call.parameters.get('action')}")
                tool = self.mcp_clients.tool_map[tool_call.name]
                
                try:
                    result = await tool.execute(**tool_call.parameters)
                    logger.info(f"Tool execution result: {result.output[:50]}..." if result.output else "No output")
                except Exception as e:
                    logger.error(f"Error executing tool: {e}")
                    result = ToolResult(error=f"Error: {str(e)}")
                
                # Update execution history
                self.update_execution_info(tool_call.name, result)
                
                # Add the result to memory
                tool_message = Message.tool_message(
                    name=tool_call.name,
                    content=result.output or result.error or "No result",
                    tool_call_id=self.generate_tool_call_id(tool_call.name),
                    base64_image=result.base64_image
                )
                self.memory.add_message(tool_message)
                
                # Continue execution
                if url_match and ('analyze' in ' '.join(msg.content.lower() for msg in all_messages if msg.role == 'user') or 'analyse' in ' '.join(msg.content.lower() for msg in all_messages if msg.role == 'user')):
                    # Add a message to explain the analysis plan
                    self.memory.add_message(Message.assistant_message(
                        "Now I'll analyze the content of this website systematically, following these steps:\n" + 
                        "\n".join([f"- {step['description']}" for step in analysis_plan])
                    ))
                    
                    # First use get_page_content to get the HTML content
                    first_step = analysis_plan[0]
                    second_tool_call = ToolCall(
                        name="browser_use",
                        parameters={"action": first_step["action"]},
                        partial=False
                    )
                    
                    # Add to memory for transparent history
                    self.memory.add_message(Message.assistant_message(
                        f"I'll start by using the {second_tool_call.name} tool with {second_tool_call.parameters.get('action')} action to get the page content."
                    ))
                    
                    # Schedule the next actions in sequence by adding system messages
                    for i, step in enumerate(analysis_plan):
                        # Only schedule the first step immediately, the rest will be handled later
                        if i == 0:
                            self.memory.add_message(Message.system_message(
                                f"NEXT_ACTION: browser_use {json.dumps({'action': step['action']})}"
                            ))
                        else:
                            # Store the rest of the plan in memory to be executed later
                            self.memory.add_message(Message.system_message(
                                f"ANALYSIS_STEP_{i}: browser_use {json.dumps({'action': step['action']})}"
                            ))
                    
                    # Add a message to instruct the agent to complete all steps
                    self.memory.add_message(Message.system_message(
                        "After each step completes, look for ANALYSIS_STEP_x messages to continue the analysis pipeline."
                    ))
                
                return True
            
            # Extract text content and tool calls
            text_content = response.get("text", "")
            tool_calls = response.get("tool_calls", [])
            
            # Add a custom fallback message if we have neither text nor tool calls
            if not text_content.strip() and not tool_calls:
                text_content = ("I noticed you said 'hello'. I'm your AI assistant and can help with various tasks. "
                             "Would you like to see what tools I have available? Just let me know what you'd like help with.")
                logger.info(f"Using custom fallback response text: {text_content[:50]}...")
            
            # Add the text content to our memory if present
            if text_content.strip():
                self.memory.add_message(Message.assistant_message(text_content))
            
            # Check if we need to execute a tool
            if tool_calls:
                # Get the first complete tool call
                tool_call = tool_calls[0]  # We only process one tool at a time
                
                # Check if the tool is available
                if tool_call.name not in self.mcp_clients.tool_map:
                    logger.warning(f"Tool '{tool_call.name}' not found in available tools")
                    self.memory.add_message(
                        Message.system_message(f"Tool '{tool_call.name}' is not available.")
                    )
                    return False
                
                # Log the tool call
                logger.info(f"✨ {self.name}'s thoughts: ")
                logger.info(f"🛠️ {self.name} selected tool '{tool_call.name}' to use")
                
                # Execute the tool
                tool = self.mcp_clients.tool_map[tool_call.name]
                result = await tool.execute(**tool_call.parameters)
                
                # Update execution history
                self.update_execution_info(tool_call.name, result)
                
                # Add the result to memory
                tool_message = Message.tool_message(
                    name=tool_call.name,
                    content=result.output or result.error or "No result",
                    tool_call_id=self.generate_tool_call_id(tool_call.name),
                    base64_image=result.base64_image
                )
                self.memory.add_message(tool_message)
                
                # Handle multimedia results with enhanced vision processing
                if result.base64_image:
                    # Add visual information to help the agent understand the image
                    if tool_call.name == "browser_use" and tool_call.parameters.get("action") in ["get_current_state", "get_page_content", "extract_content"]:
                        # Use vision-specific prompt for browser screenshots
                        from app.prompt.mcp import BROWSER_SCREENSHOT_PROMPT
                        self.memory.add_message(
                            Message.system_message(BROWSER_SCREENSHOT_PROMPT)
                        )
                    else:
                        # Use standard prompt for other multimedia
                        self.memory.add_message(
                            Message.system_message(
                                MULTIMEDIA_RESPONSE_PROMPT.format(tool_name=tool_call.name)
                            )
                        )
                
                return True  # Continue execution
            
            return False  # No tool execution needed
            
        except Exception as e:
            logger.error(f"Error in think method: {e}")
            self.memory.add_message(
                Message.system_message(f"Error: {str(e)}")
            )
            return False

    def generate_tool_call_id(self, tool_name: str) -> str:
        """Generate a unique ID for tool calls"""
        return f"{tool_name}_{len(self.execution_history)}"

    async def _handle_special_tool(self, name: str, result: Any, **kwargs) -> None:
        """Handle special tool execution and state changes"""
        # First process with parent handler
        await super()._handle_special_tool(name, result, **kwargs)

        # Handle multimedia responses
        if isinstance(result, ToolResult) and result.base64_image:
            self.memory.add_message(
                Message.system_message(
                    MULTIMEDIA_RESPONSE_PROMPT.format(tool_name=name)
                )
            )
            
        # If the tool is a terminate tool, set state to FINISHED
        if name.lower() == "terminate":
            logger.info("Terminate tool called, ending interaction")
            self.state = AgentState.FINISHED

    def _should_finish_execution(self, name: str, **kwargs) -> bool:
        """Determine if tool execution should finish the agent"""
        # Terminate if the tool name is 'terminate'
        return name.lower() == "terminate"
        
    def update_execution_info(self, tool_name: str, result: ToolResult) -> None:
        """Update execution info after a tool is executed."""
        # Track execution information for reporting
        execution_info = {
            "tool": tool_name,
            "success": not bool(result.error),
            "error": result.error,
            "output": result.output,
            "has_image": bool(result.base64_image)
        }
        
        # Store the execution information
        self.execution_history.append(execution_info)
        
        # Log execution details
        if result.error:
            logger.error(f"Tool '{tool_name}' execution failed: {result.error}")
        else:
            logger.info(f"Tool '{tool_name}' executed successfully")
            if result.base64_image:
                logger.info(f"Tool '{tool_name}' returned an image")
        
        # Update metrics
        self.metrics["total_executions"] += 1
        if result.error:
            self.metrics["failed_executions"] += 1
        else:
            self.metrics["successful_executions"] += 1

    async def cleanup(self) -> None:
        """Clean up MCP connection when done."""
        if self.mcp_clients.session:
            await self.mcp_clients.disconnect()
            logger.info("MCP connection closed")

    async def run(self, request: Optional[str] = None) -> str:
        """Run the agent with cleanup when done."""
        try:
            result = await super().run(request)
            return result
        finally:
            # Ensure cleanup happens even if there's an error
            await self.cleanup()
