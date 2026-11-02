"""Elite ``Key_*`` names -> (set-1 scancode, extended flag) for SendInput with KEYEVENTF_SCANCODE."""

_BASE = {
    "Key_Escape": 0x01, "Key_1": 0x02, "Key_2": 0x03, "Key_3": 0x04, "Key_4": 0x05, "Key_5": 0x06,
    "Key_6": 0x07, "Key_7": 0x08, "Key_8": 0x09, "Key_9": 0x0A, "Key_0": 0x0B, "Key_Minus": 0x0C,
    "Key_Equals": 0x0D, "Key_Backspace": 0x0E, "Key_Tab": 0x0F, "Key_Q": 0x10, "Key_W": 0x11,
    "Key_E": 0x12, "Key_R": 0x13, "Key_T": 0x14, "Key_Y": 0x15, "Key_U": 0x16, "Key_I": 0x17,
    "Key_O": 0x18, "Key_P": 0x19, "Key_LeftBracket": 0x1A, "Key_RightBracket": 0x1B, "Key_Enter": 0x1C,
    "Key_LeftControl": 0x1D, "Key_A": 0x1E, "Key_S": 0x1F, "Key_D": 0x20, "Key_F": 0x21, "Key_G": 0x22,
    "Key_H": 0x23, "Key_J": 0x24, "Key_K": 0x25, "Key_L": 0x26, "Key_SemiColon": 0x27,
    "Key_Apostrophe": 0x28, "Key_Grave": 0x29, "Key_LeftShift": 0x2A, "Key_BackSlash": 0x2B,
    "Key_Z": 0x2C, "Key_X": 0x2D, "Key_C": 0x2E, "Key_V": 0x2F, "Key_B": 0x30, "Key_N": 0x31,
    "Key_M": 0x32, "Key_Comma": 0x33, "Key_Period": 0x34, "Key_Slash": 0x35, "Key_RightShift": 0x36,
    "Key_Numpad_Multiply": 0x37, "Key_LeftAlt": 0x38, "Key_Space": 0x39, "Key_CapsLock": 0x3A,
    "Key_F1": 0x3B, "Key_F2": 0x3C, "Key_F3": 0x3D, "Key_F4": 0x3E, "Key_F5": 0x3F, "Key_F6": 0x40,
    "Key_F7": 0x41, "Key_F8": 0x42, "Key_F9": 0x43, "Key_F10": 0x44, "Key_NumLock": 0x45,
    "Key_ScrollLock": 0x46, "Key_Numpad_7": 0x47, "Key_Numpad_8": 0x48, "Key_Numpad_9": 0x49,
    "Key_Numpad_Subtract": 0x4A, "Key_Numpad_4": 0x4B, "Key_Numpad_5": 0x4C, "Key_Numpad_6": 0x4D,
    "Key_Numpad_Add": 0x4E, "Key_Numpad_1": 0x4F, "Key_Numpad_2": 0x50, "Key_Numpad_3": 0x51,
    "Key_Numpad_0": 0x52, "Key_Numpad_Decimal": 0x53, "Key_F11": 0x57, "Key_F12": 0x58,
}
_EXTENDED = {
    "Key_Numpad_Enter": 0x1C, "Key_RightControl": 0x1D, "Key_Numpad_Divide": 0x35,
    "Key_RightAlt": 0x38, "Key_Home": 0x47, "Key_UpArrow": 0x48, "Key_PageUp": 0x49,
    "Key_LeftArrow": 0x4B, "Key_RightArrow": 0x4D, "Key_End": 0x4F, "Key_DownArrow": 0x50,
    "Key_PageDown": 0x51, "Key_Insert": 0x52, "Key_Delete": 0x53, "Key_LeftWin": 0x5B,
    "Key_RightWin": 0x5C, "Key_Apps": 0x5D,
}
SCANCODES = {**{k: (v, False) for k, v in _BASE.items()}, **{k: (v, True) for k, v in _EXTENDED.items()}}


def scancode(key_name):
    """``(scancode, extended)`` or None when the key is not mappable (e.g. joystick buttons)."""
    return SCANCODES.get(key_name)


def unmapped(keys):
    return [k for k in keys if k not in SCANCODES]
