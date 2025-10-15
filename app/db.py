from typing import AsyncGenerator
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "mysql+asyncmy://root:@127.0.0.1:3306/waifu_db"

# ENGINE
async_engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# session maker function
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async_session = sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

# function to create db & tables
async def create_db_and_tables():
    async with async_engine.begin() as conn:
        from app.models import User, Interaction
        await conn.run_sync(SQLModel.metadata.create_all)


# 🧩 Tambahan untuk FastAPI Users
from fastapi_users_db_sqlmodel import SQLModelUserDatabase
from app.models import User

class AsyncSQLModelUserDatabase(SQLModelUserDatabase):
    async def update(self, user):
        await self.session.commit()
        await self.session.refresh(user)
        return user

async def get_user_db(session: AsyncSession):
    yield AsyncSQLModelUserDatabase(session, User)
