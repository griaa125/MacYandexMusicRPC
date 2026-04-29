"""
mac_autostart.py — LaunchAgent-based autostart for macOS.

Replaces winreg + Windows Startup folder logic from the original Windows version.
"""

import os
import sys
import plistlib
import subprocess


LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST_LABEL = "com.makyandexmusicrpc.app"
PLIST_PATH = os.path.join(LAUNCH_AGENTS_DIR, f"{PLIST_LABEL}.plist")


def _exe_path() -> str:
    """Return absolute path to the current executable or script."""
    return os.path.abspath(sys.argv[0])


def is_in_autostart() -> bool:
    """Check whether the LaunchAgent plist exists and is loaded."""
    return os.path.exists(PLIST_PATH)


def enable_autostart() -> bool:
    """Create and load the LaunchAgent plist. Returns True on success."""
    try:
        os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)

        exe = _exe_path()
        # If running as a .py script, use the current Python interpreter
        if exe.endswith(".py"):
            program_args = [sys.executable, exe, "--run-through-startup"]
        else:
            program_args = [exe, "--run-through-startup"]

        plist_data = {
            "Label": PLIST_LABEL,
            "ProgramArguments": program_args,
            "RunAtLoad": True,
            "KeepAlive": False,
            "StandardOutPath": os.path.expanduser(
                f"~/Library/Logs/MacYandexMusicRPC.log"
            ),
            "StandardErrorPath": os.path.expanduser(
                f"~/Library/Logs/MacYandexMusicRPC.err.log"
            ),
        }

        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist_data, f)

        subprocess.run(
            ["launchctl", "load", "-w", PLIST_PATH],
            check=True, capture_output=True
        )
        return True
    except Exception as e:
        print(f"[MacYandexMusicRPC] Failed to enable autostart: {e}")
        return False


def disable_autostart() -> bool:
    """Unload and remove the LaunchAgent plist. Returns True on success."""
    try:
        if os.path.exists(PLIST_PATH):
            subprocess.run(
                ["launchctl", "unload", "-w", PLIST_PATH],
                capture_output=True
            )
            os.remove(PLIST_PATH)
        return True
    except Exception as e:
        print(f"[MacYandexMusicRPC] Failed to disable autostart: {e}")
        return False


def toggle_autostart(enable: bool) -> bool:
    if enable:
        return enable_autostart()
    else:
        return disable_autostart()
