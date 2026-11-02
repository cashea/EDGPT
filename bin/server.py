from diagnostics import health, capabilities, version, start_indexer
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from history_store import history_summary, recent_events, search_events, latest_state_events
from current_state import build_state
from map_page import render_map_page
from system_map_store import get_current_system_map, get_system_map, list_system_maps
from session_store import get_current_session_summary, get_game_session, list_game_sessions
from system_map_store import get_system_summary
import modules

if __name__ == "__main__" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if __name__ == "__main__" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_ELITE_DIR = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
ELITE_DIR = Path(os.environ.get("ELITE_JOURNAL_DIR", str(DEFAULT_ELITE_DIR))).expanduser()
PORT = int(os.environ.get("EDGPT_STATE_PORT", "8080"))

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def current_page_map():
    events = latest_state_events(("Location", "FSDJump", "CarrierJump"))
    location = next((event for event in reversed(events)
                     if event.get("SystemAddress") is not None), None)
    if location is None:
        return get_current_system_map(include_model=True)
    return get_system_map(str(location["SystemAddress"]), include_model=True) or {
        "system_name": location.get("StarSystem", "Unknown system"),
        "system_address": location["SystemAddress"],
        "last_updated": location.get("timestamp"),
        "simple_text": "No bodies recorded for this system yet. Scan bodies to populate the map.",
    }


def parse_state_options(query):
    """Parse strict, independent /state output-selection options."""

    def optional_bool(name):
        if name not in query:
            return False
        values = query[name]
        if len(values) != 1:
            raise ValueError(f"{name} must be specified once.")
        value = values[0].strip().lower()
        if value in TRUE_VALUES:
            return True
        if value in FALSE_VALUES:
            return False
        raise ValueError(f"{name} must be true or false.")

    recent_event_count = None
    if "recent_events" in query:
        values = query["recent_events"]
        if len(values) != 1:
            raise ValueError("recent_events must be specified once.")
        try:
            recent_event_count = int(values[0].strip())
        except (TypeError, ValueError):
            raise ValueError("recent_events must be an integer from 0 to 5000.") from None
        if not 0 <= recent_event_count <= 5000:
            raise ValueError("recent_events must be an integer from 0 to 5000.")

    return {
        "include_history_summary": optional_bool("history_summary"),
        "recent_event_count": recent_event_count,
        "include_loadout": optional_bool("loadout"),
        "include_live_files": optional_bool("live_files"),
    }


def send_json(handler, value, code=200):
    body = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query, keep_blank_values=True)

        if path in ("/map", "/map/export"):
            exporting = path == "/map/export"
            system = qs.get("system", [None])[0]
            code, message, result = 200, None, None
            if (any(key != "system" or len(values) != 1 for key, values in qs.items())
                    or (system is not None and (not system.isascii() or not system.isdecimal()
                        or len(system) > 19 or int(system) > 9223372036854775807))):
                code, message = 400, "Enter a numeric SystemAddress between 0 and 9223372036854775807."
            else:
                result = current_page_map() if system is None else get_system_map(system, include_model=True)
                if result is None and system is not None:
                    code, message = 404, "No saved map for this system ID. Only systems recorded in your journals are available."
            body = render_map_page(result, system=system, message=message,
                                   export=exporting and code == 200).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            if exporting and code == 200:
                address = (result or {}).get("system_address")
                identifier = str(address if address is not None else system or "current")
                if not identifier.isascii() or not identifier.isdecimal():
                    identifier = "current"
                self.send_header("Content-Disposition", f'attachment; filename="elite-map-{identifier}.html"')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/health":
            return send_json(self, health())
        if path == "/capabilities":
            return send_json(self, capabilities())
        if path == "/version":
            return send_json(self, version())

        if path == "/state":
            try:
                options = parse_state_options(qs)
            except ValueError as exc:
                return send_json(self, {"error": str(exc)}, 400)
            return send_json(self, build_state(**options))

        if path in ("/sessions", "/sessions/current", "/sessions/get"):
            try:
                allowed = {"/sessions": {"limit", "before", "start", "end"},
                           "/sessions/current": set(), "/sessions/get": {"id"}}[path]
                if any(key not in allowed or len(values) != 1 for key, values in qs.items()):
                    raise ValueError("Unknown or repeated session query parameter.")
                if path == "/sessions/current":
                    result = get_current_session_summary()
                elif path == "/sessions/get":
                    result = get_game_session(qs.get("id", [""])[0])
                    if not result:
                        return send_json(self, {"error": "Session not found."}, 404)
                else:
                    result = list_game_sessions(qs.get("limit", ["20"])[0], qs.get("before", ["0"])[0],
                                                qs.get("start", [""])[0], qs.get("end", [""])[0])
            except ValueError as exc:
                return send_json(self, {"error": str(exc)}, 400)
            return send_json(self, result)

        if path == "/history/summary":
            return send_json(self, history_summary())

        if path == "/history/recent":
            try:
                count = int(qs.get("count", ["250"])[0])
            except Exception:
                count = 250
            return send_json(self, recent_events(count))

        if path == "/history/search":
            query = qs.get("q", [""])[0]
            event = qs.get("event", [""])[0]
            start = qs.get("start", [""])[0]
            end = qs.get("end", [""])[0]
            try:
                limit = int(qs.get("limit", ["200"])[0])
            except Exception:
                limit = 200
            return send_json(self, search_events(query, event, start, end, limit))

        if path == "/system-map/summary":
            if any(key != "system" or len(values) != 1 or not values[0].strip()
                   for key, values in qs.items()):
                return send_json(self, {"error": "Specify system once as a name or SystemAddress."}, 400)
            return send_json(self, get_system_summary(qs.get("system", [None])[0]) or {})

        if path == "/system-map/simple":
            return send_json(self, get_current_system_map(include_full=False) or {})

        if path == "/system-map/full":
            return send_json(self, get_current_system_map(include_full=True) or {})

        if path == "/system-maps":
            query = qs.get("q", [""])[0]
            try:
                limit = int(qs.get("limit", ["100"])[0])
            except Exception:
                limit = 100
            return send_json(self, list_system_maps(query, limit))

        if path == "/system-maps/get":
            identifier = qs.get("system", [""])[0]
            include_full = qs.get("detail", ["simple"])[0].lower() == "full"
            result = get_system_map(identifier, include_full)
            if result is None:
                return send_json(self, {"error": "Saved system map not found."}, 404)
            return send_json(self, result)

        if path == "/":
            html = """<!DOCTYPE html><html><head><meta charset='UTF-8'><title>EDGPT Full Context</title>
<style>body{background:#111;color:#eee;font-family:Consolas,monospace;margin:30px}h1{color:#ff9500}pre{background:#191919;padding:20px;border-radius:8px;white-space:pre-wrap}</style></head>
<body><h1>EDGPT Full Context</h1><p>Current state + complete indexed journal history.</p><p><a href='/map' style='color:#ff9500'>Live system map</a></p><pre id='data'>Loading...</pre>
<script>async function update(){try{const r=await fetch('/state?time='+Date.now());const d=await r.json();document.getElementById('data').textContent=JSON.stringify(d,null,2)}catch(e){document.getElementById('data').textContent='ERROR: '+e}}update();setInterval(update,5000)</script></body></html>"""
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        module_handler = modules.http_route(path)
        if module_handler is not None:
            try:
                return send_json(self, module_handler(qs))
            except ValueError as exc:
                return send_json(self, {"error": str(exc)}, 400)

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    print("\n======================================")
    print(" EDGPT FULL CONTEXT SERVER")
    print("======================================\n")
    print("Elite folder:")
    print(ELITE_DIR)
    start_indexer()
    print(f"\nDashboard: http://localhost:{PORT}")
    print(f"Raw API:   http://localhost:{PORT}/state")
    print(f"History:   http://localhost:{PORT}/history/summary\n")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
