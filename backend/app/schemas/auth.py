from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

EmailInput = EmailStr
UserNameInput = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
]


class RegisterRequest(BaseModel):
    user_name: UserNameInput
    email: EmailInput
    # Checked in a validator for a readable message; minLength still documents it.
    password: SecretStr = Field(json_schema_extra={"minLength": 8})

    @field_validator("password")
    @classmethod
    def require_eight_characters(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class LoginRequest(BaseModel):
    user_name: UserNameInput | None = None
    email: EmailInput | None = None
    password: SecretStr = Field(min_length=1)

    @field_validator("user_name", "email", mode="before")
    @classmethod
    def normalize_optional_identifier(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def require_login_identifier(self):
        if self.email is None and self.user_name is None:
            raise ValueError("Provide email or user_name.")
        return self


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_name: str
    user_id: int
    email: str
    created_at: datetime
