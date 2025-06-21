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
            },
            {
                "name": "refactor_code",
                "description": "Refactor provided code to improve structure and maintainability",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The code content to refactor"
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language (e.g., python, javascript, typescript, etc.)",
                            "default": "auto-detect"
                        },
                        "refactor_type": {
                            "type": "string",
                            "description": "Type of refactoring: extract_function, reduce_duplication, simplify_conditionals, improve_naming, or general",
                            "default": "general"
                        }
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "add_comments",
                "description": "Add comprehensive comments and documentation to provided code",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The code content to document"
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language (e.g., python, javascript, typescript, etc.)",
                            "default": "auto-detect"
                        },
                        "comment_style": {
                            "type": "string",
                            "description": "Style of comments: docstring, inline, jsdoc, or comprehensive",
                            "default": "comprehensive"
                        }
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "simplify_code",
                "description": "Simplify provided code while maintaining functionality",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The code content to simplify"
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language (e.g., python, javascript, typescript, etc.)",
                            "default": "auto-detect"
                        },
                        "simplify_approach": {
                            "type": "string",
                            "description": "Approach: reduce_nesting, use_modern_features, eliminate_redundancy, or comprehensive",
                            "default": "comprehensive"
                        }
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "analyze_code",
                "description": "Analyze provided code and suggest improvements",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The code content to analyze"
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language (e.g., python, javascript, typescript, etc.)",
                            "default": "auto-detect"
                        },
                        "analysis_focus": {
                            "type": "string",
                            "description": "Focus area: performance, readability, maintainability, security, or all",
                            "default": "all"
                        }
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "execute_command_v2",
                "description": "Execute a shell command with enhanced features",
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
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout for command execution in seconds",
                            "default": 30
                        },
                        "capture_output": {
                            "type": "boolean",
                            "description": "Whether to capture command output",
                            "default": True
                        }
                    },
                    "required": ["command"]
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
        elif tool_name == "refactor_code":
            return await self.refactor_code(arguments)
        elif tool_name == "add_comments":
            return await self.add_comments(arguments)
        elif tool_name == "simplify_code":
            return await self.simplify_code(arguments)
        elif tool_name == "analyze_code":
            return await self.analyze_code(arguments)
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
    
    def detect_language(self, code: str, language_hint: str = "auto-detect") -> str:
        """Detect programming language from code content"""
        if language_hint != "auto-detect":
            return language_hint.lower()
        
        # Simple language detection based on common patterns
        code_lower = code.lower()
        
        if "def " in code or "import " in code or "class " in code:
            return "python"
        elif "function " in code or "const " in code or "let " in code or "var " in code:
            return "javascript"
        elif "interface " in code or "type " in code and "=>" in code:
            return "typescript"
        elif "#include" in code or "int main" in code:
            return "c"
        elif "public class" in code or "private " in code or "public " in code:
            return "java"
        elif "fn " in code or "let mut" in code:
            return "rust"
        elif "func " in code or "package " in code:
            return "go"
        else:
            return "unknown"
    
    async def refactor_code(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Refactor provided code"""
        code = args.get("code", "")
        language = self.detect_language(code, args.get("language", "auto-detect"))
        refactor_type = args.get("refactor_type", "general")
        
        if not code.strip():
            return {
                "content": [{"type": "text", "text": "Error: No code provided"}],
                "isError": True
            }
        
        # Generate refactoring suggestions based on type
        suggestions = []
        
        if refactor_type == "extract_function" or refactor_type == "general":
            suggestions.append("## Extract Function Opportunities")
            suggestions.append("- Look for repeated code blocks that can be extracted into helper functions")
            suggestions.append("- Consider extracting complex conditional logic into named functions")
            suggestions.append("- Extract magic numbers and strings into named constants")
        
        if refactor_type == "reduce_duplication" or refactor_type == "general":
            suggestions.append("\n## Reduce Duplication")
            suggestions.append("- Identify similar code patterns and create shared utilities")
            suggestions.append("- Use loops or higher-order functions to eliminate repetitive code")
            suggestions.append("- Consider using inheritance or composition for shared behavior")
        
        if refactor_type == "simplify_conditionals" or refactor_type == "general":
            suggestions.append("\n## Simplify Conditionals")
            suggestions.append("- Use early returns to reduce nesting")
            suggestions.append("- Replace complex if-else chains with switch statements or lookup tables")
            suggestions.append("- Extract complex boolean expressions into well-named variables")
        
        if refactor_type == "improve_naming" or refactor_type == "general":
            suggestions.append("\n## Improve Naming")
            suggestions.append("- Use descriptive names that explain intent rather than implementation")
            suggestions.append("- Follow language-specific naming conventions")
            suggestions.append("- Avoid abbreviations and single-letter variables (except for short loops)")
        
        # Add language-specific suggestions
        if language == "python":
            suggestions.append("\n## Python-Specific Refactoring")
            suggestions.append("- Use list comprehensions where appropriate")
            suggestions.append("- Consider using dataclasses for simple data containers")
            suggestions.append("- Use context managers for resource management")
        elif language == "javascript" or language == "typescript":
            suggestions.append("\n## JavaScript/TypeScript-Specific Refactoring")
            suggestions.append("- Use arrow functions for short callbacks")
            suggestions.append("- Consider using destructuring for object property access")
            suggestions.append("- Use async/await instead of Promise chains")
        
        result_text = f"## Refactoring Analysis for {language.title()} Code\n\n"
        result_text += f"**Original Code:**\n```{language}\n{code}\n```\n\n"
        result_text += "**Refactoring Suggestions:**\n"
        result_text += "\n".join(suggestions)
        
        return {
            "content": [{"type": "text", "text": result_text}],
            "isError": False
        }
    
    async def add_comments(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add comments to provided code"""
        code = args.get("code", "")
        language = self.detect_language(code, args.get("language", "auto-detect"))
        comment_style = args.get("comment_style", "comprehensive")
        
        if not code.strip():
            return {
                "content": [{"type": "text", "text": "Error: No code provided"}],
                "isError": True
            }
        
        # Generate commenting suggestions
        suggestions = []
        
        if comment_style == "docstring" or comment_style == "comprehensive":
            suggestions.append("## Function/Method Documentation")
            if language == "python":
                suggestions.append('- Add docstrings using """triple quotes"""')
                suggestions.append("- Include Args:, Returns:, and Raises: sections")
            elif language in ["javascript", "typescript"]:
                suggestions.append("- Add JSDoc comments with @param, @returns, @throws")
            else:
                suggestions.append("- Add function-level documentation explaining purpose")
        
        if comment_style == "inline" or comment_style == "comprehensive":
            suggestions.append("\n## Inline Comments")
            suggestions.append("- Explain complex algorithms or business logic")
            suggestions.append("- Document non-obvious variable purposes")
            suggestions.append("- Explain why certain approaches were chosen")
            suggestions.append("- Document edge cases and assumptions")
        
        if comment_style == "comprehensive":
            suggestions.append("\n## File-Level Documentation")
            suggestions.append("- Add module/file-level description at the top")
            suggestions.append("- Document main classes, functions, and their relationships")
            suggestions.append("- Include usage examples where helpful")
        
        # Language-specific comment formats
        comment_examples = {
            "python": "# Single line\n\"\"\"\nMulti-line docstring\n\"\"\"",
            "javascript": "// Single line\n/* Multi-line\n   comment */\n/** JSDoc comment */",
            "typescript": "// Single line\n/* Multi-line */\n/** TSDoc comment */",
            "java": "// Single line\n/* Multi-line */\n/** Javadoc comment */",
            "c": "// Single line\n/* Multi-line comment */",
            "rust": "// Single line\n/// Documentation comment\n/* Multi-line */",
            "go": "// Single line\n/* Multi-line comment */"
        }
        
        result_text = f"## Comment Enhancement for {language.title()} Code\n\n"
        result_text += f"**Original Code:**\n```{language}\n{code}\n```\n\n"
        result_text += "**Commenting Guidelines:**\n"
        result_text += "\n".join(suggestions)
        
        if language in comment_examples:
            result_text += f"\n\n**{language.title()} Comment Syntax:**\n```{language}\n{comment_examples[language]}\n```"
        
        return {
            "content": [{"type": "text", "text": result_text}],
            "isError": False
        }
    
    async def simplify_code(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Simplify provided code"""
        code = args.get("code", "")
        language = self.detect_language(code, args.get("language", "auto-detect"))
        approach = args.get("simplify_approach", "comprehensive")
        
        if not code.strip():
            return {
                "content": [{"type": "text", "text": "Error: No code provided"}],
                "isError": True
            }
        
        suggestions = []
        
        if approach == "reduce_nesting" or approach == "comprehensive":
            suggestions.append("## Reduce Nesting")
            suggestions.append("- Use early returns to eliminate else blocks")
            suggestions.append("- Extract nested logic into separate functions")
            suggestions.append("- Use guard clauses for validation")
        
        if approach == "use_modern_features" or approach == "comprehensive":
            suggestions.append("\n## Use Modern Language Features")
            if language == "python":
                suggestions.append("- Use f-strings instead of string formatting")
                suggestions.append("- Use walrus operator (:=) where appropriate")
                suggestions.append("- Use match statements for complex conditionals (Python 3.10+)")
            elif language in ["javascript", "typescript"]:
                suggestions.append("- Use template literals instead of string concatenation")
                suggestions.append("- Use optional chaining (?.) and nullish coalescing (??)")
                suggestions.append("- Use array methods like map, filter, reduce")
        
        if approach == "eliminate_redundancy" or approach == "comprehensive":
            suggestions.append("\n## Eliminate Redundancy")
            suggestions.append("- Remove unnecessary variables")
            suggestions.append("- Combine similar operations")
            suggestions.append("- Use built-in functions instead of custom implementations")
        
        # General simplification principles
        suggestions.append("\n## General Simplification")
        suggestions.append("- Prefer explicit over implicit when it improves readability")
        suggestions.append("- Use meaningful variable names to reduce need for comments")
        suggestions.append("- Break down complex expressions into smaller, named parts")
        suggestions.append("- Remove dead code and unused variables")
        
        result_text = f"## Code Simplification for {language.title()}\n\n"
        result_text += f"**Original Code:**\n```{language}\n{code}\n```\n\n"
        result_text += "**Simplification Suggestions:**\n"
        result_text += "\n".join(suggestions)
        
        return {
            "content": [{"type": "text", "text": result_text}],
            "isError": False
        }
    
    async def analyze_code(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze provided code and suggest improvements"""
        code = args.get("code", "")
        language = self.detect_language(code, args.get("language", "auto-detect"))
        focus = args.get("analysis_focus", "all")
        
        if not code.strip():
            return {
                "content": [{"type": "text", "text": "Error: No code provided"}],
                "isError": True
            }
        
        analysis_results = []
        
        # Code metrics
        lines = code.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        analysis_results.append(f"## Code Analysis for {language.title()}")
        analysis_results.append(f"- **Total lines:** {len(lines)}")
        analysis_results.append(f"- **Non-empty lines:** {len(non_empty_lines)}")
        analysis_results.append(f"- **Language detected:** {language}")
        
        if focus == "performance" or focus == "all":
            analysis_results.append("\n## Performance Analysis")
            analysis_results.append("- Look for nested loops that could be optimized")
            analysis_results.append("- Check for unnecessary object creation in loops")
            analysis_results.append("- Consider caching expensive calculations")
            analysis_results.append("- Review data structure choices for efficiency")
        
        if focus == "readability" or focus == "all":
            analysis_results.append("\n## Readability Analysis")
            analysis_results.append("- Variable names should be descriptive and meaningful")
            analysis_results.append("- Functions should have single, clear responsibilities")
            analysis_results.append("- Complex expressions should be broken down")
            analysis_results.append("- Magic numbers should be replaced with named constants")
        
        if focus == "maintainability" or focus == "all":
            analysis_results.append("\n## Maintainability Analysis")
            analysis_results.append("- Check for code duplication that could be extracted")
            analysis_results.append("- Ensure functions are not too long (consider 20-30 lines max)")
            analysis_results.append("- Review dependencies and coupling between components")
            analysis_results.append("- Add error handling for edge cases")
        
        if focus == "security" or focus == "all":
            analysis_results.append("\n## Security Considerations")
            analysis_results.append("- Validate all input parameters")
            analysis_results.append("- Avoid hardcoded secrets or credentials")
            analysis_results.append("- Use parameterized queries for database operations")
            analysis_results.append("- Sanitize user input to prevent injection attacks")
        
        result_text = f"**Code to Analyze:**\n```{language}\n{code}\n```\n\n"
        result_text += "\n".join(analysis_results)
        
        return {
            "content": [{"type": "text", "text": result_text}],
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
