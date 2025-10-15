from typing import Optional
from sqlmodel import Field, SQLModel
from fastapi_users_db_sqlmodel import SQLModelBaseUserDB
from fastapi_users.schemas import BaseUser, BaseUserCreate, BaseUserUpdate


# === MODEL DATABASE ===
class User(SQLModelBaseUserDB, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, nullable=False)
    hashed_password: str
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    
    nama: str
    nim: str = Field(sa_column_kwargs={"unique": True})


# === SKEMA UNTUK API ===
class UserRead(BaseUser[int]):
    nama: str
    nim: str


class UserCreate(BaseUserCreate):
    nama: str
    nim: str


class UserUpdate(BaseUserUpdate):
    nama: Optional[str] = None
    nim: Optional[str] = None


# === MODEL UNTUK INTERAKSI ===
class Interaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    character_id: str
    message_count: int
    timestamp: str


class InteractionCreate(SQLModel):
    character_id: str
    message_count: int
    timestamp: str
