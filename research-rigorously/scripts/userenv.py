import ctypes
import os

try:
    import winreg
except ImportError:
    winreg = None


def get_user(name):
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return None


def set_user(name, value):
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def broadcast_change():
    if winreg is None:
        return
    try:
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x1A, 0, "Environment", 2, 1000, ctypes.byref(result)
        )
    except Exception:
        pass


def get_active_value(name):
    return get_user(name) or os.environ.get(name)
