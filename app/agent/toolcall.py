import asyncio
import json
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from app.agent.react import ReActAgent
from app.exceptions import TokenLimitExceeded
from app.logger import logger
from app.parser.tool_parser import ToolCall, parse_assistant_message
from app.prompt.toolcall import NEXT_STEP_PROMPT, SYSTEM_PROMPT
from app.schema import TOOL_CHOICE_TYPE, AgentState, Message, ToolChoice
from app.tool import CreateChatCompletion, Terminate, ToolCollection


TOOL_CALL_REQUIRED = "Tool calls required but none provided"


class ToolCallAgent(ReActAgent):
    """Agent that handles XML-formatted tool calls"""

    name: str = "toolcall"
    description: str = "an agent that can execute XML-formatted tool calls."

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = ToolCollection(
        CreateChatCompletion(), Terminate()
    )
    tool_choices: TOOL_CHOICE_TYPE = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    tool_calls: List[ToolCall] = Field(default_factory=list)
    _current_base64_image: Optional[str] = None

    max_steps: int = 30
    max_observe: Optional[Union[int, bool]] = None

    async def think(self) -> bool:
        """Process LLM response and extract XML tool calls"""
        if self.next_step_prompt:
            user_msg = Message.user_message(self.next_step_prompt)
            self.messages += [user_msg]

        try:
            # Get raw LLM response
            response = await self.llm.ask(
                messages=self.messages,
                system_msgs=(
                    [Message.system_message(self.system_prompt)]
                    if self.system_prompt
                    else None
                )
            )
            
            if not response or not response.content:
                raise RuntimeError("No response received from the LLM")

            # Parse XML tool calls from response
            text_content, tool_calls = parse_assistant_message(response.content)
            self.tool_calls = tool_calls

            # Log response info
            logger.info(f"✨ {self.name}'s thoughts: {text_content}")
            logger.info(f"🛠️ {self.name} selected {len(tool_calls)} tools to use")
            if tool_calls:
                logger.info(f"🧰 Tools being prepared: {[call.name for call in tool_calls]}")
                logger.info(f"🔧 Tool parameters: {tool_calls[0].parameters}")

            # Add assistant message to memory
            if text_content:
                self.memory.add_message(Message.assistant_message(text_content))

            return bool(self.tool_calls or text_content)

        except Exception as e:
            logger.error(f"🚨 Error in {self.name}'s thinking process: {e}")
            self.memory.add_message(
                Message.assistant_message(f"Error encountered: {str(e)}")
            )
            return False

    async def act(self) -> str:
        """Execute parsed tool calls"""
        if not self.tool_calls:
            if self.tool_choices == ToolChoice.REQUIRED:
                raise ValueError(TOOL_CALL_REQUIRED)
            return self.messages[-1].content or ""

        results = []
        for tool_call in self.tool_calls:
            self._current_base64_image = None
            result = await self.execute_tool(tool_call)
            
            if self.max_observe:
                result = result[:self.max_observe]

            logger.info(f"🎯 Tool '{tool_call.name}' completed. Result: {result}")
            
            # Add tool response to memory
            tool_msg = Message.tool_message(
                content=result,
                tool_call_id=tool_call.name,  # Using name as ID for simplicity
                name=tool_call.name,
                base64_image=self._current_base64_image
            )
            self.memory.add_message(tool_msg)
            results.append(result)

        return "\n\n".join(results)

    async def execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a single XML-parsed tool call"""
        if not tool_call or not tool_call.name:
            return "Error: Invalid tool call format"

        if tool_call.name not in self.available_tools.tool_map:
            return f"Error: Unknown tool '{tool_call.name}'"

        try:
            # Execute the tool with parsed parameters
            logger.info(f"🔧 Activating tool: '{tool_call.name}'...")
            result = await self.available_tools.execute(
                name=tool_call.name, 
                tool_input=tool_call.parameters
            )

            # Handle special tools
            await self._handle_special_tool(name=tool_call.name, result=result)

            # Handle image results
            if hasattr(result, "base64_image") and result.base64_image:
                self._current_base64_image = result.base64_image

            return str(result) if result else f"Tool '{tool_call.name}' completed"

        except Exception as e:
            error_msg = f"⚠️ Tool '{tool_call.name}' failed: {str(e)}"
            logger.exception(error_msg)
            return f"Error: {error_msg}"

    # ... (keep existing _handle_special_tool, _is_special_tool, cleanup, and run methods)
    async def _handle_special_tool(self, name: str, result: Any, **kwargs):
        """Handle special tool execution and state changes"""
        if not self._is_special_tool(name):
            return

        if self._should_finish_execution(name=name, result=result, **kwargs):
            logger.info(f"🏁 Special tool '{name}' has completed the task!")
            self.state = AgentState.FINISHED

    @staticmethod
    def _should_finish_execution(**kwargs) -> bool:
        """Determine if tool execution should finish the agent"""
        return True

    def _is_special_tool(self, name: str) -> bool:
        """Check if tool name is in special tools list"""
        return name.lower() in [n.lower() for n in self.special_tool_names]

    async def cleanup(self):
        """Clean up resources used by the agent's tools."""
        logger.info(f"🧹 Cleaning up resources for agent '{self.name}'...")
        for tool_name, tool_instance in self.available_tools.tool_map.items():
            if hasattr(tool_instance, "cleanup") and asyncio.iscoroutinefunction(
                tool_instance.cleanup
            ):
                try:
                    logger.debug(f"🧼 Cleaning up tool: {tool_name}")
                    await tool_instance.cleanup()
                except Exception as e:
                    logger.error(
                        f"🚨 Error cleaning up tool '{tool_name}': {e}", exc_info=True
                    )
        logger.info(f"✨ Cleanup complete for agent '{self.name}'.")

    async def run(self, request: Optional[str] = None) -> str:
        """Run the agent with cleanup when done."""
        try:
            return await super().run(request)
        finally:
            await self.cleanup()
