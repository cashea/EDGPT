"""Parse Elite Dangerous ``.binds`` XML into action -> key chord. Pure except ``load``."""
import os
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_BINDINGS_DIR = (Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
                        / "Frontier Developments" / "Elite Dangerous" / "Options" / "Bindings")
SLOT_TAGS = ("Primary", "Secondary")


def parse_binds(xml_text):
    """Return ``{action: {"primary": chord|None, "secondary": chord|None}}``.

    A chord is ``{"device": str, "key": str, "modifiers": [{"device","key"}, ...]}``.
    Axes, toggles and numeric settings are ignored. ``{NoDevice}`` slots are ``None``.
    """
    root = ET.fromstring(xml_text)
    actions = {}
    for element in root:
        slots = {tag.lower(): None for tag in SLOT_TAGS}
        found = False
        for tag in SLOT_TAGS:
            slot = element.find(tag)
            if slot is None:
                continue
            found = True
            device = slot.get("Device", "")
            key = slot.get("Key", "")
            if not device or device == "{NoDevice}" or not key:
                continue
            modifiers = [{"device": m.get("Device", ""), "key": m.get("Key", "")}
                         for m in slot.findall("Modifier")
                         if m.get("Device") and m.get("Device") != "{NoDevice}" and m.get("Key")]
            slots[tag.lower()] = {"device": device, "key": key, "modifiers": modifiers}
        if found:
            actions[element.tag] = slots
    return {
        "preset": root.get("PresetName", ""),
        "version": f"{root.get('MajorVersion', '')}.{root.get('MinorVersion', '')}",
        "layout": (root.findtext("KeyboardLayout") or "").strip(),
        "actions": actions,
    }


def keyboard_chord(binding, action):
    """First slot of ``action`` that is on the keyboard with keyboard-only modifiers, else None."""
    slots = binding.get("actions", {}).get(action)
    if not slots:
        return None
    for name in ("primary", "secondary"):
        chord = slots.get(name)
        if chord and chord["device"] == "Keyboard" and all(m["device"] == "Keyboard" for m in chord["modifiers"]):
            return chord
    return None


def chord_keys(chord):
    """Ordered key names to hold: modifiers first, then the main key."""
    return [m["key"] for m in chord["modifiers"]] + [chord["key"]]


def active_preset_names(bindings_dir):
    """Preset names from ``StartPreset.4.start`` (one per line: general, ship, srv, on-foot)."""
    start = Path(bindings_dir) / "StartPreset.4.start"
    try:
        lines = [line.strip() for line in start.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return []
    return [line for line in lines if line]


def find_binds_file(bindings_dir=None):
    """Newest ``<preset>.*.binds`` for the active preset, else the newest ``*.binds``."""
    folder = Path(bindings_dir or DEFAULT_BINDINGS_DIR)
    if not folder.is_dir():
        return None
    candidates = sorted(folder.glob("*.binds"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    for preset in active_preset_names(folder):
        for path in candidates:
            if path.name.startswith(preset + "."):
                return path
    return candidates[0]


class BindsWatcher:
    """Re-parse the binds file whenever its mtime changes."""

    def __init__(self, bindings_dir=None):
        self.bindings_dir = bindings_dir
        self.path = None
        self.mtime = None
        self.binding = None
        self.error = None

    def load(self):
        path = find_binds_file(self.bindings_dir)
        if path is None:
            self.path, self.binding, self.error = None, None, "No .binds file found."
            return None
        try:
            mtime = path.stat().st_mtime
            if path != self.path or mtime != self.mtime or self.binding is None:
                self.binding = parse_binds(path.read_text(encoding="utf-8", errors="replace"))
                self.path, self.mtime, self.error = path, mtime, None
        except (OSError, ET.ParseError) as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        return self.binding

    def summary(self):
        self.load()
        return {"file": str(self.path) if self.path else None, "error": self.error,
                "preset": (self.binding or {}).get("preset"), "layout": (self.binding or {}).get("layout"),
                "actions": len((self.binding or {}).get("actions", {}))}
