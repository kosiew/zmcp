from fastapi import FastAPI, HTTPException, Depends, Request, status, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import os
import shlex
import subprocess
import asyncio
import json
import signal
from typing import List, Optional, Dict
import threading

# --- Configuration ---
API_TOKEN = os.getenv('MCP_API_TOKEN', 'MYSECRET')

# Global dict to track running processes for cancellation
running_processes: Dict[str, subprocess.Popen] = {}

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
    'top': ['-l', '1'],  # Limit top to one iteration to avoid hanging
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
    'ping': ['-c', '1', '-c', '2', '-c', '3', '-c', '4', '-c', '5'],  # Limit ping counts
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

app = FastAPI(
    title="MCP Local Executor",
    description="A simple FastAPI server to run whitelisted shell commands via a modeled context protocol.",
    version="1.0.0"
)

# --- Security ---
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return True

# --- Request Schema ---
class ExecuteRequest(BaseModel):
    id: str = Field(..., description="Unique request identifier")
    command: str = Field(..., description="Base command to execute")
    args: List[str] = Field(default_factory=list, description="List of string arguments")
    stream: bool = Field(False, description="Whether to stream output (currently returns full output)")

class ExecuteResponse(BaseModel):
    id: str
    exit_code: int
    output: str

# WebSocket message types
class WSExecuteRequest(BaseModel):
    id: str
    command: str
    args: List[str] = Field(default_factory=list)
    token: str

class WSMessage(BaseModel):
    type: str  # "output", "exit", "error", "cancel_ack"
    id: str
    data: Optional[str] = None
    exit_code: Optional[int] = None

# --- Helpers ---
def is_allowed(cmd: str, args: List[str]) -> bool:
    if cmd not in ALLOWED_COMMANDS:
        return False
    allowed = ALLOWED_COMMANDS[cmd]
    if allowed is None:
        return True
    return all(arg in allowed for arg in args)

# --- Endpoint ---
@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest, authorized: bool = Depends(verify_token)):
    if not req.id or not req.command:
        raise HTTPException(status_code=400, detail="Missing id or command field")

    if not is_allowed(req.command, req.args):
        raise HTTPException(status_code=403, detail="Command or args not allowed")

    # Build command line safely
    cmd_line = [req.command] + req.args
    safe_cmd = [shlex.quote(part) for part in cmd_line]

    try:
        # For simplicity, return full output even if stream=True
        completed = subprocess.run(
            safe_cmd,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        return ExecuteResponse(
            id=req.id,
            exit_code=completed.returncode,
            output=completed.stdout
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WebSocket Endpoint ---
@app.websocket("/ws/execute")
async def websocket_execute(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            # Receive command request
            data = await websocket.receive_text()
            req = None
            try:
                req_data = json.loads(data)
                
                # Handle cancel requests
                if req_data.get("type") == "cancel":
                    command_id = req_data.get("id")
                    if command_id in running_processes:
                        try:
                            process = running_processes[command_id]
                            process.terminate()
                            # Wait a bit, then kill if still running
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            del running_processes[command_id]
                            await websocket.send_text(json.dumps({
                                "type": "cancel_ack",
                                "id": command_id,
                                "data": "Command cancelled"
                            }))
                        except Exception as e:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "id": command_id,
                                "data": f"Error cancelling command: {str(e)}"
                            }))
                    continue
                
                # Parse execute request
                req = WSExecuteRequest(**req_data)
                
                # Verify token
                if req.token != API_TOKEN:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "id": req.id,
                        "data": "Invalid token"
                    }))
                    continue
                
                # Check if command is allowed
                if not is_allowed(req.command, req.args):
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "id": req.id,
                        "data": "Command or args not allowed"
                    }))
                    continue
                
                # Execute command with streaming
                await execute_command_streaming(websocket, req)
                
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "id": "unknown",
                    "data": "Invalid JSON"
                }))
            except Exception as e:
                error_id = req.id if req else "unknown"
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "id": error_id,
                    "data": str(e)
                }))
                
    except WebSocketDisconnect:
        # Clean up any running processes for this connection
        for command_id, process in list(running_processes.items()):
            try:
                process.terminate()
                process.wait(timeout=1)
            except:
                try:
                    process.kill()
                except:
                    pass
            running_processes.pop(command_id, None)

async def execute_command_streaming(websocket: WebSocket, req: WSExecuteRequest):
    """Execute command and stream output in real-time"""
    cmd_line = [req.command] + req.args
    
    try:
        # Start process
        process = subprocess.Popen(
            cmd_line,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Track the process for potential cancellation
        running_processes[req.id] = process
        
        # Read output line by line and stream it
        try:
            if process.stdout:
                while True:
                    line = process.stdout.readline()
                    if line:
                        await websocket.send_text(json.dumps({
                            "type": "output",
                            "id": req.id,
                            "data": line
                        }))
                    elif process.poll() is not None:
                        # Process has finished
                        break
                    else:
                        # No output but process still running, small delay
                        await asyncio.sleep(0.1)
            
            # Get final exit code
            exit_code = process.poll()
            
            # Send completion message
            await websocket.send_text(json.dumps({
                "type": "exit",
                "id": req.id,
                "exit_code": exit_code
            }))
            
        finally:
            # Clean up
            if req.id in running_processes:
                del running_processes[req.id]
            try:
                process.terminate()
            except:
                pass
                
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error",
            "id": req.id,
            "data": f"Execution error: {str(e)}"
        }))
        if req.id in running_processes:
            del running_processes[req.id]

# --- Simple test page for WebSocket ---
@app.get("/test")
async def test_page():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Command Executor Test</title>
    <style>
        body { font-family: monospace; margin: 20px; }
        #output { 
            background: #000; 
            color: #0f0; 
            padding: 10px; 
            height: 400px; 
            overflow-y: scroll; 
            white-space: pre-wrap;
            border: 1px solid #333;
        }
        input[type="text"] { 
            width: 300px; 
            padding: 5px; 
            margin: 5px;
            font-family: monospace;
        }
        button { 
            padding: 5px 10px; 
            margin: 5px;
        }
    </style>
</head>
<body>
    <h1>WebSocket Command Executor</h1>
    
    <div>
        <input type="text" id="command" placeholder="Command (e.g., ls)" value="ls">
        <input type="text" id="args" placeholder="Args (space separated)" value="-la">
        <input type="text" id="token" placeholder="API Token" value="MYSECRET">
        <button onclick="executeCommand()">Execute</button>
        <button onclick="cancelCommand()">Cancel</button>
        <button onclick="clearOutput()">Clear</button>
    </div>
    
    <div>
        <strong>Examples:</strong>
        <button onclick="setExample('tail', '-f /var/log/system.log')">tail -f</button>
        <button onclick="setExample('find', '. -name \"*.py\"')">find .py files</button>
        <button onclick="setExample('ping', '-c 5 google.com')">ping</button>
        <button onclick="setExample('cargo', 'build')">cargo build</button>
    </div>
    
    <div id="output"></div>
    
    <script>
        let ws = null;
        let currentCommandId = null;
        
        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/execute`);
            
            ws.onopen = function() {
                addOutput('Connected to WebSocket\\n', '#0f0');
            };
            
            ws.onmessage = function(event) {
                const msg = JSON.parse(event.data);
                
                switch(msg.type) {
                    case 'output':
                        addOutput(msg.data, '#0f0');
                        break;
                    case 'exit':
                        addOutput(`\\n[Command completed with exit code: ${msg.exit_code}]\\n`, '#ff0');
                        currentCommandId = null;
                        break;
                    case 'error':
                        addOutput(`\\n[ERROR: ${msg.data}]\\n`, '#f00');
                        currentCommandId = null;
                        break;
                    case 'cancel_ack':
                        addOutput(`\\n[Command cancelled]\\n`, '#ff0');
                        currentCommandId = null;
                        break;
                }
            };
            
            ws.onclose = function() {
                addOutput('\\nWebSocket connection closed\\n', '#f00');
                setTimeout(connect, 1000); // Reconnect
            };
            
            ws.onerror = function(error) {
                addOutput(`\\nWebSocket error: ${error}\\n`, '#f00');
            };
        }
        
        function executeCommand() {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                addOutput('Not connected to WebSocket\\n', '#f00');
                return;
            }
            
            const command = document.getElementById('command').value.trim();
            const argsStr = document.getElementById('args').value.trim();
            const token = document.getElementById('token').value.trim();
            const args = argsStr ? argsStr.split(/\\s+/) : [];
            
            if (!command || !token) {
                addOutput('Please enter command and token\\n', '#f00');
                return;
            }
            
            currentCommandId = 'cmd_' + Date.now();
            
            addOutput(`$ ${command} ${argsStr}\\n`, '#0ff');
            
            ws.send(JSON.stringify({
                id: currentCommandId,
                command: command,
                args: args,
                token: token
            }));
        }
        
        function cancelCommand() {
            if (currentCommandId && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'cancel',
                    id: currentCommandId
                }));
            }
        }
        
        function addOutput(text, color = '#0f0') {
            const output = document.getElementById('output');
            const span = document.createElement('span');
            span.style.color = color;
            span.textContent = text;
            output.appendChild(span);
            output.scrollTop = output.scrollHeight;
        }
        
        function clearOutput() {
            document.getElementById('output').innerHTML = '';
        }
        
        function setExample(cmd, args) {
            document.getElementById('command').value = cmd;
            document.getElementById('args').value = args;
        }
        
        // Handle Enter key in input fields
        document.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && (e.target.id === 'command' || e.target.id === 'args')) {
                executeCommand();
            }
        });
        
        // Connect on page load
        connect();
    </script>
</body>
</html>
    """
