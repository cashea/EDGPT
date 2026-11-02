"""Macro model, validation, storage and a single-owner execution engine. No Win32 here."""
import json
import os
import threading
import time
from pathlib import Path

from . import binds as B

MAX_STEPS = 12
MAX_RUNTIME_MS = 30_000
MAX_WAIT_MS = 10_000
DEFAULT_HOLD_MS = 60
DEFAULT_GAP_MS = 120   # pause after each press so the game registers consecutive keys
POLL_MS = 50
MACROS_FILE_NAME = "macros.json"

# Status.json GuiFocus -> pseudo flag "GuiFocus:<name>" usable in if_flag / wait_until.
GUI_FOCUS_FLAGS = ("NoFocus", "InternalPanel", "ExternalPanel", "CommsPanel", "RolePanel",
                   "StationServices", "GalaxyMap", "SystemMap", "Orrery", "FSS", "DSS", "Codex")


def gui_focus_flag(value):
    """``"GuiFocus:StationServices"`` for 5, ``None`` for unknown or non-integer values."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(GUI_FOCUS_FLAGS):
        return None
    return "GuiFocus:" + GUI_FOCUS_FLAGS[value]


DEFAULT_MACROS = [
    {"name": "Gear down", "enabled": False, "description": "Lower landing gear if it is up.",
     "steps": [{"if_flag": "LandingGearDown", "is": False, "press": "LandingGearToggle"}]},
    {"name": "Gear up", "enabled": False, "description": "Raise landing gear if it is down.",
     "steps": [{"if_flag": "LandingGearDown", "is": True, "press": "LandingGearToggle"}]},
    {"name": "Hardpoints out", "enabled": False, "description": "Deploy hardpoints if retracted.",
     "steps": [{"if_flag": "HardpointsDeployed", "is": False, "press": "DeployHardpointToggle"}]},
    {"name": "Hardpoints in", "enabled": False, "description": "Retract hardpoints if deployed.",
     "steps": [{"if_flag": "HardpointsDeployed", "is": True, "press": "DeployHardpointToggle"}]},
    {"name": "Lights on", "enabled": False, "description": "Ship lights on if off.",
     "steps": [{"if_flag": "LightsOn", "is": False, "press": "ShipSpotLightToggle"}]},
    {"name": "Lights off", "enabled": False, "description": "Ship lights off if on.",
     "steps": [{"if_flag": "LightsOn", "is": True, "press": "ShipSpotLightToggle"}]},
    {"name": "Scoop out", "enabled": False, "description": "Deploy cargo scoop if retracted.",
     "steps": [{"if_flag": "CargoScoopDeployed", "is": False, "press": "ToggleCargoScoop"}]},
    {"name": "Scoop in", "enabled": False, "description": "Retract cargo scoop if deployed.",
     "steps": [{"if_flag": "CargoScoopDeployed", "is": True, "press": "ToggleCargoScoop"}]},
    {"name": "Prepare to land", "enabled": False,
     "description": "Retract hardpoints, lights on, gear down, waiting for each state change.",
     "steps": [{"if_flag": "HardpointsDeployed", "is": True, "press": "DeployHardpointToggle"},
               {"wait_until": "HardpointsDeployed", "is": False, "timeout_ms": 4000},
               {"if_flag": "LightsOn", "is": False, "press": "ShipSpotLightToggle"},
               {"if_flag": "LandingGearDown", "is": False, "press": "LandingGearToggle"},
               {"wait_until": "LandingGearDown", "is": True, "timeout_ms": 4000}]},
    {"name": "Open Starport Services", "enabled": False,
     "description": "Docked, no panel open: park the station menu on its bottom row (it clamps, never wraps), "
                    "go up two rows to STARPORT SERVICES, select, then confirm GuiFocus=StationServices. "
                    "Never touches AUTO LAUNCH or DISEMBARK. Leave with UI_Back.",
     "steps": [{"wait_until": "Docked", "timeout_ms": 100},
               {"wait_until": "GuiFocus:NoFocus", "timeout_ms": 100},
               {"press": "UI_Down"}, {"press": "UI_Down"}, {"press": "UI_Down"}, {"press": "UI_Down"},
               {"press": "UI_Up"}, {"press": "UI_Up"},
               {"press": "UI_Select"},
               {"wait_until": "GuiFocus:StationServices", "timeout_ms": 5000}]},
    {"name": "Close Starport Services", "enabled": False,
     "description": "Leave Station Services from its root or one or two pages deep: UI_Back up to three "
                    "times, each only while GuiFocus is still StationServices, then confirm the cockpit view.",
     "steps": [{"wait_until": "GuiFocus:StationServices", "timeout_ms": 100},
               {"if_flag": "GuiFocus:StationServices", "is": True, "press": "UI_Back"}, {"wait": 600},
               {"if_flag": "GuiFocus:StationServices", "is": True, "press": "UI_Back"}, {"wait": 600},
               {"if_flag": "GuiFocus:StationServices", "is": True, "press": "UI_Back"},
               {"wait_until": "GuiFocus:NoFocus", "timeout_ms": 3000}]},
    {"name": "Open galaxy map", "enabled": False,
     "description": "From the cockpit view, press GalaxyMapOpen and confirm GuiFocus=GalaxyMap.",
     "steps": [{"wait_until": "GuiFocus:NoFocus", "timeout_ms": 100},
               {"press": "GalaxyMapOpen"},
               {"wait_until": "GuiFocus:GalaxyMap", "timeout_ms": 8000}]},
    {"name": "Close galaxy map", "enabled": False,
     "description": "With the galaxy map open, press GalaxyMapOpen again (it toggles) and confirm the cockpit view.",
     "steps": [{"wait_until": "GuiFocus:GalaxyMap", "timeout_ms": 100},
               {"press": "GalaxyMapOpen"},
               {"wait_until": "GuiFocus:NoFocus", "timeout_ms": 5000}]},
]


def data_dir():
    return Path(os.environ.get("EDGPT_DATA_DIR") or Path(__file__).resolve().parents[3] / "data")


def macros_path():
    return data_dir() / MACROS_FILE_NAME


def validate_macro(macro):
    """Return a list of problems (empty when valid)."""
    problems = []
    if not isinstance(macro, dict) or not str(macro.get("name", "")).strip():
        return ["macro needs a name"]
    steps = macro.get("steps")
    if not isinstance(steps, list) or not steps:
        return ["macro needs a non-empty steps list"]
    if len(steps) > MAX_STEPS:
        problems.append(f"too many steps ({len(steps)} > {MAX_STEPS})")
    budget = 0
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            problems.append(f"step {index}: not an object")
            continue
        kinds = [k for k in ("press", "wait", "wait_until") if k in step]
        if len(kinds) != 1:
            problems.append(f"step {index}: exactly one of press/wait/wait_until required")
            continue
        kind = kinds[0]
        if kind == "press":
            if not isinstance(step["press"], str) or not step["press"]:
                problems.append(f"step {index}: press needs an action name")
            hold = step.get("hold_ms", DEFAULT_HOLD_MS)
            if not isinstance(hold, int) or not 0 <= hold <= 2000:
                problems.append(f"step {index}: hold_ms must be 0-2000")
            gap = step.get("gap_ms", DEFAULT_GAP_MS)
            if not isinstance(gap, int) or not 0 <= gap <= 2000:
                problems.append(f"step {index}: gap_ms must be 0-2000")
            budget += (hold if isinstance(hold, int) else 0) + (gap if isinstance(gap, int) else 0) + 50
        elif kind == "wait":
            ms = step["wait"]
            if not isinstance(ms, int) or not 0 <= ms <= MAX_WAIT_MS:
                problems.append(f"step {index}: wait must be 0-{MAX_WAIT_MS} ms")
            budget += ms if isinstance(ms, int) else 0
        else:
            timeout = step.get("timeout_ms")
            if not isinstance(step["wait_until"], str) or not step["wait_until"]:
                problems.append(f"step {index}: wait_until needs a flag name")
            if not isinstance(timeout, int) or not 1 <= timeout <= MAX_WAIT_MS:
                problems.append(f"step {index}: wait_until needs timeout_ms 1-{MAX_WAIT_MS}")
            if "is" in step and not isinstance(step["is"], bool):
                problems.append(f"step {index}: 'is' must be true/false")
            budget += timeout if isinstance(timeout, int) else 0
        if "if_flag" in step and (not isinstance(step["if_flag"], str) or not isinstance(step.get("is", True), bool)):
            problems.append(f"step {index}: if_flag needs a flag name and boolean 'is'")
    if budget > MAX_RUNTIME_MS:
        problems.append(f"worst-case runtime {budget} ms exceeds {MAX_RUNTIME_MS} ms")
    return problems


def load_macros(path=None):
    """Macros from disk; writes the defaults (all disabled) when the file is missing."""
    path = Path(path or macros_path())
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"macros": DEFAULT_MACROS}, indent=2), encoding="utf-8")
        except OSError:
            return [dict(m) for m in DEFAULT_MACROS]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        macros = data.get("macros", []) if isinstance(data, dict) else data
        return [m for m in macros if isinstance(m, dict)]
    except (OSError, ValueError):
        return []


def save_macros(macros, path=None):
    path = Path(path or macros_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"macros": macros}, indent=2), encoding="utf-8")


def describe_macro(macro, binding=None):
    """Macro plus validation problems and, when a binding is given, resolved keys per press step."""
    out = {"name": macro.get("name"), "enabled": bool(macro.get("enabled", False)),
           "description": macro.get("description", ""), "steps": macro.get("steps", []),
           "problems": validate_macro(macro), "unbound_actions": []}
    if binding:
        for step in macro.get("steps", []):
            action = step.get("press") if isinstance(step, dict) else None
            if action and B.keyboard_chord(binding, action) is None:
                out["unbound_actions"].append(action)
    return out


class FakeSender:
    """Records chords instead of injecting them (tests, dry runs)."""

    def __init__(self):
        self.pressed = []

    def press_chord(self, keys, hold_ms=DEFAULT_HOLD_MS):
        self.pressed.append((list(keys), hold_ms))

    def release_all(self, keys):
        pass


class MacroEngine:
    """Runs one macro at a time with cancellation, flag waits, focus guard and runtime cap."""

    def __init__(self, sender, status_flags, focus_check, binding_provider, sleep=time.sleep, clock=time.monotonic):
        self.sender = sender
        self.status_flags = status_flags          # () -> set of active flag names
        self.focus_check = focus_check            # () -> bool
        self.binding_provider = binding_provider  # () -> parsed binding dict
        self.sleep = sleep
        self.clock = clock
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.current = None
        self.last_result = None

    def cancel(self):
        self._cancel.set()
        return {"cancelled": self.current is not None, "macro": self.current}

    def _check(self, log):
        if self._cancel.is_set():
            raise _Abort("cancelled")
        if not self.focus_check():
            raise _Abort("game window lost focus")

    def run(self, macro, dry_run=False):
        """Execute synchronously; returns a result dict. Rejects a second concurrent run."""
        problems = validate_macro(macro)
        if problems:
            return {"ok": False, "macro": macro.get("name"), "error": "invalid macro", "problems": problems}
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "macro": macro.get("name"), "error": f"busy running {self.current!r}"}
        log, started = [], self.clock()
        try:
            self.current = macro["name"]
            self._cancel.clear()
            binding = self.binding_provider()
            if not binding:
                return {"ok": False, "macro": macro["name"], "error": "no key bindings loaded"}
            if not dry_run and not self.focus_check():
                return {"ok": False, "macro": macro["name"], "error": "game window is not focused"}
            for index, step in enumerate(macro["steps"], 1):
                if self.clock() - started > MAX_RUNTIME_MS / 1000.0:
                    raise _Abort("runtime cap reached")
                if not dry_run:
                    self._check(log)
                flags = self.status_flags()
                if "if_flag" in step and ((step["if_flag"] in flags) != step.get("is", True)):
                    log.append(f"{index}: skip (flag {step['if_flag']} is {step['if_flag'] in flags})")
                    continue
                if "press" in step:
                    chord = B.keyboard_chord(binding, step["press"])
                    if chord is None:
                        raise _Abort(f"action {step['press']} has no keyboard binding")
                    keys = B.chord_keys(chord)
                    if not dry_run:
                        self.sender.press_chord(keys, step.get("hold_ms", DEFAULT_HOLD_MS))
                    log.append(f"{index}: press {step['press']} -> {'+'.join(keys)}")
                    self._sleep_checked(step.get("gap_ms", DEFAULT_GAP_MS) / 1000.0, dry_run)
                elif "wait" in step:
                    self._sleep_checked(step["wait"] / 1000.0, dry_run)
                    log.append(f"{index}: wait {step['wait']} ms")
                else:
                    want = step.get("is", True)
                    deadline = self.clock() + step["timeout_ms"] / 1000.0
                    while (step["wait_until"] in self.status_flags()) != want:
                        if self.clock() >= deadline:
                            raise _Abort(f"timeout waiting for {step['wait_until']}={want}")
                        self._sleep_checked(POLL_MS / 1000.0, dry_run)
                    log.append(f"{index}: {step['wait_until']} is {want}")
            result = {"ok": True, "macro": macro["name"], "dry_run": dry_run, "log": log,
                      "elapsed_ms": int((self.clock() - started) * 1000)}
        except _Abort as exc:
            result = {"ok": False, "macro": macro["name"], "error": str(exc), "log": log,
                      "elapsed_ms": int((self.clock() - started) * 1000)}
        except Exception as exc:  # sender failures, bad scancodes
            result = {"ok": False, "macro": macro["name"], "error": f"{type(exc).__name__}: {exc}", "log": log}
        finally:
            self.current = None
            self.last_result = result if "result" in locals() else None
            self._lock.release()
        return result

    def _sleep_checked(self, seconds, dry_run):
        end = self.clock() + seconds
        while True:
            if not dry_run:
                self._check(None)
            remaining = end - self.clock()
            if remaining <= 0:
                return
            self.sleep(min(remaining, POLL_MS / 1000.0))


class _Abort(Exception):
    pass
