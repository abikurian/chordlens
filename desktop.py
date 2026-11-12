"""Native desktop launcher for ChordLens using pywebview (WebView2) and FastAPI.

- Picks a free port on 127.0.0.1 (never 0.0.0.0).
- Starts FastAPI server in a daemon background thread.
- Displays the UI in a native window with WebView2 (falls back to default browser).
- Ensures single instance via a Windows named mutex.
- Cleans up temporary resources on exit.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.paths import DATA_DIR, get_frontend_dir  # noqa: E402
from backend.version import APP_DESCRIPTION, APP_NAME, get_version  # noqa: E402


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int):
    import uvicorn
    from backend.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def wait_for_server(port: int, timeout_sec: float = 15.0) -> bool:
    deadline = time.time() + timeout_sec
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as res:
                if res.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def acquire_single_instance_mutex():
    """Ensure only one instance runs. If another exists, returns False."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        CreateMutexW.restype = wintypes.HANDLE
        ERROR_ALREADY_EXISTS = 183

        mutex_name = "Global\\ChordLensSingleInstanceMutex"
        handle = CreateMutexW(None, False, mutex_name)
        last_error = ctypes.get_last_error()
        if last_error == ERROR_ALREADY_EXISTS:
            return False
        # Keep handle open for the lifetime of this process
        acquire_single_instance_mutex._handle = handle
        return True
    except Exception:
        return True


def main():
    if not acquire_single_instance_mutex():
        print("ChordLens is already running.")
        sys.exit(0)

    port = find_free_port()
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    if not wait_for_server(port):
        print("Error: FastAPI backend failed to start.")
        sys.exit(1)

    app_url = f"http://127.0.0.1:{port}"
    title = f"{APP_NAME} v{get_version()}"
    ico_path = get_frontend_dir() / "ChordLens.ico"

    webview_started = False
    try:
        import webview

        # Attempt to create native window with WebView2
        window = webview.create_window(
            title=title,
            url=app_url,
            width=1280,
            height=860,
            min_size=(360, 500),
            background_color="#F2F5F4",
        )
        webview_started = True
        webview.start(gui="edgechromium", icon=str(ico_path) if ico_path.exists() else None)
    except Exception as exc:
        print(f"Native WebView2 could not start ({exc}). Falling back to default browser.")
        webbrowser.open(app_url)
        # Keep process alive until user closes terminal or presses Ctrl+C
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
