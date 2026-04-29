"""
mac_media.py — macOS Now Playing info via osascript only.
No direct subprocess calls to external binaries from .app — no process leaks.
"""

import subprocess
from datetime import timedelta


def _run_osascript(script: str, timeout=8):
    """Run AppleScript via osascript. Guaranteed cleanup via finally."""
    proc = None
    try:
        proc = subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            close_fds=True
        )
        stdout, _ = proc.communicate(timeout=timeout)
        return stdout.strip() if proc.returncode == 0 else None
    except Exception:
        return None
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()


# ---------------------------------------------------------------------------
# nowplaying-cli called via osascript "do shell script"
# This way only ONE osascript process is spawned, not nowplaying-cli directly
# ---------------------------------------------------------------------------

def _via_nowplaying_osascript():
    """Call nowplaying-cli through osascript to avoid PyInstaller process leak."""
    script = '''
set fields to {"title", "artist", "album", "duration", "elapsedTime", "playbackRate", "bundleIdentifier"}
set cmd to "/usr/local/bin/nowplaying-cli get"
repeat with f in fields
    set cmd to cmd & " " & f
end repeat
try
    return do shell script cmd
on error
    return ""
end try
'''
    out = _run_osascript(script)
    if not out:
        return None

    parts = out.splitlines()
    if len(parts) < 7:
        parts += [""] * (7 - len(parts))

    def v(s):
        s = (s or "").strip()
        return "" if s in ("(null)", "null") else s

    title = v(parts[0])
    if not title:
        return None

    def sf(s):
        try:
            val = v(s)
            return float(val) if val else 0.0
        except ValueError:
            return 0.0

    rate = sf(parts[5])
    return {
        "title":        title,
        "artist":       v(parts[1]),
        "album":        v(parts[2]),
        "duration_sec": sf(parts[3]),
        "elapsed_sec":  sf(parts[4]),
        "state":        "Playing" if rate > 0 else "Paused",
        "app_name":     v(parts[6]) or "Unknown",
    }


# ---------------------------------------------------------------------------
# AppleScript fallback — all apps checked in ONE osascript call
# ---------------------------------------------------------------------------

_APPS = ["Yandex Music", "Spotify", "Music", "VOX"]


def _via_applescript():
    """Check all known apps in a single osascript call."""
    apps_list = '{"' + '", "'.join(_APPS) + '"}'
    script = f'''
set appList to {apps_list}
repeat with appName in appList
    tell application "System Events"
        set isRunning to (name of processes) contains appName
    end tell
    if isRunning then
        tell application appName
            try
                set t to name of current track
                set ar to artist of current track
                set al to album of current track
                set dur to duration of current track
                set pos to player position
                set st to player state as string
                return t & "|||" & ar & "|||" & al & "|||" & (dur as string) & "|||" & (pos as string) & "|||" & st & "|||" & appName
            end try
        end tell
    end if
end repeat
return ""
'''
    out = _run_osascript(script)
    if not out or "|||" not in out:
        return None

    parts = out.split("|||")
    if len(parts) < 6:
        return None

    title, artist, album, dur_s, pos_s, state_s = [p.strip() for p in parts[:6]]
    app_name = parts[6].strip() if len(parts) > 6 else "Unknown"

    def sf(s):
        try: return float(s)
        except: return 0.0

    sl = state_s.lower()
    state = "Playing" if "play" in sl else "Paused" if "paus" in sl else "Stopped"

    if not title:
        return None

    return {
        "title":        title,
        "artist":       artist,
        "album":        album,
        "duration_sec": sf(dur_s),
        "elapsed_sec":  sf(pos_s),
        "state":        state,
        "app_name":     app_name,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_media_info():
    """
    Returns dict with keys: artist, title, playback_status,
    position (timedelta), session_title, app_name, duration_sec.
    Returns None if nothing is playing.
    """
    info = _via_nowplaying_osascript()
    if info is None:
        info = _via_applescript()
    if info is None:
        return None

    title  = info.get("title",  "").strip()
    artist = info.get("artist", "").strip()
    if not title:
        return None

    return {
        "artist":           artist,
        "title":            title,
        "playback_status":  info.get("state", "Stopped"),
        "position":         timedelta(seconds=info.get("elapsed_sec", 0.0)),
        "session_title":    title,
        "app_name":         info.get("app_name", "Unknown"),
        "duration_sec":     info.get("duration_sec", 0.0),
    }


def get_session_ids():
    """Return list of currently running music app names — single osascript call."""
    apps_list = '{"' + '", "'.join(_APPS) + '"}'
    script = f'''
set appList to {apps_list}
set running to {{}}
repeat with appName in appList
    tell application "System Events"
        if (name of processes) contains appName then
            set end of running to appName
        end if
    end tell
end repeat
set out to ""
repeat with a in running
    set out to out & a & "\\n"
end repeat
return out
'''
    out = _run_osascript(script)
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]
