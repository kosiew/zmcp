#!/usr/bin/env python3
"""
MCP Server for shell command execution.
Uses the official MCP library for proper protocol implementation.
"""

import asyncio
import logging
import subprocess
from typing import Any, Dict, List, Optional, Sequence

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio

MCP_NAME = "shell-executor-mcp"
MCP_VERSION = "0.1.0"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(MCP_NAME)

# Create the server instance
server = Server(MCP_NAME)


def _create_schema(properties: Dict[str, Any], required: List[str] | None = None) -> Dict[str, Any]:
    """Helper function to create input schema with consistent structure"""
    return {
        "type": "object",
        "properties": properties,
        "required": required or []
    }


def _string_property(description: str, default: str | None = None) -> Dict[str, Any]:
    """Helper function to create a string property"""
    prop = {
        "type": "string",
        "description": description
    }
    if default is not None:
        prop["default"] = default
    return prop


def _array_property(description: str, item_type: str = "string", default: List[Any] | None = None) -> Dict[str, Any]:
    """Helper function to create an array property"""
    prop = {
        "type": "array",
        "items": {"type": item_type},
        "description": description
    }
    if default is not None:
        prop["default"] = default
    return prop


class CommandWhitelist:
    """Manages allowed commands for security"""
    
    def __init__(self):
        # Define allowed commands and their argument patterns
        self.allowed_commands = {
            # File operations
            "ls": {"max_args": 10, "allowed_flags": ["-l", "-a", "-la", "-h", "-R"]},
            "cat": {"max_args": 5, "allowed_flags": []},
            "head": {"max_args": 5, "allowed_flags": ["-n"]},
            "tail": {"max_args": 5, "allowed_flags": ["-n", "-f"]},
            "find": {"max_args": 20, "allowed_flags": ["-name", "-type", "-size", "-mtime"]},
            "grep": {"max_args": 10, "allowed_flags": ["-r", "-i", "-n", "-v", "-l"]},
            "wc": {"max_args": 5, "allowed_flags": ["-l", "-w", "-c"]},
            
            # Directory operations
            "pwd": {"max_args": 0, "allowed_flags": []},
            "mkdir": {"max_args": 5, "allowed_flags": ["-p"]},
            
            # Process operations
            "ps": {"max_args": 5, "allowed_flags": ["aux", "-ef"]},
            "top": {"max_args": 3, "allowed_flags": ["-n"]},
            
            # System info
            "uname": {"max_args": 2, "allowed_flags": ["-a"]},
            "whoami": {"max_args": 0, "allowed_flags": []},
            "date": {"max_args": 2, "allowed_flags": []},
            "uptime": {"max_args": 0, "allowed_flags": []},
            
            # Development tools
            "git": {"max_args": 20, "allowed_flags": ["status", "log", "diff", "branch", "show"]},
            "python": {"max_args": 10, "allowed_flags": ["--version", "-c", "-m"]},
            "python3": {"max_args": 10, "allowed_flags": ["--version", "-c", "-m"]},
            "node": {"max_args": 10, "allowed_flags": ["--version", "-v"]},
            "npm": {"max_args": 10, "allowed_flags": ["list", "version", "info"]},
            "pip": {"max_args": 10, "allowed_flags": ["list", "show", "freeze"]},
            
            # Text processing
            "sort": {"max_args": 5, "allowed_flags": ["-r", "-n", "-u"]},
            "uniq": {"max_args": 3, "allowed_flags": ["-c"]},
            "cut": {"max_args": 5, "allowed_flags": ["-d", "-f"]},
        }
        
        # Dangerous commands that are never allowed
        self.dangerous_commands = {
            "rm", "rmdir", "mv", "cp", "chmod", "chown", "su", "sudo", 
            "passwd", "usermod", "userdel", "groupdel", "killall", "pkill",
            "reboot", "shutdown", "halt", "mount", "umount", "fdisk",
            "dd", "mkfs", "fsck", "crontab", "service", "systemctl"
        }
    
    def is_allowed(self, command: str, args: List[str]) -> bool:
        """Check if a command with given arguments is allowed"""
        if command in self.dangerous_commands:
            return False
        
        if command not in self.allowed_commands:
            return False
        
        config = self.allowed_commands[command]
        
        # Check argument count
        if len(args) > config["max_args"]:
            return False
        
        # Check for dangerous patterns in arguments
        dangerous_patterns = ["sudo", "su", "rm", "del", ">", ">>", "|", "&", ";", "`", "$"]
        for arg in args:
            for pattern in dangerous_patterns:
                if pattern in arg:
                    return False
        
        return True


# Initialize command whitelist
whitelist = CommandWhitelist()



@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="execute_command",
            description="Execute a whitelisted shell command safely",
            inputSchema=_create_schema({
                "command": _string_property("The command to execute"),
                "args": _array_property("Command arguments", default=[]),
                "working_directory": _string_property(
                    "Working directory for command execution", 
                    "."
                )
            }, ["command"]),
        ),
        types.Tool(
            name="get_joke",
            description="Get a simple joke for testing",
            inputSchema=_create_schema({}),
        ),

    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls"""
    if arguments is None:
        arguments = {}
    
    if name == "execute_command":
        return await execute_command(arguments)
    elif name == "get_joke":
        return await get_joke(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def execute_command(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Execute a shell command"""
    command = args.get("command")
    cmd_args = args.get("args", [])
    working_dir = args.get("working_directory", ".")
    
    if not command:
        return [types.TextContent(type="text", text="Error: No command specified")]
    
    # Check if command is allowed
    if not whitelist.is_allowed(command, cmd_args):
        return [types.TextContent(
            type="text", 
            text=f"Error: Command '{command}' with args {cmd_args} is not allowed"
        )]
    
    # Build command line
    cmd_line = [command] + cmd_args
    
    try:
        # Execute command
        result = subprocess.run(
            cmd_line,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Prepare output
        output_parts = []
        if result.stdout:
            output_parts.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"STDERR:\n{result.stderr}")
        
        output = "\n\n".join(output_parts) if output_parts else "(no output)"
        
        return [types.TextContent(
            type="text",
            text=f"Command: {' '.join(cmd_line)}\nExit Code: {result.returncode}\n\n{output}"
        )]
        
    except subprocess.TimeoutExpired:
        return [types.TextContent(
            type="text",
            text=f"Error: Command '{' '.join(cmd_line)}' timed out after 30 seconds"
        )]
    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"Error executing command: {str(e)}"
        )]


async def get_joke(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Get a joke"""
    return [types.TextContent(type="text", text="Why do programmers prefer dark mode? Because light attracts bugs! 🐛")]




async def main():
    """Main entry point for the MCP server"""
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=MCP_NAME,
                server_version=MCP_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
