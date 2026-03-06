#!/usr/bin/env python3
"""
BITWILL Web Server.
Run this to start the web UI and REST API.

Usage:
    python -m bitwill.web.server [--port PORT] [--host HOST] [--mainnet]
"""

import argparse
import os

from .api import create_app


def main():
    parser = argparse.ArgumentParser(
        description="BITWILL Web Server"
    )
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to listen on (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--storage-dir", default=None,
                        help="Wallet storage directory")
    parser.add_argument("--mainnet", action="store_true",
                        help="Use Bitcoin mainnet (default: testnet)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app(
        storage_dir=args.storage_dir,
        testnet=not args.mainnet,
    )

    print(f"\n  BITWILL Web UI")
    print(f"  {'='*40}")
    print(f"  Network:  {'mainnet' if args.mainnet else 'testnet'}")
    print(f"  Address:  http://{args.host}:{args.port}")
    print(f"  Storage:  {args.storage_dir or '~/.bitwill'}")
    print(f"  {'='*40}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
