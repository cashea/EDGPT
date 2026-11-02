"""Screen probes: answer "which tab is highlighted?" from a capture of the game window.

Pure ctypes GDI capture (no PIL). Probe geometry is defined at the 2560x1440 reference
and scaled to the actual window size. A probe returns a label or ``None`` when nothing
matches unambiguously, so macros can stop instead of guessing.
"""
import ctypes
import json
import os
import struct
import subprocess
import tempfile
from ctypes import wintypes
from pathlib import Path

REFERENCE = (2560, 1440)
HOT_MIN = 0.5      # fraction of bright-orange pixels for a box to count as highlighted
OTHER_MAX = 0.3    # any second box above this makes the probe ambiguous
GAME_WINDOW_TITLE = "Elite - Dangerous (CLIENT)"

# Box probes: label -> (x0, x1, y0, y1) at the reference resolution; the highlighted
# box is the one filled with Elite's selection orange. Measured 2026-11-01, docked,
# default head position.
PROBES = {
    # right cockpit panel tab headers (the row slants in perspective)
    "right_panel_tab": {
        "Home": (818, 866, 312, 352),
        "Modules": (880, 1060, 312, 352),
        "FireGroups": (1078, 1268, 318, 358),
        "Ship": (1286, 1486, 322, 362),
        "Inventory": (1503, 1715, 326, 366),
        "Storage": (1733, 1956, 330, 370),
        "Status": (1974, 2210, 334, 374),
        "Playlist": (2226, 2300, 338, 378),
    },
    # galaxy map: icon column right of the system-information card
    "galmap_strip": {
        "Route": (2382, 2408, 778, 833),
    },
}

# Text probes read a screen region with Windows OCR; the expectation matches when the
# wanted text occurs in what was read (case-insensitive, whitespace collapsed).
GALMAP_LIST = (960, 1640, 190, 960)        # search suggestion list
GALMAP_ROUTE_BAR = (380, 2200, 1240, 1340)  # route summary bar at the bottom
GALMAP_LIST_COLUMN = 1250                   # x where a highlighted row is solid orange

TEXT_PROBES = ("galmap_search_row", "galmap_route_bar")
# State probes answer with one of a fixed set of labels, computed by a function.
STATE_PROBES = {"galmap_search_list": ("open", "closed")}

OCR_SCRIPT = Path(__file__).with_name("ocr.ps1")


def parse_expectation(text):
    """``"probe=value"`` -> ``(probe, value)``; None when the probe or value is unknown."""
    if not isinstance(text, str) or text.count("=") != 1:
        return None
    probe, value = (part.strip() for part in text.split("="))
    if not value:
        return None
    if probe in PROBES and value in PROBES[probe]:
        return probe, value
    if probe in STATE_PROBES and value in STATE_PROBES[probe]:
        return probe, value
    if probe in TEXT_PROBES:
        return probe, value
    return None


def matches(probe, seen, want):
    """Does a probe result satisfy the expectation?"""
    if probe in TEXT_PROBES:
        return seen is not None and _norm(want) in _norm(seen)
    return seen == want


def _norm(text):
    return " ".join(str(text).upper().split())


def is_hot(r, g, b):
    """Elite's highlighted-tab orange (around 211,133,0) and nothing darker or whiter."""
    return r > 170 and g > 90 and b < 90 and r - g > 40


def hot_fraction(pixel_at, box, scale=(1.0, 1.0), step=2):
    """Fraction of sampled pixels in ``box`` (reference coords) that are highlight orange."""
    x0, x1, y0, y1 = box
    sx, sy = scale
    total = hot = 0
    for y in range(int(y0 * sy), int(y1 * sy), step):
        for x in range(int(x0 * sx), int(x1 * sx), step):
            total += 1
            hot += is_hot(*pixel_at(x, y))
    return hot / total if total else 0.0


def evaluate(probe, pixel_at, size, ocr=None):
    """Probe result: a box label, a state label, OCR text, or None when nothing qualifies.

    ``ocr(box)`` reads text lines from a reference-coordinate box; text probes need it.
    """
    if probe in STATE_PROBES or probe in TEXT_PROBES:
        return _evaluate_special(probe, pixel_at, size, ocr)
    boxes = PROBES[probe]
    scale = (size[0] / REFERENCE[0], size[1] / REFERENCE[1])
    scored = sorted(((hot_fraction(pixel_at, box, scale), label) for label, box in boxes.items()), reverse=True)
    best, label = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best >= HOT_MIN and second <= OTHER_MAX:
        return label
    return None


def _evaluate_special(probe, pixel_at, size, ocr):
    sx, sy = size[0] / REFERENCE[0], size[1] / REFERENCE[1]
    if probe == "galmap_search_list":
        # an open list fills the region with rows of orange text (closed: < 1 % orange)
        x0, x1, y0, y1 = GALMAP_LIST
        orange = total = 0
        for y in range(int(y0 * sy), int(y1 * sy), 2):
            for x in range(int((x0 + 10) * sx), int((x1 - 40) * sx), 2):
                total += 1
                r, g, b = pixel_at(x, y)
                orange += r > 150 and g > 70 and b < 80
        return "open" if total and orange / total > 0.025 else "closed"
    if probe == "galmap_search_row":
        row = _highlighted_row(pixel_at, sy, GALMAP_LIST_COLUMN * sx, GALMAP_LIST[2], GALMAP_LIST[3])
        if row is None or ocr is None:
            return None
        x0, x1, _, _ = GALMAP_LIST
        lines = ocr((x0, x1, int(row[0] / sy), int(row[1] / sy) + 1))
        return " ".join(line["text"] for line in lines) if lines else None
    if probe == "galmap_route_bar":
        if ocr is None:
            return None
        lines = ocr(GALMAP_ROUTE_BAR)
        return " ".join(line["text"] for line in lines) if lines else None
    return None


def _highlighted_row(pixel_at, sy, x, y0, y1):
    """(top, bottom) in window pixels of a solid-orange run taller than 20 px, else None."""
    start = prev = None
    for y in range(int(y0 * sy), int(y1 * sy)):
        if is_hot(*pixel_at(int(x), y)):
            if start is None:
                start = y
            prev = y
        elif start is not None:
            if prev - start > 20:
                return start, prev
            start = None
    return None


# ---- OCR (Windows.Media.Ocr through PowerShell) -------------------------------

def write_bmp(path, raw_bgra, width, height, box):
    """Write ``box`` (x0, x1, y0, y1 in window pixels) of a top-down BGRA buffer as a 32-bit BMP."""
    x0, x1, y0, y1 = (max(0, min(v, limit)) for v, limit in zip(box, (width, width, height, height)))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return False
    rows = []
    for y in range(y1 - 1, y0 - 1, -1):          # BMP rows are bottom-up
        i = (y * width + x0) * 4
        rows.append(raw_bgra[i:i + w * 4])
    pixels = b"".join(rows)
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 32, 0, len(pixels), 2835, 2835, 0, 0)
    Path(path).write_bytes(header + info + pixels)
    return True


def ocr_file(path, timeout=20):
    """OCR lines ``{"text","x","y","w","h"}`` from an image file via ``ocr.ps1``; [] on failure."""
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              str(OCR_SCRIPT), "-Path", str(path)],
                             capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return []
    lines = []
    for line in out.stdout.splitlines():
        if line.startswith("{"):
            try:
                lines.append(json.loads(line))
            except ValueError:
                pass
    return lines


# ---- Win32 capture ------------------------------------------------------------

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def capture_game_window():
    """``(pixel_at, (width, height))`` for the game window's screen area, or None if not found.

    Grabs from the screen, so the window must be visible (the macro engine already
    requires it to be the foreground window).
    """
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = user32.FindWindowW(None, GAME_WINDOW_TITLE)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    screen = user32.GetDC(0)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    try:
        gdi32.SelectObject(memory, bitmap)
        gdi32.BitBlt(memory, 0, 0, width, height, screen, origin.x, origin.y, 0x00CC0020)  # SRCCOPY
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth, info.bmiHeader.biHeight = width, -height  # top-down rows
        info.bmiHeader.biPlanes, info.bmiHeader.biBitCount = 1, 32
        buffer = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), 0)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(0, screen)
    raw = buffer.raw

    def pixel_at(x, y):
        i = (y * width + x) * 4
        return raw[i + 2], raw[i + 1], raw[i]   # BGRA -> RGB

    return pixel_at, (width, height), raw


def probe_game(probe):
    """Run ``probe`` against a fresh capture; None when the window is missing or nothing matches."""
    grab = capture_game_window()
    if grab is None:
        return None
    pixel_at, size, raw = grab
    sx, sy = size[0] / REFERENCE[0], size[1] / REFERENCE[1]

    def ocr(box):
        x0, x1, y0, y1 = box
        path = os.path.join(tempfile.gettempdir(), "edgpt_ocr.bmp")
        window_box = (int(x0 * sx), int(x1 * sx), int(y0 * sy), int(y1 * sy))
        if not write_bmp(path, raw, size[0], size[1], window_box):
            return []
        return ocr_file(path)

    return evaluate(probe, pixel_at, size, ocr)
