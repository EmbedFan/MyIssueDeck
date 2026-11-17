"""The built-in help of the dashboard (IS-0007).

The pages are generated from Markdown sources (see ``help_build``) and shipped with the package,
one per supported language. The help follows the language the user has chosen.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Request

from issuedeck import __version__
from issuedeck.features.dashboard.help_build import html_path
from issuedeck.features.dashboard.helpers import render
from issuedeck.features.dashboard.i18n import language_from_request
from issuedeck.features.dashboard.routes import _ctx

router = APIRouter(prefix="/dashboard/help", tags=["dashboard"])


@lru_cache(maxsize=8)
def _page(lang: str) -> str | None:
    path = html_path(lang)
    return path.read_text(encoding="utf-8") if path.exists() else None


@router.get("")
async def help_page(request: Request, project: str = ""):
    lang = language_from_request(request)
    page = _page(lang)
    fallback = page is None
    if page is None:
        page = _page("en") or ""
    known = {p.key for p in request.app.state.registry.all_projects()}
    return render(
        "pages/help.html", request,
        # the project the user came from, so the left panel keeps its project views
        **_ctx(request, project if project in known else None),
        active_page="help",
        help_html=page,
        help_fallback=fallback,
        version=__version__,
    )
