from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Literal

# Impor dari file-file konfigurasi baru kita
from app.db import create_db_and_tables, get_async_session
from app.models import User, Interaction, InteractionCreate, UserCreate, UserUpdate, UserRead
from app.users import auth_backend, current_active_user, fastapi_users

# Impor agen dan definisi karakter
from app.recomender import get_recommendations 
from app.agent import chat_agent
from app.waifu import WAIFU
from langchain_core.messages import HumanMessage, AIMessage

from fastapi.middleware.cors import CORSMiddleware

# setup app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# setup message
class Message(BaseModel):
    role: Literal["human", "ai"]
    content: str

class ChatRequest(BaseModel):
    character_id: str
    messages: List[Message] = Field(
        default_factory=list,
        description="Seluruh riwayat percakapan, termasuk pesan terbaru dari pengguna."
    )

# Fungsi helper untuk mengubah model Pydantic ke model LangChain
def to_langchain_message(messages: List[Message]): 
    lc_messages = []
    for msg in messages:
        if msg.role == "human":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "ai":
            lc_messages.append(AIMessage(content=msg.content))
    return lc_messages

# Routes Autentikasi
app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
)
    
# setup routes
@app.get("/api/waifu")
async def get_waifus(user: User = Depends(current_active_user)):
    return list(WAIFU.values())

@app.post("/api/chat")
async def stream_chat(request: ChatRequest, user: User = Depends(current_active_user)):
    """
    Endpoint utama untuk chat. Dilindungi dan hanya bisa diakses oleh user yang login.
    """
    langchain_messages = to_langchain_message(request.messages)

    initial_state = {
        "character_id": request.character_id,
        "messages": langchain_messages,
    }

    # Panggil agent LangChain Anda
    final_state = chat_agent.invoke(initial_state)
    ai_response_content = final_state["messages"][-1].content

    return {"role": "ai", "content": ai_response_content}

@app.post("/api/interactions", response_model=Interaction)
async def log_interaction(
    interaction: InteractionCreate,
    user: User = Depends(current_active_user),
    session = Depends(get_async_session)
):
    """Mencatat data interaksi user dengan karakter ke database."""
    # Membuat objek Interaction dari data request dan menambahkan user_id dari user yang login
    db_interaction = Interaction.from_orm(interaction, update={"user_id": user.id})
    session.add(db_interaction)
    await session.commit()
    await session.refresh(db_interaction)
    return db_interaction

@app.get("/api/recommendations", response_model=List[str])
async def get_character_recommendations(user: User = Depends(current_active_user)):
    """Memberikan rekomendasi karakter berdasarkan riwayat interaksi user."""
    # PERUBAHAN: Memanggil fungsi rekomendasi yang sudah benar
    return await get_recommendations(user_id=user.id)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/", include_in_schema=False)
async def read_root():
    """Menyajikan halaman utama web."""
    return FileResponse("static/index.html")

@app.on_event("startup")
async def on_startup():
    """Fungsi ini dijalankan sekali saat server pertama kali hidup."""
    # Membuat tabel di database (jika belum ada) secara otomatis.
    await create_db_and_tables()

# run app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
