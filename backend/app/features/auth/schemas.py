"""Auth schemas — shared user identity model."""

from pydantic import BaseModel


class UserSchema(BaseModel):
    # UUID from Supabase Auth, sourced from JWT "sub" claim
    id: str
    # Email from JWT "email" claim — empty string if claim is absent
    email: str
