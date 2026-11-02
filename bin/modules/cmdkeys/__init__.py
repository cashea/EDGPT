"""Command keys: .binds parser, state-reactive key macros, SendInput behind a local gate.

Safety model
- Injection is OFF when the server starts; a local POST to /cmdkeys/enable turns it on
  for this process only. Nothing is persisted.
- Each macro is opt-in (``enabled`` in macros.json), capped at 12 steps / 30 s, every
  wait has a timeout, only one macro runs at a time, CANCEL aborts immediately, and
  keys are sent only while EliteDangerous64.exe owns the foreground window.
- MCP tools can list macros and bindings. They cannot run, enable or edit anything.
- Frontier's stance on input automation is not clearly stated; the user accepts the risk.
"""
import threading

from . import binds as B
from . import macros as M
from .page import PAGE

NAME = "cmdkeys"
_lock = threading.RLock()  # _engine() -> _watcher() re-enters
_runtime = {"watcher": None, "engine": None, "enabled": False}


def _status_flags():
    from current_state import read_json_file
    from status_flags import decode_status_flags
    status = decode_status_flags(read_json_file("Status.json")) or {}
    flags = set(status.get("FlagsDecoded", [])) | set(status.get("Flags2Decoded", []))
    focus = M.gui_focus_flag(status.get("GuiFocus"))
    if focus:
        flags.add(focus)
    return flags


def _watcher():
    with _lock:
        if _runtime["watcher"] is None:
            _runtime["watcher"] = B.BindsWatcher()
        return _runtime["watcher"]


def _engine():
    with _lock:
        if _runtime["engine"] is None:
            from .sendinput import Win32Sender, game_focused
            from .screen import probe_game
            _runtime["engine"] = M.MacroEngine(Win32Sender(), _status_flags, game_focused, _watcher().load,
                                               screen_probe=probe_game)
        return _runtime["engine"]


def _param(qs, key):
    value = (qs or {}).get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    return value or None


def _find_macro(name):
    for macro in M.load_macros():
        if macro.get("name") == name:
            return macro
    return None


# ---- GET -------------------------------------------------------------------

def list_macros(qs=None):
    """Macros with validation problems and unbound actions, plus binds and engine state."""
    binding = _watcher().load()
    engine = _runtime["engine"]
    return {
        "module": NAME,
        "injection_enabled": bool(_runtime["enabled"]),
        "running": engine.current if engine else None,
        "last_result": engine.last_result if engine else None,
        "binds": _watcher().summary(),
        "macros_file": str(M.macros_path()),
        "macros": [M.describe_macro(m, binding) for m in M.load_macros()],
        "limits": {"max_steps": M.MAX_STEPS, "max_runtime_ms": M.MAX_RUNTIME_MS, "max_wait_ms": M.MAX_WAIT_MS},
        "flags": sorted(_status_flags()),
    }


def bindings(qs=None):
    """Parsed .binds. ``?action=<Name>`` returns one action; otherwise every bound action."""
    binding = _watcher().load() or {}
    actions = binding.get("actions", {})
    wanted = _param(qs, "action")
    if wanted:
        chord = B.keyboard_chord(binding, wanted) if actions.get(wanted) else None
        return {"module": NAME, "action": wanted, "slots": actions.get(wanted),
                "keyboard": chord, "keys": B.chord_keys(chord) if chord else None}
    return {"module": NAME, "file": _watcher().summary(), "actions": actions}


def page(qs=None):
    """Commands page: macro buttons, live flags, injection switch, CANCEL."""
    from modules import Html
    return Html(PAGE)


# ---- POST (local user actions only) ----------------------------------------

def enable(qs=None, body=None):
    """``{"enabled": true|false}``; session-scoped master switch for key injection."""
    value = (body or {}).get("enabled")
    if not isinstance(value, bool):
        raise ValueError("body must be {\"enabled\": true|false}")
    _runtime["enabled"] = value
    if not value and _runtime["engine"]:
        _runtime["engine"].cancel()
    return {"module": NAME, "injection_enabled": value}


def run(qs=None, body=None):
    """``{"macro": "<name>", "dry_run": false}``. Blocks until the macro finishes (<= 30 s)."""
    body = body or {}
    name = body.get("macro")
    macro = _find_macro(name) if isinstance(name, str) else None
    if macro is None:
        raise ValueError(f"unknown macro {name!r}")
    dry_run = bool(body.get("dry_run", False))
    if not dry_run:
        if not _runtime["enabled"]:
            return {"ok": False, "macro": name, "error": "key injection is disabled; POST /cmdkeys/enable first"}
        if not macro.get("enabled", False):
            return {"ok": False, "macro": name, "error": "macro is disabled in macros.json"}
    return {"module": NAME, **_engine().run(macro, dry_run=dry_run)}


def cancel(qs=None, body=None):
    engine = _runtime["engine"]
    return {"module": NAME, **(engine.cancel() if engine else {"cancelled": False, "macro": None})}


# ---- MCP (read-only) ---------------------------------------------------------

def get_command_macros() -> dict:
    """List the commander's key macros (name, steps, enabled, validation problems) and whether
    local key injection is currently enabled. Read-only: macros can only be run by the user
    from the local Commands page or hotkeys, never through MCP."""
    return list_macros()


def get_key_binding(action: str) -> dict:
    """Resolve one Elite Dangerous bindings action (e.g. 'LandingGearToggle') to the commander's
    current keys from their .binds file. Read-only."""
    return bindings({"action": action})


HTTP_ROUTES = {"/cmdkeys": list_macros, "/cmdkeys/binds": bindings, "/cmdkeys/page": page}
HTTP_POST_ROUTES = {"/cmdkeys/enable": enable, "/cmdkeys/run": run, "/cmdkeys/cancel": cancel}
MCP_TOOLS = [get_command_macros, get_key_binding]
