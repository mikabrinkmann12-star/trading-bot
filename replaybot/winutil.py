"""Windows-Hilfen: DPI-Skalierung, Mausposition, Fenstertitel unter einem Punkt."""
from __future__ import annotations

import sys


def set_dpi_aware():
    """Ohne das stimmen bei 125 %/150 % Skalierung die Koordinaten von tkinter, mss und
    pyautogui nicht überein. Muss vor dem ersten Fenster aufgerufen werden."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def mouse_pos() -> tuple[int, int] | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def window_title_at(x: int, y: int) -> str:
    """Titel des Hauptfensters, das am Punkt (x, y) liegt."""
    if sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    root = user32.GetAncestor(hwnd, 2)  # GA_ROOT
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(root, buf, 512)
    return buf.value
