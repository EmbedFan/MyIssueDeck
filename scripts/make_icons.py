"""Make the web icons of the dashboard from the master picture (IS-0007).

    python scripts/make_icons.py

The master is ``src/resources/favicon_my_issuedeck.png`` (large, kept only in the sources).
The small versions are written into the package (``static/img``), so that they are served by the
dashboard and shipped in the wheel, and no page has to download the large original.

Needs Pillow. It is a tool for this script only and not a dependency of the software; the
generated files are committed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "src" / "resources" / "favicon_my_issuedeck.png"
OUT = ROOT / "src" / "issuedeck" / "features" / "dashboard" / "static" / "img"

PNG_SIZES = {
    "favicon-32.png": 32,       # browser tab
    "favicon-48.png": 48,       # high-density tab, shortcut
    "apple-touch-icon.png": 180,  # iOS home screen
    "icon-192.png": 192,        # Android / web manifest
    "icon-512.png": 512,        # web manifest, splash
}
ICO_SIZES = (16, 32, 48)


def square(image: Image.Image) -> Image.Image:
    """The master as a square (padded with transparency when it is not one)."""
    image = image.convert("RGBA")
    side = max(image.size)
    if image.size == (side, side):
        return image
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def main() -> int:
    if not MASTER.exists():
        print(f"master picture not found: {MASTER}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    master = square(Image.open(MASTER))
    for name, size in PNG_SIZES.items():
        master.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)
    # one .ico with several sizes: what browsers ask for at /favicon.ico
    master.resize((256, 256), Image.LANCZOS).save(
        OUT / "favicon.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES],
    )
    manifest = {
        "name": "MyIssueDesk",
        "short_name": "MyIssueDesk",
        "start_url": "/dashboard/",
        "display": "browser",
        "icons": [
            {"src": "/dashboard/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/dashboard/static/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    (OUT.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    for path in sorted(OUT.iterdir()):
        print(f"{path.name:22} {path.stat().st_size:>8} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
