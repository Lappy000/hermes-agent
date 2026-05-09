"""
Cross-platform user and system information for Hermes Agent.

Provides unified APIs for querying user identity, home directories, and runtime
paths that work on both Unix (Linux/macOS) and Windows. Replaces direct usage of
os.getuid(), pwd module, and Unix-specific path conventions.
"""

import getpass
import os
import sys
from pathlib import Path
from typing import Optional

__all__ = [
    "get_username",
    "get_uid",
    "get_gid",
    "get_home_dir",
    "get_runtime_dir",
    "get_user_info",
    "is_root",
    "IS_WINDOWS",
]

IS_WINDOWS = sys.platform == "win32"


def get_username() -> str:
    """Return the current user's login name (cross-platform).

    On Unix: uses os.getlogin() with fallback to getpass.getuser().
    On Windows: uses os.getlogin() with fallback to %USERNAME%.
    """
    try:
        return getpass.getuser()
    except Exception:
        pass

    if IS_WINDOWS:
        return os.environ.get("USERNAME", "unknown")
    else:
        return os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))


def get_uid() -> int:
    """Return the numeric user ID.

    On Unix: os.getuid() (real UID).
    On Windows: returns 1000 (placeholder — not meaningful but prevents crashes
    in code that constructs paths like /run/user/{uid}).
    """
    if IS_WINDOWS:
        return 1000  # Placeholder; Windows uses SIDs not numeric UIDs
    return os.getuid()


def get_gid() -> int:
    """Return the numeric group ID.

    On Unix: os.getgid() (real GID).
    On Windows: returns 1000 (placeholder).
    """
    if IS_WINDOWS:
        return 1000  # Placeholder
    return os.getgid()


def get_home_dir() -> Path:
    """Return the user's home directory (cross-platform).

    On Unix: resolves via HOME, expanduser, or pwd module.
    On Windows: uses USERPROFILE or expanduser.
    """
    # Try pathlib first — handles both platforms
    home = Path.home()
    if home and str(home) != "~":
        return home

    # Fallback to environment variables
    if IS_WINDOWS:
        home_str = os.environ.get("USERPROFILE", "")
    else:
        home_str = os.environ.get("HOME", "")

    if home_str:
        return Path(home_str)

    # Last resort: expanduser
    expanded = os.path.expanduser("~")
    if expanded and expanded != "~":
        return Path(expanded)

    # Unix-only fallback via pwd module
    if not IS_WINDOWS:
        try:
            import pwd
            return Path(pwd.getpwuid(os.getuid()).pw_dir)
        except Exception:
            pass

    # Absolute last resort
    if IS_WINDOWS:
        return Path(os.environ.get("TEMP", "C:\\Users\\Default"))
    return Path("/tmp")


def get_runtime_dir() -> str:
    """Return the XDG_RUNTIME_DIR equivalent.

    On Unix: XDG_RUNTIME_DIR or /run/user/{uid}.
    On Windows: TEMP or LOCALAPPDATA\\Temp.
    """
    if IS_WINDOWS:
        return os.environ.get(
            "TEMP",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp"),
        )
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")


def get_user_info() -> dict:
    """Return a dict with user identity info (cross-platform).

    Returns dict with keys: username, uid, gid, home, shell.
    On Windows, uid/gid are placeholders and shell is powershell/cmd.
    """
    info = {
        "username": get_username(),
        "uid": get_uid(),
        "gid": get_gid(),
        "home": str(get_home_dir()),
    }

    if IS_WINDOWS:
        import shutil
        info["shell"] = (
            shutil.which("pwsh") or shutil.which("powershell") or
            os.environ.get("COMSPEC", "cmd.exe")
        )
    else:
        info["shell"] = os.environ.get("SHELL", "/bin/sh")

    return info


def is_root() -> bool:
    """Return True if running as root/administrator.

    On Unix: checks os.getuid() == 0.
    On Windows: checks via ctypes shell32.IsUserAnAdmin().
    """
    if IS_WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.getuid() == 0


def get_user_home_from_pwd(uid: Optional[int] = None) -> Path:
    """Return the home directory from the password database (Unix) or
    USERPROFILE (Windows).

    This is used when we need the *real* home directory even when HOME env
    is overridden (e.g., for launchd/service artifacts that must live under
    the actual account home).

    Args:
        uid: Numeric user ID (Unix). Defaults to current user.

    Returns:
        Path to the user's home directory.
    """
    if IS_WINDOWS:
        # Windows: USERPROFILE is the canonical home
        home = os.environ.get("USERPROFILE", "")
        if home:
            return Path(home)
        return Path.home()

    # Unix: use pwd module for authoritative home
    try:
        import pwd
        if uid is None:
            uid = os.getuid()
        return Path(pwd.getpwuid(uid).pw_dir)
    except Exception:
        return Path.home()


def get_username_from_uid(uid: Optional[int] = None) -> str:
    """Resolve a UID to a username (Unix) or return current username (Windows).

    Args:
        uid: Numeric user ID. Defaults to current user.

    Returns:
        Username string.
    """
    if IS_WINDOWS:
        return get_username()

    try:
        import pwd
        if uid is None:
            uid = os.getuid()
        return pwd.getpwuid(uid).pw_name
    except Exception:
        return get_username()
