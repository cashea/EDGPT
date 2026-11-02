from diagnostics import health, capabilities
import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from history_store import (
    get_event_page,
    history_summary,
    latest_event,
    recent_events,
    search_events,
)
from current_state import build_state, read_json_file, list_live_json
from system_map_store import get_current_system_map, get_system_map, list_system_maps
import session_store
from system_map_store import get_system_summary
import modules

mcp = FastMCP("Elite Dangerous Full Context", stateless_http=True, json_response=True,
              host="127.0.0.1", port=int(os.environ.get("EDGPT_MCP_PORT", "8000")))


@mcp.tool()
def get_current_system_summary() -> dict:
    """Read the compact current-system overview: grouped bodies/rings and recorded biology.

    Includes partial scans; all_bodies_found marks retained FSSAllBodiesFound.
    Returns {} if no map exists. Refreshes and
    saves derived curiosities from the merged map. Use full map tools for detail.
    """
    return get_system_summary() or {}


@mcp.tool()
def get_saved_system_summary(system: str) -> dict:
    """Read a partial or complete system overview by name or SystemAddress, refreshing
    derived curiosities. Returns {} if unknown; all_bodies_found marks recorded FSS completion.
    """
    return get_system_summary(system) or {}


def build_current_state():
    return build_state(include_history_summary=True, recent_event_count=250,
                       include_loadout=True, mcp_profile=True)


@mcp.tool()
def get_edgpt_health() -> dict:
    """Check EDGPT readiness, indexing, stale data and component failures without exposing private data."""
    return health(origin="mcp")


@mcp.tool()
def get_edgpt_capabilities() -> dict:
    """Discover API versions, endpoints, tools, state profiles, limits and enabled integrations."""
    return capabilities()


@mcp.tool()
def get_current_session_summary() -> dict:
    """Summarize the latest play session, including after shutdown; empty if unavailable."""
    return session_store.get_current_session_summary()


@mcp.tool()
def list_game_sessions(limit: int = 20, before: int = 0, start_time: str = "", end_time: str = "") -> dict:
    """Page session summaries newest first (limit 1-100); use next_before as before.

    Optional inclusive start-time filters require ISO 8601 timestamps with zones.
    """
    return session_store.list_game_sessions(limit, before, start_time, end_time)


@mcp.tool()
def get_game_session(session_id: str) -> dict:
    """Get a saved session's activities, text summary and source ID ranges; empty if not found."""
    return session_store.get_game_session(session_id)


@mcp.tool()
def get_elite_state() -> dict:
    """Get normalized current state plus raw location/loadout, live status/route, recent events, and history summary."""
    return build_current_state()


@mcp.tool()
def get_full_loadout() -> dict:
    """Get the most recent complete Loadout journal event, including modules and engineering."""
    return latest_event("Loadout") or {}


@mcp.tool()
def get_navroute() -> dict:
    """Get the currently plotted Elite Dangerous route."""
    return read_json_file("NavRoute.json") or {}


@mcp.tool()
def get_status() -> dict:
    """Get Status.json with raw numeric flags plus decoded names and unknown bit positions."""
    return read_json_file("Status.json") or {}


@mcp.tool()
def list_elite_live_files() -> list:
    """List every current JSON state file exposed by Elite Dangerous in the journal directory."""
    return list_live_json()


@mcp.tool()
def get_elite_live_file(filename: str) -> dict:
    """Read any Elite Dangerous JSON state file by filename."""
    if not filename.lower().endswith(".json"):
        filename += ".json"
    safe = Path(filename).name
    value = read_json_file(safe)
    return {"filename": safe, "data": value}


@mcp.tool()
def get_recent_events(count: int = 250) -> list:
    """Get recent raw journal events. Timestamps and all original journal fields are preserved."""
    return recent_events(max(1, min(count, 5000)))


@mcp.tool()
def search_journal(
    query: str = "",
    event: str = "",
    start_time: str = "",
    end_time: str = "",
    limit: int = 200,
) -> list:
    """Search ALL indexed current and historical Elite journals."""
    return search_events(query, event, start_time, end_time, limit)


@mcp.tool()
def get_latest_journal_event(event: str) -> dict:
    """Get the newest historical event of an exact Elite journal event type."""
    return latest_event(event) or {}


@mcp.tool()
def get_history_summary() -> dict:
    """Get statistics about the complete local journal-history index."""
    return history_summary()


@mcp.tool()
def get_raw_history_page(before_id: int = 0, limit: int = 500) -> dict:
    """Page through every raw journal event, newest first."""
    return get_event_page(None if before_id <= 0 else before_id, limit)


@mcp.tool()
def get_current_system_map_simple() -> str:
    """Get the current system as a compact body tree with body types and arrival distances."""
    result = get_current_system_map(include_full=False)
    return result["simple_text"] if result else "No saved current-system map is available."


@mcp.tool()
def get_current_system_map_full() -> str:
    """Get the current system as a detailed tree containing all saved scan and signal data."""
    result = get_current_system_map(include_full=True)
    return result["full_text"] if result else "No saved current-system map is available."


@mcp.tool()
def list_saved_system_maps(query: str = "", limit: int = 100) -> list:
    """List saved historical system maps, optionally filtering by part of a system name."""
    return list_system_maps(query, limit)


@mcp.tool()
def get_saved_system_map_simple(system: str) -> str:
    """Get a compact saved map by exact system name or numeric SystemAddress."""
    result = get_system_map(system, include_full=False)
    return result["simple_text"] if result else f"No saved system map found for: {system}"


@mcp.tool()
def get_saved_system_map_full(system: str) -> str:
    """Get a detailed saved map by exact system name or numeric SystemAddress."""
    result = get_system_map(system, include_full=True)
    return result["full_text"] if result else f"No saved system map found for: {system}"


modules.register_mcp_tools(mcp)


class _SuccessfulMCPRequests(logging.Filter):
    def filter(self, record):
        # Uvicorn access records contain client, method, path, HTTP version, status.
        args = record.args
        return not (isinstance(args, tuple) and len(args) == 5
                    and args[1] == "POST" and args[2] == "/mcp"
                    and args[4] in (200, 202, 204))


if __name__ == "__main__":
    logging.getLogger("uvicorn.access").addFilter(_SuccessfulMCPRequests())
    mcp.run(transport="streamable-http")
