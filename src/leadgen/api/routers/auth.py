"""Authentication endpoints: ``/auth/*``.

Handlers are synchronous so FastAPI runs them in a threadpool — argon2 hashing
would otherwise block the event loop.
"""

from fastapi import APIRouter, Depends, Request, Response

from leadgen import config
from leadgen.auth.dependencies import current_session, get_auth_service, request_context, require_user
from leadgen.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordChangeResponse,
    PasswordResetRequest,
    RecoveryCodeResponse,
    RegenerateRecoveryCodeRequest,
    SetupRequest,
    SetupResponse,
    SetupStatusResponse,
    StatusResponse,
    UserOut,
)
from leadgen.auth.service import AuthService, AuthenticatedSession, SessionGrant, SetupResult
from leadgen.db.models import User

router = APIRouter(tags=["auth"], prefix="/auth")


def _set_session_cookie(response: Response, grant: SessionGrant) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=grant.token,
        max_age=config.SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=config.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
    )


@router.get("/setup-status", response_model=SetupStatusResponse)
def setup_status(service: AuthService = Depends(get_auth_service)) -> SetupStatusResponse:
    """Whether the first-run setup screen is still required."""
    return SetupStatusResponse(needs_setup=service.needs_setup())


@router.post("/setup", response_model=SetupResponse)
def setup(
    payload: SetupRequest,
    response: Response,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> SetupResponse:
    """Create the first account (an admin) and sign it in."""
    result: SetupResult = service.setup(payload.username, payload.password, request_context(request))
    _set_session_cookie(response, result)
    return SetupResponse(user=UserOut.model_validate(result.user), recovery_code=result.recovery_code)


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    grant = service.login(payload.username, payload.password, request_context(request))
    _set_session_cookie(response, grant)
    return UserOut.model_validate(grant.user)


@router.post("/logout", response_model=StatusResponse)
def logout(
    response: Response,
    request: Request,
    authenticated: AuthenticatedSession = Depends(current_session),
    service: AuthService = Depends(get_auth_service),
) -> StatusResponse:
    service.logout(authenticated, request_context(request))
    _clear_session_cookie(response)
    return StatusResponse(status="logged_out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> UserOut:
    """The signed-in account, including ``must_change_password``."""
    return UserOut.model_validate(user)


@router.post("/password/change", response_model=PasswordChangeResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(current_session),
    service: AuthService = Depends(get_auth_service),
) -> PasswordChangeResponse:
    """Change the current password; a forced first change also rotates the recovery code."""
    recovery_code = service.change_password(
        authenticated, payload.current_password, payload.new_password, request_context(request)
    )
    return PasswordChangeResponse(user=UserOut.model_validate(authenticated.user), recovery_code=recovery_code)


@router.post("/password/reset", response_model=RecoveryCodeResponse)
def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> RecoveryCodeResponse:
    """Reset a forgotten password with the recovery code; every session is revoked."""
    code = service.reset_password(
        payload.username, payload.recovery_code, payload.new_password, request_context(request)
    )
    return RecoveryCodeResponse(recovery_code=code)


@router.post("/recovery-code/regenerate", response_model=RecoveryCodeResponse)
def regenerate_recovery_code(
    payload: RegenerateRecoveryCodeRequest,
    request: Request,
    user: User = Depends(require_user),
    service: AuthService = Depends(get_auth_service),
) -> RecoveryCodeResponse:
    """Issue a fresh recovery code after confirming the password."""
    code = service.regenerate_recovery_code(user, payload.password, request_context(request))
    return RecoveryCodeResponse(recovery_code=code)
