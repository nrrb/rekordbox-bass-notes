"""PyInstaller entry point: run the FastAPI app on a random localhost port and
show it in a native window.

Flow:
  1. set up file logging; single-instance lock in Application Support.
  2. pick a free 127.0.0.1 port.
  3. run uvicorn in a background thread (serving the bundled SPA at ``/``).
  4. open a pywebview window at that URL; register a native file picker so the
     "choose your master.db" fields get an OS dialog.
  5. window closed -> tell uvicorn to exit -> join -> quit.

Falls back to opening the default browser if pywebview can't start.
"""
from __future__ import annotations

import atexit
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

# --- logging & single instance -------------------------------------------------
from backend.logging_setup import setup_logging
from backend.runtime import APP_NAME, config_path

setup_logging()
log = logging.getLogger("launcher")

HOST = "127.0.0.1"
_lock_handle = None  # keep the fd alive for the process lifetime


def _acquire_single_instance_lock() -> bool:
    """True if we got the lock; False if another copy is already running."""
    global _lock_handle
    import fcntl

    lock_path = config_path().parent / "app.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    fh.write(str(os.getpid()))
    fh.flush()
    _lock_handle = fh
    atexit.register(_release_lock, fh, lock_path)
    return True


def _release_lock(fh, lock_path: Path) -> None:
    try:
        fh.close()
        lock_path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --- uvicorn in a thread -----------------------------------------------------
class _ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        import uvicorn

        from backend.main import app

        self._server = uvicorn.Server(
            uvicorn.Config(app, host=HOST, port=port, log_config=None, access_log=False)
        )

    def run(self) -> None:
        self._server.run()

    def wait_until_ready(self, url: str, timeout: float = 20.0) -> bool:
        import urllib.request

        deadline = time.time() + timeout
        while time.time() < deadline:
            if getattr(self._server, "started", False):
                try:
                    urllib.request.urlopen(url + "/api/health", timeout=1).read()
                    return True
                except Exception:  # noqa: BLE001 - not up yet
                    pass
            time.sleep(0.1)
        return False

    def stop(self) -> None:
        self._server.should_exit = True


# --- native file picker (wired into backend.desktop) ------------------------
def _install_file_picker() -> None:
    import webview

    from backend import desktop

    open_dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
    if open_dialog is None:  # pywebview < 5.4
        open_dialog = webview.OPEN_DIALOG

    def pick() -> str | None:
        windows = webview.windows
        if not windows:
            return None
        result = windows[0].create_file_dialog(
            open_dialog,
            file_types=("Rekordbox library (master.db;*.db)", "All files (*.*)"),
        )
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    desktop.set_file_picker(pick)


# --- main ------------------------------------------------------------------
def main() -> int:
    if not _acquire_single_instance_lock():
        log.warning("another instance is already running; exiting")
        print(f"{APP_NAME} is already running.", file=sys.stderr)
        return 0

    port = _free_port()
    url = f"http://{HOST}:{port}"
    log.info("starting %s on %s (frozen=%s)", APP_NAME, url, getattr(sys, "frozen", False))

    server = _ServerThread(port)
    server.start()
    if not server.wait_until_ready(url):
        log.error("backend did not become ready; opening browser fallback anyway")

    headless = os.environ.get("RKBX_NO_WINDOW") == "1"
    try:
        if headless:
            raise RuntimeError("RKBX_NO_WINDOW=1")
        import webview

        _install_file_picker()
        webview.create_window(APP_NAME, url, width=1180, height=820, min_size=(880, 600))
        webview.start()  # blocks until every window is closed
    except Exception as e:  # noqa: BLE001 - no GUI backend: degrade to a browser tab
        if not headless:
            log.warning("pywebview unavailable (%s); falling back to the default browser", e)
            import webbrowser

            webbrowser.open(url)
        else:
            log.info("RKBX_NO_WINDOW=1 — serving headless; Ctrl-C to stop")
        try:
            while server.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    log.info("window closed; shutting down backend")
    server.stop()
    server.join(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
