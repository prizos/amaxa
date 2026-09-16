#!/usr/bin/env python3
"""
Run a board's design source with the network physically unavailable.

The claim in hw/README.md is that a build reaches nothing over the network — no
parts service, no registry, no account. That claim was made once, by hand, and
then stood for months as a property of the pipeline with nothing re-checking it.
A property nobody re-checks is a property that used to be true.

This makes it a build step. `socket.socket`, `socket.create_connection` and
`socket.getaddrinfo` are all replaced with functions that raise, then the board
is built in-process. Anything that so much as resolves a hostname fails loudly
and says what it tried to reach.

    python3 tools/no_network.py led12

It is deliberately not a pytest check: the checks run against a build that has
already happened, and the thing worth proving is about the build itself.
"""

import os
import runpy
import socket
import sys
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent


class NetworkUsed(Exception):
    """The design source tried to reach the network."""


def _blocked(name):
    def refuse(*args, **kwargs):
        raise NetworkUsed(f"socket.{name}{args!r}")

    return refuse


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <board>")
    board = HW_DIR / sys.argv[1]
    source = board / f"{sys.argv[1]}.py"
    if not source.is_file():
        sys.exit(f"no design source at {source}")

    # Not the socket class itself: `ssl` subclasses it at import time, so
    # replacing it breaks the standard library before the design source runs.
    # These are the four ways out.
    socket.socket.connect = _blocked("socket.connect")
    socket.socket.connect_ex = _blocked("socket.connect_ex")
    socket.create_connection = _blocked("create_connection")
    socket.getaddrinfo = _blocked("getaddrinfo")
    socket.gethostbyname = _blocked("gethostbyname")

    (board / "build").mkdir(exist_ok=True)
    os.chdir(board)
    sys.argv = [str(source)]
    try:
        runpy.run_path(str(source), run_name="__main__")
    except NetworkUsed as used:
        print(f"\nThe build reached the network: {used}", file=sys.stderr)
        return 1
    except SystemExit as exit:
        if exit.code:
            print(f"\nThe build failed with sockets blocked: exit {exit.code}",
                  file=sys.stderr)
            return int(exit.code)

    print("Built with socket, create_connection, getaddrinfo and gethostbyname "
          "all raising. Nothing reached the network.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
