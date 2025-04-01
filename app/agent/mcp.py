from typing import Any, Dict, List, Optional, Tuple

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

    # Special tool names that should trigger termination
    special_tool_names: List[str] = Field(default_factory=lambda: ["terminate"])
    
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
        # Check MCP session and tools availability
        if not self.mcp_clients.session or not self.mcp_clients.tool_map:
            logger.info("MCP service is no longer available, ending interaction")
            self.state = AgentState.FINISHED
            return False

        # Refresh tools periodically
        if self.current_step % self._refresh_tools_interval == 0:
            await self._refresh_tools()
            # All tools removed indicates shutdown
            if not self.mcp_clients.tool_map:
                logger.info("MCP service has shut down, ending interaction")
                self.state = AgentState.FINISHED
                return False

        # Create an LLM integration instance
        llm_integration = LLMIntegration()

        try:
            # Get the latest messages for context
            all_messages = self.memory.messages
            
            # Format system prompt with available tools
            tool_names = list(self.mcp_clients.tool_map.keys())
            tools_info = ", ".join(tool_names)
            system_message = Message.system_message(
                f"{self.system_prompt}\n\nAvailable MCP tools: {tools_info}"
            )
            
            # Ask LLM with tools
            response = await llm_integration.ask_with_tools(
                messages=all_messages[1:],  # Skip system message as we're providing it separately
                system_msgs=[system_message.to_dict()],
                tools=None,  # We're using XML-based tool calls
                stream=False
            )
            
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
                
                # Handle multimedia results
                if result.base64_image:
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
