"""Win32 SendInput key injection with a game-focus guard. Only imported on demand; never at module import."""
import ctypes
import time
from ctypes import wintypes

from .scancodes import scancode

GAME_EXE_NAMES = ("elitedangerous64.exe",)
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _user32():
    return ctypes.windll.user32


def foreground_process_name():
    """Lower-case executable name of the foreground window's process, or ''."""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return ""
            return buffer.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def game_focused():
    return foreground_process_name() in GAME_EXE_NAMES


def _key_input(code, extended, up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
    item = INPUT()
    item.type = INPUT_KEYBOARD
    item.u.ki = KEYBDINPUT(0, code, flags, 0, 0)
    return item


def _send(items):
    array = (INPUT * len(items))(*items)
    sent = _user32().SendInput(len(items), array, ctypes.sizeof(INPUT))
    if sent != len(items):
        raise OSError(f"SendInput sent {sent} of {len(items)} events")


class Win32Sender:
    """Presses a chord: modifiers down, key down, hold, key up, modifiers up (reverse order)."""

    def press_chord(self, keys, hold_ms=60):
        codes = []
        for key in keys:
            mapped = scancode(key)
            if mapped is None:
                raise ValueError(f"No scancode for {key}")
            codes.append(mapped)
        _send([_key_input(code, ext, False) for code, ext in codes])
        time.sleep(max(0, hold_ms) / 1000.0)
        _send([_key_input(code, ext, True) for code, ext in reversed(codes)])

    def release_all(self, keys):
        codes = [scancode(k) for k in keys if scancode(k)]
        if codes:
            _send([_key_input(code, ext, True) for code, ext in reversed(codes)])
