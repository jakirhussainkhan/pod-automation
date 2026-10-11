"""HTML page router serving Jinja2 templates."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, get_settings

router: APIRouter = APIRouter(tags=["pages"])

templates: Jinja2Templates = Jinja2Templates(
    directory=str(BASE_DIR / "app" / "templates")
)


def _page_context(active_page: str) -> dict:
    """Build the shared template context for a page."""
    settings = get_settings()
    return {
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "active_page": active_page,
    }


@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    """Render the Overview Dashboard landing page."""
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=_page_context("dashboard"),
    )


@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request) -> HTMLResponse:
    """Render the products management page."""
    return templates.TemplateResponse(
        request=request,
        name="products.html",
        context=_page_context("products"),
    )


@router.get("/posts", response_class=HTMLResponse)
def posts_page(request: Request) -> HTMLResponse:
    """Render the posts management page."""
    return templates.TemplateResponse(
        request=request,
        name="posts.html",
        context=_page_context("posts"),
    )


@router.get("/studio", response_class=HTMLResponse)
def studio_page(request: Request) -> HTMLResponse:
    """Render the AI studio page."""
    return templates.TemplateResponse(
        request=request,
        name="studio.html",
        context=_page_context("studio"),
    )


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request) -> HTMLResponse:
    """Render the activity logs page."""
    return templates.TemplateResponse(
        request=request,
        name="logs.html",
        context=_page_context("logs"),
    )


@router.get("/groups", response_class=HTMLResponse)
def groups_page(request: Request) -> HTMLResponse:
    """Render the Group Lead & DM Funnel workbench page."""
    return templates.TemplateResponse(
        request=request,
        name="groups.html",
        context=_page_context("groups"),
    )


@router.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request) -> HTMLResponse:
    """Render the Facebook Accounts ghost-profile manager page."""
    return templates.TemplateResponse(
        request=request,
        name="accounts.html",
        context=_page_context("accounts"),
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    """Render the settings page."""
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context=_page_context("settings"),
    )
