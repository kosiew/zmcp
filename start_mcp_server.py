#!/usr/bin/env python3
"""
Startup script for the MCP Shell Executor Server
"""

import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
