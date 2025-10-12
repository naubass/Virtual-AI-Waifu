from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Literal

# Impor agen dan definisi karakter
from app.agent import chat_agent
from app.waifu import WAIFU
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

# setup app
app = FastAPI()

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

    history: List[str] = Field(
        default_factory=list,
        description="Seluruh riwayat percakapan, termasuk pesan terbaru dari pengguna."
    )

# Fungsi helper untuk mengubah model Pydantic ke model LangChain
def to_langchain_message(messages: Message):
    lc_messages = []
    for msg in messages:
        if msg.role == "human":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "ai":
            lc_messages.append(AIMessage(content=msg.content))
    return lc_messages
    
# setup routes
@app.get("/", include_in_schema=False)
async def read_root():
    """Menyajikan halaman utama web."""
    return FileResponse("static/index.html")

@app.get("/api/waifu")
async def get_waifus():
    """Mengambil daftar semua karakter waifu yang tersedia."""
    waifu_list = [
        {
            "id": data["id"],
            "name": data["name"],
            "description": data["description"],
            "image": data["image"],
        }
        for data in WAIFU.values()
    ]
    return waifu_list

@app.post("/api/chat")
async def stream_chat(request: ChatRequest):
    """
    Endpoint utama untuk chat. Server ini stateless.
    Client mengirim seluruh riwayat, server membalas dengan pesan baru dari AI.
    """

    # covert langchain message
    langchain_messages = to_langchain_message(request.messages)

    # buat state graph awal
    initial_state = {
        "character_id": request.character_id,
        "messages": langchain_messages,
    }

    final_state = chat_agent.invoke(initial_state)
    ai_response_content = final_state["messages"][-1].content

    return {"role": "ai", "content": ai_response_content}

app.mount("/", StaticFiles(directory="static", html=True), name="static")

# run app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)







   







