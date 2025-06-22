# ZMCP - Multi-Tool MCP Server

A comprehensive Model Context Protocol (MCP) server that provides safe shell command execution and advanced code analysis capabilities for AI agents and tools like VS Code Copilot.

## Features

### Shell Execution (zshell)
- **Safe Command Execution**: Whitelist-based command filtering
- **Comprehensive Tool Set**: Support for file operations, text processing, development tools, and system utilities
- **Security First**: 30-second timeouts, no destructive operations, controlled environment

### Code Analysis (zcode)
- **Code Quality Metrics**: Cyclomatic complexity, maintainability index, technical debt assessment
- **Intelligent Refactoring**: Extract functions, reduce duplication, simplify conditionals, improve naming
- **Documentation Generation**: Add comprehensive comments and documentation
- **Code Simplification**: Reduce nesting, use modern features, eliminate redundancy
- **Import Organization**: Streamline Python and Rust import statements
- **Multi-Language Support**: Python, JavaScript, TypeScript, Rust, C, Java, Go

### MCP Integration
- **Full MCP Compatibility**: Complete Model Context Protocol support
- **JSON-RPC Interface**: Simple integration over stdio
- **VS Code Ready**: Direct integration with VS Code Copilot

## Installation

### Option 1: Direct Usage
```bash
git clone https://github.com/yourusername/zmcp.git
cd zmcp
pip install -e .
```

### Option 2: Install from PyPI (when published)
```bash
pip install shell-executor-mcp
```

### Option 3: Using uv (recommended)
```bash
git clone https://github.com/yourusername/zmcp.git
cd zmcp
uv sync
```

## VS Code Integration

### 1. Global Configuration
Add to your VS Code settings.json or MCP configuration:

```json
{
  "mcpServers": {
    "zmcp-shell": {
      "command": "python",
      "args": ["/path/to/zmcp/src/zshell.py"]
    },
    "zmcp-code": {
      "command": "python", 
      "args": ["/path/to/zmcp/src/zcode.py"]
    }
  }
}
```

### 2. Workspace Configuration
Create `.vscode/mcp_servers.json` in your workspace:

```json
{
  "zmcp-shell": {
    "command": "python",
    "args": ["${workspaceFolder}/path/to/zshell.py"]
  },
  "zmcp-code": {
    "command": "python",
    "args": ["${workspaceFolder}/path/to/zcode.py"]
  }
}
```

### 3. Using with VS Code Copilot
Once configured, Copilot can discover and use both servers through MCP:

**Shell commands:**
```
@zmcp-shell execute ls -la
@zmcp-shell execute git status
@zmcp-shell execute cargo build
```

**Code analysis:**
```
@zmcp-code analyze this function for performance issues
@zmcp-code refactor this code to reduce complexity
@zmcp-code add comprehensive documentation to this class
```

## Manual Testing

### Start the servers:

**Shell executor:**
```bash
python src/zshell.py
```

**Code analyzer:**
```bash
python src/zcode.py
```

### Send test requests:

1. **Initialize:**
```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0.0"}}}
```

2. **List tools:**
```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
```

3. **Execute shell command:**
```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "execute_command", "arguments": {"command": "echo", "args": ["Hello World"]}}}
```

4. **Analyze code:**
```json
{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "analyze_code", "arguments": {"code": "def hello():\n    print('world')", "language": "python"}}}
```

## Available Tools

### Shell Execution Tools (zshell)

- **execute_command**: Execute whitelisted shell commands safely
- **get_joke**: Get a random programming joke (for testing server connection)

#### Supported Commands:

**File System:**
- `ls`, `cat`, `head`, `tail`, `find`, `tree`, `wc`, `du`, `df`
- `file`, `stat`, `pwd`

**Text Processing:**
- `grep`, `sed`, `awk`, `sort`, `uniq`, `cut`, `tr`

**Development:**
- `git`, `npm`, `yarn`, `pip`, `python`, `node`, `cargo`, `make`
- `rustc`, `go`, `java`, `javac`

**System Info:**
- `ps`, `uptime`, `whoami`, `id`, `uname`, `which`

**Network:**
- `curl`, `wget`, `ping`, `dig`, `nslookup`

**Archives:**
- `tar`, `zip`, `unzip`, `gzip`, `gunzip`

**Utilities:**
- `echo`, `date`, `cal`, `bc`, `expr`, `basename`, `dirname`
- Hash tools: `md5`, `sha256sum`, `shasum`

### Code Analysis Tools (zcode)

- **get_prompts**: Get useful development prompts for code improvement
- **get_code_metrics**: Calculate detailed code quality metrics (complexity, maintainability, technical debt)
- **refactor_code**: Analyze code and provide refactoring suggestions
- **add_comments**: Add comprehensive comments and documentation
- **simplify_code**: Simplify code while maintaining functionality
- **analyze_code**: Analyze code and suggest improvements
- **detect_code_patterns**: Detect design patterns and anti-patterns
- **generate_tests**: Generate comprehensive unit tests with edge cases
- **streamline_rust_imports**: Consolidate Rust import statements
- **streamline_python_imports**: Consolidate Python import statements

## Security

### Shell Execution Security
- Commands are filtered through a whitelist
- 30-second execution timeout
- No destructive operations (rm, mv, cp) allowed
- No privilege escalation (sudo, su) allowed
- Environment variables can be controlled

### Code Analysis Security
- Code analysis is performed locally
- No code execution during analysis
- Input validation for all code submissions
- Sandboxed analysis environment

## Configuration

Each server can be configured independently:

**zshell.py**: 
- Whitelist-based command filtering
- Configurable timeout (default: 30 seconds)
- Working directory control

**zcode.py**:
- Language detection and support
- Analysis depth configuration
- Output format preferences

## Project Structure

```
zmcp/
├── src/
│   ├── zshell.py          # Shell command execution MCP server
│   ├── zcode.py           # Code analysis and refactoring MCP server
│   ├── tool_helpers.py    # Common MCP tool utilities
│   ├── rust_import_helpers.py    # Rust import consolidation
│   └── python_import_helpers.py  # Python import consolidation
├── pyproject.toml         # Project configuration and dependencies
├── uv.lock               # Locked dependencies (uv package manager)
└── README.md             # This file
```

## Development

### Prerequisites
- Python 3.10+
- MCP library (`pip install mcp`)
- Optional: uv package manager for faster dependency management

### Running from Source
```bash
# Clone the repository
git clone https://github.com/yourusername/zmcp.git
cd zmcp

# Install dependencies
pip install -e .
# OR using uv
uv sync

# Run individual servers
python src/zshell.py
python src/zcode.py
```

### Adding New Tools
1. Add tool definition to the appropriate server's `handle_list_tools()` function
2. Implement the tool handler in the `handle_call_tool()` function
3. Add input validation and error handling
4. Update this README with the new tool documentation
````


## Future commands to add for zcode

```
async def security_audit(args: Dict[str, Any]) -> List[types.TextContent]:
    """Audit code for security vulnerabilities including SQL injection, XSS, hardcoded secrets"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    audit_focus = args.get("audit_focus", "all")
    
    # Rust-specific: unsafe blocks, buffer overflows, memory safety
    # Python-specific: pickle vulnerabilities, eval/exec usage, SQL injection
    # Go-specific: race conditions, input validation, cryptographic issues
```

```
async def dependency_vulnerabilities(args: Dict[str, Any]) -> List[types.TextContent]:
    """Scan dependencies for known security vulnerabilities"""
    dependencies = args.get("dependencies", "")
    language = detect_language(dependencies, args.get("language", "auto-detect"))
    
    # Parse Cargo.toml, requirements.txt, go.mod
    # Check against vulnerability databases (cargo audit, safety, govulncheck)
```

```
async def performance_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze code for performance bottlenecks and optimization opportunities"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    focus = args.get("focus", "all")  # algorithms, memory, concurrency, io
    
    # Rust: zero-cost abstractions, allocation patterns, async performance
    # Python: GIL issues, list comprehensions vs loops, generator usage
    # Go: goroutine leaks, channel usage, garbage collection pressure
```

```
async def memory_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze code for memory usage patterns and potential leaks"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    
    # Rust: ownership patterns, unnecessary clones, Box usage
    # Python: circular references, large object creation
    # Go: pointer usage, slice/map growth patterns
```

```
async def concurrency_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze concurrent code for race conditions and performance issues"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    
    # Rust: thread safety, async/await patterns, Arc/Mutex usage
    # Python: asyncio patterns, threading vs multiprocessing
    # Go: goroutine patterns, channel usage, context handling
```

```
async def rust_ownership_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze Rust code for ownership, borrowing, and lifetime issues"""
    code = args.get("code", "")
    
    # Detect unnecessary clones, lifetime issues, borrow checker problems
    # Suggest better ownership patterns, zero-copy alternatives
```

```
async def python_async_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze Python async/await patterns and suggest improvements"""
    code = args.get("code", "")
    
    # Detect blocking calls in async functions, improper exception handling
    # Suggest proper async patterns, asyncio best practices
```

```
async def go_error_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze Go error handling patterns and suggest improvements"""
    code = args.get("code", "")
    
    # Detect improper error handling, missing error checks
    # Suggest error wrapping, custom error types
```

```
async def rust_modernizer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Modernize Rust code to use latest idioms and features"""
    code = args.get("code", "")
    edition = args.get("edition", "2021")
    
    # Update to modern Rust patterns, suggest new std library features
    # Convert to use const generics, async/await, pattern matching improvements
```

```
async def python_type_annotator(args: Dict[str, Any]) -> List[types.TextContent]:
    """Add type annotations to Python code for better static analysis"""
    code = args.get("code", "")
    strict_mode = args.get("strict_mode", False)
    
    # Add missing type hints, suggest generic types, Union types
    # Use mypy-compatible annotations, dataclasses
```

```
async def go_generics_converter(args: Dict[str, Any]) -> List[types.TextContent]:
    """Convert Go code to use generics where appropriate (Go 1.18+)"""
    code = args.get("code", "")
    
    # Convert interface{} to generics, type-safe collections
    # Suggest generic functions and types
```

```
async def rust_macro_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze Rust macros and suggest improvements or alternatives"""
    code = args.get("code", "")
    
    # Analyze macro complexity, suggest proc macros vs declarative
    # Detect macro hygiene issues, performance implications
```

```
async def python_import_optimizer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Optimize Python imports and suggest better organization"""
    code = args.get("code", "")
    
    # Extend existing streamline_python_imports with more intelligence
    # Suggest lazy imports, detect circular imports, optimize for startup time
```

```
async def go_interface_extractor(args: Dict[str, Any]) -> List[types.TextContent]:
    """Extract Go interfaces from concrete implementations"""
    code = args.get("code", "")
    minimal = args.get("minimal", True)
    
    # Extract minimal interfaces, suggest interface segregation
    # Detect implicit interface satisfaction
```

```
async def python_dataclass_generator(args: Dict[str, Any]) -> List[types.TextContent]:
    """Generate Python dataclasses from specifications or existing code"""
    specification = args.get("specification", "")
    frozen = args.get("frozen", False)
    slots = args.get("slots", True)
    
    # Generate dataclasses with proper typing, validation
    # Include __post_init__, property methods
```

```
async def go_struct_generator(args: Dict[str, Any]) -> List[types.TextContent]:
    """Generate Go structs with JSON tags and validation"""
    specification = args.get("specification", "")
    include_json_tags = args.get("include_json_tags", True)
    
    # Generate structs with appropriate tags, validation methods
    # Include String() methods, comparison functions
```

```
async def error_handling_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze error handling patterns across languages"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    
    # Rust: Result<T, E> patterns, ? operator usage
    # Python: exception handling, error context
    # Go: error return patterns, error wrapping
```

```
async def serialization_analyzer(args: Dict[str, Any]) -> List[types.TextContent]:
    """Analyze serialization patterns and suggest improvements"""
    code = args.get("code", "")
    language = detect_language(code, args.get("language", "auto-detect"))
    
    # Rust: serde patterns, custom serializers
    # Python: json, pickle, dataclasses serialization
    # Go: json tags, custom marshalers
```
