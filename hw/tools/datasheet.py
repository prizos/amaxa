#!/usr/bin/env python3
"""
Fetch a datasheet, render a figure from it, and keep the figure as evidence.

Several parts on these boards carry a review note saying a fact "needs a human
eye": the pin-out, the cathode, the exposed pad, all drawn rather than written,
in a PDF with no text layer. That note was half right. The fact does need an
eye — but a drawing rendered to an image can be looked at by whoever is doing
the review, and what the note was really recording is that nobody had looked.

So: fetch the manufacturer's own document, render the page region that carries
the claim, and commit the crop beside the part's note. The claim then rests on
a picture anyone can check in five seconds, from a document identified by its
SHA-256, instead of on someone's memory of having looked once.

    tools/datasheet.py fetch dmp10h400se https://www.diodes.com/assets/...pdf
    tools/datasheet.py page dmp10h400se 1                    # whole page, to find the figure
    tools/datasheet.py evidence cpu1 SOT223 pinout dmp10h400se 1 \\
        --crop 850,1030,900,520 --shows "Top View: tab D, leads S/D/G"

The PDFs themselves are not committed - they are megabytes, and they are the
manufacturer's to distribute. `evidence` records the URL and the hash, so a
reviewer who wants the original can fetch the same bytes and prove it.

Nothing here runs during a build. `make offline` is a claim about generating
the design, and this generates nothing: it reads documents so a person can
write a review note that is true.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

HW = Path(__file__).resolve().parent.parent
CACHE = HW / ".datasheets"
AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _pdf(name: str) -> Path:
    path = CACHE / f"{name}.pdf"
    if not path.is_file():
        sys.exit(f"no datasheet cached as {name!r}; fetch it first")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(args) -> int:
    CACHE.mkdir(exist_ok=True)
    out = CACHE / f"{args.name}.pdf"
    request = urllib.request.Request(args.url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    if not body.startswith(b"%PDF"):
        sys.exit(f"{args.url} did not return a PDF (starts {body[:16]!r})")
    out.write_bytes(body)
    print(f"{out}  {len(body)} bytes\nsha256 {_sha256(out)}")
    return 0


def _render(pdf: Path, page: int, dpi: int, crop: str | None, stem: Path) -> Path:
    cmd = ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page)]
    if crop:
        x, y, w, h = (int(v) for v in crop.split(","))
        cmd += ["-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h)]
    cmd += [str(pdf), str(stem)]
    subprocess.run(cmd, check=True)
    # pdftoppm appends the page number, with a width that depends on the count.
    made = sorted(stem.parent.glob(f"{stem.name}-*.png"))
    if not made:
        sys.exit("pdftoppm wrote nothing")
    final = stem.with_suffix(".png")
    made[0].replace(final)
    for extra in made[1:]:
        extra.unlink()
    return final


def page(args) -> int:
    pdf = _pdf(args.name)
    out = _render(pdf, args.page, args.dpi, args.crop, CACHE / f"{args.name}-p{args.page}")
    print(out)
    return 0


def evidence(args) -> int:
    pdf = _pdf(args.name)
    part = HW / args.board / "parts" / args.lib
    if not part.is_dir():
        sys.exit(f"no part library at {part}")
    where = part / "evidence"
    where.mkdir(exist_ok=True)

    _render(pdf, args.page, args.dpi, args.crop, where / args.slug)

    index = where / "sources.json"
    records = json.loads(index.read_text()) if index.is_file() else {}
    records[args.slug] = {
        "document": args.title,
        "url": args.url,
        "sha256": _sha256(pdf),
        "page": args.page,
        "dpi": args.dpi,
        "crop": args.crop,
        "shows": args.shows,
        "assumes": args.assumes,
        "read": date.today().isoformat(),
    }
    index.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    print(f"{where / (args.slug + '.png')}\n{index}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="download a datasheet into the cache")
    f.add_argument("name")
    f.add_argument("url")
    f.set_defaults(func=fetch)

    p = sub.add_parser("page", help="render a page, to find the figure")
    p.add_argument("name")
    p.add_argument("page", type=int)
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--crop", help="x,y,w,h in pixels at this dpi")
    p.set_defaults(func=page)

    e = sub.add_parser("evidence", help="commit a figure beside a part's note")
    e.add_argument("board")
    e.add_argument("lib")
    e.add_argument("slug")
    e.add_argument("name")
    e.add_argument("page", type=int)
    e.add_argument("--dpi", type=int, default=200)
    e.add_argument("--crop", help="x,y,w,h in pixels at this dpi")
    e.add_argument("--title", required=True, help="the document, as it names itself")
    e.add_argument("--url", required=True)
    e.add_argument("--shows", required=True, help="what the figure settles")
    e.add_argument("--assumes", default="", help="what it does not settle, and is taken on convention")
    e.set_defaults(func=evidence)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
