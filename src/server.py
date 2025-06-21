#!/usr/bin/env python3
"""
MCP Server for Shell Command Execution
A Model Context Protocol server that allows safe execution of whitelisted shell commands.
"""

import asyncio
import json
import logging
import os
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
ALLOWED_COMMANDS = {
    # File system operations
    'ls': None,
    'cat': None,
    'head': None,
    'tail': None,
    'find': None,
    'tree': None,
    'wc': None,
    'du': None,
    'df': None,
    
    # Text processing
    'grep': None,
    'sed': None,
    'awk': None,
    'sort': None,
    'uniq': None,
    'cut': None,
    'tr': None,
    
    # Development tools
    'git': None,
    'npm': None,
    'yarn': None,
    'pip': None,
    'python': None,
    'node': None,
    'cargo': None,
    'make': None,
    'cmake': None,
    'rustc': None,
    'go': None,
    'java': None,
    'javac': None,
    
    # Process and system info
    'ps': None,
    'top': ['-l', '1'],  # Limit top to one iteration
    'uptime': [],
    'whoami': [],
    'id': [],
    'uname': None,
    'which': None,
    'where': None,
    'whereis': None,
    
    # Network tools
    'curl': None,
    'wget': None,
    'ping': ['-c', '1', '-c', '2', '-c', '3', '-c', '4', '-c', '5'],
    'dig': None,
    'nslookup': None,
    
    # Archive operations
    'tar': None,
    'zip': None,
    'unzip': None,
    'gzip': None,
    'gunzip': None,
    
    # Utilities
    'echo': None,
    'date': None,
    'cal': None,
    'bc': None,
    'expr': None,
    'basename': None,
    'dirname': None,
    'realpath': None,
    'pwd': [],
    
    # File operations (read-only for safety)
    'file': None,
    'stat': None,
    'md5': None,
    'sha256sum': None,
    'shasum': None,
}

class MCPServer:
    def __init__(self):
        self.running_processes: Dict[str, subprocess.Popen] = {}
    
    def is_allowed(self, cmd: str, args: List[str]) -> bool:
        """Check if command and arguments are allowed"""
        if cmd not in ALLOWED_COMMANDS:
            return False
        allowed = ALLOWED_COMMANDS[cmd]
        if allowed is None:
            return True
        return all(arg in allowed for arg in args)
    
    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request"""
        logger.info("Initializing MCP server")
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "shell-executor",
                "version": "1.0.0"
            }
        }
    
    async def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available tools"""
        tools = [
            {
                "name": "execute_command",
                "description": "Execute a shell command safely",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The command to execute"
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Command arguments",
                            "default": []
                        },
                        "working_directory": {
                            "type": "string",
                            "description": "Working directory for command execution",
                            "default": "."
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "get_joke",
                "description": "Get a joke",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_prompts",
                "description": "Get useful prompts for VSCode development and code improvement",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Category of prompts to return (all, refactoring, commenting, simplifying)",
                            "default": "all"
                        }
                    },
                    "required": []
                }
            }
        ]
        return {"tools": tools}
    
    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "execute_command":
            return await self.execute_command(arguments)
        elif tool_name == "get_joke":
            return await self.get_joke(arguments)
        elif tool_name == "get_prompts":
            return await self.get_prompts(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def execute_command(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a shell command"""
        command = args.get("command")
        cmd_args = args.get("args", [])
        working_dir = args.get("working_directory", ".")
        
        if not command:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: No command specified"
                    }
                ],
                "isError": True
            }
        
        # Check if command is allowed
        if not self.is_allowed(command, cmd_args):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Command '{command}' with args {cmd_args} is not allowed"
                    }
                ],
                "isError": True
            }
        
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
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Command: {' '.join(cmd_line)}\nExit Code: {result.returncode}\n\n{output}"
                    }
                ],
                "isError": result.returncode != 0
            }
            
        except subprocess.TimeoutExpired:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Command '{' '.join(cmd_line)}' timed out after 30 seconds"
                    }
                ],
                "isError": True
            }
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error executing command: {str(e)}"
                    }
                ],
                "isError": True
            }
    
    async def get_joke(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get a joke"""
        return {
            "content": [
                {
                    "type": "text",
                    "text": "haha"
                }
            ],
            "isError": False
        }
    
    async def get_prompts(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get useful VSCode prompts for development"""
        category = args.get("category", "all").lower()
        
        prompts = {
            "refactoring": [
                "Extract this code into a helper function with an appropriate name and parameters",
                "Refactor this code to reduce duplication and improve maintainability",
                "Break down this large function into smaller, more focused functions",
                "Extract common patterns into reusable utility functions",
                "Simplify this complex conditional logic by extracting helper methods",
                "Convert this code to use a more appropriate design pattern",
                "Refactor this code to improve separation of concerns"
            ],
            "commenting": [
                "Add comprehensive docstrings to this code explaining purpose, parameters, and return values",
                "Add inline comments explaining the complex logic in this code",
                "Add JSDoc/TypeScript comments for better IDE support and documentation",
                "Add comments explaining the business logic and why certain decisions were made",
                "Document the edge cases and assumptions in this code",
                "Add examples in the comments showing how to use this function",
                "Explain the algorithm or approach used in this code with comments"
            ],
            "simplifying": [
                "Simplify this code while maintaining the same functionality",
                "Remove unnecessary complexity and make this code more readable",
                "Replace this verbose code with a more concise equivalent",
                "Use modern language features to simplify this code",
                "Eliminate redundant variables and intermediate steps where possible",
                "Convert this imperative code to a more functional style",
                "Simplify these nested conditions using early returns or guard clauses"
            ]
        }
        
        if category == "all":
            result_prompts = []
            for cat, cat_prompts in prompts.items():
                result_prompts.append(f"\n## {cat.title()} Prompts:")
                result_prompts.extend([f"- {prompt}" for prompt in cat_prompts])
            text = "\n".join(result_prompts)
        elif category in prompts:
            text = f"## {category.title()} Prompts\n" + "\n".join([f"- {prompt}" for prompt in prompts[category]])
        else:
            text = f"Unknown category '{category}'. Available categories: all, refactoring, commenting, simplifying"
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": text
                }
            ],
            "isError": False
        }
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC request"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                result = await self.handle_initialize(params)
            elif method == "tools/list":
                result = await self.handle_tools_list(params)
            elif method == "tools/call":
                result = await self.handle_tools_call(params)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                }
            }
    
    async def run_stdio(self):
        """Run server using stdio transport"""
        logger.info("Starting MCP server on stdio")
        
        while True:
            try:
                # Read line from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Parse JSON-RPC request
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    continue
                
                # Handle request
                response = await self.handle_request(request)
                
                # Send response
                print(json.dumps(response), flush=True)
                
            except KeyboardInterrupt:
                logger.info("Shutting down server")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

async def main():
    """Main entry point"""
    server = MCPServer()
    await server.run_stdio()

if __name__ == "__main__":
    asyncio.run(main())
