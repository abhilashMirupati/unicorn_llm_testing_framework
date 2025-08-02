"""
Dashboard Application
---------------------

This module exposes a FastAPI server that allows users to browse
versioned test sets, compare differences and trigger test runs.  It
uses the `VersionManager` to retrieve version information and the
`MCPRouter` to execute test cases on demand.  The UI is rendered
using Jinja2 templates for simplicity.
"""

from fastapi import FastAPI, Depends, Response
from starlette.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import List

from ..config import Config
from ..reporting.reporter import Reporter
from ..mcp_router import MCPRouter, TestCase
from ..executor import TestExecutor
from ..versioning.version_manager import VersionManager
from ..security.auth import get_auth_manager, get_current_user, require_admin, AuthManager
from ..utils.audit import AuditLogger



def create_app() -> FastAPI:
    config = Config()
    version_manager = VersionManager(config)
    reporter = Reporter(config)
    # Create an executor based on configuration
    executor = None
    try:
        use_concurrency = str(config.get("concurrency.enabled", "false")).lower() == "true"
        workers = int(config.get("concurrency.workers", 4))
        if use_concurrency:
            executor = TestExecutor(max_workers=workers)
    except Exception:
        executor = None
    router = MCPRouter(config, reporter, executor=executor)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    # Initialise authentication manager
    auth_manager: AuthManager = get_auth_manager()
    # Initialise audit logger
    audit_logger = AuditLogger(config)

    app = FastAPI(title="Test Set Dashboard")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        version_manager.close()
        router.close()
        # Shutdown executor if present
        if router.executor:
            try:
                router.executor.shutdown()
            except Exception:
                pass
        # Close audit logger
        try:
            audit_logger.close()
        except Exception:
            pass

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, user: dict = Depends(get_current_user), q: str = ""):
        """Home page listing all user stories with optional filtering."""
        # List distinct user stories
        version_manager.cursor.execute("SELECT DISTINCT user_story FROM test_set_versions")
        stories = [row[0] for row in version_manager.cursor.fetchall()]
        # Apply query filter
        if q:
            stories = [s for s in stories if q.lower() in s.lower()]
        # Log view
        audit_logger.log(username=user.get("username"), action=f"Viewed index page (filter={q})")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "stories": stories,
                "user": user,
                "query": q or "",
            },
        )

    @app.get("/versions/{story}", response_class=HTMLResponse)
    async def versions(request: Request, story: str, user: dict = Depends(get_current_user)):
        """Display all versions of a given user story along with a chart of case counts."""
        versions_list = version_manager.list_versions(story)
        # Compute number of test cases per version for chart display
        counts: List[int] = []
        for item in versions_list:
            try:
                cases = version_manager.get_test_cases(item["id"])
                counts.append(len(cases))
            except Exception:
                counts.append(0)
        audit_logger.log(username=user.get("username"), action=f"Viewed versions for story '{story}'")
        return templates.TemplateResponse(
            "versions.html",
            {
                "request": request,
                "story": story,
                "versions": versions_list,
                "user": user,
                "counts": counts,
            },
        )

    @app.get("/compare/{a}/{b}", response_class=HTMLResponse)
    async def compare_versions(request: Request, a: int, b: int, user: dict = Depends(get_current_user)):
        """Compare two versions and show added/removed/unchanged test cases."""
        diff = version_manager.compare_versions(a, b)
        audit_logger.log(username=user.get("username"), action=f"Compared versions {a} vs {b}")
        return templates.TemplateResponse(
            "compare.html", {"request": request, "a": a, "b": b, "diff": diff, "user": user}
        )

    @app.post("/run/{version_id}")
    async def run_version(version_id: int, user: dict = Depends(get_current_user)):
        """Trigger execution of all test cases in a version."""
        cases_data = version_manager.get_test_cases(version_id)
        test_cases_list: List[TestCase] = []
        for tc in cases_data:
            test_cases_list.append(
                TestCase(
                    identifier=tc.get("identifier", f"tc{version_id}"),
                    steps=tc.get("steps", []),
                    type=tc.get("type"),
                )
            )
        # Use executor if configured; otherwise run synchronously
        if router.executor:
            # Submit to thread pool to avoid blocking the request
            router.executor.submit(router.run_all, test_cases_list)
        else:
            router.run_all(test_cases_list)
        audit_logger.log(username=user.get("username"), action=f"Triggered test run for version {version_id}")
        return RedirectResponse(url="/", status_code=303)

    # Authentication routes
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request})

    @app.post("/login")
    async def login(request: Request):
        """
        Process the login form and set a JWT cookie on success.

        This handler relies on ``python-multipart`` to parse form data via
        ``request.form()``.  If parsing fails (e.g. missing fields) the user
        is shown the login page with an error.  On successful authentication
        a JWT is created and stored in an ``access_token`` cookie and the
        user is redirected to the home page.
        """
        # First try to extract credentials from query parameters (e.g. /login?username=...&password=...).
        username = request.query_params.get("username", "")
        password = request.query_params.get("password", "")
        # If credentials are not supplied via query, attempt to parse the body as URL encoded data.
        if not username and not password:
            try:
                # Avoid dependency on python‑multipart by reading raw body
                body_bytes = await request.body()
                from urllib.parse import parse_qs
                data = parse_qs(body_bytes.decode()) if body_bytes else {}
                username = data.get("username", [""])[0]
                password = data.get("password", [""])[0]
            except Exception:
                username = ""
                password = ""
        user = auth_manager.authenticate_user(username, password)
        if not user:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password"},
                status_code=401,
            )
        token = auth_manager.create_access_token({"sub": user["username"]})
        # Set the token in an HTTPOnly cookie so the browser can use it on subsequent requests
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="access_token", value=token, httponly=True)
        audit_logger.log(username=username, action="Logged in")
        return response

    @app.get("/logout")
    async def logout():
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(key="access_token")
        return response

    # Token endpoint for programmatic clients
    @app.post("/token")
    async def token_endpoint(request: Request):
        """Return JWT access token for API clients without python-multipart.

        Accepts urlencoded form fields ``username`` and ``password`` in
        the request body.  If the credentials are valid a JSON
        object with ``access_token`` and ``token_type`` is returned.
        """
        body = await request.body()
        from urllib.parse import parse_qs
        params = parse_qs(body.decode()) if body else {}
        username = params.get("username", [None])[0]
        password = params.get("password", [None])[0]
        if not username or not password:
            return Response(content="Missing credentials", status_code=400)
        user = auth_manager.authenticate_user(str(username), str(password))
        if not user:
            return Response(content="Invalid credentials", status_code=401)
        token = auth_manager.create_access_token({"sub": user["username"]})
        return {"access_token": token, "token_type": "bearer"}

    # List users (admin only)
    @app.get("/users", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
    async def list_users(request: Request, user: dict = Depends(get_current_user)):
        users = auth_manager.users
        audit_logger.log(username=user.get("username"), action="Viewed user list")
        return templates.TemplateResponse(
            "users.html", {"request": request, "users": users, "user": user}
        )

    # Audit log page (admin only)
    @app.get("/audit", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
    async def audit_log_page(request: Request, user: dict = Depends(get_current_user)):
        events = audit_logger.list_events(limit=200)
        audit_logger.log(username=user.get("username"), action="Viewed audit log")
        return templates.TemplateResponse(
            "audit.html", {"request": request, "events": events, "user": user}
        )

    # Endpoint to add a new user (admin only).  Adds user to in‑memory store.
    @app.post("/users/add", dependencies=[Depends(require_admin)])
    async def add_user(request: Request, user: dict = Depends(get_current_user)):
        """Create a new user from urlencoded form data without python-multipart."""
        body = await request.body()
        from urllib.parse import parse_qs
        params = parse_qs(body.decode()) if body else {}
        username = str(params.get("username", [""])[0])
        password = str(params.get("password", [""])[0])
        role = str(params.get("role", ["viewer"])[0])
        if not username or not password:
            return RedirectResponse(url="/users", status_code=303)
        if username in auth_manager.users:
            return RedirectResponse(url="/users", status_code=303)
        from ..security.auth import pwd_context, _passlib_available
        if _passlib_available:
            try:
                password_hash = pwd_context.hash(password)
            except Exception:
                password_hash = password
        else:
            password_hash = password
        auth_manager.users[username] = {"username": username, "password_hash": password_hash, "role": role}
        audit_logger.log(username=user.get("username"), action=f"Added user {username} with role {role}")
        return RedirectResponse(url="/users", status_code=303)

    return app


app = create_app()