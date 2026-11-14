"""Session cookies. Names and flags live here only."""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

from app.core.config import Settings

ACCESS_COOKIE = "sb_session"
REFRESH_COOKIE = "sb_refresh"
CSRF_COOKIE = "sb_csrf"
CSRF_HEADER = "X-CSRF-Token"


def refresh_path(settings: Settings) -> str:
    return f"{settings.api_prefix}/auth"  # the refresh cookie is only ever sent to /auth/*


def _set(
    response: Response,
    settings: Settings,
    name: str,
    value: str,
    *,
    expires: datetime,
    path: str,
    httponly: bool,
) -> None:
    response.set_cookie(
        name,
        value,
        expires=expires,
        path=path,
        httponly=httponly,
        secure=settings.secure_cookies,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )


def set_session_cookies(
    response: Response,
    settings: Settings,
    *,
    access_token: str,
    access_expires: datetime,
    refresh_token: str,
    refresh_expires: datetime,
    csrf_token: str,
) -> None:
    _set(
        response,
        settings,
        ACCESS_COOKIE,
        access_token,
        expires=access_expires,
        path="/",
        httponly=True,
    )
    _set(
        response,
        settings,
        REFRESH_COOKIE,
        refresh_token,
        expires=refresh_expires,
        path=refresh_path(settings),
        httponly=True,
    )
    # Not HttpOnly: same-site frontends may read it. The token is also returned in the
    # response body, so cross-site frontends never need to read another site's cookie.
    _set(
        response,
        settings,
        CSRF_COOKIE,
        csrf_token,
        expires=refresh_expires,
        path="/",
        httponly=False,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    for name, path, httponly in (
        (ACCESS_COOKIE, "/", True),
        (REFRESH_COOKIE, refresh_path(settings), True),
        (CSRF_COOKIE, "/", False),
    ):
        response.delete_cookie(
            name,
            path=path,
            httponly=httponly,
            secure=settings.secure_cookies,
            samesite=settings.cookie_samesite,
            domain=settings.cookie_domain,
        )
