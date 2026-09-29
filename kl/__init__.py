"""The knowledge layer: the graph as a hosted service.

Teams keep separate workspaces. Files come in, the graph is built from them,
projects are edited through change requests a person approves, and any agent
on any machine works through one run protocol. REST (kl.api) and MCP
(kl.mcp_server) are two doors to the same operations (kl.service).

    python -m kl serve                 run it
    python -m kl init --workspace acme first workspace, an admin and a key
    python -m kl openapi docs/openapi.json
"""
__version__ = "1.0.0"
