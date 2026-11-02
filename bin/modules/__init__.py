"""Companion module registry (MIT, additive to EDGPT).

Each module is a package under ``bin/modules`` exposing:

- ``NAME``: short identifier, unique.
- ``HTTP_ROUTES``: ``{"/path": handler}``; ``handler(qs: dict) -> JSON-able``.
- ``MCP_TOOLS``: list of plain functions registered with FastMCP as tools.

Modules must not start threads, listeners, or touch the filesystem at import
time (same rule as the rest of EDGPT). Input injection lives only in cmdkeys.
"""
import importlib

MODULE_NAMES = ("exobio", "cmdkeys", "industry")

_loaded = None


def load_modules():
    """Import every module once and return them in registry order."""
    global _loaded
    if _loaded is None:
        mods = []
        for name in MODULE_NAMES:
            mod = importlib.import_module(f"modules.{name}")
            for attr in ("NAME", "HTTP_ROUTES", "MCP_TOOLS"):
                if not hasattr(mod, attr):
                    raise AttributeError(f"module {name!r} is missing {attr}")
            mods.append(mod)
        _loaded = mods
    return list(_loaded)


def http_routes():
    """Merged ``{path: handler}`` across modules; duplicate paths are an error."""
    routes = {}
    for mod in load_modules():
        for path, handler in mod.HTTP_ROUTES.items():
            if path in routes:
                raise ValueError(f"duplicate HTTP route {path!r} in module {mod.NAME!r}")
            routes[path] = handler
    return routes


def http_route(path):
    """Return the handler for ``path`` or ``None`` when no module owns it."""
    return http_routes().get(path)


def register_mcp_tools(mcp):
    """Attach every module's MCP tools to a FastMCP instance; returns tool names."""
    names = []
    for mod in load_modules():
        for func in mod.MCP_TOOLS:
            mcp.tool()(func)
            names.append(func.__name__)
    return names


def module_info():
    """Summary used by /capabilities-style discovery."""
    return [{"name": mod.NAME,
             "http_routes": sorted(mod.HTTP_ROUTES),
             "mcp_tools": [f.__name__ for f in mod.MCP_TOOLS]}
            for mod in load_modules()]
