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
      "args": ["/path/to/zmcp/src/zshell.py"],
      "env": {
        "MCP_API_TOKEN": "your-secret-token"
      }
    },
    "zmcp-code": {
      "command": "python", 
      "args": ["/path/to/zmcp/src/zcode.py"],
      "env": {
        "MCP_API_TOKEN": "your-secret-token"
      }
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
    "args": ["${workspaceFolder}/path/to/zshell.py"],
    "env": {
      "MCP_API_TOKEN": "your-secret-token"
    }
  },
  "zmcp-code": {
    "command": "python",
    "args": ["${workspaceFolder}/path/to/zcode.py"],
    "env": {
      "MCP_API_TOKEN": "your-secret-token"
    }
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

### Environment Variables
- `MCP_API_TOKEN`: Authentication token (default: "MYSECRET")

### Server Configuration
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
