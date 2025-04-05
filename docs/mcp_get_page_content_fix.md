# MCP Get Page Content Fix

## Issue Overview

When using the OpenManus MCP (Model Context Protocol) agent with the `run_mcp.py` script, the user tried to analyze a website using a command like:

```
go to https://occasionhirenottingham.co.uk and analyse the website
```

The MCP agent successfully navigated to the website but then attempted to use a non-existent action called `get_page_content`:

```
Executing browser_use: {'action': 'get_page_content', ...}
Result of browser_use: Error: Unknown action: get_page_content
```

The problem was that the MCP agent is trying to use an action called `get_page_content` which wasn't defined in the `browser_use_tool.py` file. The similar action that was available is `extract_content`, but the system prompt for the MCP agent likely refers to `get_page_content` instead.

## Solution

The fix involved adding a new `get_page_content` action to the `browser_use_tool.py` file that serves as an alias for the `extract_content` action:

1. Added `get_page_content` to the list of allowed actions in the enum
2. Updated the dependencies section to include `get_page_content` with no required parameters
3. Added the action to the tool description for discoverability
4. Implemented the action by:
   - Checking for either `get_page_content` or `extract_content` action
   - Using a default goal for `get_page_content`
   - Leveraging the same code for both actions

The implementation also includes enhanced mock content to better represent a real website analysis, which is especially helpful since we're using mock responses instead of real LLM analysis.

## Code Changes

### 1. Added action to enum list:
```python
"enum": [
    "go_to_url",
    "click_element",
    ...
    "extract_content",
    "get_page_content",  # Added this line
    "switch_tab",
    ...
]
```

### 2. Added to dependencies list:
```python
"dependencies": {
    ...
    "extract_content": ["goal"],
    "get_page_content": [],  # Added this line
    "refresh": [],
}
```

### 3. Updated tool description:
```
Content Actions:
- extract_content: Extract page info
- get_page_content: Get current page content  # Added this line
```

### 4. Implemented the action:
```python
# Content extraction actions
elif action == "get_page_content" or action == "extract_content":
    # Use a default goal if this is get_page_content
    if action == "get_page_content":
        goal = "Extract and analyze the current page content"
    elif not goal:
        return ToolResult(
            error="Goal is required for 'extract_content' action"
        )
    
    # Rest of the implementation is shared...
```

## Benefits

1. **Better UX**: The MCP agent can now use either `get_page_content` or `extract_content` actions, making it more robust across different prompts and system setups.

2. **Error Prevention**: By making `get_page_content` not require a goal parameter, it's easier to use for simple content extraction requests.

3. **Backwards Compatibility**: The existing `extract_content` action continues to work as before, maintaining compatibility with existing code.

4. **Enhanced Output**: The updated mock content provides more detailed and structured analysis information.

## Future Improvements

In the future, it would be ideal to replace the mock responses with actual content analysis, either by:

1. **Fixing the LLM integration** to properly handle content analysis requests
2. **Implementing a rule-based analysis system** that can extract meaningful information from web pages without requiring an LLM
3. **Creating a hybrid approach** that uses basic pattern matching for common elements and LLM calls for deeper analysis

This current fix is a pragmatic solution that allows the system to continue functioning while more robust solutions are developed.
