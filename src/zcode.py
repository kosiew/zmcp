#!/usr/bin/env python3
"""
MCP Server for code analysis and refactoring tools.
Uses the official MCP library for proper protocol implementation.
"""

import asyncio
import logging
import re
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
            name="get_code_metrics",
            description="Calculate detailed code quality metrics including cyclomatic complexity, maintainability index, and technical debt assessment",
            inputSchema=create_schema({
                "code": code_property("The code content to analyze for quality metrics"),
                "language": language_property(),
                "metrics_focus": string_property(
                    "Focus area: complexity, maintainability, halstead, solid_principles, or all",
                    "all"
                )
            }, ["code"])
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
        ),
        types.Tool(
            name="detect_code_patterns",
            description="Detect design patterns and anti-patterns in code",
            inputSchema=create_schema({
                "code": code_property("The code content to analyze for patterns"),
                "language": language_property(),
                "pattern_focus": string_property(
                    "Focus area: design_patterns, anti_patterns, code_smells, architecture_patterns, or all",
                    "all"
                )
            }, ["code"])
        ),
        types.Tool(
            name="generate_tests",
            description="Generate comprehensive unit tests for provided code with edge cases, mocks, and coverage analysis",
            inputSchema=create_schema({
                "code": code_property("The code content to generate tests for"),
                "language": language_property(),
                "test_type": string_property(
                    "Type of tests: unit, integration, property_based, mock_heavy, or comprehensive",
                    "comprehensive"
                ),
                "test_framework": string_property(
                    "Preferred testing framework (e.g., pytest, jest, junit, go_test, or auto)",
                    "auto"
                )
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
    elif name == "get_code_metrics":
        return await get_code_metrics(arguments)
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
    elif name == "detect_code_patterns":
        return await detect_code_patterns(arguments)
    elif name == "generate_tests":
        return await generate_tests(arguments)
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


async def get_code_metrics(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Calculate detailed code quality metrics"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    metrics_focus = args.get("metrics_focus", "all")
    
    # Validate input and provide elicitation if needed
    is_valid, validation_message = validate_code_input(code, min_lines=5)
    if not is_valid:
        suggestions = [
            "Source code for quality analysis (at least 5+ lines for meaningful metrics)",
            "Complete functions or classes work best for accurate complexity measurements",
            "Specify the programming language if auto-detection might be unclear",
            "Choose metrics focus: 'complexity' for cyclomatic complexity, 'maintainability' for maintainability index, 'halstead' for Halstead metrics, 'solid_principles' for SOLID adherence, or 'all' for comprehensive analysis",
            "Include actual production code rather than simple examples for realistic metrics"
        ]
        elicitation_text = create_elicitation_message("get_code_metrics", validation_message, suggestions)
        return [types.TextContent(type="text", text=elicitation_text)]
    
    # Get basic complexity analysis
    complexity = detect_code_complexity(code)
    
    # Calculate advanced metrics
    metrics_results = []
    
    # Enhanced cyclomatic complexity calculation
    cyclomatic_complexity = calculate_cyclomatic_complexity(code)
    
    # Halstead metrics calculation
    halstead_metrics = calculate_halstead_metrics(code, language)
    
    # Maintainability index calculation
    maintainability_index = calculate_maintainability_index(code, cyclomatic_complexity, halstead_metrics)
    
    # Technical debt assessment
    technical_debt = assess_technical_debt(code, complexity, language)
    
    # SOLID principles adherence (where applicable)
    solid_assessment = assess_solid_principles(code, language, complexity)
    
    metrics_results.append(f"## Comprehensive Code Quality Metrics for {language.value.title()}")
    metrics_results.append(f"**Code Size:** {len(code.split())} words, {complexity['non_empty_lines']} non-empty lines")
    
    if metrics_focus == "complexity" or metrics_focus == "all":
        metrics_results.append("\n### 📊 Cyclomatic Complexity Analysis")
        metrics_results.append(f"- **Cyclomatic Complexity:** {cyclomatic_complexity['total']} (McCabe)")
        metrics_results.append(f"- **Average per Function:** {cyclomatic_complexity['average']:.1f}")
        metrics_results.append(f"- **Maximum Function Complexity:** {cyclomatic_complexity['max']}")
        metrics_results.append(f"- **Risk Assessment:** {get_complexity_risk_level(cyclomatic_complexity['max'])}")
        
        # Complexity interpretation
        if cyclomatic_complexity['max'] <= 10:
            metrics_results.append("- ✅ **Good**: Low complexity, easy to test and maintain")
        elif cyclomatic_complexity['max'] <= 20:
            metrics_results.append("- ⚠️ **Moderate**: Consider refactoring complex functions")
        else:
            metrics_results.append("- 🚨 **High**: Significant refactoring recommended")
    
    if metrics_focus == "halstead" or metrics_focus == "all":
        metrics_results.append("\n### 🔢 Halstead Complexity Metrics")
        metrics_results.append(f"- **Program Length (N):** {halstead_metrics['length']}")
        metrics_results.append(f"- **Vocabulary Size (n):** {halstead_metrics['vocabulary']}")
        metrics_results.append(f"- **Estimated Length (N̂):** {halstead_metrics['estimated_length']:.1f}")
        metrics_results.append(f"- **Volume (V):** {halstead_metrics['volume']:.1f}")
        metrics_results.append(f"- **Difficulty (D):** {halstead_metrics['difficulty']:.1f}")
        metrics_results.append(f"- **Effort (E):** {halstead_metrics['effort']:.1f}")
        metrics_results.append(f"- **Programming Time:** {halstead_metrics['time']:.1f} seconds")
        metrics_results.append(f"- **Estimated Bugs:** {halstead_metrics['bugs']:.2f}")
    
    if metrics_focus == "maintainability" or metrics_focus == "all":
        metrics_results.append("\n### 🔧 Maintainability Assessment")
        metrics_results.append(f"- **Maintainability Index:** {maintainability_index:.1f}/100")
        
        if maintainability_index >= 85:
            metrics_results.append("- ✅ **Excellent**: Highly maintainable code")
        elif maintainability_index >= 70:
            metrics_results.append("- ✅ **Good**: Generally maintainable with minor issues")
        elif maintainability_index >= 50:
            metrics_results.append("- ⚠️ **Moderate**: Maintainability concerns present")
        else:
            metrics_results.append("- 🚨 **Poor**: Significant maintainability issues")
        
        # Technical debt assessment
        metrics_results.append(f"\n### 💳 Technical Debt Assessment")
        for debt_item in technical_debt:
            metrics_results.append(f"- {debt_item}")
    
    if metrics_focus == "solid_principles" or metrics_focus == "all":
        if complexity['class_count'] > 0 or complexity['function_count'] > 0:
            metrics_results.append("\n### 🏗️ SOLID Principles Adherence")
            for principle, assessment in solid_assessment.items():
                metrics_results.append(f"- **{principle}:** {assessment}")
        else:
            metrics_results.append("\n### 🏗️ SOLID Principles Assessment")
            metrics_results.append("- No classes or functions detected - SOLID principles primarily apply to object-oriented code")
    
    # Overall code quality score
    overall_score = calculate_overall_quality_score(cyclomatic_complexity, maintainability_index, halstead_metrics)
    metrics_results.append(f"\n### 🎯 Overall Quality Score: {overall_score:.1f}/100")
    
    if overall_score >= 80:
        metrics_results.append("**Assessment:** High-quality code with good practices")
    elif overall_score >= 60:
        metrics_results.append("**Assessment:** Good code quality with room for improvement")
    elif overall_score >= 40:
        metrics_results.append("**Assessment:** Moderate quality, consider refactoring")
    else:
        metrics_results.append("**Assessment:** Significant quality issues requiring attention")
    
    # Specific recommendations based on metrics
    metrics_results.append("\n### 💡 Improvement Recommendations")
    recommendations = generate_metrics_recommendations(cyclomatic_complexity, maintainability_index, halstead_metrics, technical_debt)
    for rec in recommendations:
        metrics_results.append(f"- {rec}")
    
    result_text = f"**Code Under Analysis:**\n```{language.value}\n{code}\n```\n\n"
    
    # Add language guidance if needed
    language_guide = get_language_guidance(language, code)
    if language_guide:
        result_text += language_guide
    
    result_text += "\n".join(metrics_results)
    
    return [types.TextContent(type="text", text=result_text)]


def calculate_cyclomatic_complexity(code: str) -> Dict[str, Any]:
    """Calculate McCabe cyclomatic complexity"""
    lines = code.split('\n')
    total_complexity = 1  # Base complexity
    function_complexities = []
    current_function_complexity = 1
    in_function = False
    
    # Decision points that increase complexity
    decision_keywords = ['if', 'elif', 'else', 'for', 'while', 'case', 'catch', 'except', 'and', 'or', '&&', '||', '?']
    
    for line in lines:
        line_stripped = line.strip().lower()
        
        # Detect function start
        if any(func_start in line_stripped for func_start in ['def ', 'function ', 'fn ', 'func ']):
            if in_function:
                function_complexities.append(current_function_complexity)
            current_function_complexity = 1
            in_function = True
        
        # Count decision points
        for keyword in decision_keywords:
            if keyword in line_stripped:
                current_function_complexity += 1
                total_complexity += 1
    
    # Add the last function if we were in one
    if in_function:
        function_complexities.append(current_function_complexity)
    
    return {
        'total': total_complexity,
        'average': sum(function_complexities) / len(function_complexities) if function_complexities else total_complexity,
        'max': max(function_complexities) if function_complexities else total_complexity,
        'functions': function_complexities
    }


def calculate_halstead_metrics(code: str, language: LanguageType) -> Dict[str, float]:
    """Calculate Halstead complexity metrics"""
    # Define operators and operands based on language
    operators = set()
    operands = set()
    
    # Language-specific keywords and operators
    if language == LanguageType.PYTHON:
        python_operators = {'+', '-', '*', '/', '//', '%', '**', '=', '==', '!=', '<', '>', '<=', '>=', 
                          'and', 'or', 'not', 'in', 'is', 'if', 'elif', 'else', 'for', 'while', 'def', 
                          'class', 'return', 'import', 'from', 'as', 'try', 'except', 'finally', 'with'}
        operators.update(python_operators)
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        js_operators = {'+', '-', '*', '/', '%', '=', '==', '===', '!=', '!==', '<', '>', '<=', '>=',
                       '&&', '||', '!', 'if', 'else', 'for', 'while', 'function', 'return', 'var', 
                       'let', 'const', 'try', 'catch', 'finally', 'throw', 'new', 'typeof'}
        operators.update(js_operators)
    else:
        # Generic operators
        generic_operators = {'+', '-', '*', '/', '%', '=', '==', '!=', '<', '>', '<=', '>=', 
                           'if', 'else', 'for', 'while', 'return', 'function', 'def'}
        operators.update(generic_operators)
    
    # Simple tokenization (this is a basic implementation)
    import re
    tokens = re.findall(r'\b\w+\b|[^\w\s]', code)
    
    operator_count = 0
    operand_count = 0
    unique_operators = set()
    unique_operands = set()
    
    for token in tokens:
        if token in operators or not token.isalnum():
            operator_count += 1
            unique_operators.add(token)
        elif token.isalnum():
            operand_count += 1
            unique_operands.add(token)
    
    # Halstead metrics calculations
    n1 = len(unique_operators)  # Number of distinct operators
    n2 = len(unique_operands)   # Number of distinct operands
    N1 = operator_count         # Total number of operators
    N2 = operand_count         # Total number of operands
    
    # Avoid division by zero
    n = n1 + n2  # Vocabulary
    N = N1 + N2  # Length
    
    if n1 == 0 or n2 == 0 or n == 0:
        return {
            'length': N, 'vocabulary': n, 'estimated_length': 0, 'volume': 0,
            'difficulty': 0, 'effort': 0, 'time': 0, 'bugs': 0
        }
    
    import math
    estimated_length = n1 * math.log2(n1) + n2 * math.log2(n2)
    volume = N * math.log2(n) if n > 0 else 0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0
    effort = difficulty * volume
    time = effort / 18  # Seconds (Stroud number)
    bugs = volume / 3000  # Estimated bugs
    
    return {
        'length': N,
        'vocabulary': n,
        'estimated_length': estimated_length,
        'volume': volume,
        'difficulty': difficulty,
        'effort': effort,
        'time': time,
        'bugs': bugs
    }


def calculate_maintainability_index(code: str, cyclomatic_complexity: Dict[str, Any], halstead_metrics: Dict[str, float]) -> float:
    """Calculate maintainability index (0-100 scale)"""
    lines_of_code = len([line for line in code.split('\n') if line.strip()])
    
    # Avoid invalid values
    volume = max(halstead_metrics['volume'], 1)
    complexity = max(cyclomatic_complexity['average'], 1)
    loc = max(lines_of_code, 1)
    
    import math
    
    # Microsoft's maintainability index formula (modified for 0-100 scale)
    try:
        mi = 171 - 5.2 * math.log(volume) - 0.23 * complexity - 16.2 * math.log(loc)
        # Normalize to 0-100 scale
        mi = max(0, min(100, mi))
    except (ValueError, OverflowError):
        mi = 50  # Default middle value if calculation fails
    
    return mi


def assess_technical_debt(code: str, complexity: Dict[str, Any], language: LanguageType) -> List[str]:
    """Assess technical debt indicators"""
    debt_indicators = []
    
    lines = code.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]
    
    # Long methods/functions
    if complexity['non_empty_lines'] > 50:
        debt_indicators.append("🚨 **Long Code Block**: Consider breaking into smaller functions")
    
    # High complexity
    if complexity['max_nesting_level'] > 4:
        debt_indicators.append("🚨 **Deep Nesting**: Refactor to reduce complexity")
    
    # Magic numbers (simple detection)
    magic_numbers = 0
    for line in non_empty_lines:
        import re
        numbers = re.findall(r'\b\d+\b', line)
        magic_numbers += len([n for n in numbers if n not in ['0', '1']])
    
    if magic_numbers > 3:
        debt_indicators.append("⚠️ **Magic Numbers**: Replace with named constants")
    
    # Code duplication (basic detection)
    line_frequency = {}
    for line in non_empty_lines:
        clean_line = line.strip()
        if len(clean_line) > 10:  # Ignore very short lines
            line_frequency[clean_line] = line_frequency.get(clean_line, 0) + 1
    
    duplicated_lines = sum(1 for count in line_frequency.values() if count > 1)
    if duplicated_lines > 3:
        debt_indicators.append("⚠️ **Code Duplication**: Extract common functionality")
    
    # Missing error handling (basic detection)
    has_error_handling = any(keyword in code.lower() for keyword in ['try', 'catch', 'except', 'error', 'throw'])
    if not has_error_handling and complexity['non_empty_lines'] > 20:
        debt_indicators.append("⚠️ **Missing Error Handling**: Add exception handling")
    
    # Large parameter lists (basic detection)
    import re
    function_params = re.findall(r'\([^)]*\)', code)
    for params in function_params:
        param_count = len([p for p in params.split(',') if p.strip()])
        if param_count > 4:
            debt_indicators.append("⚠️ **Long Parameter Lists**: Consider parameter objects")
            break
    
    if not debt_indicators:
        debt_indicators.append("✅ **Low Technical Debt**: No major debt indicators detected")
    
    return debt_indicators


def assess_solid_principles(code: str, language: LanguageType, complexity: Dict[str, Any]) -> Dict[str, str]:
    """Assess adherence to SOLID principles"""
    assessment = {}
    
    # Single Responsibility Principle
    if complexity['class_count'] > 0:
        if complexity['non_empty_lines'] / max(complexity['class_count'], 1) > 50:
            assessment["Single Responsibility"] = "⚠️ Large classes detected - may violate SRP"
        else:
            assessment["Single Responsibility"] = "✅ Class sizes appear reasonable"
    else:
        assessment["Single Responsibility"] = "ℹ️ No classes detected - assess function responsibilities"
    
    # Open/Closed Principle
    has_inheritance = any(keyword in code.lower() for keyword in ['extends', 'inherits', 'class.*:', 'interface'])
    if has_inheritance:
        assessment["Open/Closed"] = "✅ Inheritance/interfaces detected - good for extensibility"
    else:
        assessment["Open/Closed"] = "ℹ️ Limited inheritance patterns - consider for future extensions"
    
    # Liskov Substitution Principle
    if complexity['class_count'] > 1:
        assessment["Liskov Substitution"] = "ℹ️ Multiple classes - ensure substitutability in inheritance"
    else:
        assessment["Liskov Substitution"] = "ℹ️ Limited class hierarchy - LSP not immediately applicable"
    
    # Interface Segregation Principle
    has_interfaces = 'interface' in code.lower() or 'abstract' in code.lower()
    if has_interfaces:
        assessment["Interface Segregation"] = "✅ Interfaces/abstractions detected"
    else:
        assessment["Interface Segregation"] = "ℹ️ Consider using interfaces for better decoupling"
    
    # Dependency Inversion Principle
    has_dependency_injection = any(pattern in code.lower() for pattern in ['inject', 'dependency', 'container'])
    if has_dependency_injection:
        assessment["Dependency Inversion"] = "✅ Dependency injection patterns detected"
    else:
        assessment["Dependency Inversion"] = "ℹ️ Consider dependency injection for better testability"
    
    return assessment


def get_complexity_risk_level(complexity: int) -> str:
    """Get risk level based on cyclomatic complexity"""
    if complexity <= 10:
        return "Low Risk"
    elif complexity <= 20:
        return "Moderate Risk"
    elif complexity <= 50:
        return "High Risk"
    else:
        return "Very High Risk"


def calculate_overall_quality_score(cyclomatic_complexity: Dict[str, Any], maintainability_index: float, halstead_metrics: Dict[str, float]) -> float:
    """Calculate overall code quality score"""
    # Complexity score (inverse relationship)
    complexity_score = max(0, 100 - (cyclomatic_complexity['max'] * 5))
    
    # Maintainability score
    maintainability_score = maintainability_index
    
    # Halstead score (based on estimated bugs)
    halstead_score = max(0, 100 - (halstead_metrics['bugs'] * 50))
    
    # Weighted average
    overall_score = (complexity_score * 0.4 + maintainability_score * 0.4 + halstead_score * 0.2)
    
    return min(100, max(0, overall_score))


def generate_metrics_recommendations(cyclomatic_complexity: Dict[str, Any], maintainability_index: float, halstead_metrics: Dict[str, float], technical_debt: List[str]) -> List[str]:
    """Generate specific recommendations based on metrics"""
    recommendations = []
    
    # Complexity recommendations
    if cyclomatic_complexity['max'] > 10:
        recommendations.append("**Reduce Cyclomatic Complexity**: Break down complex functions into smaller, focused functions")
    
    # Maintainability recommendations
    if maintainability_index < 70:
        recommendations.append("**Improve Maintainability**: Add documentation, reduce complexity, and improve naming")
    
    # Halstead recommendations
    if halstead_metrics['bugs'] > 0.5:
        recommendations.append("**Address Potential Bugs**: Review complex logic and add comprehensive testing")
    
    # Volume recommendations
    if halstead_metrics['volume'] > 1000:
        recommendations.append("**Reduce Code Volume**: Consider extracting functionality into separate modules")
    
    # Technical debt recommendations
    debt_count = len([debt for debt in technical_debt if '🚨' in debt or '⚠️' in debt])
    if debt_count > 2:
        recommendations.append("**Address Technical Debt**: Prioritize fixing identified debt indicators")
    
    if not recommendations:
        recommendations.append("**Good Code Quality**: Continue following current practices and consider regular code reviews")
    
    return recommendations


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


async def detect_code_patterns(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Detects design patterns, anti-patterns, code smells, and architecture patterns in code.
    
    Args:
        code: The code to analyze
        language: Programming language (optional, auto-detected if not provided)
        pattern_focus: Focus area - 'design_patterns', 'anti_patterns', 'code_smells', 'architecture', or 'all'
        
    Returns:
        List containing analysis results
    """
    try:
        code = args.get("code", "").strip()
        language_str = args.get("language", "auto-detect").lower()
        pattern_focus = args.get("pattern_focus", "all").lower()
        
        # Validate input
        if not code:
            return [types.TextContent(
                type="text",
                text="❌ **Error**: No code provided for analysis.\n\n**Usage**: Please provide the code you want to analyze for patterns.\n\n**Example**:\n```python\nclass DatabaseManager:\n    def __init__(self):\n        self.connection = None\n    \n    def get_connection(self):\n        if self.connection is None:\n            self.connection = Database.connect()\n        return self.connection\n```"
            )]
        
        # Auto-detect language
        language = detect_language(code, language_str)
        
        # Validate pattern focus
        valid_focuses = ["design_patterns", "anti_patterns", "code_smells", "architecture", "all"]
        if pattern_focus not in valid_focuses:
            pattern_focus = "all"
        
        pattern_results = []
        
        # Initialize variables
        design_patterns = []
        anti_patterns = []
        code_smells = []
        arch_patterns = []
        
        # Detect design patterns
        if pattern_focus in ["design_patterns", "all"]:
            design_patterns = detect_design_patterns(code, language)
            if design_patterns:
                pattern_results.append("## 🎨 Design Patterns Detected")
                for pattern in design_patterns:
                    pattern_results.append(f"### {pattern['name']}")
                    pattern_results.append(f"**Confidence:** {pattern['confidence']}")
                    pattern_results.append(f"**Description:** {pattern['description']}")
                    pattern_results.append(f"**Evidence:** {pattern['evidence']}")
                    if pattern['benefits']:
                        pattern_results.append(f"**Benefits:** {', '.join(pattern['benefits'])}")
                    pattern_results.append("")
        
        # Detect anti-patterns
        if pattern_focus in ["anti_patterns", "all"]:
            anti_patterns = detect_anti_patterns(code, language)
            if anti_patterns:
                pattern_results.append("## ⚠️ Anti-Patterns Detected")
                for pattern in anti_patterns:
                    pattern_results.append(f"### {pattern['name']}")
                    pattern_results.append(f"**Severity:** {pattern['severity']}")
                    pattern_results.append(f"**Description:** {pattern['description']}")
                    pattern_results.append(f"**Evidence:** {pattern['evidence']}")
                    if pattern['impacts']:
                        pattern_results.append(f"**Negative Impacts:** {', '.join(pattern['impacts'])}")
                    if pattern['refactoring_suggestions']:
                        pattern_results.append(f"**Refactoring Suggestions:** {', '.join(pattern['refactoring_suggestions'])}")
                    pattern_results.append("")
        
        # Detect code smells
        if pattern_focus in ["code_smells", "all"]:
            code_smells = detect_code_smells(code, language)
            if code_smells:
                pattern_results.append("## 👃 Code Smells Detected")
                for smell in code_smells:
                    pattern_results.append(f"### {smell['name']}")
                    pattern_results.append(f"**Type:** {smell['type']}")
                    pattern_results.append(f"**Severity:** {smell['severity']}")
                    pattern_results.append(f"**Description:** {smell['description']}")
                    pattern_results.append(f"**Evidence:** {smell['evidence']}")
                    if smell['refactoring_suggestions']:
                        pattern_results.append(f"**Refactoring Suggestions:** {', '.join(smell['refactoring_suggestions'])}")
                    pattern_results.append("")
        
        # Detect architecture patterns
        if pattern_focus in ["architecture", "all"]:
            arch_patterns = detect_architecture_patterns(code, language)
            if arch_patterns:
                pattern_results.append("## 🏗️ Architecture Patterns Detected")
                for pattern in arch_patterns:
                    pattern_results.append(f"### {pattern['name']}")
                    pattern_results.append(f"**Type:** {pattern['type']}")
                    pattern_results.append(f"**Confidence:** {pattern['confidence']}")
                    pattern_results.append(f"**Description:** {pattern['description']}")
                    pattern_results.append(f"**Evidence:** {pattern['evidence']}")
                    if pattern['benefits']:
                        pattern_results.append(f"**Benefits:** {', '.join(pattern['benefits'])}")
                    pattern_results.append("")
        
        # Overall pattern assessment
        if not any([design_patterns, anti_patterns, code_smells, arch_patterns]):
            pattern_results.append("## ✅ Pattern Analysis Results")
            pattern_results.append("No significant patterns, anti-patterns, or code smells detected in the provided code.")
            pattern_results.append("This could indicate:")
            pattern_results.append("- Clean, straightforward code")
            pattern_results.append("- Simple functionality that doesn't require complex patterns")
            pattern_results.append("- Code that follows good practices")
        else:
            # Generate overall recommendations
            pattern_results.append("## 💡 Overall Recommendations")
            recommendations = generate_pattern_recommendations(design_patterns, anti_patterns, code_smells, arch_patterns)
            for rec in recommendations:
                pattern_results.append(f"- {rec}")
        
        result_text = f"**Code Under Analysis:**\n```{language.value}\n{code}\n```\n\n"
        
        # Add pattern-specific guidance
        pattern_guide = get_pattern_guidance(language, pattern_focus)
        if pattern_guide:
            result_text += pattern_guide
        
        result_text += "\n".join(pattern_results)
        
        return [types.TextContent(type="text", text=result_text)]
        
    except Exception as e:
        logger.error(f"Error detecting code patterns: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"Error detecting code patterns: {str(e)}\n\nPlease ensure you provide valid code for analysis."
        )]


def detect_design_patterns(code: str, language: LanguageType) -> List[Dict[str, Any]]:
    """Detect design patterns in the code"""
    patterns = []
    
    # Singleton Pattern
    if re.search(r'class\s+\w+.*:\s*\n.*_instance\s*=\s*None', code, re.MULTILINE | re.DOTALL):
        patterns.append({
            'name': 'Singleton Pattern',
            'confidence': 'High',
            'description': 'Ensures a class has only one instance and provides global access to it',
            'evidence': 'Found class with _instance attribute, typical of Singleton implementation',
            'benefits': ['Controlled access to sole instance', 'Reduced namespace pollution', 'Permits refinement of operations']
        })
    
    # Factory Pattern
    if re.search(r'def\s+create_\w+|def\s+make_\w+|class\s+\w*Factory', code, re.IGNORECASE):
        patterns.append({
            'name': 'Factory Pattern',
            'confidence': 'Medium',
            'description': 'Creates objects without specifying the exact class to create',
            'evidence': 'Found factory-like method or class names (create_*, make_*, *Factory)',
            'benefits': ['Decouples object creation', 'Promotes code reusability', 'Makes testing easier']
        })
    
    # Observer Pattern
    if re.search(r'(notify|update|subscribe|observer|listener)', code, re.IGNORECASE):
        patterns.append({
            'name': 'Observer Pattern',
            'confidence': 'Medium',
            'description': 'Defines a one-to-many dependency between objects',
            'evidence': 'Found observer-related keywords (notify, update, subscribe, etc.)',
            'benefits': ['Loose coupling between subjects and observers', 'Dynamic relationships', 'Support for broadcast communication']
        })
    
    # Strategy Pattern
    if re.search(r'strategy|algorithm.*interface|def\s+execute', code, re.IGNORECASE):
        patterns.append({
            'name': 'Strategy Pattern',
            'confidence': 'Medium',
            'description': 'Defines a family of algorithms and makes them interchangeable',
            'evidence': 'Found strategy-related keywords or algorithm interfaces',
            'benefits': ['Algorithms can vary independently', 'Eliminates conditional statements', 'Runtime algorithm selection']
        })
    
    # Decorator Pattern
    if re.search(r'@\w+|decorator|wrapper.*function', code, re.IGNORECASE):
        patterns.append({
            'name': 'Decorator Pattern',
            'confidence': 'High' if '@' in code else 'Medium',
            'description': 'Adds new functionality to objects dynamically without altering structure',
            'evidence': 'Found decorators (@) or decorator-related patterns',
            'benefits': ['Extends functionality without inheritance', 'Flexible and reusable', 'Composition over inheritance']
        })
    
    # Command Pattern
    if re.search(r'execute.*command|invoke|undo|redo', code, re.IGNORECASE):
        patterns.append({
            'name': 'Command Pattern',
            'confidence': 'Medium',
            'description': 'Encapsulates a request as an object, allowing parameterization and queuing',
            'evidence': 'Found command execution, undo/redo, or invoke patterns',
            'benefits': ['Decouples sender and receiver', 'Supports undo operations', 'Supports logging and queuing']
        })
    
    # Builder Pattern
    if re.search(r'builder|build\(\)|with_\w+.*return\s+self', code, re.IGNORECASE):
        patterns.append({
            'name': 'Builder Pattern',
            'confidence': 'Medium',
            'description': 'Constructs complex objects step by step',
            'evidence': 'Found builder methods or fluent interface patterns',
            'benefits': ['Controls construction process', 'Allows different representations', 'Isolates complex construction code']
        })
    
    return patterns


def detect_anti_patterns(code: str, language: LanguageType) -> List[Dict[str, Any]]:
    """Detect anti-patterns in the code"""
    anti_patterns = []
    
    # God Object / God Class
    lines = code.split('\n')
    class_line_count = 0
    method_count = 0
    
    for line in lines:
        if re.match(r'\s*def\s+', line):
            method_count += 1
        elif re.match(r'\s*class\s+', line):
            if method_count > 20 or class_line_count > 200:
                anti_patterns.append({
                    'name': 'God Object',
                    'severity': 'High',
                    'description': 'A class that knows too much or does too much',
                    'evidence': f'Class with {method_count} methods or {class_line_count} lines',
                    'impacts': ['Hard to maintain', 'Difficult to test', 'Violates single responsibility'],
                    'refactoring_suggestions': ['Split into smaller classes', 'Apply Single Responsibility Principle', 'Use composition']
                })
            method_count = 0
            class_line_count = 0
        class_line_count += 1
    
    # Spaghetti Code
    if re.search(r'goto|continue.*break|break.*continue', code, re.IGNORECASE):
        anti_patterns.append({
            'name': 'Spaghetti Code',
            'severity': 'High',
            'description': 'Code with a complex and tangled control structure',
            'evidence': 'Found complex control flow patterns (goto, nested continue/break)',
            'impacts': ['Hard to follow logic', 'Difficult to debug', 'Error-prone'],
            'refactoring_suggestions': ['Simplify control flow', 'Extract methods', 'Use early returns']
        })
    
    # Magic Numbers
    magic_numbers = re.findall(r'\b(?<![\w\.])\d{2,}\b(?![\w\.])', code)
    if len(magic_numbers) > 3:
        anti_patterns.append({
            'name': 'Magic Numbers',
            'severity': 'Medium',
            'description': 'Hard-coded numerical values without explanation',
            'evidence': f'Found {len(magic_numbers)} potential magic numbers: {", ".join(set(magic_numbers[:5]))}',
            'impacts': ['Reduces code readability', 'Makes maintenance difficult', 'Prone to errors'],
            'refactoring_suggestions': ['Replace with named constants', 'Use configuration files', 'Add explanatory comments']
        })
    
    # Copy-Paste Programming
    lines_set = set()
    duplicate_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) > 10:
            if stripped in lines_set:
                duplicate_lines.append(stripped)
            lines_set.add(stripped)
    
    if len(duplicate_lines) > 5:
        anti_patterns.append({
            'name': 'Copy-Paste Programming',
            'severity': 'Medium',
            'description': 'Code duplication through copy-paste operations',
            'evidence': f'Found {len(duplicate_lines)} duplicate lines of code',
            'impacts': ['Maintenance nightmare', 'Inconsistent changes', 'Bloated codebase'],
            'refactoring_suggestions': ['Extract common functionality', 'Create reusable functions', 'Use inheritance or composition']
        })
    
    # Shotgun Surgery
    if code.count('import') > 15 or code.count('from') > 15:
        anti_patterns.append({
            'name': 'Shotgun Surgery',
            'severity': 'Medium',
            'description': 'Many imports suggest changes require modifications across many classes',
            'evidence': f'High number of imports ({code.count("import") + code.count("from")})',
            'impacts': ['Changes affect many files', 'Hard to track dependencies', 'Increased risk of bugs'],
            'refactoring_suggestions': ['Consolidate related functionality', 'Reduce coupling', 'Use dependency injection']
        })
    
    return anti_patterns


def detect_code_smells(code: str, language: LanguageType) -> List[Dict[str, Any]]:
    """Detect code smells in the code"""
    smells = []
    
    # Long Method
    methods = re.findall(r'def\s+\w+.*?(?=def|\Z)', code, re.DOTALL)
    for method in methods:
        method_lines = len([line for line in method.split('\n') if line.strip()])
        if method_lines > 30:
            method_name = re.search(r'def\s+(\w+)', method)
            name = method_name.group(1) if method_name else 'unknown'
            smells.append({
                'name': 'Long Method',
                'type': 'Bloater',
                'severity': 'Medium',
                'description': f'Method "{name}" is too long ({method_lines} lines)',
                'evidence': f'Method exceeds recommended length of 20-30 lines',
                'refactoring_suggestions': ['Extract smaller methods', 'Break down complex logic', 'Use composition']
            })
    
    # Long Parameter List
    param_lists = re.findall(r'def\s+\w+\([^)]*\)', code)
    for param_list in param_lists:
        param_count = len([p for p in param_list.split(',') if p.strip() and 'self' not in p])
        if param_count > 5:
            smells.append({
                'name': 'Long Parameter List',
                'type': 'Bloater',
                'severity': 'Medium',
                'description': f'Function has too many parameters ({param_count})',
                'evidence': f'Parameter count exceeds recommended maximum of 4-5',
                'refactoring_suggestions': ['Use parameter objects', 'Break into smaller functions', 'Use configuration objects']
            })
    
    # Duplicate Code
    lines = [line.strip() for line in code.split('\n') if line.strip() and len(line.strip()) > 5]
    line_counts = {}
    for line in lines:
        line_counts[line] = line_counts.get(line, 0) + 1
    
    duplicates = {line: count for line, count in line_counts.items() if count > 2}
    if duplicates:
        smells.append({
            'name': 'Duplicate Code',
            'type': 'Dispensable',
            'severity': 'High',
            'description': f'Found {len(duplicates)} duplicated code patterns',
            'evidence': f'Multiple identical or similar code segments detected',
            'refactoring_suggestions': ['Extract common code into functions', 'Use inheritance', 'Create utility functions']
        })
    
    # Dead Code
    if re.search(r'#.*TODO|#.*FIXME|#.*HACK|pass\s*$|return\s*$', code, re.MULTILINE):
        smells.append({
            'name': 'Dead Code / TODO Comments',
            'type': 'Dispensable',
            'severity': 'Low',
            'description': 'Found commented code, TODOs, or empty implementations',
            'evidence': 'TODO comments, FIXME notes, or pass statements detected',
            'refactoring_suggestions': ['Remove unused code', 'Implement TODOs', 'Clean up comments']
        })
    
    # Large Class
    class_matches = re.findall(r'class\s+\w+.*?(?=class|\Z)', code, re.DOTALL)
    for class_match in class_matches:
        class_lines = len([line for line in class_match.split('\n') if line.strip()])
        method_count = len(re.findall(r'def\s+\w+', class_match))
        if class_lines > 100 or method_count > 15:
            class_name = re.search(r'class\s+(\w+)', class_match)
            name = class_name.group(1) if class_name else 'unknown'
            smells.append({
                'name': 'Large Class',
                'type': 'Bloater',
                'severity': 'Medium',
                'description': f'Class "{name}" is too large ({class_lines} lines, {method_count} methods)',
                'evidence': f'Class exceeds recommended size limits',
                'refactoring_suggestions': ['Split into smaller classes', 'Extract responsibilities', 'Use composition']
            })
    
    return smells


def detect_architecture_patterns(code: str, language: LanguageType) -> List[Dict[str, Any]]:
    """Detect architecture patterns in the code"""
    patterns = []
    
    # MVC Pattern
    if re.search(r'(model|view|controller)', code, re.IGNORECASE):
        patterns.append({
            'name': 'Model-View-Controller (MVC)',
            'type': 'Architectural',
            'confidence': 'Medium',
            'description': 'Separates application logic into three interconnected components',
            'evidence': 'Found model, view, or controller related keywords',
            'benefits': ['Separation of concerns', 'Parallel development', 'Code reusability']
        })
    
    # Repository Pattern
    if re.search(r'repository|repo.*class', code, re.IGNORECASE):
        patterns.append({
            'name': 'Repository Pattern',
            'type': 'Data Access',
            'confidence': 'High',
            'description': 'Abstracts data access logic and provides a more object-oriented view of the persistence layer',
            'evidence': 'Found repository classes or interfaces',
            'benefits': ['Centralized data access logic', 'Easier testing', 'Database agnostic code']
        })
    
    # Service Layer Pattern
    if re.search(r'service.*class|.*service\.py', code, re.IGNORECASE):
        patterns.append({
            'name': 'Service Layer Pattern',
            'type': 'Architectural',
            'confidence': 'Medium',
            'description': 'Defines application boundaries with a layer of services',
            'evidence': 'Found service classes or service modules',
            'benefits': ['Clear application boundaries', 'Encapsulates business logic', 'Promotes reusability']
        })
    
    # Dependency Injection
    if re.search(r'inject|dependency|container|wire', code, re.IGNORECASE):
        patterns.append({
            'name': 'Dependency Injection',
            'type': 'Structural',
            'confidence': 'Medium',
            'description': 'Provides dependencies to an object rather than having it create them itself',
            'evidence': 'Found dependency injection related keywords',
            'benefits': ['Loose coupling', 'Better testability', 'Flexible configuration']
        })
    
    # Event-Driven Architecture
    if re.search(r'event|emit|dispatch|publish|subscribe', code, re.IGNORECASE):
        patterns.append({
            'name': 'Event-Driven Architecture',
            'type': 'Architectural',
            'confidence': 'Medium',
            'description': 'Uses events to trigger and communicate between services',
            'evidence': 'Found event handling, publishing, or subscription patterns',
            'benefits': ['Loose coupling', 'Scalability', 'Flexibility']
        })
    
    # Layered Architecture
    if re.search(r'layer|tier|presentation|business|data', code, re.IGNORECASE):
        patterns.append({
            'name': 'Layered Architecture',
            'type': 'Architectural',
            'confidence': 'Low',
            'description': 'Organizes code into horizontal layers',
            'evidence': 'Found layer or tier related terminology',
            'benefits': ['Separation of concerns', 'Maintainability', 'Testability']
        })
    
    return patterns


def generate_pattern_recommendations(design_patterns: List[Dict], anti_patterns: List[Dict], code_smells: List[Dict], arch_patterns: List[Dict]) -> List[str]:
    """Generate recommendations based on detected patterns"""
    recommendations = []
    
    # Recommendations based on anti-patterns
    if anti_patterns:
        recommendations.append("**Address Anti-Patterns First**: Focus on eliminating anti-patterns as they actively harm code quality")
        
        high_severity_anti_patterns = [ap for ap in anti_patterns if ap['severity'] == 'High']
        if high_severity_anti_patterns:
            recommendations.append(f"**High Priority**: {len(high_severity_anti_patterns)} high-severity anti-patterns need immediate attention")
    
    # Recommendations based on code smells
    if code_smells:
        bloater_smells = [cs for cs in code_smells if cs['type'] == 'Bloater']
        if bloater_smells:
            recommendations.append("**Code Size Issues**: Consider breaking down large methods and classes")
        
        dispensable_smells = [cs for cs in code_smells if cs['type'] == 'Dispensable']
        if dispensable_smells:
            recommendations.append("**Code Cleanup**: Remove dead code and unnecessary duplication")
    
    # Recommendations based on design patterns
    if design_patterns:
        recommendations.append("**Good Pattern Usage**: Continue leveraging design patterns for maintainable code")
    else:
        recommendations.append("**Consider Design Patterns**: Evaluate if design patterns could improve code structure")
    
    # Recommendations based on architecture patterns
    if arch_patterns:
        recommendations.append("**Architectural Awareness**: Good use of architectural patterns for better organization")
    else:
        recommendations.append("**Architecture Consideration**: Consider implementing architectural patterns for better code organization")
    
    # General recommendations
    if not design_patterns and not arch_patterns:
        recommendations.append("**Pattern Learning**: Study common design and architectural patterns to improve code structure")
    
    if anti_patterns or code_smells:
        recommendations.append("**Refactoring Priority**: Focus on eliminating technical debt before adding new features")
    
    return recommendations


def get_pattern_guidance(language: LanguageType, pattern_focus: str) -> str:
    """Get language and focus-specific guidance for pattern detection"""
    guidance = []
    
    if language == LanguageType.PYTHON:
        guidance.append("### 🐍 Python Pattern Analysis")
        guidance.append("Python's dynamic nature supports many patterns naturally. Focus on:")
        guidance.append("- Pythonic patterns (decorators, context managers, generators)")
        guidance.append("- Duck typing for interface patterns")
        guidance.append("- Metaclasses for advanced patterns")
    elif language == LanguageType.JAVASCRIPT:
        guidance.append("### 🟨 JavaScript Pattern Analysis")
        guidance.append("JavaScript's prototype-based nature enables unique patterns:")
        guidance.append("- Module patterns for encapsulation")
        guidance.append("- Prototype patterns for object creation")
        guidance.append("- Functional patterns with closures")
    
    if pattern_focus == "design_patterns":
        guidance.append("**Focus**: Design Patterns - Looking for creational, structural, and behavioral patterns")
    elif pattern_focus == "anti_patterns":
        guidance.append("**Focus**: Anti-Patterns - Identifying problematic code structures")
    elif pattern_focus == "code_smells":
        guidance.append("**Focus**: Code Smells - Detecting signs of deeper problems")
    elif pattern_focus == "architecture":
        guidance.append("**Focus**: Architecture Patterns - Analyzing high-level structure")
    
    return "\n".join(guidance) + "\n\n" if guidance else ""





async def generate_tests(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Generate comprehensive unit tests for provided code"""
    code = args.get("code", "").strip()
    language = args.get("language", "auto-detect")
    test_type = args.get("test_type", "comprehensive")
    test_framework = args.get("test_framework", "auto")
    
    # Handle elicitation for insufficient input
    if not code:
        return [types.TextContent(
            type="text",
            text="❓ **Missing Code Input**\n\nTo generate tests, I need:\n- **Code**: The source code to generate tests for\n- **Language** (optional): Programming language (auto-detected if not provided)\n- **Test Type** (optional): unit, integration, property_based, mock_heavy, or comprehensive\n- **Framework** (optional): Testing framework preference\n\nPlease provide the code you'd like me to generate tests for."
        )]
    
    # Detect language if not provided
    detected_language = detect_language(code, language)
    
    # Determine appropriate test framework
    framework = determine_test_framework(detected_language, test_framework)
    
    # Parse and analyze the code
    code_analysis = analyze_code_for_testing(code, detected_language)
    
    # Generate test content based on test type
    test_content = generate_test_content(code_analysis, detected_language, framework, test_type)
    
    # Generate coverage analysis and missing scenarios
    coverage_analysis = analyze_test_coverage(code_analysis, test_type)
    
    # Get testing guidance
    guidance = get_testing_guidance(detected_language, framework, test_type)
    
    result = f"""{guidance}

## 🧪 Generated Tests

{test_content}

## 📊 Coverage Analysis

{coverage_analysis}

## 🎯 Testing Recommendations

{generate_testing_recommendations(code_analysis, detected_language, test_type)}
"""
    
    return [types.TextContent(type="text", text=result)]


def determine_test_framework(language: LanguageType, preferred_framework: str) -> str:
    """Determine the appropriate test framework based on language and preference"""
    if preferred_framework != "auto":
        return preferred_framework
    
    framework_map = {
        LanguageType.PYTHON: "pytest",
        LanguageType.JAVASCRIPT: "jest",
        LanguageType.TYPESCRIPT: "jest",
        LanguageType.JAVA: "junit",
        LanguageType.C: "unity",
        LanguageType.RUST: "rust_test",
        LanguageType.GO: "go_test",
    }
    
    return framework_map.get(language, "generic")


def analyze_code_for_testing(code: str, language: LanguageType) -> Dict[str, Any]:
    """Analyze code to extract testable components"""
    analysis = {
        "functions": [],
        "classes": [],
        "methods": [],
        "dependencies": [],
        "complexity": "medium",
        "edge_cases": [],
        "error_conditions": [],
        "async_patterns": False,
        "io_operations": False,
        "external_apis": False
    }
    
    # Function detection patterns by language
    if language == LanguageType.PYTHON:
        # Find Python functions and classes
        functions = re.findall(r'def\s+(\w+)\s*\([^)]*\):', code)
        classes = re.findall(r'class\s+(\w+)(?:\([^)]*\))?:', code)
        methods = re.findall(r'def\s+(\w+)\s*\(self[^)]*\):', code)
        
        analysis["functions"] = functions
        analysis["classes"] = classes
        analysis["methods"] = methods
        analysis["async_patterns"] = "async def" in code or "await " in code
        analysis["io_operations"] = any(keyword in code for keyword in ["open(", "file", "input(", "print("])
        analysis["external_apis"] = any(keyword in code for keyword in ["requests.", "urllib", "http"])
        
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        # Find JavaScript/TypeScript functions and classes
        functions = re.findall(r'function\s+(\w+)\s*\(|const\s+(\w+)\s*=\s*\([^)]*\)\s*=>', code)
        classes = re.findall(r'class\s+(\w+)', code)
        methods = re.findall(r'(\w+)\s*\([^)]*\)\s*{', code)
        
        analysis["functions"] = [f for f in functions if f]
        analysis["classes"] = classes
        analysis["methods"] = methods
        analysis["async_patterns"] = "async " in code or "await " in code or "Promise" in code
        analysis["io_operations"] = any(keyword in code for keyword in ["fs.", "readFile", "writeFile", "console."])
        analysis["external_apis"] = any(keyword in code for keyword in ["fetch(", "axios", "http"])
    
    elif language == LanguageType.JAVA:
        # Find Java methods and classes
        functions = re.findall(r'public\s+\w+\s+(\w+)\s*\([^)]*\)', code)
        classes = re.findall(r'class\s+(\w+)', code)
        
        analysis["functions"] = functions
        analysis["classes"] = classes
        analysis["io_operations"] = any(keyword in code for keyword in ["System.out", "Scanner", "File"])
        analysis["external_apis"] = any(keyword in code for keyword in ["HttpClient", "URL", "RestTemplate"])
    
    # Detect potential edge cases and error conditions
    analysis["edge_cases"] = detect_edge_cases(code, language)
    analysis["error_conditions"] = detect_error_conditions(code, language)
    analysis["dependencies"] = detect_dependencies(code, language)
    
    return analysis


def detect_edge_cases(code: str, language: LanguageType) -> List[str]:
    """Detect potential edge cases in the code"""
    edge_cases = []
    
    # Common edge cases across languages
    if "len(" in code or ".length" in code or ".size" in code:
        edge_cases.extend(["Empty collections", "Single-item collections", "Large collections"])
    
    if any(op in code for op in ["/", "//", "%", "div"]):
        edge_cases.extend(["Division by zero", "Negative numbers", "Floating point precision"])
    
    if "null" in code or "None" in code or "nil" in code:
        edge_cases.append("Null/None values")
    
    if any(keyword in code for keyword in ["int(", "Integer.parseInt", "Number(", "parseFloat"]):
        edge_cases.extend(["Invalid input formats", "Overflow conditions", "Underflow conditions"])
    
    if "[" in code and "]" in code:
        edge_cases.extend(["Index out of bounds", "Empty arrays/lists"])
    
    return edge_cases


def detect_error_conditions(code: str, language: LanguageType) -> List[str]:
    """Detect potential error conditions in the code"""
    error_conditions = []
    
    if language == LanguageType.PYTHON:
        if "try:" in code or "except" in code:
            error_conditions.append("Exception handling present")
        if "raise" in code:
            error_conditions.append("Custom exceptions")
    
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        if "try {" in code or "catch" in code:
            error_conditions.append("Error handling present")
        if "throw" in code:
            error_conditions.append("Custom errors")
    
    elif language == LanguageType.JAVA:
        if "try {" in code or "catch" in code:
            error_conditions.append("Exception handling present")
        if "throw" in code:
            error_conditions.append("Custom exceptions")
    
    # Network/IO related errors
    if any(keyword in code for keyword in ["http", "url", "request", "file", "socket"]):
        error_conditions.extend(["Network failures", "IO errors", "Timeout conditions"])
    
    return error_conditions


def detect_dependencies(code: str, language: LanguageType) -> List[str]:
    """Detect external dependencies that may need mocking"""
    dependencies = []
    
    if language == LanguageType.PYTHON:
        imports = re.findall(r'import\s+(\w+)|from\s+(\w+)', code)
        dependencies.extend([imp for imp in imports if imp])
    
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        imports = re.findall(r'import.*from\s+[\'"]([^\'"]+)[\'"]|require\([\'"]([^\'"]+)[\'"]\)', code)
        dependencies.extend([imp for imp in imports if imp])
    
    # Common external services that typically need mocking
    if any(keyword in code for keyword in ["database", "db", "sql", "mongo"]):
        dependencies.append("Database")
    
    if any(keyword in code for keyword in ["redis", "cache", "memcache"]):
        dependencies.append("Cache")
    
    if any(keyword in code for keyword in ["api", "http", "request", "fetch"]):
        dependencies.append("External APIs")
    
    return dependencies


def generate_test_content(analysis: Dict[str, Any], language: LanguageType, framework: str, test_type: str) -> str:
    """Generate the actual test code based on analysis"""
    if language == LanguageType.PYTHON:
        return generate_python_tests(analysis, framework, test_type)
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        return generate_javascript_tests(analysis, framework, test_type)
    elif language == LanguageType.JAVA:
        return generate_java_tests(analysis, framework, test_type)
    elif language == LanguageType.RUST:
        return generate_rust_tests(analysis, framework, test_type)
    elif language == LanguageType.GO:
        return generate_go_tests(analysis, framework, test_type)
    else:
        return generate_generic_tests(analysis, language, test_type)


def generate_python_tests(analysis: Dict[str, Any], framework: str, test_type: str) -> str:
    """Generate Python test code"""
    if framework == "pytest":
        content = "```python\nimport pytest\nfrom unittest.mock import Mock, patch, MagicMock\n"
        
        # Add imports based on detected dependencies
        if analysis.get("async_patterns"):
            content += "import asyncio\nfrom pytest_asyncio import pytest\n"
        
        if analysis.get("dependencies"):
            content += "# Mock external dependencies\n"
            for dep in analysis["dependencies"]:
                content += f"# Mock {dep}\n"
        
        content += "\n# Test fixtures\n"
        content += "@pytest.fixture\ndef sample_data():\n    return {'key': 'value'}\n\n"
        
        # Generate tests for functions
        for func in analysis["functions"]:
            content += f"class Test{func.title()}:\n"
            content += f"    def test_{func}_happy_path(self):\n"
            content += f"        # Arrange\n        # Act\n        result = {func}()\n        # Assert\n        assert result is not None\n\n"
            
            # Add edge case tests
            for edge_case in analysis["edge_cases"]:
                test_name = edge_case.lower().replace(" ", "_").replace("/", "_")
                content += f"    def test_{func}_{test_name}(self):\n"
                content += f"        # Test {edge_case}\n        pass\n\n"
            
            # Add error condition tests
            for error in analysis["error_conditions"]:
                test_name = error.lower().replace(" ", "_")
                content += f"    def test_{func}_{test_name}(self):\n"
                content += f"        # Test {error}\n        with pytest.raises(Exception):\n            {func}()\n\n"
        
        # Generate mock tests if external dependencies detected
        if analysis["dependencies"]:
            content += "# Mock tests for external dependencies\n"
            content += "@patch('requests.get')\ndef test_with_external_api_mock(mock_get):\n"
            content += "    mock_get.return_value.json.return_value = {'status': 'success'}\n"
            content += "    # Your test code here\n    pass\n\n"
        
        # Property-based testing suggestions
        if test_type in ["property_based", "comprehensive"]:
            content += "# Property-based testing with Hypothesis\n"
            content += "# pip install hypothesis\n"
            content += "from hypothesis import given, strategies as st\n\n"
            content += "@given(st.text())\ndef test_property_based_example(s):\n"
            content += "    # Property: function should handle any string input\n    pass\n\n"
        
        content += "```"
        return content
    
    else:  # unittest
        content = "```python\nimport unittest\nfrom unittest.mock import Mock, patch, MagicMock\n\n"
        content += "class TestExample(unittest.TestCase):\n"
        content += "    def setUp(self):\n        pass\n\n"
        content += "    def tearDown(self):\n        pass\n\n"
        
        for func in analysis["functions"]:
            content += f"    def test_{func}(self):\n"
            content += f"        result = {func}()\n"
            content += f"        self.assertIsNotNone(result)\n\n"
        
        content += "if __name__ == '__main__':\n    unittest.main()\n```"
        return content


def generate_javascript_tests(analysis: Dict[str, Any], framework: str, test_type: str) -> str:
    """Generate JavaScript/TypeScript test code"""
    if framework == "jest":
        content = "```javascript\n// Jest test file\n"
        
        if analysis.get("dependencies"):
            content += "// Mock external dependencies\n"
            for dep in analysis["dependencies"]:
                content += f"jest.mock('{dep}');\n"
            content += "\n"
        
        content += "describe('Test Suite', () => {\n"
        content += "  beforeEach(() => {\n    // Setup before each test\n  });\n\n"
        content += "  afterEach(() => {\n    // Cleanup after each test\n    jest.clearAllMocks();\n  });\n\n"
        
        for func in analysis["functions"]:
            content += f"  describe('{func}', () => {{\n"
            content += f"    it('should work correctly', () => {{\n"
            content += f"      const result = {func}();\n"
            content += f"      expect(result).toBeDefined();\n    }});\n\n"
            
            # Add async tests if detected
            if analysis.get("async_patterns"):
                content += f"    it('should handle async operations', async () => {{\n"
                content += f"      const result = await {func}();\n"
                content += f"      expect(result).toBeDefined();\n    }});\n\n"
            
            # Add edge case tests
            for edge_case in analysis["edge_cases"]:
                test_name = edge_case.lower().replace(" ", "_")
                content += f"    it('should handle {edge_case.lower()}', () => {{\n"
                content += f"      // Test {edge_case}\n      expect(() => {func}()).not.toThrow();\n    }});\n\n"
        
        content += "  });\n});\n```"
        return content
    
    else:  # Mocha or generic
        content = "```javascript\n// Mocha test file\nconst { expect } = require('chai');\n\n"
        content += "describe('Test Suite', function() {\n"
        
        for func in analysis["functions"]:
            content += f"  describe('{func}', function() {{\n"
            content += f"    it('should work correctly', function() {{\n"
            content += f"      const result = {func}();\n"
            content += f"      expect(result).to.exist;\n    }});\n  }});\n"
        
        content += "});\n```"
        return content


def generate_java_tests(analysis: Dict[str, Any], framework: str, test_type: str) -> str:
    """Generate Java test code"""
    content = "```java\nimport org.junit.jupiter.api.Test;\n"
    content += "import org.junit.jupiter.api.BeforeEach;\n"
    content += "import org.junit.jupiter.api.AfterEach;\n"
    content += "import org.mockito.Mock;\nimport org.mockito.MockitoAnnotations;\n"
    content += "import static org.junit.jupiter.api.Assertions.*;\n"
    content += "import static org.mockito.Mockito.*;\n\n"
    
    content += "public class ExampleTest {\n\n"
    
    if analysis["dependencies"]:
        for dep in analysis["dependencies"]:
            content += f"    @Mock\n    private {dep} mock{dep};\n"
        content += "\n"
    
    content += "    @BeforeEach\n    void setUp() {\n"
    content += "        MockitoAnnotations.openMocks(this);\n    }\n\n"
    
    for func in analysis["functions"]:
        content += f"    @Test\n    void test{func.title()}() {{\n"
        content += f"        // Arrange\n        // Act\n        // Assert\n"
        content += f"        assertNotNull(result);\n    }}\n\n"
    
    content += "}\n```"
    return content


def generate_rust_tests(analysis: Dict[str, Any], framework: str, test_type: str) -> str:
    """Generate Rust test code"""
    content = "```rust\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n"
    
    for func in analysis["functions"]:
        content += f"    #[test]\n    fn test_{func}() {{\n"
        content += f"        let result = {func}();\n"
        content += f"        assert!(result.is_ok());\n    }}\n\n"
        
        # Add error tests
        content += f"    #[test]\n    #[should_panic]\n    fn test_{func}_error_case() {{\n"
        content += f"        // Test error condition\n    }}\n\n"
    
    content += "}\n```"
    return content


def generate_go_tests(analysis: Dict[str, Any], framework: str, test_type: str) -> str:
    """Generate Go test code"""
    content = "```go\npackage main\n\nimport (\n    \"testing\"\n)\n\n"
    
    for func in analysis["functions"]:
        content += f"func Test{func.title()}(t *testing.T) {{\n"
        content += f"    result := {func}()\n"
        content += f"    if result == nil {{\n        t.Error(\"Expected non-nil result\")\n    }}\n}}\n\n"
        
        # Add benchmark test
        content += f"func Benchmark{func.title()}(b *testing.B) {{\n"
        content += f"    for i := 0; i < b.N; i++ {{\n        {func}()\n    }}\n}}\n\n"
    
    content += "```"
    return content


def generate_generic_tests(analysis: Dict[str, Any], language: LanguageType, test_type: str) -> str:
    """Generate generic test structure for unsupported languages"""
    content = f"```{language.value}\n// Generic test structure for {language.value}\n\n"
    content += "// Test Setup\n// - Initialize test data\n// - Setup mocks for dependencies\n\n"
    
    for func in analysis["functions"]:
        content += f"// Test: {func}\n"
        content += f"// - Happy path test\n"
        content += f"// - Edge case tests\n"
        content += f"// - Error condition tests\n\n"
    
    content += "// Test Cleanup\n// - Reset mocks\n// - Clean up resources\n```"
    return content


def analyze_test_coverage(analysis: Dict[str, Any], test_type: str) -> str:
    """Analyze test coverage and suggest missing scenarios"""
    coverage = []
    
    # Function coverage
    func_count = len(analysis["functions"])
    if func_count > 0:
        coverage.append(f"**Functions**: {func_count} functions detected")
        coverage.append("- ✅ Basic functionality tests")
        if analysis["edge_cases"]:
            coverage.append("- ✅ Edge case tests")
        if analysis["error_conditions"]:
            coverage.append("- ✅ Error handling tests")
    
    # Coverage gaps
    missing = []
    if analysis.get("async_patterns") and test_type != "comprehensive":
        missing.append("- ⚠️ Async/concurrent execution tests")
    
    if analysis.get("io_operations"):
        missing.append("- ⚠️ IO operation error handling")
    
    if analysis.get("external_apis"):
        missing.append("- ⚠️ API failure scenarios")
    
    if analysis["dependencies"] and test_type != "mock_heavy":
        missing.append("- ⚠️ Comprehensive dependency mocking")
    
    if missing:
        coverage.append("\n**Missing Coverage Areas:**")
        coverage.extend(missing)
    
    # Coverage recommendations
    recommendations = [
        "\n**Coverage Recommendations:**",
        "- Aim for >90% line coverage",
        "- Include integration tests for critical paths",
        "- Add performance/load tests for bottlenecks",
        "- Consider mutation testing for test quality"
    ]
    
    if test_type == "comprehensive":
        recommendations.extend([
            "- Property-based testing for complex logic",
            "- Fuzz testing for input validation",
            "- Contract testing for APIs"
        ])
    
    coverage.extend(recommendations)
    
    return "\n".join(coverage)


def generate_testing_recommendations(analysis: Dict[str, Any], language: LanguageType, test_type: str) -> str:
    """Generate specific testing recommendations"""
    recommendations = []
    
    # Language-specific recommendations
    if language == LanguageType.PYTHON:
        recommendations.extend([
            "🐍 **Python Testing Best Practices:**",
            "- Use `pytest` fixtures for test data setup",
            "- Leverage `mock.patch` for external dependencies",
            "- Consider `hypothesis` for property-based testing",
            "- Use `pytest-cov` for coverage reporting"
        ])
    elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
        recommendations.extend([
            "🟨 **JavaScript/TypeScript Testing Best Practices:**",
            "- Use Jest's built-in mocking capabilities",
            "- Implement async/await testing patterns",
            "- Consider `@testing-library` for UI components",
            "- Use `supertest` for API testing"
        ])
    elif language == LanguageType.JAVA:
        recommendations.extend([
            "☕ **Java Testing Best Practices:**",
            "- Use Mockito for mocking frameworks",
            "- Implement parameterized tests with JUnit 5",
            "- Consider TestContainers for integration tests",
            "- Use AssertJ for fluent assertions"
        ])
    
    # Test type specific recommendations
    if test_type == "unit":
        recommendations.extend([
            "\n🔧 **Unit Testing Focus:**",
            "- Test individual functions in isolation",
            "- Mock all external dependencies",
            "- Focus on business logic validation"
        ])
    elif test_type == "integration":
        recommendations.extend([
            "\n🔗 **Integration Testing Focus:**",
            "- Test component interactions",
            "- Use real dependencies where possible",
            "- Validate data flow between layers"
        ])
    elif test_type == "property_based":
        recommendations.extend([
            "\n🎲 **Property-Based Testing Focus:**",
            "- Define invariants that should always hold",
            "- Use random input generation",
            "- Focus on mathematical properties"
        ])
    
    # Code-specific recommendations
    if analysis.get("async_patterns"):
        recommendations.extend([
            "\n⚡ **Async Testing:**",
            "- Test race conditions and timing issues",
            "- Mock time-dependent operations",
            "- Validate timeout and cancellation handling"
        ])
    
    if analysis.get("external_apis"):
        recommendations.extend([
            "\n🌐 **API Testing:**",
            "- Mock external service responses",
            "- Test error response handling",
            "- Validate retry and circuit breaker logic"
        ])
    
    return "\n".join(recommendations)


def get_testing_guidance(language: LanguageType, framework: str, test_type: str) -> str:
    """Get language and framework-specific testing guidance"""
    guidance = []
    
    guidance.append(f"# 🧪 Test Generation for {language.value.title()}")
    guidance.append(f"**Framework**: {framework} | **Type**: {test_type}")
    
    if framework == "pytest":
        guidance.append("Using pytest - Python's premier testing framework")
    elif framework == "jest":
        guidance.append("Using Jest - JavaScript testing framework with built-in mocking")
    elif framework == "junit":
        guidance.append("Using JUnit - Java's standard testing framework")
    
    return "\n".join(guidance) + "\n"


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
