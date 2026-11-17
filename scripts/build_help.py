"""Generate the HTML help pages of the dashboard from their Markdown sources (IS-0007).

    python scripts/build_help.py            write src/issuedeck/features/dashboard/help/<lang>.html
    python scripts/build_help.py --check    only compare; exit 1 when a page is out of date

The sources are ``help/src/<lang>.md``; the generated pages are committed and shipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from issuedeck.features.dashboard.help_build import build_all, html_path  # noqa: E402
from issuedeck.features.dashboard.i18n import SUPPORTED_LANGS  # noqa: E402


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for lang, page in build_all(sorted(SUPPORTED_LANGS)).items():
        target = html_path(lang)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current != page:
            stale.append(lang)
            if not check:
                target.write_text(page, encoding="utf-8", newline="\n")
                print(f"wrote {target.relative_to(ROOT)}")
    if check and stale:
        print("out of date: " + ", ".join(stale) + " (run python scripts/build_help.py)")
        return 1
    if not stale:
        print("help pages are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
