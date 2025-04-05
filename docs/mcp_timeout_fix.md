# MCP Timeout and Browser Launch Fix

## Issue Overview

When using the OpenManus MCP agent with the `run_mcp.py` script to analyze websites, the process was getting stuck without opening the browser. The issue appeared to be with the MCP agent's `think` method, where it was hanging indefinitely during the LLM call.

## Root Cause Analysis

After investigating the code, we identified the following issues:

1. **LLM Call Hanging**: The agent was getting stuck in the LLM call that decides what tool to use. This is likely due to network issues, rate limiting, or problems with the LLM configuration.

2. **No Timeout Mechanism**: There was no timeout for the LLM call, so when it got stuck, the entire agent would hang indefinitely.

3. **Missing Debug Information**: There was insufficient logging to diagnose exactly where the process was getting stuck.

4. **No Fallback Mechanism**: If the LLM call failed, there was no fallback mechanism to proceed with a reasonable default action.

## Solution

We implemented a comprehensive solution:

### 1. Added Detailed Logging

Added extensive logging throughout the agent code to better understand the execution flow:
- Log when the agent starts thinking
- Log when tools are refreshed
- Log before and after LLM calls
- Log details of tool execution

### 2. Added Timeout for LLM Calls

Implemented a 30-second timeout for LLM calls using `asyncio.wait_for()`:
```python
llm_task = asyncio.create_task(llm_integration.ask_with_tools(...))
response = await asyncio.wait_for(llm_task, timeout=30)
```

### 3. Created Smart Fallback Mechanism

When a timeout occurs, the agent now:
1. Analyzes the user request to see if it's a website analysis request
2. Extracts any URLs from the request
3. Creates a direct tool call to navigate to the detected URL (or a default URL if none is found)
4. Adds detailed error handling for the fallback tool execution

### 4. Implemented Two-Step Website Analysis

For website analysis requests, we implemented a two-step process:
1. First step: Navigate to the website
2. Second step: Use the `get_page_content` action to analyze the website

### 5. Added Forced Next Action Mechanism

Implemented a mechanism to force a specific next action:
1. The agent can now add a special system message with the next action to execute
2. The `think` method checks for these messages and executes the specified action
3. This allows for reliable multi-step sequences like website analysis

## Key Code Changes

### 1. Timeout Implementation
```python
try:
    llm_task = asyncio.create_task(llm_integration.ask_with_tools(...))
    response = await asyncio.wait_for(llm_task, timeout=30)
except asyncio.TimeoutError:
    # Fallback mechanism
```

### 2. URL Detection and Smart Fallback
```python
# Check if this looks like a website analysis request
url_match = None
for msg in all_messages:
    if msg.role == 'user':
        # Look for URLs in the message
        urls = re.findall(r'https?://[^\s]+', msg.content)
        if urls and 'analyze' in msg.content.lower():
            url_match = urls[0]  # Use the first URL
            break
```

### 3. Forced Next Action Mechanism
```python
# Schedule this for the next step by adding a system message
self.memory.add_message(Message.system_message(
    f"NEXT_ACTION: {second_tool_call.name} {json.dumps(second_tool_call.parameters)}"
))
```

```python
# Check for a forced next action from previous step
for msg in reversed(self.memory.messages):
    if msg.role == 'system' and msg.content.startswith('NEXT_ACTION:'):
        # Extract and execute the specified action
```

## Future Improvements

There are still some areas for improvement:

1. **Robust LLM Integration**: Investigate why the LLM call is hanging and implement a more reliable LLM integration.

2. **Configurable Timeouts**: Make the timeout configurable through the configuration system.

3. **Better Error Recovery**: Implement more sophisticated error recovery strategies for different types of failures.

4. **Proactive Health Checks**: Add proactive health checks for LLM availability before making calls.

5. **Persistent Memory**: Consider implementing a persistent memory system so that if the agent crashes, it can resume from where it left off.

This fix ensures that the MCP agent can reliably analyze websites even when the LLM service is unresponsive or experiencing issues.