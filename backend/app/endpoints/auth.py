from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.dto.auth import LoginRequest, UserOut
from app.errors import bad_request, conflict, unauthorized
from app.security import token_from_cookie
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["认证"])


def _set_session_cookie(response: Response, issued: auth_service.IssuedSession) -> None:
    response.set_cookie(
        settings.session_cookie,
        issued.token,
        max_age=issued.max_age,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


@router.post("/auth/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    response: Response,
    session: DbSession,
) -> UserOut:
    try:
        user = await auth_service.login(session, email=body.email, password=body.password)
    except auth_service.InvalidCredentialsError as error:
        logger.warning("登录失败：邮箱或密码错误，email=%s", body.email)
        raise unauthorized() from error

    issued = await auth_service.issue_session(session, user)
    _set_session_cookie(response, issued)
    return UserOut.model_validate(user)


@router.post("/auth/register", response_model=UserOut)
async def register(
    body: LoginRequest,
    response: Response,
    session: DbSession,
) -> UserOut:
    try:
        user = await auth_service.register(session, email=body.email, password=body.password)
    except auth_service.EmailTakenError as error:
        logger.warning("注册失败：邮箱已注册，email=%s", body.email)
        raise conflict() from error
    except auth_service.WeakPasswordError as error:
        logger.warning("注册失败：密码长度不足，email=%s", body.email)
        raise bad_request() from error

    issued = await auth_service.issue_session(session, user)
    _set_session_cookie(response, issued)
    return UserOut.model_validate(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: DbSession,
) -> Response:
    cookie = request.cookies.get(settings.session_cookie)
    token = token_from_cookie(cookie) if cookie else None
    if token is not None:
        await auth_service.revoke_session(session, token)
    response.delete_cookie(settings.session_cookie, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
