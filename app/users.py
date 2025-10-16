from typing import Optional
from fastapi import Depends, Request # <-- 1. Tambahkan impor 'Request'
from fastapi_users import FastAPIUsers, BaseUserManager, IntegerIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.password import PasswordHelper
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi_users_db_sqlmodel import SQLModelUserDatabase

from app.db import get_async_session
from app.models import User, UserCreate


# ====== KONFIGURASI DASAR ======
SECRET = "e1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2"


# === Database Adapter yang Benar ===
class CustomSQLModelUserDatabase(SQLModelUserDatabase[User, int]):
    async def get_by_email(self, email: str) -> Optional[User]:
        statement = select(self.user_model).where(self.user_model.email == email)
        results = await self.session.exec(statement)
        return results.first()

    async def get(self, id: int) -> Optional[User]:
        return await self.session.get(self.user_model, id)


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield CustomSQLModelUserDatabase(session, User)


# === User Manager ===
class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    password_helper = PasswordHelper()

    def __init__(self, user_db):
        super().__init__(user_db)
        self.session: AsyncSession = user_db.session

    # --- 2. PERBAIKAN DI SINI ---
    async def create(
        self,
        user_create: UserCreate,
        safe: bool = False,
        request: Optional[Request] = None, # Tambahkan parameter 'request'
    ) -> User:
        # Isi fungsi ini tetap sama, hanya 'signature'-nya yang diubah
        create_dict = user_create.model_dump()
        hashed_password = self.password_helper.hash(create_dict["password"])
        create_dict["hashed_password"] = hashed_password
        del create_dict["password"]

        create_dict["is_active"] = True
        create_dict["is_superuser"] = False
        create_dict["is_verified"] = False

        user = User(**create_dict)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


# === JWT Auth ===
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# === FastAPI Users Factory ===
fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

# === Dependency untuk endpoint ===
current_active_user = fastapi_users.current_user(active=True)

