from typing import Dict, List, Optional, Tuple
import re


class ToolCall:
    """Represents a parsed tool call from a model response."""
    
    def __init__(self, name: str, parameters: Dict[str, str] = None, partial: bool = False):
        self.name = name
        self.parameters = parameters or {}
        self.partial = partial  # True if tool parsing was incomplete
    
    def __repr__(self):
        return f"ToolCall(name={self.name}, parameters={self.parameters}, partial={self.partial})"


def parse_tool_calls(content: str) -> List[Tuple[str, ToolCall]]:
    """
    Parse tool calls from model content using XML-like tags.
    
    Returns a list of tuples containing (text_before_tool, tool_call)
    This preserves any text content that appeared before the tool call.
    """
    results = []
    remaining_content = content
    
    # Define the pattern for finding tool calls
    # This regex looks for <tool_name>...</tool_name> patterns
    tool_pattern = r'<([a-zA-Z_][a-zA-Z0-9_]*)>(.*?)</\1>'
    
    while remaining_content:
        # Look for the next tool call
        match = re.search(tool_pattern, remaining_content, re.DOTALL)
        
        if not match:
            # No more tool calls, add remaining text and exit
            if remaining_content.strip():
                results.append((remaining_content, None))
            break
        
        # Extract text before the tool call
        text_before = remaining_content[:match.start()].strip()
        if text_before:
            results.append((text_before, None))
        
        # Extract tool name and content
        tool_name = match.group(1)
        tool_content = match.group(2)
        
        # Parse parameters within the tool call
        parameters = {}
        param_pattern = r'<([a-zA-Z_][a-zA-Z0-9_]*)>(.*?)</\1>'
        for param_match in re.finditer(param_pattern, tool_content, re.DOTALL):
            param_name = param_match.group(1)
            param_value = param_match.group(2).strip()
            parameters[param_name] = param_value
        
        # Create and add the tool call
        tool_call = ToolCall(name=tool_name, parameters=parameters)
        results.append(("", tool_call))
        
        # Update remaining content
        remaining_content = remaining_content[match.end():].strip()
    
    return results


def parse_partial_tool_call(content: str) -> Optional[ToolCall]:
    """
    Parse a potentially incomplete tool call at the end of the content.
    This is useful for streaming responses where the tool call might be cut off.
    """
    # First check if there's an opening tag without a matching closing tag
    opening_tags = re.findall(r'<([a-zA-Z_][a-zA-Z0-9_]*)>(?!.*?</\1>)', content, re.DOTALL)
    
    if not opening_tags:
        return None
    
    # Take the last opening tag as the tool name
    tool_name = opening_tags[-1]
    
    # Extract content after the opening tag
    tool_content_match = re.search(f'<{tool_name}>(.*?)$', content, re.DOTALL)
    if not tool_content_match:
        return ToolCall(name=tool_name, partial=True)
    
    tool_content = tool_content_match.group(1)
    
    # Parse any complete parameters
    parameters = {}
    param_pattern = r'<([a-zA-Z_][a-zA-Z0-9_]*)>(.*?)</\1>'
    for param_match in re.finditer(param_pattern, tool_content, re.DOTALL):
        param_name = param_match.group(1)
        param_value = param_match.group(2).strip()
        parameters[param_name] = param_value
    
    # Check for partial parameter
    partial_param_match = re.search(r'<([a-zA-Z_][a-zA-Z0-9_]*)>([^<]*)$', tool_content, re.DOTALL)
    if partial_param_match:
        param_name = partial_param_match.group(1)
        param_value = partial_param_match.group(2).strip()
        parameters[param_name] = param_value
    
    return ToolCall(name=tool_name, parameters=parameters, partial=True)


def parse_assistant_message(content: str) -> Tuple[str, List[ToolCall]]:
    """
    Parse an assistant message to extract text content and tool calls.
    
    Returns:
        Tuple of (text_content, tool_calls) where:
        - text_content is all non-tool text combined
        - tool_calls is a list of ToolCall objects
    """
    parsed_segments = parse_tool_calls(content)
    
    # Collect all text segments
    text_content = " ".join(text for text, tool in parsed_segments if tool is None and text)
    
    # Collect all tool calls
    tool_calls = [tool for _, tool in parsed_segments if tool is not None]
    
    # Check for partial tool call at the end
    partial_tool = parse_partial_tool_call(content)
    if partial_tool:
        tool_calls.append(partial_tool)
    
    return text_content, tool_calls
