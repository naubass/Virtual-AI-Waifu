from typing import AsyncGenerator
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "mysql+asyncmy://root:@127.0.0.1:3306/waifu_db"

async_engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# --- PERUBAHAN DI SINI ---
# Buat sessionmaker sekali saja dan ekspor agar bisa digunakan di file lain
# Ini adalah praktik terbaik dan memungkinkan kita membuat sesi independen.
AsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False
)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Fungsi ini sekarang khusus untuk dependency injection FastAPI per-request.
    """
    async with AsyncSessionLocal() as session:
        yield session

async def create_db_and_tables():
    async with async_engine.begin() as conn:
        # Impor semua model Anda di sini agar terdeteksi oleh SQLModel
        from app.models import User, Interaction, ChatMessage
        await conn.run_sync(SQLModel.metadata.create_all)

