"""
Windows Service management for Hermes Gateway.

Provides install/start/stop/restart/status/uninstall operations for the
Hermes Gateway running as a Windows Service via NSSM (Non-Sucking Service
Manager) or Task Scheduler as a fallback.

NSSM: https://nssm.cc/ — lightweight service wrapper for Windows.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

__all__ = [
    "is_nssm_available",
    "get_service_name",
    "install_service",
    "uninstall_service",
    "start_service",
    "stop_service",
    "restart_service",
    "get_service_status",
    "is_service_installed",
    "is_service_running",
]

_DEFAULT_SERVICE_NAME = "HermesGateway"


def _get_nssm_path() -> Optional[str]:
    """Find NSSM executable."""
    # Check config
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
        gw_cfg = cfg.get("gateway") or {}
        custom_path = gw_cfg.get("nssm_path")
        if custom_path and os.path.isfile(custom_path):
            return custom_path
    except Exception:
        pass

    # Check PATH
    nssm = shutil.which("nssm")
    if nssm:
        return nssm

    # Common install locations
    for candidate in (
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nssm", "win64", "nssm.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "nssm", "win32", "nssm.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "nssm", "nssm.exe"),
        os.path.join(str(Path.home()), ".hermes", "bin", "nssm.exe"),
    ):
        if candidate and os.path.isfile(candidate):
            return candidate

    return None


def is_nssm_available() -> bool:
    """Check if NSSM is installed and accessible."""
    return _get_nssm_path() is not None


def get_service_name(profile: str = "default") -> str:
    """Return the Windows Service name for a given profile."""
    if profile and profile != "default":
        return f"{_DEFAULT_SERVICE_NAME}_{profile}"
    return _DEFAULT_SERVICE_NAME


def _run_nssm(*args, check: bool = True) -> subprocess.CompletedProcess:
    """Run an NSSM command."""
    nssm = _get_nssm_path()
    if not nssm:
        raise RuntimeError(
            "NSSM (Non-Sucking Service Manager) not found.\n"
            "Install from: https://nssm.cc/download\n"
            "Or place nssm.exe in %USERPROFILE%\\.hermes\\bin\\"
        )
    cmd = [nssm] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def _get_python_path() -> str:
    """Get the Python executable for the gateway."""
    # Prefer the venv python
    hermes_home = Path.home() / ".hermes" / "hermes-agent"
    venv_python = hermes_home / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _get_gateway_script() -> str:
    """Get the gateway run script path."""
    hermes_home = Path.home() / ".hermes" / "hermes-agent"
    gateway_run = hermes_home / "gateway" / "run.py"
    if gateway_run.exists():
        return str(gateway_run)
    # Fallback: use module invocation
    return "-m hermes_cli.main gateway run"


def install_service(
    profile: str = "default",
    description: str = "Hermes Agent Gateway Service",
) -> Tuple[bool, str]:
    """Install the Hermes Gateway as a Windows Service via NSSM.

    Returns (success, message) tuple.
    """
    service_name = get_service_name(profile)
    python_path = _get_python_path()
    hermes_root = str(Path.home() / ".hermes" / "hermes-agent")

    try:
        # Check if already installed
        result = _run_nssm("status", service_name, check=False)
        if result.returncode == 0 and "SERVICE_" in result.stdout:
            return False, f"Service '{service_name}' is already installed"

        # Install the service
        # Use hermes CLI module to run gateway
        app_path = python_path
        app_args = f"-m hermes_cli.main gateway run"
        if profile != "default":
            app_args = f"-m hermes_cli.main -p {profile} gateway run"

        _run_nssm("install", service_name, app_path, app_args)

        # Configure service parameters
        _run_nssm("set", service_name, "AppDirectory", hermes_root, check=False)
        _run_nssm("set", service_name, "Description", description, check=False)
        _run_nssm("set", service_name, "Start", "SERVICE_AUTO_START", check=False)
        _run_nssm("set", service_name, "AppStdout",
                  str(Path.home() / ".hermes" / "logs" / "gateway-stdout.log"), check=False)
        _run_nssm("set", service_name, "AppStderr",
                  str(Path.home() / ".hermes" / "logs" / "gateway-stderr.log"), check=False)
        _run_nssm("set", service_name, "AppRotateFiles", "1", check=False)
        _run_nssm("set", service_name, "AppRotateBytes", "10485760", check=False)  # 10MB

        # Set environment variables
        env_file = Path.home() / ".hermes" / ".env"
        if env_file.exists():
            _run_nssm("set", service_name, "AppEnvironmentExtra",
                      f"HERMES_ENV_FILE={env_file}", check=False)

        return True, f"Service '{service_name}' installed successfully"

    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        return False, f"Failed to install service: {stderr}"
    except Exception as e:
        return False, f"Failed to install service: {e}"


def uninstall_service(profile: str = "default") -> Tuple[bool, str]:
    """Remove the Hermes Gateway Windows Service."""
    service_name = get_service_name(profile)
    try:
        # Stop first if running
        stop_service(profile)
        _run_nssm("remove", service_name, "confirm")
        return True, f"Service '{service_name}' removed"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        return False, f"Failed to remove service: {stderr}"
    except Exception as e:
        return False, f"Failed to remove service: {e}"


def start_service(profile: str = "default") -> Tuple[bool, str]:
    """Start the Hermes Gateway Windows Service."""
    service_name = get_service_name(profile)
    try:
        _run_nssm("start", service_name)
        return True, f"Service '{service_name}' started"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        return False, f"Failed to start service: {stderr}"


def stop_service(profile: str = "default") -> Tuple[bool, str]:
    """Stop the Hermes Gateway Windows Service."""
    service_name = get_service_name(profile)
    try:
        _run_nssm("stop", service_name)
        return True, f"Service '{service_name}' stopped"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        # Don't error if it wasn't running
        if "SERVICE_STOPPED" in stderr or "not installed" in stderr.lower():
            return True, f"Service '{service_name}' was not running"
        return False, f"Failed to stop service: {stderr}"


def restart_service(profile: str = "default") -> Tuple[bool, str]:
    """Restart the Hermes Gateway Windows Service."""
    service_name = get_service_name(profile)
    try:
        _run_nssm("restart", service_name)
        return True, f"Service '{service_name}' restarted"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        return False, f"Failed to restart service: {stderr}"


def get_service_status(profile: str = "default") -> str:
    """Get the current status of the Windows Service.

    Returns one of: 'running', 'stopped', 'paused', 'not_installed', 'unknown'.
    """
    service_name = get_service_name(profile)
    try:
        result = _run_nssm("status", service_name, check=False)
        output = result.stdout.strip()
        if "SERVICE_RUNNING" in output:
            return "running"
        elif "SERVICE_STOPPED" in output:
            return "stopped"
        elif "SERVICE_PAUSED" in output:
            return "paused"
        elif result.returncode != 0:
            return "not_installed"
        return "unknown"
    except Exception:
        return "not_installed"


def is_service_installed(profile: str = "default") -> bool:
    """Check if the service is installed."""
    return get_service_status(profile) != "not_installed"


def is_service_running(profile: str = "default") -> bool:
    """Check if the service is currently running."""
    return get_service_status(profile) == "running"


# ─── Task Scheduler fallback ─────────────────────────────────────────────────

def install_task_scheduler(profile: str = "default") -> Tuple[bool, str]:
    """Install Hermes Gateway as a Task Scheduler job (fallback when NSSM not available).

    Creates a scheduled task that runs at user login.
    """
    task_name = f"HermesGateway{'_' + profile if profile != 'default' else ''}"
    python_path = _get_python_path()
    args = "-m hermes_cli.main gateway run"
    if profile != "default":
        args = f"-m hermes_cli.main -p {profile} gateway run"

    try:
        # Delete existing task if present
        subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True, check=False, timeout=10,
        )

        # Create new task
        result = subprocess.run(
            [
                "schtasks", "/Create",
                "/TN", task_name,
                "/TR", f'"{python_path}" {args}',
                "/SC", "ONLOGON",
                "/RL", "LIMITED",
                "/F",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        return True, f"Task '{task_name}' created (runs at login)"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        return False, f"Failed to create scheduled task: {stderr}"
    except Exception as e:
        return False, f"Failed to create scheduled task: {e}"


def uninstall_task_scheduler(profile: str = "default") -> Tuple[bool, str]:
    """Remove the Task Scheduler job."""
    task_name = f"HermesGateway{'_' + profile if profile != 'default' else ''}"
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return True, f"Task '{task_name}' removed"
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or e.stdout or "").strip()
        return False, f"Failed to remove task: {stderr}"
    except Exception as e:
        return False, f"Failed to remove task: {e}"
