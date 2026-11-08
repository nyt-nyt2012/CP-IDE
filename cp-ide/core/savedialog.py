"""Windows 原生「另存为」对话框。

直接用 ctypes 调 comdlg32 的 GetSaveFileNameW：

* 不需要额外的 Tk 窗口（打包成 exe 时也更省资源）
* 在后台线程里也能弹，Flask 的请求线程调用没问题
* 走系统原生外观，用户按熟悉的「保存到某处」流程
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Optional

# OFN_* 标志位
OFN_OVERWRITEPROMPT = 0x00000002
OFN_PATHMUSTEXIST = 0x00000800
OFN_NOCHANGEDIR = 0x00000008
OFN_EXPLORER = 0x00080000


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", ctypes.c_void_p),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


def find_owner_window(title_prefix: str = "CP-IDE") -> Optional[int]:
    """找出 IDE 主窗口句柄，让「另存为」对话框出现在它前面。"""
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return None
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.startswith(title_prefix):
                found.append(hwnd)
                return False
        return True

    try:
        user32.EnumWindows(_callback, 0)
    except Exception:
        return None
    return found[0] if found else None


def save_file_dialog(
    default_name: str = "",
    title: str = "另存为",
    filters: str = "",
    owner: Optional[int] = None,
) -> str:
    """弹出「另存为」对话框。

    返回用户选择的完整路径；取消或非 Windows 平台时返回空字符串。
    """
    if os.name != "nt":
        return ""
    default_name = os.path.basename(default_name or "")
    buffer = ctypes.create_unicode_buffer(4096)
    buffer.value = default_name

    options = OPENFILENAMEW()
    options.lStructSize = ctypes.sizeof(options)
    if owner is None:
        owner = find_owner_window()
    if owner is None:
        try:
            owner = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            owner = None
    options.hwndOwner = owner
    options.lpstrFilter = filters or None
    options.nFilterIndex = 1
    options.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    options.nMaxFile = len(buffer)
    options.lpstrTitle = title
    options.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER
    extension = os.path.splitext(default_name)[1]
    if extension:
        options.lpstrDefExt = extension.lstrip(".")

    try:
        ok = ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(options))
    except Exception:
        return ""
    if not ok:
        return ""
    return buffer.value
