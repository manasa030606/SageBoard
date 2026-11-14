"""Sign up, sign in, refresh, sign out, current user.

Sessions are cookies: ``sb_session`` (short-lived JWT, HttpOnly), ``sb_refresh``
(rotating opaque token, HttpOnly, sent only to /auth) and ``sb_csrf`` (double-submit
token, also returned in the body as ``csrf_token``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    AuthServiceDep,
    CurrentUser,
    RateLimiterDep,
    SessionDep,
    SettingsDep,
    client_ip,
    csrf_protect,
    enforce,
)
from app.auth.cookies import CSRF_COOKIE, REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from app.auth.tokens import new_csrf_token
from app.core.config import Settings
from app.schemas.auth import LoginRequest, RegisterRequest, SessionOut, UserOut
from app.schemas.errors import ErrorResponse
from app.services.auth import IssuedSession, normalise_email

router = APIRouter(prefix="/auth", tags=["auth"])
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 409, 422, 429, 503)
}
LOGIN_WINDOW_S = 60
REGISTER_WINDOW_S = 3600
IP_LOGIN_MULTIPLIER = 4  # one address may try a few different accounts (shared networks)


def _respond(response: Response, settings: Settings, issued: IssuedSession) -> SessionOut:
    set_session_cookies(
        response,
        settings,
        access_token=issued.access_token,
        access_expires=issued.access_expires,
        refresh_token=issued.refresh_token,
        refresh_expires=issued.refresh_expires,
        csrf_token=issued.csrf_token,
    )
    return SessionOut(
        user=UserOut.model_validate(issued.user),
        csrf_token=issued.csrf_token,
        auth_mode=settings.auth_mode,
    )


@router.post(
    "/register",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
    summary="Create an account and sign in",
)
async def register(  # noqa: PLR0917 - FastAPI dependencies
    body: RegisterRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    session: SessionDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> SessionOut:
    ip = client_ip(request)
    enforce(
        limiter,
        f"register:{ip}",
        settings.registrations_per_hour,
        REGISTER_WINDOW_S,
        "Too many new accounts from this network. Please try again later.",
    )
    issued = await auth.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return _respond(response, settings, issued)


@router.post("/login", response_model=SessionOut, responses=ERRORS, summary="Sign in")
async def login(  # noqa: PLR0917 - FastAPI dependencies
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    session: SessionDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> SessionOut:
    ip = client_ip(request)
    per_account = settings.login_attempts_per_minute
    message = "Too many sign-in attempts. Please wait a minute and try again."
    enforce(
        limiter, f"login:{ip}:{normalise_email(body.email)}", per_account, LOGIN_WINDOW_S, message
    )
    enforce(limiter, f"login-ip:{ip}", per_account * IP_LOGIN_MULTIPLIER, LOGIN_WINDOW_S, message)
    issued = await auth.login(
        email=body.email,
        password=body.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return _respond(response, settings, issued)


# Not CSRF-checked, on purpose: after a page reload the browser has no CSRF token in
# memory yet, and refresh is how it gets one. A forged cross-site refresh can only
# rotate the victim's own tokens into the victim's own cookie jar; the attacker can't
# read the response. The refresh cookie is also only ever sent to /auth/*.
@router.post(
    "/refresh",
    response_model=SessionOut,
    responses=ERRORS,
    summary="Rotate the refresh token and get a new access token",
)
async def refresh(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> SessionOut:
    issued = await auth.refresh(
        request.cookies.get(REFRESH_COOKIE),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return _respond(response, settings, issued)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    dependencies=[Depends(csrf_protect)],
    summary="Sign out (revokes this login's refresh tokens)",
)
async def logout(
    request: Request, auth: AuthServiceDep, session: SessionDep, settings: SettingsDep
) -> Response:
    await auth.logout(request.cookies.get(REFRESH_COOKIE), ip=client_ip(request))
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookies(response, settings)
    return response


@router.get("/me", response_model=SessionOut, responses=ERRORS, summary="The signed-in user")
async def me(
    request: Request, response: Response, user: CurrentUser, settings: SettingsDep
) -> SessionOut:
    csrf = request.cookies.get(CSRF_COOKIE) or ""
    if settings.auth_mode == "session" and not csrf:
        # Cookie lost (e.g. cleared by the browser) while the session survived: re-issue.
        csrf = new_csrf_token()
        response.set_cookie(
            CSRF_COOKIE,
            csrf,
            path="/",
            httponly=False,
            secure=settings.secure_cookies,
            samesite=settings.cookie_samesite,
            domain=settings.cookie_domain,
        )
    return SessionOut(
        user=UserOut.model_validate(user), csrf_token=csrf, auth_mode=settings.auth_mode
    )
