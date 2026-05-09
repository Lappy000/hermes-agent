"""
Cross-platform process management abstraction for Hermes Agent.

Provides unified APIs for process lifecycle operations that work on both
Unix (Linux/macOS) and Windows systems. Uses os.setsid/killpg on Unix and
taskkill/ctypes kernel32 on Windows.
"""

import os
import sys
import signal
import subprocess
import time
from typing import Any, Dict, Optional

__all__ = [
    "create_process_group",
    "kill_process_tree",
    "is_process_alive",
    "signal_reload",
    "terminate_process",
    "force_kill_process",
    "graceful_kill",
    "wait_for_process_exit",
]

IS_WINDOWS = sys.platform == "win32"


def create_process_group(popen_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Modify subprocess.Popen kwargs to create a new process group.

    On Unix: adds preexec_fn=os.setsid so the child becomes a session leader.
    On Windows: adds CREATE_NEW_PROCESS_GROUP creation flag and removes any
    preexec_fn (which is not supported on Windows).

    Args:
        popen_kwargs: Dictionary of kwargs to pass to subprocess.Popen.

    Returns:
        Modified copy of popen_kwargs with platform-appropriate settings.
    """
    kwargs = dict(popen_kwargs)

    if IS_WINDOWS:
        # Remove preexec_fn which is Unix-only
        kwargs.pop("preexec_fn", None)
        # Add CREATE_NEW_PROCESS_GROUP flag
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        existing_flags = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = existing_flags | CREATE_NEW_PROCESS_GROUP
    else:
        # On Unix, make the child a session leader
        kwargs["preexec_fn"] = os.setsid

    return kwargs


def kill_process_tree(pid: int, force: bool = False) -> bool:
    """
    Kill a process and all its children (the entire process tree).

    On Unix: sends SIGKILL (force) or SIGTERM to the process group.
    On Windows: uses taskkill /T /PID (with /F for force).

    Args:
        pid: Process ID of the root process.
        force: If True, use SIGKILL/taskkill /F for immediate termination.

    Returns:
        True if the kill command succeeded, False otherwise.
    """
    if IS_WINDOWS:
        cmd = ["taskkill", "/T", "/PID", str(pid)]
        if force:
            cmd.insert(1, "/F")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
    else:
        try:
            pgid = os.getpgid(pid)
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.killpg(pgid, sig)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False
        except OSError:
            return False


def is_process_alive(pid: int) -> bool:
    """
    Check if a process with the given PID is still running.

    On Unix: sends signal 0 to the process (no actual signal delivered).
    On Windows: uses ctypes OpenProcess with PROCESS_QUERY_LIMITED_INFORMATION.

    Args:
        pid: Process ID to check.

    Returns:
        True if the process exists and is accessible, False otherwise.
    """
    if IS_WINDOWS:
        import ctypes
        import ctypes.wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle == 0:
            return False

        # Process exists; close the handle
        kernel32.CloseHandle(handle)
        return True
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we don't have permission to signal it
            return True
        except OSError:
            return False


def signal_reload(pid: int) -> bool:
    """
    Send a reload signal to the specified process.

    On Unix: sends SIGUSR1 to the process.
    On Windows: opens a named event 'HermesReload_{pid}' and sets it via
    kernel32 SetEvent.

    Args:
        pid: Process ID to signal.

    Returns:
        True if the signal was sent successfully, False otherwise.
    """
    if IS_WINDOWS:
        import ctypes

        kernel32 = ctypes.windll.kernel32

        event_name = f"HermesReload_{pid}"
        # OpenEventW(dwDesiredAccess, bInheritHandle, lpName)
        EVENT_MODIFY_STATE = 0x0002
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, event_name)
        if handle == 0:
            return False

        try:
            result = kernel32.SetEvent(handle)
            return result != 0
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, signal.SIGUSR1)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False
        except OSError:
            return False


def terminate_process(pid: int) -> bool:
    """
    Send a graceful termination signal to a process.

    On Unix: sends SIGTERM.
    On Windows: uses taskkill /PID without /F (allows graceful shutdown).

    Args:
        pid: Process ID to terminate.

    Returns:
        True if the signal was sent successfully, False otherwise.
    """
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False
        except OSError:
            return False


def force_kill_process(pid: int) -> bool:
    """
    Forcefully kill a process immediately.

    On Unix: sends SIGKILL (cannot be caught or ignored).
    On Windows: uses taskkill /F /PID for forced termination.

    Args:
        pid: Process ID to kill.

    Returns:
        True if the kill was sent successfully, False otherwise.
    """
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
    else:
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False
        except OSError:
            return False


def wait_for_process_exit(pid: int, timeout: float) -> bool:
    """
    Wait for a process to exit, polling at short intervals.

    Args:
        pid: Process ID to wait for.
        timeout: Maximum seconds to wait.

    Returns:
        True if the process exited within the timeout, False if still alive.
    """
    deadline = time.monotonic() + timeout
    poll_interval = 0.05  # 50ms

    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            return True
        time.sleep(min(poll_interval, deadline - time.monotonic()))
        # Gradually increase poll interval up to 250ms
        poll_interval = min(poll_interval * 1.5, 0.25)

    return not is_process_alive(pid)


def graceful_kill(pid: int, grace_seconds: float = 3.0) -> bool:
    """
    Attempt graceful termination, escalating to force kill if needed.

    Sends SIGTERM (or Windows equivalent), waits up to grace_seconds for
    the process to exit, then sends SIGKILL (or taskkill /F) if still alive.

    Args:
        pid: Process ID to kill.
        grace_seconds: Seconds to wait after SIGTERM before sending SIGKILL.

    Returns:
        True if the process is confirmed dead, False if it could not be killed.
    """
    # First check if already dead
    if not is_process_alive(pid):
        return True

    # Send graceful termination
    terminate_process(pid)

    # Wait for process to exit
    if wait_for_process_exit(pid, grace_seconds):
        return True

    # Still alive - force kill
    force_kill_process(pid)

    # Brief wait to confirm death
    return wait_for_process_exit(pid, 1.0)
