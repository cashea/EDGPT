"""Screen probes: answer "which tab is highlighted?" from a capture of the game window.

Pure ctypes GDI capture (no PIL). Probe geometry is defined at the 2560x1440 reference
and scaled to the actual window size. A probe returns a label or ``None`` when nothing
matches unambiguously, so macros can stop instead of guessing.
"""
import ctypes
from ctypes import wintypes

REFERENCE = (2560, 1440)
HOT_MIN = 0.5      # fraction of bright-orange pixels for a box to count as highlighted
OTHER_MAX = 0.3    # any second box above this makes the probe ambiguous
GAME_WINDOW_TITLE = "Elite - Dangerous (CLIENT)"

# Right cockpit panel tab headers, measured 2026-11-01 (docked, default head position).
# Boxes are (x0, x1, y0, y1) at the reference resolution; the row slants in perspective.
PROBES = {
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
}


def parse_expectation(text):
    """``"right_panel_tab=Inventory"`` -> ``("right_panel_tab", "Inventory")``; None when malformed."""
    if not isinstance(text, str) or text.count("=") != 1:
        return None
    probe, value = (part.strip() for part in text.split("="))
    if probe not in PROBES or value not in PROBES[probe]:
        return None
    return probe, value


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


def evaluate(probe, pixel_at, size):
    """Label whose box is highlighted, or None when no box or more than one box qualifies."""
    boxes = PROBES[probe]
    scale = (size[0] / REFERENCE[0], size[1] / REFERENCE[1])
    scored = sorted(((hot_fraction(pixel_at, box, scale), label) for label, box in boxes.items()), reverse=True)
    best, label = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best >= HOT_MIN and second <= OTHER_MAX:
        return label
    return None


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

    return pixel_at, (width, height)


def probe_game(probe):
    """Run ``probe`` against a fresh capture; None when the window is missing or nothing matches."""
    grab = capture_game_window()
    if grab is None:
        return None
    pixel_at, size = grab
    return evaluate(probe, pixel_at, size)
