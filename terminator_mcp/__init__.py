"""terminator_mcp — an MCP server that lets an LLM observe and (later) drive a
running Terminator terminal emulator via a local Unix-domain control socket
hosted by the in-process MCPBridge plugin.

P0: read-only (list / read buffer+scrollback / read selection).
"""

__version__ = '0.0.1'
