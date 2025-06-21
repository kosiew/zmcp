# Shell Executor MCP Server

A Model Context Protocol (MCP) server that provides safe shell command execution capabilities for AI agents and tools like VS Code Copilot.

## Features

- **Safe Command Execution**: Whitelist-based command filtering
- **Comprehensive Tool Set**: Support for file operations, text processing, development tools, and system utilities
- **MCP Compatible**: Full Model Context Protocol support
- **Easy Integration**: Simple JSON-RPC interface over stdio

## Installation

### Option 1: Direct Usage
```bash
git clone https://github.com/yourusername/shell-executor-mcp.git
cd shell-executor-mcp
pip install -e .
```

### Option 2: Install from PyPI (when published)
```bash
pip install shell-executor-mcp
```

## VS Code Integration

### 1. Global Configuration
Add to your VS Code settings.json or MCP configuration:

```json
{
  "mcpServers": {
    "shell-executor": {
      "command": "python",
      "args": ["/path/to/shell-executor-mcp/src/mcp_server.py"],
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
  "shell-executor": {
    "command": "python",
    "args": ["${workspaceFolder}/path/to/mcp_server.py"],
    "env": {
      "MCP_API_TOKEN": "your-secret-token"
    }
  }
}
```

### 3. Using with VS Code Copilot
Once configured, Copilot can discover and use the shell executor through MCP:

```
@shell-executor execute ls -la
@shell-executor execute git status
@shell-executor execute cargo build
```

## Manual Testing

### Start the server:
```bash
python src/mcp_server.py
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

3. **Execute command:**
```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "execute_command", "arguments": {"command": "echo", "args": ["Hello World"]}}}
```

## Supported Commands

### File System
- `ls`, `cat`, `head`, `tail`, `find`, `tree`, `wc`, `du`, `df`
- `file`, `stat`, `pwd`

### Text Processing
- `grep`, `sed`, `awk`, `sort`, `uniq`, `cut`, `tr`

### Development
- `git`, `npm`, `yarn`, `pip`, `python`, `node`, `cargo`, `make`
- `rustc`, `go`, `java`, `javac`

### System Info
- `ps`, `uptime`, `whoami`, `id`, `uname`, `which`

### Network
- `curl`, `wget`, `ping`, `dig`, `nslookup`

### Archives
- `tar`, `zip`, `unzip`, `gzip`, `gunzip`

### Utilities
- `echo`, `date`, `cal`, `bc`, `expr`, `basename`, `dirname`
- Hash tools: `md5`, `sha256sum`, `shasum`

## Security

- Commands are filtered through a whitelist
- 30-second execution timeout
- No destructive operations (rm, mv, cp) allowed
- No privilege escalation (sudo, su) allowed
- Environment variables can be controlled

## Configuration

Set environment variables:
- `MCP_API_TOKEN`: Authentication token (default: "MYSECRET")

## License

MIT License - see LICENSE file for details.
