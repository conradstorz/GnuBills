"""
Windows desktop launcher for GnuCash Bill Processor web UI.

To use: create a Windows shortcut to this file on your desktop.
Double-clicking will start the server (if not already running)
and open the browser at http://localhost:8008.

The .pyw extension runs Python without a console window on Windows.
"""
import subprocess
import sys
import time
import webbrowser
import socket
from pathlib import Path

PORT = 8008
URL = f"http://localhost:{PORT}"
PROJECT_ROOT = Path(__file__).parent


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def main():
    if _port_in_use(PORT):
        # Server already running — just open browser
        webbrowser.open(URL)
        return

    # Start uvicorn server
    # CREATE_NO_WINDOW (0x08000000) prevents a console from appearing on Windows
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000

    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bill_processor.web.app:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(PROJECT_ROOT),
        **kwargs,
    )

    # Wait for server to start (up to 10 seconds)
    started = False
    for _ in range(20):
        if _port_in_use(PORT):
            started = True
            break
        time.sleep(0.5)

    if started:
        webbrowser.open(URL)
    else:
        # .pyw has no console — write failure to a temp file and open it
        import os as _os
        import tempfile
        log_path = Path(tempfile.gettempdir()) / "bill_processor_launch_error.txt"
        with open(log_path, "w") as f:
            f.write(f"GnuCash Bill Processor failed to start on port {PORT}.\n")
            f.write("Check that 'uv' is on your PATH and all dependencies are installed.\n")
            f.write(f"Project root: {PROJECT_ROOT}\n")
        _os.startfile(str(log_path))


if __name__ == "__main__":
    main()
