"""
mac_media.py — macOS Now Playing info via nowplaying-cli or AppleScript.

Install nowplaying-cli for best results:
    brew install nowplaying-cli
"""

import subprocess
from datetime import timedelta


def _run(cmd: list, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _run_osascript(script: str):
    return _run(["osascript", "-e", script])


# ---------------------------------------------------------------------------
# nowplaying-cli (brew install nowplaying-cli)
# ---------------------------------------------------------------------------

def _via_nowplaying_cli():
    """Use nowplaying-cli to get current track info."""
    def get(field):
        out = _run(["nowplaying-cli", "get", field])
        return (out or "").strip()

    title = get("title")
    if not title or title == "(null)":
        return None

    artist   = get("artist")
    album    = get("album")
    dur_s    = get("duration")
    elap_s   = get("elapsedTime")
    rate_s   = get("playbackRate")

    def safe_float(s):
        try:
            return float(s) if s and s != "(null)" else 0.0
        except ValueError:
            return 0.0

    duration = safe_float(dur_s)
    elapsed  = safe_float(elap_s)
    rate     = safe_float(rate_s)
    state    = "Playing" if rate > 0 else "Paused"

    return {
        "title":        title,
        "artist":       artist if artist and artist != "(null)" else "",
        "album":        album  if album  and album  != "(null)" else "",
        "duration_sec": duration,
        "elapsed_sec":  elapsed,
        "state":        state,
        "app_name":     get("bundleIdentifier") or "Unknown",
    }


# ---------------------------------------------------------------------------
# AppleScript fallback for known apps
# ---------------------------------------------------------------------------

_APPS = ["Yandex Music", "Spotify", "Music", "VOX"]


def _via_applescript():
    for app in _APPS:
        is_running = _run_osascript(
            f'tell application "System Events" to return (name of processes) contains "{app}"'
        )
        if not is_running or is_running.lower() != "true":
            continue

        out = _run_osascript(f'''
tell application "{app}"
    try
        set t to name of current track
        set ar to artist of current track
        set al to album of current track
        set dur to duration of current track
        set pos to player position
        set st to player state as string
        return t & "|||" & ar & "|||" & al & "|||" & (dur as string) & "|||" & (pos as string) & "|||" & st
    end try
end tell
''')
        if out and "|||" in out:
            parts = out.split("|||")
            if len(parts) >= 6:
                title, artist, album, dur_s, pos_s, state_s = [p.strip() for p in parts[:6]]
                def sf(s):
                    try: return float(s)
                    except: return 0.0
                sl = state_s.lower()
                state = "Playing" if "play" in sl else "Paused" if "paus" in sl else "Stopped"
                if title:
                    return {
                        "title":        title,
                        "artist":       artist,
                        "album":        album,
                        "duration_sec": sf(dur_s),
                        "elapsed_sec":  sf(pos_s),
                        "state":        state,
                        "app_name":     app,
                    }
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_media_info():
    """
    Returns dict with keys: artist, title, playback_status,
    position (timedelta), session_title, app_name, duration_sec.
    Returns None if nothing is playing.
    """
    info = _via_nowplaying_cli()
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
    """Return list of currently running music app names."""
    running = []
    for app in _APPS:
        out = _run_osascript(
            f'tell application "System Events" to return (name of processes) contains "{app}"'
        )
        if out and out.strip().lower() == "true":
            running.append(app)
    return running
