"""
Model Context Protocol (MCP) Client for OmniCode.
Connects to external MCP servers via stdio and exposes their tools to the OmniCode agent.
"""

import asyncio
import json
import os
import shutil
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult


class MCPExternalTool(BaseTool):
    """Adapter wrapping a tool exposed by an external MCP server."""

    def __init__(
        self,
        server_name: str,
        name: str,
        description: str,
        schema: Dict[str, Any],
        mcp_client: "MCPClient",
        is_read_only: bool = False,
    ):
        self.server_name = server_name
        self.name = f"mcp__{server_name}__{name}"
        self.raw_name = name
        self.description = f"[{server_name}] {description}"
        self.schema = schema
        self.mcp_client = mcp_client
        self.is_read_only = is_read_only

    def get_parameters_schema(self) -> Dict[str, Any]:
        return self.schema

    async def execute(self, **kwargs) -> ToolResult:
        return await self.mcp_client.call_tool(self.server_name, self.raw_name, kwargs)


class MCPClient:
    """Manages stdio connections to external MCP servers."""

    def __init__(self):
        self.servers: Dict[str, Any] = {}
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.request_id = 0

    async def start_server(
        self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None
    ) -> List[MCPExternalTool]:
        """Spawn MCP server process and query its tools."""
        try:
            full_env = os.environ.copy()
            if env:
                full_env.update(env)

            executable = shutil.which(command) or command
            proc = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
            )
            self.processes[name] = proc

            # Send initialize JSON-RPC request
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "omnicode", "version": "1.0.0"},
                },
            }
            await self._send_msg(proc, init_req)
            await self._read_msg(proc)

            # Send initialized notification
            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            await self._send_msg(proc, notif)

            # List tools
            tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            await self._send_msg(proc, tools_req)
            resp = await self._read_msg(proc)

            tools = []
            if resp and "result" in resp and "tools" in resp["result"]:
                for t in resp["result"]["tools"]:
                    tool = MCPExternalTool(
                        server_name=name,
                        name=t["name"],
                        description=t.get("description", ""),
                        schema=t.get("inputSchema", {"type": "object", "properties": {}}),
                        mcp_client=self,
                        is_read_only=t.get("readOnly", False),
                    )
                    tools.append(tool)

            return tools
        except Exception:
            return []

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Call tool on target MCP server via JSON-RPC."""
        proc = self.processes.get(server_name)
        if not proc:
            return ToolResult(
                success=False, error=f"MCP server '{server_name}' is not running."
            )

        self.request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        try:
            await self._send_msg(proc, req)
            resp = await self._read_msg(proc)
            if not resp:
                return ToolResult(
                    success=False, error=f"No response from MCP server '{server_name}'."
                )

            if "error" in resp:
                return ToolResult(
                    success=False, error=str(resp["error"].get("message", resp["error"]))
                )

            res = resp.get("result", {})
            content = res.get("content", [])
            output_lines = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    output_lines.append(item["text"])
                elif isinstance(item, str):
                    output_lines.append(item)

            return ToolResult(
                success=not res.get("isError", False),
                output="\n".join(output_lines) or str(res),
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to execute MCP tool: {str(e)}"
            )

    async def _send_msg(self, proc: asyncio.subprocess.Process, msg: dict):
        line = json.dumps(msg) + "\n"
        if proc.stdin:
            proc.stdin.write(line.encode("utf-8"))
            await proc.stdin.drain()

    async def _read_msg(
        self, proc: asyncio.subprocess.Process, timeout: float = 10.0
    ) -> Optional[dict]:
        try:
            if not proc.stdout:
                return None
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not line:
                return None
            return json.loads(line.decode("utf-8"))
        except Exception:
            return None

    def close(self):
        for proc in self.processes.values():
            try:
                proc.kill()
            except Exception:
                pass
        self.processes.clear()
