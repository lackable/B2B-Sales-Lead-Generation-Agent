"""Pydantic request/response models for ``/auth/*`` and ``/admin/*``."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from leadgen.db.models import ROLE_USER


class UserOut(BaseModel):
    """Public projection of an account — never the hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class StatusResponse(BaseModel):
    status: str


class SetupRequest(BaseModel):
    username: str
    password: str


class SetupResponse(BaseModel):
    user: UserOut
    recovery_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordChangeResponse(BaseModel):
    user: UserOut
    recovery_code: Optional[str] = None


class PasswordResetRequest(BaseModel):
    username: str
    recovery_code: str
    new_password: str


class RecoveryCodeResponse(BaseModel):
    recovery_code: str


class RegenerateRecoveryCodeRequest(BaseModel):
    password: str


class CreateUserRequest(BaseModel):
    username: str
    role: str = ROLE_USER


class CreatedUserResponse(BaseModel):
    user: UserOut
    temporary_password: str
    recovery_code: str


class UpdateUserRequest(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None


class UserListResponse(BaseModel):
    users: List[UserOut]


class SessionRevokedResponse(BaseModel):
    status: str
    revoked_sessions: int
