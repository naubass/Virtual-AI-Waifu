from typing import TypedDict, Annotated, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import StateGraph, END
import os
from dotenv import load_dotenv

# Load environment variables dari file .env
load_dotenv()

# Pastikan environment variable GOOGLE_API_KEY sudah diatur
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")

# Inisialisasi LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.8,
)

class GraphState(TypedDict):
    """
    Mendefinisikan state untuk graph kita.
    
    Args:
        character_id: ID karakter yang dipilih.
        messages: Daftar seluruh pesan dalam percakapan.
        system_prompt: System prompt yang SUDAH diformat dengan nama user.
    """
    character_id: str
    messages: Annotated[List[BaseMessage], "Daftar pesan dalam percakapan"]
    system_prompt: str  # <-- TAMBAHAN BARU

def chat_node(state: GraphState):
    """
    Node utama untuk memanggil LLM dan menghasilkan balasan.
    """
    messages = state["messages"]
    system_prompt = state["system_prompt"] # <-- Gunakan prompt dari state

    # Pisahkan riwayat chat dari input pengguna terbaru
    current_user_input = messages[-1].content
    chat_history = messages[:-1]

    # Buat prompt template yang dinamis
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt), # <-- Langsung gunakan prompt yang sudah diformat
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
    ])

    # Buat rantai (chain) untuk node ini
    chain = prompt_template | llm

    # Panggil chain dengan konteks yang sesuai
    response = chain.invoke({
        "chat_history": chat_history,
        "input": current_user_input,
    })

    # Tambahkan respons AI ke dalam daftar pesan
    new_messages = messages + [AIMessage(content=response.content)]

    # Kembalikan state yang telah diperbarui
    return {
        "character_id": state["character_id"],
        "messages": new_messages,
        "system_prompt": system_prompt, # Teruskan state
    }

# Definisikan alur kerja (workflow) graph
workflow = StateGraph(GraphState)
workflow.add_node("chat", chat_node)
workflow.set_entry_point("chat")
workflow.add_edge("chat", END)

# Kompilasi graph menjadi objek yang bisa dipanggil
chat_agent = workflow.compile()

