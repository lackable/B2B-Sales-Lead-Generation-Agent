"""User administration endpoints: ``/admin/users/*`` (administrators only)."""

from fastapi import APIRouter, Depends, Request

from leadgen.auth.dependencies import get_auth_service, request_context, require_admin
from leadgen.auth.schemas import (
    CreatedUserResponse,
    CreateUserRequest,
    SessionRevokedResponse,
    UpdateUserRequest,
    UserListResponse,
    UserOut,
)
from leadgen.auth.service import AuthService
from leadgen.db.models import User

router = APIRouter(tags=["admin"], prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/users", response_model=UserListResponse)
def list_users(service: AuthService = Depends(get_auth_service)) -> UserListResponse:
    return UserListResponse(users=[UserOut.model_validate(user) for user in service.list_users()])


@router.post("/users", response_model=CreatedUserResponse, status_code=201)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
) -> CreatedUserResponse:
    """Create an account. The temporary password must be changed at first login."""
    created = service.create_user(
        username=payload.username, role=payload.role, created_by=admin, ctx=request_context(request)
    )
    return CreatedUserResponse(
        user=UserOut.model_validate(created.user),
        temporary_password=created.temporary_password,
        recovery_code=created.recovery_code,
    )


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    """Enable/disable an account or change its role."""
    user = service.update_user(
        user_id=user_id,
        is_active=payload.is_active,
        role=payload.role,
        acting_user=admin,
        ctx=request_context(request),
    )
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/revoke-sessions", response_model=SessionRevokedResponse)
def revoke_sessions(
    user_id: str,
    service: AuthService = Depends(get_auth_service),
) -> SessionRevokedResponse:
    """Force an account to log out everywhere."""
    count = service.revoke_user_sessions(user_id)
    return SessionRevokedResponse(status="revoked", revoked_sessions=count)
