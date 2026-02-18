#!/usr/bin/env python3
"""
Spotify Web API helper used by pi2_agent.py.

Credentials loaded in priority order:
  1. config.py (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN)
  2. Environment variables (same names)
  3. Hardcoded defaults (placeholder values)

Token auto-refreshes before expiry, so it never expires.
"""

import base64
import os
import threading
import time
import urllib3

# Disable SSL warnings for UCLA network
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
except Exception:
    requests = None

# Try to import from config.py first (preferred method)
try:
    from config import (
        SPOTIFY_CLIENT_ID,
        SPOTIFY_CLIENT_SECRET,
        SPOTIFY_REFRESH_TOKEN,
    )
    print("[SPOTIFY] Loaded credentials from config.py")
except ImportError:
    # Fall back to environment variables
    SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN", "")
    
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN:
        print("[SPOTIFY] Loaded credentials from environment variables")
    else:
        print("[SPOTIFY] WARNING: No credentials found in config.py or environment")
        print("[SPOTIFY] Run 'python3 launcher.py --setup' to configure Spotify")

SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"

# Token management
_token_lock = threading.Lock()
_access_token = None
_access_token_expiry = 0.0


def _configured():
    """Check if Spotify is properly configured."""
    return bool(
        SPOTIFY_CLIENT_ID and 
        SPOTIFY_CLIENT_SECRET and 
        SPOTIFY_REFRESH_TOKEN and 
        requests is not None
    )


def _token_valid():
    """Check if current access token is still valid."""
    return _access_token is not None and time.time() < _access_token_expiry


def _refresh_access_token():
    """
    Refresh the access token using the refresh token.
    Returns True if successful, False otherwise.
    """
    global _access_token, _access_token_expiry

    if not _configured():
        print("[SPOTIFY] Not configured - missing credentials or requests library")
        return False

    # Encode credentials for Basic auth
    auth = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode("utf-8")
    auth_b64 = base64.b64encode(auth).decode("ascii")

    try:
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": SPOTIFY_REFRESH_TOKEN,
            },
            timeout=5,
            verify=False,  # Disabled for UCLA network compatibility
        )
    except Exception as exc:
        print(f"[SPOTIFY] Token refresh request failed: {exc}")
        return False

    if response.status_code != 200:
        print(f"[SPOTIFY] Token refresh HTTP {response.status_code}: {response.text[:200]}")
        return False

    payload = response.json()
    _access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3600))
    
    # Refresh 30 seconds before expiry to be safe
    _access_token_expiry = time.time() + max(30, expires_in - 30)
    
    return bool(_access_token)


def _get_access_token():
    """
    Get a valid access token, refreshing if necessary.
    Returns token string or None if unavailable.
    """
    with _token_lock:
        # Return existing token if still valid
        if _token_valid():
            return _access_token
        
        # Refresh token
        if _refresh_access_token():
            return _access_token
        
        return None


def _spotify_request(method, path, params=None, body=None):
    """
    Make an authenticated request to the Spotify API.
    Returns True if successful (200-204), False otherwise.
    """
    token = _get_access_token()
    if not token:
        print("[SPOTIFY] No valid access token available")
        return False

    try:
        response = requests.request(
            method,
            f"https://api.spotify.com/v1{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            params=params,
            json=body,
            timeout=5,
            verify=False,  # Disabled for UCLA network compatibility
        )
    except Exception as exc:
        print(f"[SPOTIFY] Request error ({method} {path}): {exc}")
        return False

    # Success codes
    if response.status_code in (200, 202, 204):
        return True

    # Handle 401 Unauthorized - refresh token and retry once
    if response.status_code == 401:
        print("[SPOTIFY] Token expired, refreshing...")
        with _token_lock:
            if _refresh_access_token():
                token = _access_token
            else:
                token = None
        
        if token:
            try:
                retry = requests.request(
                    method,
                    f"https://api.spotify.com/v1{path}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    params=params,
                    json=body,
                    timeout=5,
                    verify=False,
                )
                if retry.status_code in (200, 202, 204):
                    return True
                response = retry
            except Exception as exc:
                print(f"[SPOTIFY] Retry error: {exc}")
                return False

    # Log failures
    print(f"[SPOTIFY] HTTP {response.status_code} {method} {path}: {response.text[:200]}")
    return False


def _device_params():
    """
    Return device parameters for API calls.
    None means use currently active device.
    """
    return None


def warmup():
    """
    Warm up the Spotify connection at startup.
    Pre-fetches a valid access token.
    Returns True if configured and working, False otherwise.
    """
    if not _configured():
        print("[SPOTIFY] Not configured - run 'python3 launcher.py --setup' to configure")
        return False
    
    # Try to get a token
    if _get_access_token():
        print("[SPOTIFY] ✓ Ready")
        return True
    else:
        print("[SPOTIFY] ✗ Failed to get access token - check credentials")
        return False


# ============================================================
# Public API - Playback Controls
# ============================================================

def play():
    """Resume playback on the active Spotify device."""
    return _spotify_request("PUT", "/me/player/play", params=_device_params())


def pause():
    """Pause playback on the active Spotify device."""
    return _spotify_request("PUT", "/me/player/pause", params=_device_params())


def next_track():
    """Skip to next track on the active Spotify device."""
    return _spotify_request("POST", "/me/player/next", params=_device_params())


def previous_track():
    """Go to previous track on the active Spotify device."""
    return _spotify_request("POST", "/me/player/previous", params=_device_params())


def set_volume(percent):
    """
    Set Spotify volume on the active device.
    
    Args:
        percent: Volume level 0-100
        
    Returns:
        True if successful, False otherwise
    """
    level = max(0, min(100, int(percent)))
    params = {"volume_percent": level}
    return _spotify_request("PUT", "/me/player/volume", params=params)


def get_status():
    """
    Get current playback status (for debugging).
    Returns dict with playback info or None.
    """
    token = _get_access_token()
    if not token:
        return None
    
    try:
        response = requests.get(
            "https://api.spotify.com/v1/me/player",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
            verify=False,
        )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 204:
            return {"message": "No active playback"}
        else:
            return None
    except Exception:
        return None