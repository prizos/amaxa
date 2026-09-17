#!/usr/bin/env python3
"""
Judge a DRC report for a board whose routing is declared incomplete.

Any violation fails: a short, a clearance, a hole too small is wrong whether or
not the board is finished. Connections not yet routed are counted and printed,
not hidden, and do not fail — the board said, in its own board.mk, that it is
still being drawn.

    python3 tools/drc_report.py cpu1/elec/layout/default/drc.json
"""

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <drc.json>")
    report = json.loads(Path(sys.argv[1]).read_text())
    violations = report["violations"]
    unrouted = report["unconnected_items"]

    print(f"{len(violations)} violations; {len(unrouted)} connections not yet routed")
    for kind, count in sorted(Counter(v["type"] for v in violations).items()):
        print(f"  {count} x {kind}")
    for violation in violations[:20]:
        items = " / ".join(item.get("description", "") for item in violation.get("items", []))
        print(f"    {violation['type']}: {items}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
