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


def _code_property(description: str = "The code content to process") -> Dict[str, Any]:
    """Helper function to create a code property"""
    return _string_property(description)


def _language_property() -> Dict[str, Any]:
    """Helper function to create a language property"""
    return _string_property(
        "Programming language (e.g., rust, python, javascript, typescript, etc.)",
        "auto-detect"
    )


def detect_language(code: str, language_hint: str = "auto-detect") -> LanguageType:
    """Detect programming language from code content"""
    if language_hint != "auto-detect":
        # Try to match the hint to an enum value
        hint_lower = language_hint.lower()
        for lang in LanguageType:
            if lang.value == hint_lower:
                return lang
        return LanguageType.UNKNOWN
    
    # Simple language detection based on common patterns
    code_lower = code.lower()
    
    if "def " in code or "import " in code or "class " in code:
        return LanguageType.PYTHON
    elif "function " in code or "const " in code or "let " in code or "var " in code:
        return LanguageType.JAVASCRIPT
    elif "interface " in code or "type " in code and "=>" in code:
        return LanguageType.TYPESCRIPT
    elif "#include" in code or "int main" in code:
        return LanguageType.C
    elif "public class" in code or "private " in code or "public " in code:
        return LanguageType.JAVA
    elif "fn " in code or "let mut" in code:
        return LanguageType.RUST
    elif "func " in code or "package " in code:
        return LanguageType.GO
    else:
        return LanguageType.UNKNOWN


@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="get_prompts",
            description="Get useful development prompts for code improvement",
            inputSchema=_create_schema({
                "category": _string_property(
                    "Category of prompts: all, refactoring, commenting, or simplifying", 
                    "all"
                )
            })
        ),
        types.Tool(
            name="refactor_code",
            description="Analyze code and provide refactoring suggestions",
            inputSchema=_create_schema({
                "code": _code_property("The code content to refactor"),
                "language": _language_property(),
                "refactor_type": _string_property(
                    "Type of refactoring: extract_function, reduce_duplication, simplify_conditionals, improve_naming, or general",
                    "general"
                )
            }, ["code"])
        ),
        types.Tool(
            name="add_comments",
            description="Add comprehensive comments and documentation to provided code",
            inputSchema=_create_schema({
                "code": _code_property("The code content to document"),
                "language": _language_property(),
                "comment_style": _string_property(
                    "Style of comments: docstring, inline, jsdoc, or comprehensive",
                    "comprehensive"
                )
            }, ["code"])
        ),
        types.Tool(
            name="simplify_code",
            description="Simplify provided code while maintaining functionality",
            inputSchema=_create_schema({
                "code": _code_property("The code content to simplify"),
                "language": _language_property(),
                "simplify_approach": _string_property(
                    "Approach: reduce_nesting, use_modern_features, eliminate_redundancy, or comprehensive",
                    "comprehensive"
                )
            }, ["code"])
        ),
        types.Tool(
            name="analyze_code",
            description="Analyze provided code and suggest improvements",
            inputSchema=_create_schema({
                "code": _code_property("The code content to analyze"),
                "language": _language_property(),
                "analysis_focus": _string_property(
                    "Focus area: performance, readability, maintainability, security, or all",
                    "all"
                )
            }, ["code"])
        ),
        types.Tool(
            name="streamline_rust_imports",
            description="Streamline Rust import statements by consolidating imports with the same base path",
            inputSchema=_create_schema({
                "code": _code_property("The Rust code with import statements to streamline")
            }, ["code"])
        ),
        types.Tool(
            name="streamline_python_imports",
            description="Streamline Python import statements by consolidating imports from the same module",
            inputSchema=_create_schema({
                "code": _code_property("The Python code with import statements to streamline")
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
    result_text += f"**Original Code:**\n```{language.value}\n{code}\n```\n\n"
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
        if language == LanguageType.PYTHON:
            suggestions.append('- Add docstrings using """triple quotes"""')
            suggestions.append("- Include Args:, Returns:, and Raises: sections")
        elif language in [LanguageType.JAVASCRIPT, LanguageType.TYPESCRIPT]:
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
        LanguageType.PYTHON: "# Single line\n\"\"\"\nMulti-line docstring\n\"\"\"",
        LanguageType.JAVASCRIPT: "// Single line\n/* Multi-line\n   comment */\n/** JSDoc comment */",
        LanguageType.TYPESCRIPT: "// Single line\n/* Multi-line */\n/** TSDoc comment */",
        LanguageType.JAVA: "// Single line\n/* Multi-line */\n/** Javadoc comment */",
        LanguageType.C: "// Single line\n/* Multi-line comment */",
        LanguageType.RUST: "// Single line\n/// Documentation comment\n/* Multi-line */",
        LanguageType.GO: "// Single line\n/* Multi-line comment */"
    }
    
    result_text = f"## Comment Enhancement for {language.value.title()} Code\n\n"
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
    result_text += f"**Original Code:**\n```{language.value}\n{code}\n```\n\n"
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
    
    analysis_results.append(f"## Code Analysis for {language.value.title()}")
    analysis_results.append(f"- **Total lines:** {len(lines)}")
    analysis_results.append(f"- **Non-empty lines:** {len(non_empty_lines)}")
    analysis_results.append(f"- **Language detected:** {language.value}")
    
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
    result_text += "\n".join(analysis_results)
    
    return [types.TextContent(type="text", text=result_text)]


async def streamline_rust_imports(args: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Streamline Rust import statements by consolidating imports with the same base path"""
    code = args.get("code", "")
    
    if not code or code.isspace():
        return [types.TextContent(type="text", text="Error: No code provided")]
    
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
        return [types.TextContent(type="text", text="Error: No code provided")]
    
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
