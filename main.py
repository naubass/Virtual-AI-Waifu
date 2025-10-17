from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Literal
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlmodel import select
from sqlalchemy.ext.asyncio.session import AsyncSession

# Impor dari file-file konfigurasi
from app.db import create_db_and_tables, get_async_session
from app.models import User, UserCreate, UserRead, UserUpdate, ChatMessage
from app.users import auth_backend, current_active_user, fastapi_users
from app.recomender import hybrid_recommendation
from app.waifu import WAIFU
# Impor LangGraph agent Anda
from app.agent import chat_agent 
from langchain_core.messages import HumanMessage, AIMessage

from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Menangani event startup dan shutdown. Ini adalah cara modern pengganti on_event.
    """
    print("Startup: Membuat tabel database...")
    await create_db_and_tables()
    yield
    print("Shutdown: Aplikasi dimatikan.")

# Setup App
app = FastAPI(title="WaifuChat AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model Pydantic untuk Request Body
class Message(BaseModel):
    role: Literal["human", "ai"]
    content: str

class ChatRequest(BaseModel):
    character_id: str
    messages: List[Message] = Field(
        default_factory=list,
        description="Hanya berisi pesan baru dari pengguna di sesi ini."
    )

def to_langchain_message(messages: List[Message]) -> List[HumanMessage | AIMessage]:
    return [
        HumanMessage(content=msg.content) if msg.role == "human" 
        else AIMessage(content=msg.content) 
        for msg in messages
    ]

# Routes Autentikasi... (Tidak ada perubahan)
app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"])
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"])
    
# Routes API
@app.get("/api/waifu", summary="Dapatkan semua karakter")
async def get_waifus(user: User = Depends(current_active_user)):
    return list(WAIFU.values())

@app.post("/api/chat", summary="Kirim pesan ke karakter")
async def chat_with_character(
    request: ChatRequest, 
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Endpoint utama untuk chat, terintegrasi dengan LangGraph Agent.
    """
    # 1. Ambil Riwayat Chat dari Database (Memori)
    stmt = select(ChatMessage).where(
        ChatMessage.user_id == user.id,
        ChatMessage.character_id == request.character_id
    ).order_by(ChatMessage.timestamp.desc()).limit(20)
    
    result = await session.exec(stmt)
    db_history = result.all()
    db_history.reverse()
    memory_messages = to_langchain_message([Message(role=msg.role, content=msg.content) for msg in db_history])

    # 2. Ambil pesan terbaru dari frontend
    latest_user_message_obj = to_langchain_message(request.messages)[-1]

    # 3. Gabungkan memori dan pesan baru untuk dikirim ke agent
    combined_messages = memory_messages + [latest_user_message_obj]

    # 4. Siapkan System Prompt yang Dinamis
    character = WAIFU.get(request.character_id)
    if not character:
        return {"role": "ai", "content": "Maaf, karakter tidak ditemukan."}

    # Format system_prompt dengan nama pengguna yang sedang login
    formatted_system_prompt = character["system_prompt"].format(user_name=user.nama)

    # 5. Panggil LangGraph Agent dengan state yang lengkap
    final_state = chat_agent.invoke({
        "character_id": request.character_id,
        "messages": combined_messages,
        "system_prompt": formatted_system_prompt # <-- Kirim prompt yang sudah diformat
    })

    # Ekstrak respons AI dari state akhir
    ai_response_content = final_state["messages"][-1].content
    
    # 6. Simpan percakapan baru (input & output) ke Database
    user_msg_to_save = ChatMessage(user_id=user.id, character_id=request.character_id, role="human", content=latest_user_message_obj.content)
    ai_msg_to_save = ChatMessage(user_id=user.id, character_id=request.character_id, role="ai", content=ai_response_content)
    session.add(user_msg_to_save)
    session.add(ai_msg_to_save)
    await session.commit()

    return {"role": "ai", "content": ai_response_content}

@app.get("/api/recommendations", response_model=List[str], summary="Dapatkan rekomendasi karakter")
async def get_character_recommendations(user: User = Depends(current_active_user)):
    return await hybrid_recommendation(user_id=user.id)

# Sajikan Frontend... (Tidak ada perubahan)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/", include_in_schema=False)
async def read_root():
    return FileResponse("static/index.html")

# @app.on_event("startup")
# async def on_startup():
#     await create_db_and_tables()

# run app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

