"""Command keys: .binds parser, macro definitions, state-reactive key macros.

Scaffold only. Input injection is OFF; this module never sends keys unless a
local user action triggers it. MCP tools can LIST macros, never run them.
"""
NAME = "cmdkeys"


def list_macros(qs=None):
    """Defined macros and their enabled/opt-in state (no execution)."""
    return {"module": NAME, "status": "scaffold", "macros": [], "injection_enabled": False}


def get_command_macros() -> dict:
    """List the user's defined command macros. Read-only; running a macro requires local user action."""
    return list_macros()


HTTP_ROUTES = {"/cmdkeys": list_macros}
MCP_TOOLS = [get_command_macros]
