"""Development launcher for the AgriTech API.

Usage (from anywhere)::

    python backend/run.py
    python backend/run.py --port 8080
    python backend/run.py --no-reload

It is equivalent to::

    cd backend
    python -m uvicorn app.main:app --reload --port 8000

but fixes ``sys.path`` and the working directory first, so it also works when
the backend folder is not the current directory (IDEs, shortcuts, etc.).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent


def _port_is_free(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AgriTech FastAPI server.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload (it is on by default for development).",
    )
    args = parser.parse_args()

    if not _port_is_free(args.host, args.port):
        raise SystemExit(
            f"Port {args.port} is already in use (host {args.host}).\n"
            "Another server is still running - stop it (or use --port 8001).\n"
            "Windows: find it with  Get-NetTCPConnection -LocalPort "
            f"{args.port} -State Listen\n"
            "then stop it with     Stop-Process -Id <OwningProcess>"
        )

    # ``app`` must be importable both here and in uvicorn's reloader child.
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=[str(BACKEND_DIR / "app")],
    )


if __name__ == "__main__":
    main()
