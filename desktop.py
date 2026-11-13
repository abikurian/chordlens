"""Native desktop launcher for ChordLens using pywebview (WebView2) and FastAPI.

- Picks a free port on 127.0.0.1 (never 0.0.0.0).
- Starts FastAPI server in a daemon background thread.
- Displays the UI in a native window with WebView2 (falls back to default browser).
- Ensures single instance via a Windows named mutex.
- Cleans up temporary resources on exit.
"""
# ============================================================
# STEP 0: freeze_support — must be first executable statement
# ============================================================
import multiprocessing
multiprocessing.freeze_support()

# ============================================================
# STEP 1: Set up logging before ANY other import
# ============================================================
import os
import sys
import pathlib
import traceback
import faulthandler
import threading

def _setup_logging():
    """Create log directory and return an open log file handle."""
    # Try %LOCALAPPDATA%\ChordLens\logs first, fall back to %TEMP%
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("TEMP"), "/tmp"):
        if base:
            log_dir = pathlib.Path(base) / "ChordLens" / "logs"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / "chordlens.log"
                fh = open(log_path, "a", encoding="utf-8", errors="replace")
                return fh, log_path
            except Exception:
                continue
    # Last resort: stderr
    return sys.stderr, None


_log_fh, _log_path = _setup_logging()

_orig_stdout = sys.stdout
_orig_stderr = sys.stderr


def _log(msg: str):
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        _log_fh.write(line)
        _log_fh.flush()
    except Exception:
        pass
    # Only write to original console stdout if it existed and is NOT our _LogWriter
    if _orig_stdout is not None and not isinstance(_orig_stdout, _LogWriter):
        try:
            _orig_stdout.write(line)
            _orig_stdout.flush()
        except Exception:
            pass


# Redirect stdout / stderr so windowed PyInstaller builds never get None
class _LogWriter:
    def __init__(self, label: str):
        self._label = label

    def write(self, msg: str):
        if msg and msg.strip():
            for line in msg.splitlines():
                clean = line.strip()
                if clean:
                    _log(f"[{self._label}] {clean}")

    def flush(self):
        try:
            _log_fh.flush()
        except Exception:
            pass

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _LogWriter("stdout")
if sys.stderr is None:
    sys.stderr = _LogWriter("stderr")


def _fatal(title: str, msg: str):
    """Show a Windows message box (or print) and exit with code 1."""
    full = f"{title}\n\n{msg}"
    if _log_path:
        full += f"\n\nLog: {_log_path}"
    _log(f"FATAL: {title}: {msg}")
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, full, "ChordLens — startup error", 0x10)
        except Exception:
            pass
    sys.exit(1)


def _sys_excepthook(exc_type, exc_value, exc_tb):
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _log(f"UNHANDLED EXCEPTION:\n{tb_str}")
    _fatal("Unhandled exception", tb_str[:800])


sys.excepthook = _sys_excepthook


def _thread_excepthook(args):
    tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb))
    _log(f"UNHANDLED THREAD EXCEPTION (thread={args.thread}):\n{tb_str}")


threading.excepthook = _thread_excepthook

# Enable faulthandler to catch segfaults etc.
try:
    faulthandler.enable(file=_log_fh)
except Exception:
    pass

_log("=" * 60)
_log("ChordLens starting up")
_log(f"Python {sys.version}")
_log(f"Frozen: {getattr(sys, 'frozen', False)}")
_log(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
_log(f"CWD: {os.getcwd()}")
_log(f"Log: {_log_path}")

# ============================================================
# STEP 2: Remaining imports (lazy where possible)
# ============================================================
import socket
import time
import urllib.request
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_log(f"ROOT: {ROOT}")

try:
    from backend.paths import DATA_DIR, get_frontend_dir
    _log(f"backend.paths OK — DATA_DIR={DATA_DIR}")
except Exception as exc:
    _fatal("Import error: backend.paths", traceback.format_exc())

try:
    from backend.version import APP_DESCRIPTION, APP_NAME, get_version
    _log(f"backend.version OK — {APP_NAME} v{get_version()}")
except Exception as exc:
    _fatal("Import error: backend.version", traceback.format_exc())


# ============================================================
# Helpers
# ============================================================

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int):
    try:
        import uvicorn
        _log(f"uvicorn imported OK")
        from backend.main import app
        _log(f"backend.main imported OK, starting uvicorn on port {port}")
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except Exception:
        tb = traceback.format_exc()
        _log(f"Server thread crashed:\n{tb}")
        _fatal("Backend server crashed", tb[:800])


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
            _log("Single-instance mutex already held — another instance is running")
            return False
        # Keep handle open for the lifetime of this process
        acquire_single_instance_mutex._handle = handle
        return True
    except Exception:
        _log(f"Mutex check failed (ignored): {traceback.format_exc()}")
        return True


# ============================================================
# Main entry point
# ============================================================

def main():
    _log("main() entered")

    # Fast CLI handling: self-check
    if "--self-check" in sys.argv:
        if _orig_stdout is not None:
            sys.stdout = _orig_stdout
        if _orig_stderr is not None:
            sys.stderr = _orig_stderr
        from backend.self_check import cli_self_check

        code = cli_self_check()
        sys.exit(code)

    # Subprocess module forwarding (e.g. frozen yt-dlp)
    if len(sys.argv) > 1 and sys.argv[1] == "-m" and len(sys.argv) > 2:
        if sys.argv[2] == "yt_dlp":
            if _orig_stdout is not None:
                sys.stdout = _orig_stdout
            if _orig_stderr is not None:
                sys.stderr = _orig_stderr
            import yt_dlp

            sys.exit(yt_dlp.main(sys.argv[3:]))

    if not acquire_single_instance_mutex():
        _log("Exiting: another instance is already running")
        sys.exit(0)

    port = find_free_port()
    _log(f"Starting backend server on port {port}")

    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    _log("Waiting for server to become ready...")
    if not wait_for_server(port):
        _fatal(
            "Backend server failed to start",
            f"The FastAPI backend did not respond on port {port} within 15 seconds.\n"
            f"Check the log for details."
        )

    _log(f"Server is ready on port {port}")

    app_url = f"http://127.0.0.1:{port}"
    title = f"{APP_NAME} v{get_version()}"
    ico_path = get_frontend_dir() / "ChordLens.ico"

    _log(f"Opening window: {title}  url={app_url}  icon={ico_path}")

    try:
        import webview
        _log("pywebview imported OK")

        window = webview.create_window(
            title=title,
            url=app_url,
            width=1280,
            height=860,
            min_size=(360, 500),
            background_color="#F2F5F4",
        )
        def on_closed():
            _log("Window closed event received — exiting cleanly")
            try:
                if hasattr(acquire_single_instance_mutex, "_handle") and acquire_single_instance_mutex._handle:
                    import ctypes
                    ctypes.windll.kernel32.CloseHandle(acquire_single_instance_mutex._handle)
            except Exception:
                pass
            os._exit(0)

        window.events.closed += on_closed

        # Optional test parameter: --test-close-after=SECONDS
        for arg in sys.argv[1:]:
            if arg.startswith("--test-close-after="):
                try:
                    delay = float(arg.split("=", 1)[1])
                    def _closer():
                        time.sleep(delay)
                        _log(f"Auto-closing window after {delay}s test delay")
                        try:
                            window.destroy()
                        except Exception:
                            on_closed()
                    threading.Thread(target=_closer, daemon=True).start()
                except Exception:
                    pass

        _log("WebView window created, starting event loop (edgechromium)")
        webview.start(gui="edgechromium", icon=str(ico_path) if ico_path.exists() else None)
        _log("WebView event loop exited normally")
        on_closed()
    except Exception as exc:
        tb = traceback.format_exc()
        _log(f"Native WebView2 could not start:\n{tb}\nFalling back to default browser.")
        webbrowser.open(app_url)
        # Keep process alive until user closes terminal or presses Ctrl+C
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
