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

from tool_helpers import create_schema, string_property, array_property

MCP_NAME = "shell-executor-mcp"
MCP_VERSION = "0.1.0"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(MCP_NAME)

# Create the server instance
server = Server(MCP_NAME)


def validate_command_input(command: str, args: List[str], working_directory: str) -> tuple[bool, str, List[str]]:
    """
    Validate command input and return validation status with helpful message and suggestions.
    
    Args:
        command: The command to execute
        args: Command arguments
        working_directory: Working directory for execution
        
    Returns:
        Tuple of (is_valid, message, suggestions)
    """
    suggestions = []
    
    # Check if command is provided
    if not command:
        return False, "No command specified", [
            "Specify a command to execute (e.g., 'ls', 'cat', 'grep')",
            "Check available commands using the whitelist",
            "Provide the command name as a string",
            "Example: command='ls', args=['-la']"
        ]
    
    # Check if command is just whitespace
    if command.isspace():
        return False, "Command appears to be empty (only whitespace)", [
            "Provide a valid command name",
            "Remove any leading/trailing spaces",
            "Use actual command names like 'ls', 'pwd', 'cat'",
            "Example: command='pwd' (not command='  ')"
        ]
    
    # Check if working directory seems suspicious
    if working_directory and any(char in working_directory for char in ['`', '$', ';', '|', '&']):
        return False, "Working directory contains potentially dangerous characters", [
            "Use a simple directory path without special characters",
            "Avoid shell metacharacters like `, $, ;, |, &",
            "Use absolute or relative paths only",
            "Example: working_directory='/home/user/project' or '.'"
        ]
    
    return True, "", suggestions


def create_command_elicitation_message(tool_name: str, issue: str, suggestions: List[str]) -> str:
    """
    Create a helpful elicitation message for shell command issues.
    
    Args:
        tool_name: Name of the tool being called
        issue: Description of what's missing or problematic
        suggestions: List of suggestions for what the user should provide
        
    Returns:
        Formatted elicitation message
    """
    message = f"## Shell Command Execution Help\n\n"
    message += f"**Issue:** {issue}\n\n"
    message += "**Please provide:**\n"
    
    for i, suggestion in enumerate(suggestions, 1):
        message += f"{i}. {suggestion}\n"
    
    message += "\n**Available Commands:**\n"
    message += "```\n"
    message += "File Operations: ls, cat, head, tail, find, grep, wc\n"
    message += "Directory Ops:   pwd, mkdir\n"
    message += "Process Info:    ps, top\n"
    message += "System Info:     uname, whoami, date, uptime\n"
    message += "Development:     git, python, python3, node, npm, pip\n"
    message += "Text Processing: sort, uniq, cut\n"
    message += "```\n\n"
    
    message += "**Examples:**\n"
    message += "```json\n"
    message += '{\n'
    message += '  "command": "ls",\n'
    message += '  "args": ["-la"],\n'
    message += '  "working_directory": "."\n'
    message += '}\n'
    message += "```\n\n"
    message += "```json\n"
    message += '{\n'
    message += '  "command": "find",\n'
    message += '  "args": [".", "-name", "*.py"],\n'
    message += '  "working_directory": "/home/user/project"\n'
    message += '}\n'
    message += "```\n\n"
    
    message += "**Security Note:** Only whitelisted commands are allowed for safety.\n"
    message += "Dangerous commands (rm, sudo, etc.) are blocked.\n\n"
    message += "Once you provide the necessary information, I can execute the command safely!"
    
    return message


def analyze_command_context(command: str, args: List[str]) -> Dict[str, Any]:
    """
    Analyze command and arguments to provide better guidance.
    
    Args:
        command: The command to analyze
        args: Command arguments
        
    Returns:
        Dictionary with analysis results and recommendations
    """
    analysis = {
        'command_type': 'unknown',
        'complexity': 'simple',
        'recommendations': [],
        'potential_issues': [],
        'usage_tips': []
    }
    
    if not command:
        return analysis
    
    # Categorize command type
    file_ops = {'ls', 'cat', 'head', 'tail', 'find', 'grep', 'wc'}
    dir_ops = {'pwd', 'mkdir'}
    process_ops = {'ps', 'top'}
    system_ops = {'uname', 'whoami', 'date', 'uptime'}
    dev_ops = {'git', 'python', 'python3', 'node', 'npm', 'pip'}
    text_ops = {'sort', 'uniq', 'cut'}
    
    if command in file_ops:
        analysis['command_type'] = 'file_operation'
        analysis['usage_tips'].append("Consider using appropriate flags for better output")
    elif command in dir_ops:
        analysis['command_type'] = 'directory_operation'
    elif command in process_ops:
        analysis['command_type'] = 'process_operation'
        analysis['usage_tips'].append("These commands show live system information")
    elif command in system_ops:
        analysis['command_type'] = 'system_information'
    elif command in dev_ops:
        analysis['command_type'] = 'development_tool'
        analysis['usage_tips'].append("Great for checking versions and project status")
    elif command in text_ops:
        analysis['command_type'] = 'text_processing'
        analysis['usage_tips'].append("Useful for processing file contents")
    
    # Analyze complexity based on argument count
    if len(args) == 0:
        analysis['complexity'] = 'simple'
    elif len(args) <= 3:
        analysis['complexity'] = 'moderate'
    else:
        analysis['complexity'] = 'complex'
        analysis['recommendations'].append("Consider breaking complex commands into simpler ones")
    
    # Check for common patterns and provide recommendations
    if command == 'ls' and not args:
        analysis['recommendations'].append("Try 'ls -la' for detailed file listing")
    elif command == 'find' and len(args) < 2:
        analysis['recommendations'].append("Find usually needs a path and search criteria")
    elif command == 'grep' and len(args) < 2:
        analysis['recommendations'].append("Grep needs a pattern and usually a file or input")
    elif command == 'git' and not args:
        analysis['recommendations'].append("Try 'git status' or 'git log' for common operations")
    
    # Check for potential issues
    for arg in args:
        if any(char in arg for char in ['`', '$', ';', '|', '&']):
            analysis['potential_issues'].append(f"Argument '{arg}' contains shell metacharacters")
        if arg.startswith('-') and len(arg) > 10:
            analysis['potential_issues'].append(f"Very long flag '{arg}' - verify it's correct")
    
    return analysis


def get_command_examples(command: str) -> List[str]:
    """Get relevant examples for a specific command."""
    examples = {
        'ls': [
            'ls -la  # Detailed listing with hidden files',
            'ls -lh  # Human-readable file sizes',
            'ls *.py # List Python files'
        ],
        'cat': [
            'cat filename.txt  # Display file contents',
            'cat file1.txt file2.txt  # Display multiple files'
        ],
        'find': [
            'find . -name "*.py"  # Find Python files',
            'find /path -type f -size +1M  # Find large files',
            'find . -mtime -7  # Files modified in last 7 days'
        ],
        'grep': [
            'grep "pattern" file.txt  # Search in file',
            'grep -r "pattern" .  # Recursive search',
            'grep -i "pattern" file.txt  # Case-insensitive'
        ],
        'git': [
            'git status  # Check repository status',
            'git log --oneline  # Compact commit history',
            'git diff  # Show changes'
        ],
        'python': [
            'python --version  # Check Python version',
            'python -c "print(\'Hello\')"  # Execute Python code',
            'python -m pip list  # List installed packages'
        ]
    }
    
    return examples.get(command, [f'{command} --help  # Get help for this command'])


def validate_working_directory(working_dir: str) -> tuple[bool, str]:
    """
    Validate working directory and provide helpful feedback.
    
    Args:
        working_dir: The working directory path
        
    Returns:
        Tuple of (is_valid, message)
    """
    import os
    
    if not working_dir:
        return False, "Working directory cannot be empty"
    
    # Check for dangerous characters
    dangerous_chars = ['`', '$', ';', '|', '&', '>', '<']
    for char in dangerous_chars:
        if char in working_dir:
            return False, f"Working directory contains dangerous character '{char}'"
    
    # Check if directory exists (if it's not relative)
    if working_dir != "." and working_dir != ".." and not working_dir.startswith("./") and not working_dir.startswith("../"):
        if os.path.isabs(working_dir) and not os.path.exists(working_dir):
            return False, f"Directory '{working_dir}' does not exist"
    
    return True, ""


def suggest_better_command(command: str, args: List[str]) -> Optional[str]:
    """
    Suggest a better version of a command based on common patterns.
    
    Args:
        command: The command name
        args: Command arguments
        
    Returns:
        Suggestion string or None
    """
    suggestions = []
    
    # Common improvements
    if command == "ls" and not args:
        suggestions.append("Try 'ls -la' for a detailed listing with hidden files")
    elif command == "ls" and "-l" in args and "-a" not in args:
        suggestions.append("Add '-a' to see hidden files: 'ls -la'")
    elif command == "find" and len(args) == 1:
        suggestions.append("Find usually needs search criteria, try: find . -name '*.ext'")
    elif command == "grep" and len(args) == 1:
        suggestions.append("Grep needs a file or use with pipe: grep 'pattern' filename")
    elif command == "git" and not args:
        suggestions.append("Try 'git status' to see repository status")
    elif command == "python" and not args:
        suggestions.append("Try 'python --version' or 'python -c \"print('Hello')\"'")
    
    return suggestions[0] if suggestions else None


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
    
    def is_allowed(self, command: str, args: List[str]) -> tuple[bool, str]:
        """Check if a command with given arguments is allowed
        
        Returns:
            Tuple of (is_allowed, reason_if_not_allowed)
        """
        if command in self.dangerous_commands:
            return False, f"Command '{command}' is blocked for security reasons (dangerous command)"
        
        if command not in self.allowed_commands:
            available_commands = ', '.join(sorted(self.allowed_commands.keys()))
            return False, f"Command '{command}' is not whitelisted. Available commands: {available_commands}"
        
        config = self.allowed_commands[command]
        
        # Check argument count
        if len(args) > config["max_args"]:
            return False, f"Too many arguments for '{command}' (max: {config['max_args']}, provided: {len(args)})"
        
        # Check for dangerous patterns in arguments
        dangerous_patterns = ["sudo", "su", "rm", "del", ">", ">>", "|", "&", ";", "`", "$"]
        for arg in args:
            for pattern in dangerous_patterns:
                if pattern in arg:
                    return False, f"Argument '{arg}' contains dangerous pattern '{pattern}'"
        
        return True, ""
    
    def get_command_info(self, command: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific command"""
        if command in self.allowed_commands:
            info = self.allowed_commands[command].copy()
            info['is_dangerous'] = False
            return info
        elif command in self.dangerous_commands:
            return {'is_dangerous': True, 'reason': 'Security risk'}
        else:
            return None
    
    def get_available_commands(self) -> List[str]:
        """Get list of all available commands"""
        return sorted(self.allowed_commands.keys())
    
    def get_command_suggestions(self, partial_command: str) -> List[str]:
        """Get command suggestions based on partial input"""
        suggestions = []
        partial_lower = partial_command.lower()
        
        for cmd in self.allowed_commands.keys():
            if cmd.startswith(partial_lower):
                suggestions.append(cmd)
        
        # If no exact matches, try fuzzy matching
        if not suggestions:
            for cmd in self.allowed_commands.keys():
                if partial_lower in cmd:
                    suggestions.append(cmd)
        
        return suggestions[:5]  # Limit to 5 suggestions


# Initialize command whitelist
whitelist = CommandWhitelist()



@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="execute_command",
            description="Execute a whitelisted shell command safely with comprehensive guidance and error handling",
            inputSchema=create_schema({
                "command": string_property("The command to execute (e.g., 'ls', 'cat', 'find', 'git')"),
                "args": array_property("Command arguments as a list of strings (e.g., ['-la'] for ls -la)", default=[]),
                "working_directory": string_property(
                    "Working directory for command execution (default: current directory)", 
                    "."
                )
            }, ["command"]),
        ),
        types.Tool(
            name="get_joke",
            description="Get a random programming joke for testing the server connection",
            inputSchema=create_schema({}),
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
    """Execute a shell command with comprehensive validation and helpful feedback"""
    command = args.get("command", "").strip()
    cmd_args = args.get("args", [])
    working_dir = args.get("working_directory", ".")
    
    # Ensure cmd_args is a list
    if not isinstance(cmd_args, list):
        cmd_args = []
    
    # Validate basic input
    is_valid, validation_message, suggestions = validate_command_input(command, cmd_args, working_dir)
    if not is_valid:
        elicitation_text = create_command_elicitation_message("execute_command", validation_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Validate working directory specifically
    dir_valid, dir_message = validate_working_directory(working_dir)
    if not dir_valid:
        suggestions = [
            "Use a simple directory path without special characters",
            "Try '.' for current directory or an absolute path like '/home/user/project'",
            "Avoid shell metacharacters in directory paths",
            "Make sure the directory exists if using an absolute path"
        ]
        elicitation_text = create_command_elicitation_message("execute_command", dir_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Analyze command context for better guidance
    context = analyze_command_context(command, cmd_args)
    
    # Check for command improvements
    better_command = suggest_better_command(command, cmd_args)
    if better_command:
        context['recommendations'].insert(0, better_command)
    
    # Check if command is allowed with detailed feedback
    is_allowed, reason = whitelist.is_allowed(command, cmd_args)
    if not is_allowed:
        # Provide helpful suggestions when command is not allowed
        response = f"## Command Not Allowed\n\n"
        response += f"**Issue:** {reason}\n\n"
        
        # Try to provide suggestions
        if command not in whitelist.get_available_commands():
            suggestions = whitelist.get_command_suggestions(command)
            if suggestions:
                response += f"**Did you mean one of these?**\n"
                for suggestion in suggestions:
                    examples = get_command_examples(suggestion)
                    response += f"- `{suggestion}` - Example: `{examples[0] if examples else suggestion}`\n"
                response += "\n"
            
            response += f"**Available commands:**\n"
            available = whitelist.get_available_commands()
            # Group commands by type for better presentation
            file_ops = [cmd for cmd in available if cmd in ['ls', 'cat', 'head', 'tail', 'find', 'grep', 'wc']]
            dir_ops = [cmd for cmd in available if cmd in ['pwd', 'mkdir']]
            process_ops = [cmd for cmd in available if cmd in ['ps', 'top']]
            system_ops = [cmd for cmd in available if cmd in ['uname', 'whoami', 'date', 'uptime']]
            dev_ops = [cmd for cmd in available if cmd in ['git', 'python', 'python3', 'node', 'npm', 'pip']]
            text_ops = [cmd for cmd in available if cmd in ['sort', 'uniq', 'cut']]
            
            if file_ops:
                response += f"- **File Operations:** {', '.join(file_ops)}\n"
            if dir_ops:
                response += f"- **Directory Operations:** {', '.join(dir_ops)}\n"
            if process_ops:
                response += f"- **Process Information:** {', '.join(process_ops)}\n"
            if system_ops:
                response += f"- **System Information:** {', '.join(system_ops)}\n"
            if dev_ops:
                response += f"- **Development Tools:** {', '.join(dev_ops)}\n"
            if text_ops:
                response += f"- **Text Processing:** {', '.join(text_ops)}\n"
        
        response += f"\n**Examples for common tasks:**\n"
        response += f"```bash\n"
        response += f"ls -la          # List files with details\n"
        response += f"find . -name \"*.py\"  # Find Python files\n"
        response += f"grep \"pattern\" file.txt  # Search in file\n"
        response += f"git status      # Check git status\n"
        response += f"python --version  # Check Python version\n"
        response += f"```\n"
        
        return [types.TextContent(type="text", text=response)]
    
    # Provide proactive suggestions based on command analysis
    if context['potential_issues']:
        warning_msg = "## ⚠️ Potential Issues Detected\n\n"
        for issue in context['potential_issues']:
            warning_msg += f"- {issue}\n"
        warning_msg += "\nProceeding with execution, but please review the command...\n\n"
    else:
        warning_msg = ""
    
    # Build command line
    cmd_line = [command] + cmd_args
    
    # Log the execution attempt
    logger.info(f"Executing command: {' '.join(cmd_line)} in directory: {working_dir}")
    
    try:
        # Execute command
        result = subprocess.run(
            cmd_line,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Prepare comprehensive output
        response = f"## Command Execution Result\n\n"
        
        if warning_msg:
            response += warning_msg
        
        response += f"**Command:** `{' '.join(cmd_line)}`\n"
        response += f"**Working Directory:** `{working_dir}`\n"
        response += f"**Exit Code:** {result.returncode}\n"
        
        # Add context-based insights
        if context['command_type'] != 'unknown':
            response += f"**Command Type:** {context['command_type'].replace('_', ' ').title()}\n"
        
        response += "\n"
        
        # Format output sections
        if result.stdout:
            response += f"**Output:**\n```\n{result.stdout.strip()}\n```\n\n"
        
        if result.stderr:
            response += f"**Error Output:**\n```\n{result.stderr.strip()}\n```\n\n"
        
        if not result.stdout and not result.stderr:
            response += "**Output:** (no output)\n\n"
        
        # Add helpful suggestions based on results
        if result.returncode != 0:
            response += f"## 🔧 Troubleshooting\n"
            response += f"The command exited with code {result.returncode}, indicating an error.\n\n"
            
            # Command-specific troubleshooting
            if command == 'find' and 'Permission denied' in result.stderr:
                response += "**Tip:** Permission denied errors in find are common and usually safe to ignore.\n"
            elif command in ['ls', 'cat'] and 'No such file or directory' in result.stderr:
                response += "**Tip:** Check if the file/directory path is correct and exists.\n"
            elif command == 'git' and result.returncode == 128:
                response += "**Tip:** Make sure you're in a git repository directory.\n"
        else:
            # Add success tips and recommendations
            if context['recommendations']:
                response += "## 💡 Suggestions\n"
                for rec in context['recommendations']:
                    response += f"- {rec}\n"
                response += "\n"
            
            if context['usage_tips']:
                response += "## 📝 Usage Tips\n"
                for tip in context['usage_tips']:
                    response += f"- {tip}\n"
                response += "\n"
        
        # Add relevant examples for next steps
        examples = get_command_examples(command)
        if examples and len(examples) > 1:
            response += "## 📖 Related Examples\n"
            for example in examples[1:3]:  # Show 2 additional examples
                response += f"- `{example}`\n"
        
        return [types.TextContent(type="text", text=response)]
        
    except subprocess.TimeoutExpired:
        response = f"## ⏰ Command Timeout\n\n"
        response += f"**Command:** `{' '.join(cmd_line)}`\n"
        response += f"**Issue:** Command timed out after 30 seconds\n\n"
        response += f"**Possible reasons:**\n"
        response += f"- Command is waiting for input\n"
        response += f"- Process is running but taking too long\n"
        response += f"- Command might be stuck or in an infinite loop\n\n"
        response += f"**Suggestions:**\n"
        response += f"- Try a simpler version of the command\n"
        response += f"- Use different arguments to limit scope\n"
        response += f"- For interactive commands, provide necessary arguments upfront\n"
        
        return [types.TextContent(type="text", text=response)]
        
    except FileNotFoundError:
        response = f"## 🚫 Command Not Found\n\n"
        response += f"**Command:** `{command}`\n"
        response += f"**Issue:** Command not found on system\n\n"
        response += f"**This might mean:**\n"
        response += f"- The command is not installed\n"
        response += f"- There's a typo in the command name\n"
        response += f"- The command is not in the system PATH\n\n"
        
        # Suggest alternatives
        suggestions = whitelist.get_command_suggestions(command)
        if suggestions:
            response += f"**Did you mean:**\n"
            for suggestion in suggestions:
                response += f"- `{suggestion}`\n"
        
        return [types.TextContent(type="text", text=response)]
        
    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        response = f"## ❌ Execution Error\n\n"
        response += f"**Command:** `{' '.join(cmd_line)}`\n"
        response += f"**Error:** {str(e)}\n\n"
        response += f"**Troubleshooting:**\n"
        response += f"- Check if all file paths are correct\n"
        response += f"- Verify command syntax\n"
        response += f"- Ensure you have necessary permissions\n"
        response += f"- Try a simpler version of the command first\n"
        
        return [types.TextContent(type="text", text=response)]


async def get_joke(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Get a programming joke for testing and fun"""
    import random
    
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
        "How many programmers does it take to change a light bulb? None, that's a hardware problem! 💡",
        "Why don't programmers like nature? It has too many bugs! 🦗",
        "What's a programmer's favorite hangout place? Foo Bar! 🍺",
        "Why did the programmer quit his job? Because he didn't get arrays! 📊",
        "What do you call a programmer from Finland? Nerdic! 🇫🇮",
        "Why do Java developers wear glasses? Because they can't C#! 👓",
        "What's the object-oriented way to become wealthy? Inheritance! 💰",
        "Why did the developer go broke? Because he used up all his cache! 💸",
        "What do you call 8 hobbits? A hobbyte! 🧙‍♂️"
    ]
    
    selected_joke = random.choice(jokes)
    
    response = "## 😄 Programming Joke\n\n"
    response += f"{selected_joke}\n\n"
    response += "---\n"
    response += "*This tool is working perfectly! You can now try executing some shell commands.*\n\n"
    response += "**Try these commands:**\n"
    response += "- `ls -la` - List files with details\n"
    response += "- `pwd` - Show current directory\n"
    response += "- `date` - Show current date and time\n"
    response += "- `python --version` - Check Python version\n"
    
    return [types.TextContent(type="text", text=response)]




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
