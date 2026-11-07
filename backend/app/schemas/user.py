from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Tier = Literal["FREE", "PREMIUM"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    role: str
    subscription_tier: str


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    subscription_tier: Tier = "FREE"


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class TierIn(BaseModel):
    subscription_tier: Tier


class UserPage(BaseModel):
    items: list[UserOut]
    page: int
    page_size: int
    total: int
