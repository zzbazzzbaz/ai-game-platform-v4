from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.models import User


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(id=str(user.id), email=user.email)
