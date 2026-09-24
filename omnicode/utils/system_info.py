"""
System information utilities for OmniCode.
Detects OS, shell, python version, terminal dimensions, and environment.
"""

import os
import platform
import sys
import shutil


def get_platform_info() -> dict:
    """Return dictionary of platform and OS details."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "is_windows": platform.system().lower() == "windows",
        "is_macos": platform.system().lower() == "darwin",
        "is_linux": platform.system().lower() == "linux",
    }


def get_default_shell() -> str:
    """Detect default shell for the current operating system."""
    if platform.system().lower() == "windows":
        # Check if powershell is available
        if shutil.which("powershell"):
            return "powershell"
        elif shutil.which("pwsh"):
            return "pwsh"
        return "cmd.exe"
    else:
        return os.environ.get("SHELL", "/bin/bash")


def get_terminal_width(default: int = 100) -> int:
    """Get current terminal column width."""
    try:
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except Exception:
        return default


def prevent_windows_quick_edit():
    """Disable QuickEdit Mode on Windows Console to prevent accidental terminal freezing upon mouse click."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            STD_INPUT_HANDLE = -10
            ENABLE_QUICK_EDIT_MODE = 0x0040
            ENABLE_EXTENDED_FLAGS = 0x0080
            h_stdin = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
                new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
                kernel32.SetConsoleMode(h_stdin, new_mode)
        except Exception:
            pass

