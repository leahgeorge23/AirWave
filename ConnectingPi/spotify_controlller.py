#!/usr/bin/env python3
"""
Spotify Web API helper used by pi2_agent.py.

Configuration is read from environment variables:
  SPOTIFY_CLIENT_ID
  SPOTIFY_CLIENT_SECRET
  SPOTIFY_REFRESH_TOKEN
"""

import base64
import os
import threading
import time

try:
    import requests
except Exception:
    requests = None


SPOTIFY_CLIENT_ID     = "ca36b53326bb4d309a48603af9f0be8d"
SPOTIFY_CLIENT_SECRET = "dd70d34f38e84e5fbea1345cfd636389"
SPOTIFY_REFRESH_TOKEN = "AQCQnTW1EukFUFckw19uzkiBUQSXBVaHfUh3I4VHDtcMmVNXxjTeX3VH8Xf3SlADLlFKOWpSjiSBJKePQCy_Kk-jnQJeEGnvU9rW0ZD7yPrlJ57q_hTrFAZsfUmqChVAVU8"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"


_token_lock = threading.Lock()
_access_token = None
_access_token_expiry = 0.0


def _configured():
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN and requests is not None)


def _token_valid():
    return _access_token is not None and time.time() < _access_token_expiry


def _refresh_access_token():
    global _access_token, _access_token_expiry

    if not _configured():
        return False

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
            timeout=4,
        )
    except Exception as exc:
        print(f"[SPOTIFY] Token refresh failed: {exc}")
        return False

    if response.status_code != 200:
        print(f"[SPOTIFY] Token refresh HTTP {response.status_code}: {response.text[:160]}")
        return False

    payload = response.json()
    _access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3600))
    _access_token_expiry = time.time() + max(30, expires_in - 30)
    return bool(_access_token)


def _get_access_token():
    with _token_lock:
        if _token_valid():
            return _access_token
        if _refresh_access_token():
            return _access_token
        return None


def _spotify_request(method, path, params=None, body=None):
    token = _get_access_token()
    if not token:
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
            timeout=4,
        )
    except Exception as exc:
        print(f"[SPOTIFY] Request error: {exc}")
        return False

    # Most playback endpoints return 204 on success.
    if response.status_code in (200, 202, 204):
        return True

    # Refresh once on unauthorized and retry.
    if response.status_code == 401:
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
                    timeout=4,
                )
                if retry.status_code in (200, 202, 204):
                    return True
                response = retry
            except Exception as exc:
                print(f"[SPOTIFY] Retry error: {exc}")
                return False

    print(f"[SPOTIFY] HTTP {response.status_code} {path}: {response.text[:160]}")
    return False


def _device_params():
    # Always use active Spotify Connect device (original behavior).
    return None


def warmup():
    if not _configured():
        print("[SPOTIFY] Not configured; using local media fallback")
        return False
    ok = bool(_get_access_token())
    if ok:
        print("[SPOTIFY] Ready")
    return ok


def play():
    return _spotify_request("PUT", "/me/player/play", params=_device_params())


def pause():
    return _spotify_request("PUT", "/me/player/pause", params=_device_params())


def next_track():
    return _spotify_request("POST", "/me/player/next", params=_device_params())


def previous_track():
    return _spotify_request("POST", "/me/player/previous", params=_device_params())


def set_volume(percent):
    level = max(0, min(100, int(percent)))
    params = {"volume_percent": level}
    return _spotify_request("PUT", "/me/player/volume", params=params)
