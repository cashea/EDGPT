"""Versioned, payload-free diagnostics. Probes never trigger ingestion."""
import json
from contextlib import closing
import os
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.5.0-beta"
STARTED = time.monotonic()
STALE_SECONDS = 3600
_observations = {}
_lock = threading.Lock()
ENDPOINTS = ["/", "/state", "/health", "/capabilities", "/version", "/history/summary",
             "/history/recent", "/history/search", "/system-map/simple", "/system-map/full",
             "/system-maps", "/system-maps/get", "/system-map/summary", "/sessions", "/sessions/current", "/sessions/get"]
TOOLS = ["get_elite_state", "get_full_loadout", "get_navroute", "get_status",
         "list_elite_live_files", "get_elite_live_file", "get_recent_events", "search_journal",
         "get_latest_journal_event", "get_history_summary", "get_raw_history_page",
         "get_current_system_map_simple", "get_current_system_map_full", "list_saved_system_maps",
         "get_saved_system_map_simple", "get_saved_system_map_full", "get_edgpt_health",
         "get_edgpt_capabilities", "get_current_session_summary", "list_game_sessions", "get_game_session",
         "get_current_system_summary", "get_saved_system_summary"]

# Companion modules (bin/modules) extend the contract additively.
import modules as _modules
ENDPOINTS += sorted(_modules.http_routes()) + sorted(_modules.http_post_routes())
TOOLS += [name for entry in _modules.module_info() for name in entry["mcp_tools"]]


def version():
    return {"application": "EDGPT", "version": VERSION, "api_schema_version": 1,
            "health_schema_version": 1, "capabilities_schema_version": 1}


def integrations():
    try:
        config = json.loads(Path(os.environ.get("EDGPT_CONFIG_FILE", "data/config.json")).read_text(encoding="utf-8"))
        return {"github": bool(config.get("github", {}).get("enabled", False)),
                "tunnel": bool(config.get("openai", {}).get("enabled", False))}
    except (OSError, ValueError):
        return {"github": False, "tunnel": False}


def capabilities():
    return {**version(), "http_endpoints": ENDPOINTS, "mcp_tools": TOOLS,
            "state_models": ["current_state", "journal_history", "system_maps", "sessions", "system_summaries"],
            "system_summary_schema_version": 2,
            "session_schema_version": 1,
            "limits": {"events": 5000, "saved_system_maps": 1000, "sessions": 100, "session_activity_examples": 20},
            "response_profiles": {"state": ["compact", "history_summary", "recent_events", "loadout", "live_files"],
                                  "system_maps": ["simple", "full", "summary"]},
            "optional_integrations": integrations(), "transports": ["http", "mcp_streamable_http"]}


def probe_service(name):
    if name == "state_server":
        url = "http://127.0.0.1:" + os.environ.get("EDGPT_STATE_PORT", "8080") + "/version"
        request = urllib.request.Request(url)
    else:
        request = urllib.request.Request("http://127.0.0.1:" + os.environ.get("EDGPT_MCP_PORT", "8000") + "/mcp", data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "edgpt-health", "version": VERSION}}}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(request, timeout=2) as response:
        value = json.load(response)
    if name == "state_server":
        if value.get("application") != "EDGPT":
            raise ValueError("Unexpected service")
    elif not value.get("result", {}).get("protocolVersion"):
        raise ValueError("MCP initialization failed")


def heartbeat(component, status, error=None):
    """Persist only fixed diagnostic messages, never exception text or payloads."""
    directory = Path(os.environ.get("EDGPT_DATA_DIR", "data"))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (component + "_health.json")
    old = {}
    try:
        old = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    value = {"status": status, "observed_at": time.time(),
             "last_success": time.time() if status == "ready" else old.get("last_success"),
             "last_error": error or old.get("last_error")}
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(target)


def health(origin="state_server"):
    import history_store as history
    import system_map_store as maps
    now = time.time()
    components = {}

    def record(name, status="ready", error=None, **details):
        with _lock:
            previous = _observations.setdefault(name, {"last_success": None, "last_error": None})
            if status == "ready":
                previous["last_success"] = now
            if error:
                previous["last_error"] = error
            components[name] = {"status": status, **previous, **details}

    try:
        with os.scandir(history.ELITE_DIR) as entries:
            journals = [Path(entry.path) for entry in entries if entry.name.startswith("Journal.") and entry.name.endswith(".log")]
        for path in journals:
            with path.open("rb"):
                pass
        record("journal_directory", readable=True, configured=True)
    except OSError:
        journals = []
        record("journal_directory", "error", "Journal directory is missing or unreadable; check Settings.", readable=False, configured=True)

    high = 0
    try:
        indexer = json.loads((history.DATA_DIR / "indexer_health.json").read_text(encoding="utf-8"))
        # The worker refreshes this between passes; a long initial backfill can
        # legitimately take longer than a heartbeat interval.
        indexing = indexer.get("status") == "indexing" and now - indexer["observed_at"] < 3600
    except (OSError, ValueError, KeyError):
        indexer = {}
        indexing = False
    try:
        with closing(sqlite3.connect(history.DB_PATH.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)) as db:
            count, high, latest = db.execute("SELECT COUNT(*), COALESCE(MAX(id),0), MAX(timestamp) FROM events").fetchone()
            journal_states = {row[0]: (row[1], row[2]) for row in db.execute(
                "SELECT journal_file, size, mtime FROM journal_state")}
        # A checked file may end with a line awaiting its newline. Compare the
        # observed file state, not the offset of the last complete line.
        pending = False
        for path in journals:
            stat = path.stat()
            if journal_states.get(path.name) != (stat.st_size, stat.st_mtime):
                pending = True
                break
        age = None
        if latest:
            try:
                age = max(0, now - datetime.fromisoformat(latest.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
            except ValueError:
                latest = None
        status = "indexing" if pending else "stale" if age is None or age > STALE_SECONDS else "ready"
        record("history", status, available=True, event_count=count, high_water_mark=high,
               latest_event_timestamp=latest, latest_event_age_seconds=age)
    except (sqlite3.Error, OSError):
        record("history", "error", "History database unavailable; check data directory permissions and restart.", available=False)

    try:
        with closing(sqlite3.connect(maps.MAP_DB_PATH.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)) as db:
            count = db.execute("SELECT COUNT(*) FROM system_maps").fetchone()[0]
            meta = dict(db.execute("SELECT key,value FROM map_meta"))
        cursor = int(meta.get("history_event_id", 0))
        pending = cursor != high or int(meta.get("schema_version", 0)) != maps.MAP_SCHEMA_VERSION
        record("system_maps", "indexing" if pending else "ready", available=True,
               map_count=count, high_water_mark=cursor, backfill_pending=pending)
    except (sqlite3.Error, OSError, ValueError):
        record("system_maps", "error", "System-map database unavailable; check data directory permissions and restart.", available=False)

    for name in ("state_server", "mcp"):
        try:
            if name != origin:
                probe_service(name)
            record(name)
        except Exception:
            record(name, "error", name + " endpoint did not respond correctly; restart the bridge.")

    for name in ("history", "system_maps"):
        if indexing:
            components[name]["status"] = "indexing"
        if indexer:
            components[name]["last_success"] = indexer.get("last_success")
            if indexer.get("last_error"):
                components[name]["last_error"] = indexer["last_error"]
            if indexer.get("status") == "error":
                components[name]["status"] = "error"

    for name, enabled in integrations().items():
        if not enabled:
            record(name, "disabled")
            continue
        try:
            value = json.loads((history.DATA_DIR / (name + "_health.json")).read_text(encoding="utf-8"))
            fresh = now - value["observed_at"] < 30
            record(name, value["status"] if fresh else "degraded",
                   value.get("last_error") if fresh else "Integration heartbeat expired; restart the bridge.")
            components[name]["last_success"] = value.get("last_success")
        except (OSError, ValueError, KeyError, TypeError):
            record(name, "degraded", "Integration has no health report; check launcher settings and logs.")
    statuses = [c["status"] for c in components.values()]
    overall = next((s for s in ("error", "degraded", "indexing", "stale") if s in statuses), "ready")
    return {**version(), "status": overall, "uptime_seconds": round(time.monotonic() - STARTED, 3),
            "checked_at": now, "stale_after_seconds": STALE_SECONDS, "components": components}


def _index_failure(stage, error):
    """Explain failures without exposing exception text, paths or journal data."""
    code = getattr(error, "sqlite_errorcode", 0) & 0xff
    if isinstance(error, sqlite3.OperationalError) and code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        detail = "Database is busy or locked; close duplicate EDGPT instances. The indexer will retry."
    elif isinstance(error, PermissionError) or code in (sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR):
        detail = "Database or files could not be accessed; check data directory permissions and free disk space."
    elif isinstance(error, sqlite3.OperationalError):
        detail = "Database operation failed; check database integrity and the EDGPT version."
    elif isinstance(error, sqlite3.DatabaseError):
        detail = "Database could not be read; check database integrity before rebuilding from journals."
    elif isinstance(error, (ValueError, TypeError, OverflowError)):
        detail = "An indexed value could not be processed; check journal data and the EDGPT version."
    else:
        detail = "Unexpected indexing failure; check the EDGPT version. The indexer will retry."
    return stage + " index update failed. " + detail


def _index_once():
    from history_store import sync_journals
    from system_map_store import sync_system_maps
    stage = "History"
    try:
        heartbeat("indexer", "indexing")
        sync_journals()
        stage = "System-map"
        sync_system_maps(sync_history=False)
        heartbeat("indexer", "ready")
    except Exception as error:
        message = _index_failure(stage, error)
        try:
            heartbeat("indexer", "error", message)
        except OSError:
            message += " Diagnostic report could not be written; check data directory permissions."
        return message
    return None


def start_indexer():

    def run():
        previous_error = None
        while True:
            error = _index_once()
            if error and error != previous_error:
                print("[INDEXER] " + error, flush=True)
            elif previous_error and not error:
                print("[INDEXER] Index update recovered.", flush=True)
            previous_error = error
            time.sleep(5)
    threading.Thread(target=run, daemon=True).start()
