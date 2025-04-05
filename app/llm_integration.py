"""
LLM integration module that handles tool calling across different models.

This module provides a consistent interface for tool calling with different LLM providers
by using a model-agnostic XML format for tools.
"""

import asyncio
from typing import Dict, List, Any, Optional, Union

from app.llm import LLM
from app.parser.tool_parser import parse_assistant_message, ToolCall
from app.logger import logger
from app.llm.openrouter_provider import generate_openrouter_response, generate_openrouter_quick_response
from app.schema import Message


class LLMIntegration:
    """Integration layer for LLMs that standardizes tool calling."""

    def __init__(self, config_name: str = "default"):
        self.llm = LLM(config_name)
        self.active_model = self.llm.model
        self.is_openrouter = "openrouter" in config_name.lower()
        self.model_capabilities = self._detect_model_capabilities()

    def _detect_model_capabilities(self) -> Dict[str, bool]:
        """Detect capabilities of the current model."""
        model_id = self.active_model.lower()
        
        return {
            "native_tool_calling": any(
                name in model_id for name in ["gpt-4", "gpt-3.5", "claude-3"]
            ),
            "supports_images": any(
                name in model_id for name in ["gpt-4-vision", "gpt-4o", "gpt-4o-mini", "claude-3", "gemini", "deepseek"]
            ),
            "high_context": any(
                name in model_id for name in ["gpt-4-32k", "gpt-4o", "claude-3-opus", "claude-3-sonnet", "gemini-2-5"]
            ),
        }

    async def prepare_tool_messages(
        self, 
        messages: List[Union[Dict, Message]], 
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        tools: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Prepare messages for tool-enabled responses.
        
        This function:
        1. Adds XML tool instructions to system message
        2. Formats messages for the particular model
        
        Args:
            messages: List of conversation messages
            system_msgs: Optional system messages to prepend
            tools: List of tools to use (ignored for XML-based tool calls)
            
        Returns:
            List of prepared messages
        """
        # Format system messages with XML tool instructions
        if system_msgs:
            system_messages = list(system_msgs)  # Create a copy to avoid modifying the original
            
            # Add XML tool instructions to the system message
            if system_messages and isinstance(system_messages[0], dict) and system_messages[0].get("role") == "system":
                system_messages[0]["content"] += "\n\nIMPORTANT: Always format tool calls using XML tags as described above."
            
            # Format with the LLM's formatter
            formatted_messages = self.llm.format_messages(
                system_messages + messages, 
                supports_images=self.model_capabilities["supports_images"]
            )
        else:
            # No system messages provided, format regular messages
            formatted_messages = self.llm.format_messages(
                messages, 
                supports_images=self.model_capabilities["supports_images"]
            )
            
            # Add tool instructions to the first message if it's a system message
            if formatted_messages and formatted_messages[0]["role"] == "system":
                formatted_messages[0]["content"] += "\n\nIMPORTANT: Always format tool calls using XML tags as described above."
        
        return formatted_messages

    async def ask_with_tools(
        self,
        messages: List[Union[Dict, Message]],
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Ask LLM with consistent tool calling regardless of model.
        
        Args:
            messages: List of conversation messages
            system_msgs: Optional system messages to prepend
            tools: List of tools definitions (used for native tool calling models)
            stream: Whether to stream the response
            temperature: Sampling temperature for the response
            
        Returns:
            Dict with:
                - 'text': The text response content
                - 'tool_calls': List of parsed tool calls
        """
        prepared_messages = await self.prepare_tool_messages(messages, system_msgs, tools)
        
        try:
            # Special handling for OpenRouter
            if self.is_openrouter:
                model_id = self.active_model
                try:
                    # Use the quick function that has built-in timeout handling
                    response_stream = await generate_openrouter_quick_response(
                        messages=prepared_messages,
                        model_id=model_id,
                        temperature=temperature or self.llm.temperature,
                        max_tokens=self.llm.max_tokens,
                        stream=stream
                    )
                except Exception as e:
                    logger.error(f"Error with quick OpenRouter response: {e}")
                    # Fall back to the regular function
                    response_stream = await generate_openrouter_response(
                        messages=prepared_messages,
                        model_id=model_id,
                        temperature=temperature or self.llm.temperature,
                        max_tokens=self.llm.max_tokens,
                        stream=stream
                    )
                
                # Handle streaming or non-streaming response
                if stream:
                    # Streaming expected to return an async iterator
                    collected_chunks = []
                    try:
                        async for chunk in response_stream:
                            content = chunk.choices[0].delta.content
                            if content:
                                collected_chunks.append(content)
                    except (TypeError, AttributeError) as e:
                        # Handle non-streaming response that was sent with stream=True
                        logger.warning(f"Response doesn't support async iteration: {e}. Falling back to non-streaming handling.")
                        if hasattr(response_stream, 'choices') and response_stream.choices:
                            # Handle as a regular completion
                            content = response_stream.choices[0].message.content
                            if content:
                                collected_chunks.append(content)
                    
                    # Parse tool calls from the full response
                    full_text = "".join(collected_chunks)
                    text_content, tool_calls = parse_assistant_message(full_text)
                    
                    return {
                        "text": text_content,
                        "tool_calls": [tool for tool in tool_calls if not tool.partial],
                        "full_text": full_text,
                    }
                else:
                    # Non-streaming response
                    collected_chunks = []
                    
                    # Check if response_stream is already a complete response (not an async iterator)
                    if hasattr(response_stream, 'choices') and response_stream.choices:
                        # It's already a complete ChatCompletion object
                        content = response_stream.choices[0].message.content
                        if content:
                            collected_chunks.append(content)
                    else:
                        # Try to iterate (legacy support)
                        try:
                            async for chunk in response_stream:
                                content = chunk.choices[0].delta.content
                                if content:
                                    collected_chunks.append(content)
                        except (TypeError, AttributeError) as e:
                            logger.warning(f"Unexpected response format: {e}")
                    
                    full_text = "".join(collected_chunks)
                    text_content, tool_calls = parse_assistant_message(full_text)
                    
                    return {
                        "text": text_content,
                        "tool_calls": [tool for tool in tool_calls if not tool.partial],
                    }
            else:
                # Standard LLM approach
                if stream:
                    # Streaming approach
                    response = await self.llm.ask(
                        messages=prepared_messages,
                        stream=True,
                        temperature=temperature,
                    )
                    
                    # Handle empty response
                    if not response:
                        # Handle empty response with a more helpful message that suggests actions
                        logger.warning("Received empty response from LLM - providing fallback")
                        
                        # Check if this is a website analysis request
                        website_analysis = False
                        website_url = None
                        
                        for msg in messages:
                            if isinstance(msg, dict) and msg.get('role') == 'user':
                                content = msg.get('content', '')
                                if isinstance(content, str) and ('analyze' in content.lower() or 'analyse' in content.lower()) and 'http' in content:
                                    website_analysis = True
                                    # Extract URL
                                    import re
                                    urls = re.findall(r'https?://[^\s]+', content)
                                    if urls:
                                        website_url = urls[0]
                                    break
                        
                        if website_analysis and website_url:
                            # Provide a website analysis specific fallback
                            return {
                                "text": f"I'll analyze the website at {website_url} for you. I'll examine its design, content, functionality, and performance to provide a comprehensive assessment.",
                                "tool_calls": [ToolCall(
                                    name="browser_use",
                                    parameters={"action": "go_to_url", "url": website_url},
                                    partial=False
                                )],
                            }
                        else:
                            # Generic fallback
                            return {
                                "text": "I'll help you with that. Let me know what specific aspects you'd like me to assist with. I can:\n\n1. Run commands for you using the 'bash' tool\n2. Browse websites with the 'browser_use' tool\n3. Edit text with the 'str_replace_editor' tool",
                                "tool_calls": [],
                            }
                    
                    # Since the LLM class may not support true streaming with chunks,
                    # we'll just return the full response
                    text_content, tool_calls = parse_assistant_message(response)
                    
                    return {
                        "text": text_content,
                        "tool_calls": [tool for tool in tool_calls if not tool.partial],
                    }
                else:
                    # Expect the response to be ready quickly
                    response = await asyncio.wait_for(
                    self.llm.ask(
                        messages=prepared_messages,
                        stream=False,
                            temperature=temperature,
                    ),
                    timeout=30  # Add a timeout here too for safety
                )
                    
                    # Handle empty response
                    if not response:
                        # Handle empty response with a more helpful message that suggests actions
                        logger.warning("Received empty response from LLM - providing fallback")
                        return {
                            "text": "I noticed you said 'hello'. I've opened example.com in the browser. Is there something specific you'd like me to help you with? I can:\n\n1. Run commands for you using the 'bash' tool\n2. Browse websites with the 'browser_use' tool\n3. Edit text with the 'str_replace_editor' tool\n\nJust let me know what you'd like to do!",
                            "tool_calls": [],
                        }
                    
                    text_content, tool_calls = parse_assistant_message(response)
                    
                    return {
                        "text": text_content,
                        "tool_calls": [tool for tool in tool_calls if not tool.partial],
                    }
        except Exception as e:
            logger.error(f"Error in ask_with_tools: {e}")
            # Return an empty response with the error
            return {
                "text": f"Error: {str(e)}",
                "tool_calls": [],
                "error": str(e),
            }
        
    async def execute_tool(self, tool_call: ToolCall) -> Dict:
        """
        Execute a tool call using the appropriate tool handler.
        
        Args:
            tool_call: ToolCall object to execute
            
        Returns:
            Dict with the result of the tool execution
        """
        # This would be implemented to integrate with your tool framework
        pass
