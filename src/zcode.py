#!/usr/bin/env python3
"""
MCP Server for code analysis and refactoring tools.
Uses the official MCP library for proper protocol implementation.
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio

from tool_helpers import create_schema, string_property, code_property, language_property

# Import Rust helpers for streamlining imports
from rust_import_helpers import (
    parse_import_statements, 
    group_imports_by_base_path,
    generate_import_statements
)

# Import Python helpers for streamlining imports
from python_import_helpers import (
    parse_python_import_statements, 
    generate_python_import_statements
)

MCP_NAME = "code-refactor-mcp"
MCP_VERSION = "0.1.0"
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(MCP_NAME)


class LanguageType(Enum):
    """Enumeration of supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    C = "c"
    JAVA = "java"
    RUST = "rust"
    GO = "go"
    UNKNOWN = "unknown"


# Create the server instance
server = Server(MCP_NAME)


def validate_code_input(code: str, min_lines: int = 1) -> tuple[bool, str]:
    """
    Validate code input and return validation status with helpful message.
    
    Args:
        code: The code string to validate
        min_lines: Minimum number of non-empty lines required
        
    Returns:
        Tuple of (is_valid, message)
    """
    if not code:
        return False, "No code provided"
    
    if code.isspace():
        return False, "Code appears to be empty (only whitespace)"
    
    # Check for minimum meaningful content
    non_empty_lines = [line.strip() for line in code.split('\n') if line.strip()]
    
    if len(non_empty_lines) < min_lines:
        return False, f"Code appears too short (found {len(non_empty_lines)} non-empty lines, need at least {min_lines})"
    
    # Check if it looks like actual code (has some programming constructs)
    code_indicators = [
        'def ', 'function ', 'class ', 'if ', 'for ', 'while ', 'import ', 'use ',
        '{', '}', '(', ')', ';', '=', '==', '!=', '<', '>', '&&', '||', 'fn ',
        'let ', 'const ', 'var ', 'return', 'struct', 'impl', 'trait'
    ]
    
    if not any(indicator in code.lower() for indicator in code_indicators):
        return False, "Input doesn't appear to contain code. Please provide actual source code for analysis."
    
    return True, ""


def create_elicitation_message(tool_name: str, issue: str, suggestions: List[str]) -> str:
    """
    Create a helpful elicitation message when user input is insufficient.
    
    Args:
        tool_name: Name of the tool being called
        issue: Description of what's missing or problematic
        suggestions: List of suggestions for what the user should provide
        
    Returns:
        Formatted elicitation message
    """
    message = f"## Input Needed for {tool_name.replace('_', ' ').title()}\n\n"
    message += f"**Issue:** {issue}\n\n"
    message += "**Please provide:**\n"
    
    for i, suggestion in enumerate(suggestions, 1):
        message += f"{i}. {suggestion}\n"
    
    message += "\n**Example:**\n"
    
    # Add tool-specific examples
    if "code" in tool_name.lower():
        message += "```python\n"
        message += "def calculate_total(items):\n"
        message += "    total = 0\n"
        message += "    for item in items:\n"
        message += "        total += item.price\n"
        message += "    return total\n"
        message += "```\n"
    
    message += "\nOnce you provide the necessary information, I can help you with your request!"
    return message


def detect_code_complexity(code: str) -> Dict[str, Any]:
    """
    Analyze code to detect complexity and provide context for better suggestions.
    
    Args:
        code: The code string to analyze
        
    Returns:
        Dictionary with complexity metrics and characteristics
    """
    lines = code.split('\n')
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    
    # Count various complexity indicators
    nesting_level = 0
    max_nesting = 0
    function_count = 0
    class_count = 0
    loop_count = 0
    conditional_count = 0
    
    for line in non_empty_lines:
        line_lower = line.lower().strip()
        
        # Track nesting level
        if any(keyword in line_lower for keyword in ['if ', 'for ', 'while ', 'def ', 'class ', 'function ']):
            nesting_level += 1
            max_nesting = max(max_nesting, nesting_level)
        
        # Count constructs
        if line_lower.startswith(('def ', 'function ')):
            function_count += 1
        elif line_lower.startswith('class '):
            class_count += 1
        elif any(keyword in line_lower for keyword in ['for ', 'while ']):
            loop_count += 1
        elif line_lower.startswith('if '):
            conditional_count += 1
    
    return {
        'total_lines': len(lines),
        'non_empty_lines': len(non_empty_lines),
        'max_nesting_level': max_nesting,
        'function_count': function_count,
        'class_count': class_count,
        'loop_count': loop_count,
        'conditional_count': conditional_count,
        'is_complex': max_nesting > 3 or len(non_empty_lines) > 50,
        'is_simple': max_nesting <= 2 and len(non_empty_lines) <= 20
    }


def detect_language(code: str, language_hint: str = "auto-detect") -> LanguageType:
    """Detect programming language from code content"""
    if language_hint != "auto-detect":
        # Try to match the hint to an enum value
        hint_lower = language_hint.lower()
        for lang in LanguageType:
            if lang.value == hint_lower:
                return lang
        # If hint doesn't match, continue with auto-detection but log the issue
        logger.warning(f"Language hint '{language_hint}' not recognized, falling back to auto-detection")
    
    # Simple language detection based on common patterns
    code_lower = code.lower()
    
    # More comprehensive detection patterns
    if any(pattern in code for pattern in ["def ", "import ", "class ", "__init__", "self.", "elif ", "None", "True", "False"]):
        return LanguageType.PYTHON
    elif any(pattern in code for pattern in ["function ", "const ", "let ", "var ", "=>", "console.", "require(", "module.exports"]):
        return LanguageType.JAVASCRIPT
    elif any(pattern in code for pattern in ["interface ", "type ", ": string", ": number", ": boolean", "export ", "import {"]):
        return LanguageType.TYPESCRIPT
    elif any(pattern in code for pattern in ["#include", "int main", "printf(", "malloc(", "free(", "struct"]):
        return LanguageType.C
    elif any(pattern in code for pattern in ["public class", "private ", "public ", "static ", "void ", "System.out"]):
        return LanguageType.JAVA
    elif any(pattern in code for pattern in ["fn ", "let mut", "impl ", "trait ", "struct ", "use ", "match "]):
        return LanguageType.RUST
    elif any(pattern in code for pattern in ["func ", "package ", "import ", ":= ", "go ", "defer "]):
        return LanguageType.GO
    else:
        return LanguageType.UNKNOWN


# Create the server instance
server = Server(MCP_NAME)


@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="get_prompts",
            description="Get useful development prompts for code improvement",
            inputSchema=create_schema({
                "category": string_property(
                    "Category of prompts: all, refactoring, commenting, or simplifying", 
                    "all"
                )
            })
        ),
        types.Tool(
            name="refactor_code",
            description="Analyze code and provide refactoring suggestions",
            inputSchema=create_schema({
                "code": code_property("The code content to refactor"),
                "language": language_property(),
                "refactor_type": string_property(
                    "Type of refactoring: extract_function, reduce_duplication, simplify_conditionals, improve_naming, or general",
                    "general"
                )
            }, ["code"])
        ),
        types.Tool(
            name="add_comments",
            description="Add comprehensive comments and documentation to provided code",
            inputSchema=create_schema({
                "code": code_property("The code content to document"),
                "language": language_property(),
                "comment_style": string_property(
                    "Style of comments: docstring, inline, jsdoc, or comprehensive",
                    "comprehensive"
                )
            }, ["code"])
        ),
        types.Tool(
            name="simplify_code",
            description="Simplify provided code while maintaining functionality",
            inputSchema=create_schema({
                "code": code_property("The code content to simplify"),
                "language": language_property(),
                "simplify_approach": string_property(
                    "Approach: reduce_nesting, use_modern_features, eliminate_redundancy, or comprehensive",
                    "comprehensive"
                )
            }, ["code"])
        ),
        types.Tool(
            name="analyze_code",
            description="Analyze provided code and suggest improvements",
            inputSchema=create_schema({
                "code": code_property("The code content to analyze"),
                "language": language_property(),
                "analysis_focus": string_property(
                    "Focus area: performance, readability, maintainability, security, or all",
                    "all"
                )
            }, ["code"])
        ),
        types.Tool(
            name="streamline_rust_imports",
            description="Streamline Rust import statements by consolidating imports with the same base path",
            inputSchema=create_schema({
                "code": code_property("The Rust code with import statements to streamline")
            }, ["code"])
        ),
        types.Tool(
            name="streamline_python_imports",
            description="Streamline Python import statements by consolidating imports from the same module",
            inputSchema=create_schema({
                "code": code_property("The Python code with import statements to streamline")
            }, ["code"])
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls"""
    if arguments is None:
        arguments = {}
    
    if name == "get_prompts":
        return await get_prompts(arguments)
    elif name == "refactor_code":
        return await refactor_code(arguments)
    elif name == "add_comments":
        return await add_comments(arguments)
    elif name == "simplify_code":
        return await simplify_code(arguments)
    elif name == "analyze_code":
        return await analyze_code(arguments)
    elif name == "streamline_rust_imports":
        return await streamline_rust_imports(arguments)
    elif name == "streamline_python_imports":
        return await streamline_python_imports(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


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
    
    # Validate input and provide elicitation if needed
    is_valid, validation_message = validate_code_input(code, min_lines=3)
    if not is_valid:
        suggestions = [
            "Actual source code that you want to refactor (at least a few lines)",
            "Specify the programming language if auto-detection might be unclear",
            "Indicate the type of refactoring you want (extract_function, reduce_duplication, simplify_conditionals, improve_naming, or general)",
            "Include the specific areas you're concerned about or want to improve"
        ]
        elicitation_text = create_elicitation_message("refactor_code", validation_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Analyze code complexity for better suggestions
    complexity = detect_code_complexity(code)
    
    # Generate refactoring suggestions based on type and complexity
    suggestions = []
    
    # Add complexity-based insights
    if complexity['is_complex']:
        suggestions.append("## Complexity Analysis")
        suggestions.append(f"- This code appears complex ({complexity['non_empty_lines']} lines, max nesting level {complexity['max_nesting_level']})")
        suggestions.append("- Consider breaking it down into smaller functions")
        if complexity['function_count'] == 0:
            suggestions.append("- No functions detected - consider extracting logic into functions")
    elif complexity['is_simple']:
        suggestions.append("## Complexity Analysis")
        suggestions.append(f"- This is relatively simple code ({complexity['non_empty_lines']} lines)")
        suggestions.append("- Focus on readability and naming improvements")
    
    if refactor_type == "extract_function" or refactor_type == "general":
        suggestions.append("## Extract Function Opportunities")
        if complexity['function_count'] == 0:
            suggestions.append("- **Priority**: No functions detected - extract main logic into named functions")
        if complexity['loop_count'] > 0:
            suggestions.append(f"- Found {complexity['loop_count']} loop(s) - consider extracting complex loop bodies")
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
    if language == LanguageType.PYTHON:
        suggestions.append("\n## Python-Specific Refactoring")
        suggestions.append("- Use list comprehensions where appropriate")
        suggestions.append("- Consider using dataclasses for simple data containers")
        suggestions.append("- Use context managers for resource management")
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        suggestions.append("\n## JavaScript/TypeScript-Specific Refactoring")
        suggestions.append("- Use arrow functions for short callbacks")
        suggestions.append("- Consider using destructuring for object property access")
        suggestions.append("- Use async/await instead of Promise chains")
    
    result_text = f"## Refactoring Analysis for {language.value.title()} Code\n\n"
    
    # Add language guidance if needed
    language_guide = get_language_guidance(language, code)
    if language_guide:
        result_text += language_guide
    
    result_text += f"**Original Code:**\n```{language.value}\n{code}\n```\n\n"
    result_text += f"**Complexity Analysis:**\n"
    result_text += f"- Lines of code: {complexity['non_empty_lines']}\n"
    result_text += f"- Functions: {complexity['function_count']}\n"
    result_text += f"- Maximum nesting: {complexity['max_nesting_level']}\n"
    result_text += f"- Complexity level: {'High' if complexity['is_complex'] else 'Low' if complexity['is_simple'] else 'Medium'}\n\n"
    result_text += "**Refactoring Suggestions:**\n"
    result_text += "\n".join(suggestions)
    
    return [types.TextContent(type="text", text=result_text)]


async def add_comments(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Add comments to provided code"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    comment_style = args.get("comment_style", "comprehensive")
    
    # Validate input and provide elicitation if needed
    is_valid, validation_message = validate_code_input(code, min_lines=2)
    if not is_valid:
        suggestions = [
            "Source code that needs commenting (functions, classes, or complex logic)",
            "Specify the programming language if it's not clear from the code",
            "Choose comment style: 'docstring' for function docs, 'inline' for line comments, 'jsdoc' for JavaScript docs, or 'comprehensive' for all types",
            "Indicate specific areas that need explanation (algorithms, business logic, etc.)"
        ]
        elicitation_text = create_elicitation_message("add_comments", validation_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Analyze code structure for targeted commenting suggestions
    complexity = detect_code_complexity(code)
    
    # Generate commenting suggestions based on code structure
    suggestions = []
    
    # Add structure-based insights
    suggestions.append("## Code Structure Analysis")
    if complexity['function_count'] > 0:
        suggestions.append(f"- Found {complexity['function_count']} function(s) - prioritize function documentation")
    if complexity['class_count'] > 0:
        suggestions.append(f"- Found {complexity['class_count']} class(es) - add class-level documentation")
    if complexity['is_complex']:
        suggestions.append(f"- Complex code detected - inline comments will be especially helpful")
    
    if comment_style == "docstring" or comment_style == "comprehensive":
        suggestions.append("\n## Function/Method Documentation")
        if language == LanguageType.PYTHON:
            suggestions.append('- Add docstrings using """triple quotes"""')
            suggestions.append("- Include Args:, Returns:, and Raises: sections")
            if complexity['function_count'] > 0:
                suggestions.append("- **Priority**: Document function parameters and return values")
        elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
            suggestions.append("- Add JSDoc comments with @param, @returns, @throws")
            if complexity['function_count'] > 0:
                suggestions.append("- **Priority**: Document function signatures for better IDE support")
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
        LanguageType.PYTHON: "# Single line\n\"\"\"\nMulti-line docstring\n\"\"\"",
        LanguageType.JAVASCRIPT: "// Single line\n/* Multi-line\n   comment */\n/** JSDoc comment */",
        LanguageType.TYPESCRIPT: "// Single line\n/* Multi-line */\n/** TSDoc comment */",
        LanguageType.JAVA: "// Single line\n/* Multi-line */\n/** Javadoc comment */",
        LanguageType.C: "// Single line\n/* Multi-line comment */",
        LanguageType.RUST: "// Single line\n/// Documentation comment\n/* Multi-line */",
        LanguageType.GO: "// Single line\n/* Multi-line comment */"
    }
    
    result_text = f"## Comment Enhancement for {language.value.title()} Code\n\n"
    
    # Add language guidance if needed
    language_guide = get_language_guidance(language, code)
    if language_guide:
        result_text += language_guide
    
    result_text += f"**Original Code:**\n```{language.value}\n{code}\n```\n\n"
    result_text += "**Commenting Guidelines:**\n"
    result_text += "\n".join(suggestions)
    
    if language in comment_examples:
        result_text += f"\n\n**{language.value.title()} Comment Syntax:**\n```{language.value}\n{comment_examples[language]}\n```"
    
    return [types.TextContent(type="text", text=result_text)]


async def simplify_code(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Simplify provided code"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    approach = args.get("simplify_approach", "comprehensive")
    
    # Validate input and provide elicitation if needed
    is_valid, validation_message = validate_code_input(code, min_lines=3)
    if not is_valid:
        suggestions = [
            "Code that appears complex or verbose and could be simplified",
            "Specify the programming language if auto-detection might fail",
            "Choose simplification approach: 'reduce_nesting', 'use_modern_features', 'eliminate_redundancy', or 'comprehensive'",
            "Mention specific issues: nested conditions, repeated code, verbose expressions, etc."
        ]
        elicitation_text = create_elicitation_message("simplify_code", validation_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Analyze code complexity for targeted simplification
    complexity = detect_code_complexity(code)
    
    suggestions = []
    
    # Add complexity-specific simplification advice
    suggestions.append("## Simplification Opportunities")
    if complexity['max_nesting_level'] > 3:
        suggestions.append(f"- **High Priority**: Deep nesting detected (level {complexity['max_nesting_level']}) - use early returns and guard clauses")
    if complexity['conditional_count'] > 3:
        suggestions.append(f"- Multiple conditionals found ({complexity['conditional_count']}) - consider using lookup tables or strategy pattern")
    if complexity['loop_count'] > 2:
        suggestions.append(f"- Multiple loops detected ({complexity['loop_count']}) - look for opportunities to combine or use built-in functions")
    
    if approach == "reduce_nesting" or approach == "comprehensive":
        suggestions.append("\n## Reduce Nesting")
        if complexity['max_nesting_level'] > 2:
            suggestions.append("- **Priority**: Use early returns to eliminate else blocks")
        suggestions.append("- Extract nested logic into separate functions")
        suggestions.append("- Use guard clauses for validation")
    
    if approach == "use_modern_features" or approach == "comprehensive":
        suggestions.append("\n## Use Modern Language Features")
        if language == LanguageType.PYTHON:
            suggestions.append("- Use f-strings instead of string formatting")
            suggestions.append("- Use walrus operator (:=) where appropriate")
            suggestions.append("- Use match statements for complex conditionals (Python 3.10+)")
        elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
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
    
    result_text = f"## Code Simplification for {language.value.title()}\n\n"
    
    # Add language guidance if needed
    language_guide = get_language_guidance(language, code)
    if language_guide:
        result_text += language_guide
    
    result_text += f"**Original Code:**\n```{language.value}\n{code}\n```\n\n"
    result_text += f"**Complexity Metrics:**\n"
    result_text += f"- Nesting level: {complexity['max_nesting_level']}\n"
    result_text += f"- Conditionals: {complexity['conditional_count']}\n"
    result_text += f"- Loops: {complexity['loop_count']}\n\n"
    result_text += "**Simplification Suggestions:**\n"
    result_text += "\n".join(suggestions)
    
    return [types.TextContent(type="text", text=result_text)]


async def analyze_code(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Analyze provided code and suggest improvements"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    focus = args.get("analysis_focus", "all")
    
    # Validate input and provide elicitation if needed
    is_valid, validation_message = validate_code_input(code, min_lines=2)
    if not is_valid:
        suggestions = [
            "Source code for analysis (functions, classes, algorithms, etc.)",
            "Specify the programming language if it's ambiguous",
            "Choose analysis focus: 'performance', 'readability', 'maintainability', 'security', or 'all'",
            "Mention specific concerns: slow execution, hard to understand, difficult to modify, security vulnerabilities, etc."
        ]
        elicitation_text = create_elicitation_message("analyze_code", validation_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Perform detailed code analysis
    complexity = detect_code_complexity(code)
    
    analysis_results = []
    
    # Enhanced code metrics with insights
    lines = code.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]
    
    analysis_results.append(f"## Comprehensive Code Analysis for {language.value.title()}")
    analysis_results.append(f"- **Total lines:** {len(lines)}")
    analysis_results.append(f"- **Non-empty lines:** {len(non_empty_lines)}")
    analysis_results.append(f"- **Language detected:** {language.value}")
    analysis_results.append(f"- **Functions found:** {complexity['function_count']}")
    analysis_results.append(f"- **Classes found:** {complexity['class_count']}")
    analysis_results.append(f"- **Maximum nesting level:** {complexity['max_nesting_level']}")
    analysis_results.append(f"- **Complexity assessment:** {'High' if complexity['is_complex'] else 'Low' if complexity['is_simple'] else 'Medium'}")
    
    # Add targeted recommendations based on code structure
    if complexity['function_count'] == 0 and len(non_empty_lines) > 10:
        analysis_results.append("\n## ⚠️ Structural Concerns")
        analysis_results.append("- No functions detected in substantial code - consider breaking into functions")
    if complexity['max_nesting_level'] > 4:
        analysis_results.append("\n## ⚠️ Complexity Warning")
        analysis_results.append("- Very deep nesting detected - refactoring recommended")
    
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
    
    result_text = f"**Code to Analyze:**\n```{language.value}\n{code}\n```\n\n"
    
    # Add language guidance if needed
    language_guide = get_language_guidance(language, code)
    if language_guide:
        result_text += language_guide
    
    result_text += "\n".join(analysis_results)
    
    return [types.TextContent(type="text", text=result_text)]


def get_language_guidance(detected_language: LanguageType, code: str) -> str:
    """
    Provide guidance when language detection fails or when code seems ambiguous.
    
    Args:
        detected_language: The language that was detected
        code: The original code string
        
    Returns:
        Helpful guidance message
    """
    if detected_language == LanguageType.UNKNOWN:
        guidance = "\n## ⚠️ Language Detection Issue\n"
        guidance += "The programming language could not be automatically detected. This might happen if:\n"
        guidance += "- The code snippet is too short or doesn't contain language-specific keywords\n"
        guidance += "- The code is pseudocode or incomplete\n"
        guidance += "- It's a configuration file or data format rather than source code\n\n"
        guidance += "**Please specify the language explicitly** using the 'language' parameter, or provide more complete code with language-specific constructs.\n\n"
        guidance += "**Supported languages:** python, javascript, typescript, c, java, rust, go\n"
        return guidance
    
    # Check if code might be in a different language than detected
    if len(code.strip()) < 50:  # Very short code
        guidance = f"\n## 💡 Language Detection Note\n"
        guidance += f"Detected as {detected_language.value}, but the code is quite short. "
        guidance += "If this is incorrect, please specify the language explicitly.\n"
        return guidance
    
    return ""


# Add this function to help with tool results formatting
def format_tool_result(title: str, original_code: str, result_code: str, language: LanguageType, additional_info: str = "") -> str:
    """Format tool results consistently with helpful information."""
    formatted = f"## {title}\n\n"
    
    if additional_info:
        formatted += f"{additional_info}\n\n"
    
    formatted += f"**Original Code:**\n```{language.value}\n{original_code}\n```\n\n"
    formatted += f"**Result:**\n```{language.value}\n{result_code}\n```\n"
    
    # Add language guidance if needed
    language_guide = get_language_guidance(language, original_code)
    if language_guide:
        formatted += language_guide
    
    return formatted


async def streamline_rust_imports(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Streamline Rust import statements by consolidating imports with the same base path"""
    code = args.get("code", "")
    
    if not code or code.isspace():
        suggestions = [
            "Rust source code containing 'use' statements that need to be consolidated",
            "Include the complete import section of your Rust file",
            "Provide the actual imports, not just function definitions",
            "Example: 'use std::collections::HashMap;' or 'use serde::{Serialize, Deserialize};'"
        ]
        elicitation_text = create_elicitation_message("streamline_rust_imports", "No Rust code provided", suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Check if the code contains Rust import statements
    if "use " not in code:
        suggestions = [
            "Rust code with 'use' statements (import statements)",
            "The code should contain lines starting with 'use'",
            "If you want to organize other Rust code, try the 'refactor_code' tool instead",
            "Example Rust imports: 'use std::fs::File;', 'use tokio::net::TcpListener;'"
        ]
        elicitation_text = create_elicitation_message("streamline_rust_imports", "No Rust import statements ('use' statements) found in the provided code", suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    try:
        # Split the text into lines
        lines = code.strip().split("\n")
        
        # Parse the import statements
        use_statements, other_lines = parse_import_statements(lines)
        
        # Group imports by base path
        grouped_by_base, special_imports = group_imports_by_base_path(use_statements)
        
        # Generate the consolidated import statements
        result = generate_import_statements(grouped_by_base, special_imports)
        
        # Combine with other non-import lines
        if other_lines and result:
            streamlined_code = "\n".join(other_lines + [""] + result)
        else:
            streamlined_code = "\n".join(other_lines + result)
        
        return [types.TextContent(
            type="text",
            text=f"**Streamlined Rust Code:**\n```rust\n{streamlined_code}\n```\n\n**Original Code:**\n```rust\n{code}\n```"
        )]
        
    except Exception as e:
        logger.error(f"Error streamlining Rust imports: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"Error streamlining Rust imports: {str(e)}\n\nOriginal code returned unchanged:\n```rust\n{code}\n```"
        )]


async def streamline_python_imports(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Streamline Python import statements by consolidating imports from the same module"""
    code = args.get("code", "")
    
    if not code or code.isspace():
        suggestions = [
            "Python source code containing import statements that need to be consolidated",
            "Include the complete import section of your Python file",
            "Provide the actual imports, not just function definitions",
            "Example: 'import os' or 'from collections import defaultdict, Counter'"
        ]
        elicitation_text = create_elicitation_message("streamline_python_imports", "No Python code provided", suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Check if the code contains Python import statements
    if not any(line.strip().startswith(('import ', 'from ')) for line in code.split('\n')):
        suggestions = [
            "Python code with import statements ('import' or 'from' statements)",
            "The code should contain lines starting with 'import' or 'from'",
            "If you want to organize other Python code, try the 'refactor_code' tool instead",
            "Example Python imports: 'import sys', 'from typing import List, Dict'"
        ]
        elicitation_text = create_elicitation_message("streamline_python_imports", "No Python import statements found in the provided code", suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    try:
        # Split the text into lines
        lines = code.strip().split("\n")
        
        # Parse the import statements
        simple_imports, from_imports = parse_python_import_statements(lines)
        
        # Generate the consolidated import statements
        result = generate_python_import_statements(simple_imports, from_imports)
        
        # Join the result back into a string
        streamlined_code = "\n".join(result)
        
        return [types.TextContent(
            type="text",
            text=f"**Streamlined Python Code:**\n```python\n{streamlined_code}\n```\n\n**Original Code:**\n```python\n{code}\n```"
        )]
        
    except Exception as e:
        logger.error(f"Error streamlining Python imports: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"Error streamlining Python imports: {str(e)}\n\nOriginal code returned unchanged:\n```python\n{code}\n```"
        )]


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
