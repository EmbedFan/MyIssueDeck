"""Settings page (FEA-0004): theme colours, display and tracking defaults, project
name/description, and runtime API tokens. Changes apply without a restart."""

from __future__ import annotations

import json
import os
import re
import secrets
import tomllib
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import SecretStr

from issuedeck.core.auth import (
    DASHBOARD_SESSION_COOKIE,
    DASHBOARD_SESSION_MAX_AGE_SECONDS,
    make_dashboard_session_cookie,
)
from issuedeck.core.config import (
    ConfigRegistry,
    ProjectConfig,
    TokenConfig,
    load_project_config,
)
from issuedeck.core.config_file import (
    mask_token,
    read_server_text,
    set_api_token,
    set_token_value,
    validate_server_text,
    write_server_text,
)
from issuedeck.core.config_file import update_token as rewrite_token_block
from issuedeck.core.errors import InvalidSetting, ProjectNotFound, TokenNotFound
from issuedeck.core.runtime_settings import (
    LANGUAGES,
    LIVE_EDITING,
    LIVE_EVENTS,
    LIVE_VIEWS,
    THEMES,
    TOKEN_SCOPES,
    WIDGET_INFO,
    WIDGET_SCOPES,
    WIDGET_STATES,
    WIDGET_STATUSES,
    RuntimeSettings,
    clean_scopes,
    clean_token_name,
)
from issuedeck.features.dashboard.helpers import render
from issuedeck.features.dashboard.routes import _ctx
from issuedeck.features.github_sync.service import (
    ConnectionCheck,
    GitHubSettings,
    check_connection,
)

router = APIRouter(prefix="/dashboard/settings", tags=["dashboard"])

ACTOR = "dashboard"
SCOPES_FORM = Form([])


def _runtime(request: Request) -> RuntimeSettings:
    return request.app.state.runtime_settings


def apply_tracking_defaults(registry: ConfigRegistry, default_hours: float | None) -> None:
    """Use the settings value as the default estimated time for new items.

    ``None`` removes the default. The value is applied to every project's
    ``estimated_time`` field, so it takes effect at once.
    """
    for project in registry.all_projects():
        cfg = project.custom_fields.get("estimated_time")
        if cfg is not None and cfg.type == "number":
            cfg.default = default_hours


def _runtime_card(record: dict) -> dict:
    """Template data for a token created in the dashboard (no value is kept for it)."""
    return {
        "kind": "runtime",
        "id": record["id"],
        "name": record["name"],
        "scopes": record["scopes"],
        "masked": "",
        "editable": True,
        "regenerable": True,
    }


async def _render_settings(
    request: Request,
    *,
    project_key: str | None = None,
    error: str | None = None,
    notice: str | None = None,
    new_token: dict | None = None,
    github_check: ConnectionCheck | None = None,
    status_code: int = 200,
):
    registry: ConfigRegistry = request.app.state.registry
    runtime = _runtime(request)
    projects = registry.all_projects()
    selected = None
    if projects:
        selected = next((p for p in projects if p.key == project_key), projects[0])
    server_cfg = registry.server
    env_admin = bool(os.environ.get("ISSUEDECK_API_TOKEN"))
    github_environ = getattr(request.app.state, "github_environ", None)
    github_token_env = runtime.settings()["github"]["token_env"]
    github_token_present = bool(
        (github_environ if github_environ is not None else os.environ).get(
            github_token_env, "",
        )
    )
    return render(
        "pages/settings.html", request,
        # Render in the context of the selected project so the page has the same
        # navigation menu as the other pages.
        **_ctx(request, selected.key if selected else None),
        active_page="settings",
        settings=runtime.settings(),
        project_list=projects,
        selected_project=selected,
        config_editable=_server_toml(request) is not None,
        config_cards=[
            {
                "kind": "config",
                "id": t.name,
                "name": t.name,
                "scopes": sorted(t.normalized_scopes()),
                "masked": mask_token(t.token.get_secret_value()),
                "editable": t.name != "api_token",
                "regenerable": not (t.name == "api_token" and env_admin),
            }
            for t in server_cfg.auth_tokens()
        ],
        runtime_cards=[_runtime_card(record) for record in runtime.public_tokens()],
        audit_entries=runtime.audit_log(20),
        scope_choices=TOKEN_SCOPES,
        widget_statuses=WIDGET_STATUSES,
        widget_scopes=WIDGET_SCOPES,
        widget_states=WIDGET_STATES,
        widget_info=WIDGET_INFO,
        live_views=LIVE_VIEWS,
        live_events=LIVE_EVENTS,
        live_editing=LIVE_EDITING,
        language_choices=LANGUAGES,
        theme_choices=THEMES,
        error=error,
        notice=notice,
        new_token=new_token,
        github_check=github_check,
        github_token_present=github_token_present,
        status_code=status_code,
    )


def _redirect(project_key: str | None = None, notice: str | None = None) -> RedirectResponse:
    url = "/dashboard/settings"
    if project_key:
        url += f"?project={project_key}"
    response = RedirectResponse(url=url, status_code=303)
    if notice:
        response.headers["X-IssueDeck-Notice"] = notice
    return response


@router.get("")
async def settings_page(request: Request, project: str | None = None):
    return await _render_settings(request, project_key=project)


# --- appearance ---------------------------------------------------------------


@router.post("/appearance")
async def save_appearance(
    request: Request,
    light_primary: str = Form(...),
    light_accent: str = Form(...),
    dark_primary: str = Form(...),
    dark_accent: str = Form(...),
):
    try:
        _runtime(request).update_settings(
            {"theme": {
                "light": {"primary": light_primary, "accent": light_accent},
                "dark": {"primary": dark_primary, "accent": dark_accent},
            }},
            actor=ACTOR,
        )
    except InvalidSetting as exc:
        return await _render_settings(request, error=exc.message, status_code=422)
    return _redirect()


@router.post("/appearance/reset")
async def reset_appearance(request: Request):
    _runtime(request).reset_theme(actor=ACTOR)
    return _redirect()


# --- agent sessions widget and live updates (FEA-0006) -------------------------


def _on(value: str | None) -> bool:
    """A checkbox is sent as a value when ticked and not at all when it is not."""
    return value is not None


STATUSES_FORM = Form([], alias="statuses")


@router.post("/agent-widget")
async def save_agent_widget(
    request: Request,
    show_kanban: str | None = Form(None),
    show_overview: str | None = Form(None),
    statuses: list[str] = STATUSES_FORM,
    completed_minutes: str = Form("0"),
    max_sessions: str = Form("8"),
    scope: str = Form("project"),
    initial_state: str = Form("expanded"),
    info_agent: str | None = Form(None),
    info_item: str | None = Form(None),
    info_goal: str | None = Form(None),
    info_last_update: str | None = Form(None),
    info_updates: str | None = Form(None),
):
    try:
        group = {
            "show_kanban": _on(show_kanban),
            "show_overview": _on(show_overview),
            "statuses": statuses,
            "completed_minutes": _whole(completed_minutes, "completed within"),
            "max_sessions": _whole(max_sessions, "maximum sessions"),
            "scope": scope,
            "initial_state": initial_state,
            "info": {
                "agent": _on(info_agent), "item": _on(info_item), "goal": _on(info_goal),
                "last_update": _on(info_last_update), "updates": _on(info_updates),
            },
        }
        _runtime(request).update_settings({"agent_widget": group}, actor=ACTOR)
    except InvalidSetting as exc:
        return await _render_settings(request, error=exc.message, status_code=422)
    return _redirect()


@router.post("/agent-widget/reset")
async def reset_agent_widget(request: Request):
    _runtime(request).reset_group("agent_widget", actor=ACTOR)
    return _redirect()


@router.post("/live")
async def save_live(
    request: Request,
    enabled: str | None = Form(None),
    fallback_seconds: str = Form("30"),
    highlight_seconds: str = Form("3"),
    while_editing: str = Form("notice"),
    view_kanban: str | None = Form(None),
    view_list: str | None = Form(None),
    view_overview: str | None = Form(None),
    view_item: str | None = Form(None),
    event_items: str | None = Form(None),
    event_sessions: str | None = Form(None),
    event_activity: str | None = Form(None),
    indicator: str | None = Form(None),
):
    try:
        group = {
            "enabled": _on(enabled),
            "fallback_seconds": _whole(fallback_seconds, "refresh interval"),
            "highlight_seconds": _whole(highlight_seconds, "highlight time"),
            "while_editing": while_editing,
            "views": {
                "kanban": _on(view_kanban), "list": _on(view_list),
                "overview": _on(view_overview), "item": _on(view_item),
            },
            "events": {
                "items": _on(event_items), "sessions": _on(event_sessions),
                "activity": _on(event_activity),
            },
            "indicator": _on(indicator),
        }
        _runtime(request).update_settings({"live": group}, actor=ACTOR)
    except InvalidSetting as exc:
        return await _render_settings(request, error=exc.message, status_code=422)
    return _redirect()


@router.post("/live/reset")
async def reset_live(request: Request):
    _runtime(request).reset_group("live", actor=ACTOR)
    return _redirect()


# --- GitHub exports (FEA-0008) -------------------------------------------------

@router.post("/github")
async def save_github(
    request: Request,
    repository: str = Form(""),
    branch: str = Form(""),
    folder: str = Form(""),
    token_env: str = Form(""),
    allow_public: str | None = Form(None),
    author_name: str = Form(""),
    author_email: str = Form(""),
):
    group = {
        "repository": repository, "branch": branch, "folder": folder,
        "token_env": token_env, "allow_public": _on(allow_public),
        "author_name": author_name, "author_email": author_email,
    }
    try:
        _runtime(request).update_settings({"github": group}, actor=ACTOR)
    except InvalidSetting as exc:
        return await _render_settings(request, error=exc.message, status_code=422)
    return _redirect()


@router.post("/github/reset")
async def reset_github(request: Request):
    _runtime(request).reset_group("github", actor=ACTOR)
    return _redirect()


@router.post("/github/test")
async def test_github(request: Request):
    """Check token, repository, branch, write access and privacy; writes nothing."""
    settings = GitHubSettings.from_group(_runtime(request).settings()["github"])
    result = await check_connection(
        settings,
        environ=getattr(request.app.state, "github_environ", None),
        transport=getattr(request.app.state, "github_transport", None),
    )
    return await _render_settings(request, github_check=result)


def _whole(raw: str, field: str) -> int:
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise InvalidSetting(f"{field} must be a whole number", details={"field": field}) from exc


# --- display and tracking -------------------------------------------------------


@router.post("/display")
async def save_display(
    request: Request,
    default_language: str = Form(...),
    default_theme: str = Form(...),
):
    try:
        _runtime(request).update_settings(
            {"default_language": default_language, "default_theme": default_theme},
            actor=ACTOR,
        )
    except InvalidSetting as exc:
        return await _render_settings(request, error=exc.message, status_code=422)
    return _redirect()


@router.post("/tracking")
async def save_tracking(request: Request, default_estimated_time: str = Form("")):
    raw = default_estimated_time.strip()
    try:
        value = None if raw == "" else float(raw.replace(",", "."))
    except ValueError:
        return await _render_settings(
            request,
            error="default estimated time must be a number of hours",
            status_code=422,
        )
    try:
        updated = _runtime(request).update_settings(
            {"default_estimated_time": value}, actor=ACTOR,
        )
    except InvalidSetting as exc:
        return await _render_settings(request, error=exc.message, status_code=422)
    apply_tracking_defaults(request.app.state.registry, updated["default_estimated_time"])
    return _redirect()


# --- project name and description ---------------------------------------------


_TOP_KEY = re.compile(r"^\s*(name|description)\s*=")


def rewrite_project_header(text: str, name: str, description: str) -> str:
    """Set the top-level ``name`` and ``description`` of a project TOML file.

    Everything after the first table header is left untouched. Missing keys are
    added at the end of the header section.
    """
    values = {"name": json.dumps(name, ensure_ascii=False),
              "description": json.dumps(description, ensure_ascii=False)}
    out: list[str] = []
    seen: set[str] = set()
    in_header = True
    for line in text.splitlines(keepends=True):
        if in_header and line.lstrip().startswith("["):
            for key in values:
                if key not in seen:
                    out.append(f"{key} = {values[key]}\n")
                    seen.add(key)
            in_header = False
        if in_header:
            match = _TOP_KEY.match(line)
            if match:
                key = match.group(1)
                out.append(f"{key} = {values[key]}\n")
                seen.add(key)
                continue
        out.append(line)
    if in_header:
        for key in values:
            if key not in seen:
                out.append(f"{key} = {values[key]}\n")
    return "".join(out)


@router.post("/projects/{project_key}")
async def save_project(
    project_key: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
):
    registry: ConfigRegistry = request.app.state.registry
    clean_name = name.strip()
    clean_description = description.strip()
    if not clean_name:
        return await _render_settings(
            request, project_key=project_key,
            error="project name is required", status_code=422,
        )
    try:
        current: ProjectConfig = registry.project(project_key)
    except ProjectNotFound:
        return await _render_settings(request, error="project not found", status_code=404)

    path = Path(registry.server.projects_dir) / f"{project_key}.toml"
    if not path.exists():
        return await _render_settings(
            request, project_key=project_key,
            error=f"config file {path.name} not found; the project cannot be edited",
            status_code=422,
        )
    new_text = rewrite_project_header(
        path.read_text(encoding="utf-8"), clean_name, clean_description,
    )
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as exc:
        return await _render_settings(
            request, project_key=project_key,
            error=f"the project file could not be updated: {exc}", status_code=422,
        )
    path.write_text(new_text, encoding="utf-8")
    reloaded = load_project_config(path)
    registry.replace_project(reloaded)
    apply_tracking_defaults(registry, _runtime(request).settings()["default_estimated_time"])
    _runtime(request).record(
        "project.updated", ACTOR,
        {"project": project_key, "changed": ["name", "description"],
         "before": {"name": current.name, "description": current.description}},
    )
    return _redirect(project_key)


# --- tokens -------------------------------------------------------------------
#
# Every token action has two modes. The page's scripts send ``Accept:
# application/json`` and get JSON back, so the token list can change in place
# without reloading the page. Without that header (no JavaScript, or a plain
# form post) the same routes answer with the page or a redirect.


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


async def _fail(request: Request, message: str, status_code: int):
    if _wants_json(request):
        return JSONResponse({"error": message}, status_code=status_code)
    return await _render_settings(request, error=message, status_code=status_code)


def _keep_signed_in(response, request: Request, value: str) -> None:
    """Dashboard sessions are signed with the admin token; re-sign after a change."""
    response.set_cookie(
        DASHBOARD_SESSION_COOKIE,
        make_dashboard_session_cookie(value),
        max_age=DASHBOARD_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/dashboard",
    )


def _config_names(request: Request) -> set[str]:
    return {t.name for t in request.app.state.registry.server.auth_tokens()}


@router.post("/tokens")
async def create_token(
    request: Request,
    name: str = Form(...),
    scopes: list[str] = SCOPES_FORM,
):
    runtime = _runtime(request)
    try:
        record, plaintext = runtime.create_token(
            name, scopes, config_names=_config_names(request), actor=ACTOR,
        )
    except InvalidSetting as exc:
        return await _fail(request, exc.message, 422)
    if _wants_json(request):
        return JSONResponse({**record, "value": plaintext}, status_code=201)
    return await _render_settings(
        request, new_token={**record, "value": plaintext},
        notice=f"Token '{record['name']}' created. Copy it now; it is shown only once.",
    )


@router.get("/tokens/{token_id}/card")
async def token_card(token_id: str, request: Request):
    """One token card as an HTML fragment, inserted into the list after creation."""
    record = next((t for t in _runtime(request).public_tokens() if t["id"] == token_id), None)
    if record is None:
        return await _fail(request, "token not found", 404)
    return render(
        "components/token_card.html", request,
        **_ctx(request),
        tok=_runtime_card(record),
        scope_choices=TOKEN_SCOPES,
        config_editable=_server_toml(request) is not None,
    )


@router.post("/tokens/{token_id}")
async def update_token(
    token_id: str,
    request: Request,
    name: str = Form(...),
    scopes: list[str] = SCOPES_FORM,
):
    try:
        record = _runtime(request).update_token(
            token_id, name=name, scopes=scopes,
            config_names=_config_names(request), actor=ACTOR,
        )
    except TokenNotFound as exc:
        return await _fail(request, exc.message, 404)
    except InvalidSetting as exc:
        return await _fail(request, exc.message, 422)
    if _wants_json(request):
        return JSONResponse(record)
    return _redirect()


@router.post("/tokens/{token_id}/regenerate")
async def regenerate_token(token_id: str, request: Request):
    try:
        record, plaintext = _runtime(request).regenerate_token(token_id, actor=ACTOR)
    except TokenNotFound as exc:
        return await _fail(request, exc.message, 404)
    if _wants_json(request):
        return JSONResponse({**record, "value": plaintext})
    return await _render_settings(
        request, new_token={**record, "value": plaintext},
        notice=f"Token '{record['name']}' regenerated. The old value no longer works.",
    )


@router.post("/tokens/{token_id}/delete")
async def delete_token(token_id: str, request: Request):
    try:
        _runtime(request).delete_token(token_id, actor=ACTOR)
    except TokenNotFound as exc:
        return await _fail(request, exc.message, 404)
    if _wants_json(request):
        return JSONResponse({"deleted": token_id})
    return _redirect()


# --- tokens defined in server.toml (IS-0003) ----------------------------------


def _server_toml(request: Request) -> Path | None:
    path = getattr(request.app.state, "server_toml", None)
    return Path(path) if path else None


def _config_token(request: Request, name: str) -> TokenConfig:
    for token in request.app.state.registry.server.auth_tokens():
        if token.name == name:
            return token
    raise TokenNotFound(f"token '{name}' not found", details={"token": name})


def _config_token_payload(token: TokenConfig, *, value: str | None = None) -> dict:
    payload = {
        "name": token.name,
        "scopes": sorted(token.normalized_scopes()),
        "masked": mask_token(token.token.get_secret_value()),
    }
    if value is not None:
        payload["value"] = value
    return payload


@router.post("/config-tokens/{token_name}/reveal")
async def reveal_config_token(token_name: str, request: Request):
    try:
        token = _config_token(request, token_name)
    except TokenNotFound as exc:
        return await _fail(request, exc.message, 404)
    _runtime(request).record("config_token.revealed", ACTOR, {"token": token_name})
    value = token.token.get_secret_value()
    if _wants_json(request):
        return JSONResponse(_config_token_payload(token, value=value))
    return await _render_settings(
        request,
        new_token={
            "name": token.name,
            "scopes": sorted(token.normalized_scopes()),
            "value": value,
            "revealed": True,
        },
    )


@router.post("/config-tokens/{token_name}/regenerate")
async def regenerate_config_token(token_name: str, request: Request):
    server = request.app.state.registry.server
    try:
        token = _config_token(request, token_name)
        path = _server_toml(request)
        if path is None:
            raise InvalidSetting("the server config file location is not known")
        if token_name == "api_token" and os.environ.get("ISSUEDECK_API_TOKEN"):
            raise InvalidSetting(
                "the administrator token is set by the ISSUEDECK_API_TOKEN environment "
                "variable and cannot be regenerated here",
            )
        new_value = secrets.token_urlsafe(32)
        text = read_server_text(path)
        new_text = (
            set_api_token(text, new_value)
            if token_name == "api_token"
            else set_token_value(text, token_name, new_value)
        )
        validate_server_text(new_text)
        write_server_text(path, new_text)
    except TokenNotFound as exc:
        return await _fail(request, exc.message, 404)
    except InvalidSetting as exc:
        return await _fail(request, exc.message, 422)

    # Apply at once: the auth middleware reads these objects on every request.
    if token_name == "api_token":
        server.api_token = SecretStr(new_value)
    else:
        token.token = SecretStr(new_value)
    scopes = sorted(token.normalized_scopes())
    _runtime(request).record("config_token.regenerated", ACTOR, {"token": token_name})

    if _wants_json(request):
        response = JSONResponse(
            {"name": token_name, "scopes": scopes, "masked": mask_token(new_value),
             "value": new_value},
        )
    else:
        response = await _render_settings(
            request,
            new_token={"name": token_name, "scopes": scopes, "value": new_value},
        )
    if "admin" in scopes:
        _keep_signed_in(response, request, new_value)
    return response


@router.post("/config-tokens/{token_name}")
async def update_config_token(
    token_name: str,
    request: Request,
    name: str = Form(...),
    scopes: list[str] = SCOPES_FORM,
):
    server = request.app.state.registry.server
    try:
        if token_name == "api_token":
            raise InvalidSetting("the administrator token keeps its name and its admin scope")
        token = _config_token(request, token_name)
        path = _server_toml(request)
        if path is None:
            raise InvalidSetting("the server config file location is not known")
        other_config_names = {t.name for t in server.auth_tokens()} - {token_name}
        new_name = clean_token_name(name, other_config_names, _runtime(request).tokens())
        new_scopes = clean_scopes(scopes)
        new_text = rewrite_token_block(
            read_server_text(path), token_name, new_name, new_scopes,
        )
        validate_server_text(new_text)
        write_server_text(path, new_text)
    except TokenNotFound as exc:
        return await _fail(request, exc.message, 404)
    except InvalidSetting as exc:
        return await _fail(request, exc.message, 422)

    before = {"name": token.name, "scopes": sorted(token.normalized_scopes())}
    token.name = new_name
    token.scopes = new_scopes
    _runtime(request).record(
        "config_token.updated", ACTOR,
        {"token": new_name, "before": before, "after": {"name": new_name, "scopes": new_scopes}},
    )
    if _wants_json(request):
        return JSONResponse(_config_token_payload(token))
    return _redirect()
