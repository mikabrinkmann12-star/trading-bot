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


def window_exe_at(x: int, y: int) -> str:
    """Programmname (z.B. 'TradingView.exe') des Fensters am Punkt (x, y)."""
    if sys.platform != "win32":
        return ""
    import ctypes
    import os
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x, y)), 2)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def foreground_info() -> tuple[str, str]:
    """(Titel, Programmname) des Fensters im Vordergrund."""
    if sys.platform != "win32":
        return "", ""
    import ctypes
    import os
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    title = buf.value
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if handle:
        try:
            pbuf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, pbuf, ctypes.byref(size)):
                exe = os.path.basename(pbuf.value)
        finally:
            kernel32.CloseHandle(handle)
    return title, exe


def left_button_down() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
