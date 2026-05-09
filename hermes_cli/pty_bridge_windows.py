"""
Windows PTY bridge using ConPTY via pywinpty.

Provides a PTY interface for interactive subprocess execution on Windows,
equivalent to the Unix pty_bridge.py (which uses fcntl/termios/pty).

Requires Windows 10 1809+ (October 2018 update) for ConPTY support.
Requires pywinpty package (already specified in pyproject.toml for win32).
"""

import logging
import os
import sys
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_WINPTY_AVAILABLE = False
try:
    if sys.platform == "win32":
        from winpty import PtyProcess  # pywinpty
        _WINPTY_AVAILABLE = True
except ImportError:
    pass


class WindowsPtyBridge:
    """ConPTY-based pseudo-terminal bridge for Windows.

    Wraps pywinpty's PtyProcess to provide a consistent interface for
    interactive subprocess management.
    """

    def __init__(
        self,
        command: str | list[str],
        cols: int = 120,
        rows: int = 40,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ):
        """Spawn a new PTY process.

        Args:
            command: Command to execute (string or list).
            cols: Terminal width in columns.
            rows: Terminal height in rows.
            cwd: Working directory for the process.
            env: Environment variables (defaults to os.environ).
        """
        if not _WINPTY_AVAILABLE:
            raise RuntimeError(
                "pywinpty not available. Install with: pip install pywinpty\n"
                "Requires Windows 10 1809+ for ConPTY support."
            )

        if isinstance(command, list):
            command = " ".join(command)

        self._cols = cols
        self._rows = rows
        self._closed = False
        self._read_callbacks: list[Callable[[str], None]] = []
        self._read_thread: Optional[threading.Thread] = None

        # Spawn the process via ConPTY
        spawn_kwargs = {
            "dimensions": (rows, cols),
        }
        if cwd:
            spawn_kwargs["cwd"] = cwd
        if env:
            # pywinpty expects env as a dict
            spawn_kwargs["env"] = env

        self._process = PtyProcess.spawn(command, **spawn_kwargs)

    @property
    def pid(self) -> int:
        """Return the PID of the child process."""
        return self._process.pid

    @property
    def is_alive(self) -> bool:
        """Check if the child process is still running."""
        return self._process.isalive()

    def read(self, size: int = 4096) -> str:
        """Read output from the PTY.

        Returns empty string if no data available or process exited.
        """
        if self._closed:
            return ""
        try:
            return self._process.read(size)
        except EOFError:
            return ""
        except Exception as e:
            logger.debug("PTY read error: %s", e)
            return ""

    def write(self, data: str) -> None:
        """Write input to the PTY."""
        if self._closed:
            return
        try:
            self._process.write(data)
        except Exception as e:
            logger.debug("PTY write error: %s", e)

    def writeline(self, data: str) -> None:
        """Write a line to the PTY (appends \\r\\n)."""
        self.write(data + "\r\n")

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal dimensions."""
        if self._closed:
            return
        self._cols = cols
        self._rows = rows
        try:
            self._process.setwinsize(rows, cols)
        except Exception as e:
            logger.debug("PTY resize error: %s", e)

    def start_read_thread(self, callback: Callable[[str], None]) -> None:
        """Start a background thread that reads PTY output and calls callback.

        The callback receives chunks of output text as they arrive.
        """
        if self._read_thread and self._read_thread.is_alive():
            return

        self._read_callbacks.append(callback)

        def _reader():
            while not self._closed and self.is_alive:
                data = self.read(4096)
                if data:
                    for cb in self._read_callbacks:
                        try:
                            cb(data)
                        except Exception:
                            pass

        self._read_thread = threading.Thread(target=_reader, daemon=True)
        self._read_thread.start()

    def close(self) -> None:
        """Close the PTY and terminate the child process."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._process.isalive():
                self._process.close(force=True)
        except Exception as e:
            logger.debug("PTY close error: %s", e)

    def wait(self, timeout: Optional[float] = None) -> int:
        """Wait for the child process to exit and return its exit code."""
        if self._closed:
            return -1
        try:
            self._process.wait()
            return self._process.exitstatus or 0
        except Exception:
            return -1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()


def is_pty_available() -> bool:
    """Check if Windows PTY support is available."""
    return _WINPTY_AVAILABLE


def create_pty(
    command: str | list[str] = None,
    cols: int = 120,
    rows: int = 40,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
) -> Optional["WindowsPtyBridge"]:
    """Create a Windows PTY bridge.

    Returns None if PTY support is not available.
    Default command is PowerShell if not specified.
    """
    if not _WINPTY_AVAILABLE:
        return None

    if command is None:
        import shutil
        command = shutil.which("pwsh") or shutil.which("powershell") or "cmd.exe"

    return WindowsPtyBridge(command, cols=cols, rows=rows, cwd=cwd, env=env)
