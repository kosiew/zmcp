#!/usr/bin/env python3
"""
MCP Server for shell command execution with enhanced code analysis tools.
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shell-executor-mcp")

# Create the server instance
server = Server("shell-executor-mcp")


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


def detect_language(code: str, language_hint: str = "auto-detect") -> str:
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


@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="execute_command",
            description="Execute a whitelisted shell command safely",
            inputSchema={
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
        ),
        types.Tool(
            name="get_joke",
            description="Get a simple joke for testing",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_prompts",
            description="Get useful development prompts for code improvement",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category of prompts: all, refactoring, commenting, or simplifying",
                        "default": "all"
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="refactor_code",
            description="Analyze code and provide refactoring suggestions",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code content to refactor"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g., rust, python, javascript, typescript, etc.)",
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
        ),
        types.Tool(
            name="add_comments",
            description="Add comprehensive comments and documentation to provided code",
            inputSchema={
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
        ),
        types.Tool(
            name="simplify_code",
            description="Simplify provided code while maintaining functionality",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code content to simplify"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g., rust, python, javascript, typescript, etc.)",
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
        ),
        types.Tool(
            name="analyze_code",
            description="Analyze provided code and suggest improvements",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code content to analyze"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (e.g., rust, python, javascript, typescript, etc.)",
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
        )
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
    elif name == "get_prompts":
        return await get_prompts(arguments)
    elif name == "refactor_code":
        return await refactor_code(arguments)
    elif name == "add_comments":
        return await add_comments(arguments)
    elif name == "simplify_code":
        return await simplify_code(arguments)
    elif name == "analyze_code":
        return await analyze_code(arguments)
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


async def get_prompts(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
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
    
    return [types.TextContent(type="text", text=text)]


async def refactor_code(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Refactor provided code"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    refactor_type = args.get("refactor_type", "general")
    
    if not code.strip():
        return [types.TextContent(type="text", text="Error: No code provided")]
    
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
    
    return [types.TextContent(type="text", text=result_text)]


async def add_comments(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Add comments to provided code"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    comment_style = args.get("comment_style", "comprehensive")
    
    if not code.strip():
        return [types.TextContent(type="text", text="Error: No code provided")]
    
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
    
    return [types.TextContent(type="text", text=result_text)]


async def simplify_code(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Simplify provided code"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    approach = args.get("simplify_approach", "comprehensive")
    
    if not code.strip():
        return [types.TextContent(type="text", text="Error: No code provided")]
    
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
    
    return [types.TextContent(type="text", text=result_text)]


async def analyze_code(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Analyze provided code and suggest improvements"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    focus = args.get("analysis_focus", "all")
    
    if not code.strip():
        return [types.TextContent(type="text", text="Error: No code provided")]
    
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
    
    return [types.TextContent(type="text", text=result_text)]


async def main():
    """Main entry point for the MCP server"""
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="shell-executor-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
