import asyncio
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Union

import httpx

from app.logger import logger


class MCPClient:
    """Client for Model Context Protocol (MCP) server."""

    def __init__(
        self,
        server_cmd: Optional[str] = None,
        server_timeout: int = 30,
        http_url: Optional[str] = None,
    ):
        """
        Initialize the MCP client.

        Args:
            server_cmd: Command to start the MCP server if not already running
            server_timeout: Timeout in seconds for server startup
            http_url: URL for HTTP transport (if using HTTP instead of stdio)
        """
        self.server_process = None
        self.server_cmd = server_cmd or "python run_mcp_server.py"
        self.server_timeout = server_timeout
        self.http_url = http_url
        self._ensure_server_running()

    def _ensure_server_running(self) -> None:
        """
        Ensure the MCP server is running, start it if necessary.
        Currently focused on subprocess-based stdio communication.
        """
        if self.http_url:
            # For HTTP mode, we don't need to start a server
            logger.info(f"Using MCP server at: {self.http_url}")
            return

        # Start the server as a subprocess
        logger.info(f"Starting MCP server: {self.server_cmd}")
        try:
            # Use shell=True to support complex commands with pipes, etc.
            self.server_process = subprocess.Popen(
                self.server_cmd,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True,
                bufsize=1,  # Line buffered
            )
            logger.info(f"MCP server started with PID: {self.server_process.pid}")
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            raise

    async def send_message(
        self, 
        message: str, 
        system_message: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Send a message to the MCP server and get the response.

        Args:
            message: The message to send
            system_message: Optional system message to provide context
            model: Optional model override
            temperature: Temperature for generation (creativity)

        Returns:
            The response from the MCP server
        """
        if self.http_url:
            return await self._send_http_message(message, system_message)
        else:
            return await self._send_stdio_message(message, system_message, model, temperature)

    async def _send_http_message(
        self, message: str, system_message: Optional[str] = None
    ) -> str:
        """Send a message using HTTP transport."""
        if not self.http_url:
            raise ValueError("HTTP URL not configured")

        payload = {"message": message}
        if system_message:
            payload["system_message"] = system_message

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.http_url}/message", json=payload, timeout=60
            )
            response.raise_for_status()
            return response.json()["response"]

    async def _send_stdio_message(
        self, 
        message: str, 
        system_message: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """Send a message using stdio transport."""
        if not self.server_process:
            raise RuntimeError("MCP server not running")

        # Prepare request in MCP format
        request = {
            "type": "message",
            "message": message,
        }
        
        if system_message:
            request["system_message"] = system_message
            
        if model:
            request["model"] = model
            
        request["temperature"] = temperature

        # Send request to server
        request_json = json.dumps(request) + "\n"
        self.server_process.stdin.write(request_json)
        self.server_process.stdin.flush()

        # Read response
        response_line = self.server_process.stdout.readline().strip()
        try:
            response_data = json.loads(response_line)
            return response_data.get("response", "")
        except json.JSONDecodeError:
            logger.error(f"Failed to decode MCP response: {response_line}")
            return "Error: Failed to get a proper response from the MCP server."

    async def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Execute a tool through the MCP server.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        if not self.server_process:
            raise RuntimeError("MCP server not running")

        # Prepare tool request
        request = {
            "type": "tool",
            "tool": tool_name,
            "parameters": kwargs,
        }

        # Send request
        request_json = json.dumps(request) + "\n"
        self.server_process.stdin.write(request_json)
        self.server_process.stdin.flush()

        # Read response
        response_line = self.server_process.stdout.readline().strip()
        try:
            response_data = json.loads(response_line)
            return response_data.get("result")
        except json.JSONDecodeError:
            logger.error(f"Failed to decode tool response: {response_line}")
            return None

    def close(self) -> None:
        """Close the connection to the MCP server."""
        if self.server_process:
            # Send graceful shutdown request
            try:
                self.server_process.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
                self.server_process.stdin.flush()
                # Give server time to shut down gracefully
                self.server_process.wait(timeout=5)
            except:
                pass
            
            # Terminate if still running
            if self.server_process.poll() is None:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
            
            logger.info("MCP server connection closed")
