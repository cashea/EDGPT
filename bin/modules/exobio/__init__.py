"""Exobiology tracker: genera on body, sample progress, payout estimate, species prediction.

Reads EDGPT's persistent system map (which already retains Scan, SAASignalsFound,
FSSBodySignals and ScanOrganic per body) plus the normalized state. Reference
data and attribution: see NOTICE.md. No I/O at import time.
"""
from . import reducer as R

NAME = "exobio"


def _current_map(sync_history=True):
    from system_map_store import get_current_system_map
    result = get_current_system_map(include_model=True, sync_history=sync_history)
    return (result or {}).get("model")


def _saved_map(system):
    from system_map_store import get_system_map
    result = get_system_map(system, include_model=True)
    return (result or {}).get("model")


def _map_for(qs):
    """Saved map when ``?system=<name|address>`` is given, else the current system."""
    system = _param(qs, "system")
    return _saved_map(system) if system else _current_map()


def _state():
    from current_state import build_state
    return build_state()


def _recent_sales(limit=50):
    from history_store import search_events
    return search_events(event="SellOrganicData", limit=limit, newest_first=True)


def _param(qs, key):
    value = (qs or {}).get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    return value or None


def status(qs=None):
    """Current body (or ``?body=<name|id>``) plus a system overview and recent sales."""
    state = _state()
    model = _current_map(sync_history=False)
    node = R.find_node(model, _param(qs, "body") or state.get("body"))
    sales = _recent_sales()
    return {
        "module": NAME,
        "status": "ok" if model else "no_system_map",
        "system": state.get("system"),
        "current_body": state.get("body"),
        "body": R.reduce_body(node, model) if node else None,
        "overview": R.reduce_system(model),
        "last_sale": sales[0] if sales else None,
        "sales_recent": R.summarize_sales(sales),
    }


def body(qs=None):
    """One body's exobiology detail. ``?body=<name|id>`` required."""
    wanted = _param(qs, "body")
    if not wanted:
        raise ValueError("body query parameter is required")
    model = _map_for(qs)
    node = R.find_node(model, wanted)
    if not node:
        return {"module": NAME, "body": None,
                "error": f"No body {wanted!r} in the {'requested' if _param(qs, 'system') else 'current'} system map."}
    return {"module": NAME, "body": R.reduce_body(node, model)}


def overview(qs=None):
    """All bodies with biology in the current system, or ``?system=<name|address>``."""
    return {"module": NAME, "overview": R.reduce_system(_map_for(qs))}


def get_exobio_status() -> dict:
    """Exobiology right now: genera on the current body, samples taken (0-3 each), confirmed
    species values, predicted species where unsampled, bodies with biology in this system,
    pending (analysed, unsold) credits and recent SellOrganicData totals."""
    return status()


def get_exobio_body(body_name: str, system: str = "") -> dict:
    """Exobiology detail for one body by name (e.g. 'Synuefe AB-C 1 a') or BodyID: conditions,
    genera, sample progress, values, candidate species. Current system unless ``system``
    names a saved system (name or SystemAddress)."""
    return body({"body": body_name, "system": system})


def get_exobio_system_overview(system: str = "") -> dict:
    """Every body with biological signals or samples in the current system (or a saved
    ``system`` by name/SystemAddress), with progress and pending credit value. Use it to
    pick the next body to land on."""
    return overview({"system": system})


HTTP_ROUTES = {"/exobio": status, "/exobio/body": body, "/exobio/overview": overview}
MCP_TOOLS = [get_exobio_status, get_exobio_body, get_exobio_system_overview]
