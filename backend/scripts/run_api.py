"""Start the API server (port 8003 by default).

On Windows the default Proactor event loop can stop accepting connections
after a client aborts mid-accept (WinError 64), leaving the process alive but
deaf. The selector loop does not have this failure mode, so it is forced here.

Usage (from backend/):  python scripts/run_api.py [--port 8003] [--host 127.0.0.1]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TUTAR X API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level=args.log_level, loop="asyncio")


if __name__ == "__main__":
    main()
