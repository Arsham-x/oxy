"""
OXY MCP — Lightweight Model Context Protocol (MCP) stdio JSON-RPC client.

Connects to external MCP servers over stdio, discovers their tools, and
registers them into OXY's ToolRegistry as first-class agent tools.
"""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Any


class MCPClient:
    """Client for a single MCP server communicating over stdio JSON-RPC 2.0."""

    def __init__(self, server_name: str, command: str, args: list[str] | None = None, env: dict[str, str] | None = None):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._proc: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = threading.Lock()
        self._tools: list[dict[str, Any]] = []

    def start(self, timeout: float = 5.0) -> bool:
        """Spawn the MCP server process and complete initialize handshake."""
        try:
            import os
            merged_env = {**os.environ, **self.env}
            full_cmd = [self.command, *self.args]
            self._proc = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=merged_env,
                bufsize=1,
            )
        except Exception:
            return False

        # Send initialize handshake
        init_res = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "oxy", "version": "1.0.0"},
        }, timeout=timeout)

        if not init_res:
            self.stop()
            return False

        # Send initialized notification
        self._send_notification("notifications/initialized", {})
        self._tools = self.discover_tools(timeout=timeout)
        return True

    def stop(self):
        """Terminate the server process cleanly."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    def _send_request(self, method: str, params: dict[str, Any], timeout: float = 10.0) -> dict[str, Any] | None:
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            return None

        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }
            try:
                line = json.dumps(payload) + "\n"
                self._proc.stdin.write(line)
                self._proc.stdin.flush()

                # Read response line
                resp_line = self._proc.stdout.readline()
                if not resp_line:
                    return None
                data = json.loads(resp_line.strip())
                return data.get("result")
            except Exception:
                return None

    def _send_notification(self, method: str, params: dict[str, Any]):
        if not self._proc or not self._proc.stdin:
            return
        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
            try:
                line = json.dumps(payload) + "\n"
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except Exception:
                pass

    def discover_tools(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        """Query tools/list to fetch the server's registered tools."""
        res = self._send_request("tools/list", {}, timeout=timeout)
        if not res or "tools" not in res:
            return []
        return res["tools"]

    def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        """Execute a tool via tools/call request."""
        res = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        }, timeout=timeout)
        if res is None:
            return {"isError": True, "content": [{"type": "text", "text": "MCP tool call timed out or failed."}]}
        return res

    def get_registered_tools(self) -> list[dict[str, Any]]:
        return list(self._tools)


class MCPManager:
    """Manages connections to multiple MCP servers defined in config."""

    def __init__(self):
        self.clients: dict[str, MCPClient] = {}

    def load_from_config(self, config: dict[str, Any]):
        """Connect to MCP servers configured in oxy_config.json under 'mcp_servers'."""
        servers = config.get("mcp_servers", {})
        if not isinstance(servers, dict):
            return

        for name, spec in servers.items():
            if not isinstance(spec, dict):
                continue
            cmd = spec.get("command")
            if not cmd:
                continue
            args = spec.get("args", [])
            env = spec.get("env", {})
            client = MCPClient(server_name=name, command=cmd, args=args, env=env)
            if client.start():
                self.clients[name] = client

    def register_tools_into(self, tool_registry: Any):
        """Register all discovered MCP tools into OXY's ToolRegistry."""
        from .tools import ToolResult
        from .security import KNOWN_TOOLS

        for server_name, client in self.clients.items():
            for tool in client.get_registered_tools():
                raw_name = tool.get("name", "")
                namespaced = f"mcp_{server_name}_{raw_name}"
                desc = tool.get("description", f"MCP tool from {server_name}")
                param_schema = tool.get("inputSchema", {"type": "object", "properties": {}})

                # Build tool definition for ToolRegistry
                schema_entry = {
                    "type": "function",
                    "function": {
                        "name": namespaced,
                        "description": desc,
                        "parameters": param_schema,
                    },
                }

                def make_handler(c=client, t_name=raw_name):
                    def handler(**kwargs) -> ToolResult:
                        res = c.call_tool(t_name, kwargs)
                        is_err = res.get("isError", False)
                        contents = res.get("content", [])
                        text_parts = [c.get("text", "") for c in contents if isinstance(c, dict) and c.get("type") == "text"]
                        output = "\n".join(text_parts) if text_parts else json.dumps(res, default=str)
                        return ToolResult(success=not is_err, output=output)
                    return handler

                # Register in tool registry and security known tools
                tool_registry.register(namespaced, make_handler(), safe=False)
                from .tools import TOOL_SCHEMAS
                TOOL_SCHEMAS.append(schema_entry)
                KNOWN_TOOLS.add(namespaced)

    def shutdown(self):
        """Stop all connected MCP servers."""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()
