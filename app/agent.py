import os
import requests
from bs4 import BeautifulSoup
from typing import TypedDict, Annotated, List

from langchain.chains import RetrievalQA
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from dotenv import load_dotenv
from serpapi import GoogleSearch

# Load environment variables
load_dotenv()
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")

# Inisialisasi LLM
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.8)
print("LLM gemini-1.5-flash diinisialisasi.")

# Inisialisasi model embedding & muat Vector Store umum
try:
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')
    vector_store = FAISS.load_local("faiss_index_all_subjects", embeddings, allow_dangerous_deserialization=True)
    general_retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    print("Vector store berhasil dimuat.")
except Exception as e:
    print(f"Peringatan: Gagal memuat vector store. Fitur e-learning & karir tidak akan aktif. Error: {e}")
    general_retriever = None

# --- ALAT PENCARIAN KERJA BARU (MENGGUNAKAN SERPAPI) ---
@tool
def job_search_tool(query: str, location: str = "Indonesia") -> str:
    """
    Cari lowongan kerja real-time dari Google Jobs via SerpAPI (dengan tampilan rapi).
    """
    print(f"--- MEMANGGIL ALAT SERPAPI (GOOGLE JOBS): Query='{query}', Lokasi='{location}' ---")

    final_query = query
    if "ai engineer" in query.lower():
        final_query = f'"{query}" OR "Machine Learning Engineer" OR "AI Specialist"'

    try:
        api_key = os.environ.get("SERPAPI_API_KEY")
        if not api_key:
            return "⚠️ SERPAPI_API_KEY belum diatur di environment."

        params = {
            "engine": "google_jobs",
            "q": final_query,
            "location": location,
            "hl": "id",
            "gl": "id",
            "api_key": api_key,
        }

        client = GoogleSearch(params)
        results = client.get_dict()

        jobs = results.get("jobs_results", [])
        if not jobs:
            return f"Tidak ada lowongan ditemukan untuk **{query}** di {location}."

        response_lines = ["**Berikut lowongan kerja yang ditemukan:**\n"]
        
        for i, job in enumerate(jobs[:5], start=1):
            title = job.get("title", "N/A")
            company = job.get("company_name", "N/A")
            loc = job.get("location", "N/A")

            # 🔗 Coba ambil link dari beberapa kemungkinan
            link = None
            if job.get("apply_options"):
                link = job["apply_options"][0].get("link")
            elif job.get("related_links"):
                link = job["related_links"][0].get("link")
            elif job.get("link"):
                link = job["link"]
            elif job.get("job_id"):
                link = f"https://www.google.com/search?q={title}+{company}&ibp=htl;jobs#htidocid={job['job_id']}"

            # Format cantik dengan Markdown
            line = (
                f"**{i}. {title}**\n"
                f"🏢 *{company}*\n"
                f"📍 {loc}\n"
                f"🔗 [Lihat Lowongan]({link})\n"
            )
            response_lines.append(line)

        return "\n".join(response_lines)

    except Exception as e:
        print(f"ERROR SerpAPI: {e}")
        return f"Terjadi kesalahan teknis: {e}"

# --- IKAT ALAT KE LLM ---
tools = [job_search_tool]
llm_with_tools = llm.bind_tools(tools)

# --- DEFINISI STATE ---
class GraphState(TypedDict):
    character_id: str
    messages: Annotated[List[BaseMessage], "Daftar pesan dalam percakapan"]
    system_prompt: str

# --- NODE 1: CHAT (HANYA UNTUK INPUT MANUSIA) ---
def chat_node(state: GraphState):
    """
    Node ini HANYA menangani input dari pengguna (HumanMessage).
    Tugasnya adalah merespons atau memutuskan untuk memanggil alat.
    """
    print("Memasuki chat_node (Human Input)")
    character_id = state["character_id"]
    system_prompt = state["system_prompt"]
    messages = state["messages"]
    
    if not messages or not isinstance(messages[-1], HumanMessage):
        print("Peringatan: chat_node dipanggil tanpa HumanMessage. Mengembalikan state.")
        return state

    current_user_input = messages[-1].content
    chat_history = messages[:-1]
    ai_response = None

    if not current_user_input or current_user_input.strip() == "":
        print("Input pengguna kosong terdeteksi.")
        ai_response = AIMessage(content="Hmm, kamu tidak mengatakan apa-apa.")
        return {"messages": messages + [ai_response], "character_id": character_id, "system_prompt": system_prompt}

    # Logika HINATA (RAG + Tools)
    if character_id == "HINATA_CHAN" and general_retriever is not None:
        print(f"Mode RAG + Tools (Human Input) Aktif untuk {character_id}")
        docs = general_retriever.get_relevant_documents(current_user_input)
        context_text = "\n\n".join([doc.page_content for doc in docs])
        
        rag_plus_tool_prompt = f"""{system_prompt}
Gunakan pengetahuanmu dari konteks berikut untuk memberikan nasihat karir.
---
KONTEKS PENGETAHUAN: {context_text}
---
ATURAN UTAMA DAN PENGECUALIAN PERSONA:
1. Jika pengguna meminta "lowongan kerja", "cari kerja", "loker", atau sinonimnya:
2. Kamu HARUS dan WAJIB memanggil alat `job_search_tool` SEGERA.
3. JANGAN menolak, JANGAN meminta CV. Langsung panggil alat.
"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", rag_plus_tool_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])
        chain = prompt | llm_with_tools
        ai_response = chain.invoke({
            "chat_history": chat_history,
            "input": current_user_input,
            "context": context_text
        })

    # Logika YUNA (RAG Saja)
    elif character_id == "YUNA_CHAN" and general_retriever is not None:
        print(f"Mode RAG (Human Input) Aktif untuk {character_id}")
        docs = general_retriever.get_relevant_documents(current_user_input)
        context_text = "\n\n".join([doc.page_content for doc in docs])
        rag_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + "\n\nKonteks:\n{context}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])
        chain = rag_prompt | llm
        ai_response = chain.invoke({
            "context": context_text,
            "chat_history": chat_history,
            "input": current_user_input,
        })

    # Logika LAIN (Chat Biasa)
    else:
        print(f"Mode Chat Biasa untuk {character_id} Aktif")
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])
        chain = prompt_template | llm
        ai_response = chain.invoke({
            "chat_history": chat_history,
            "input": current_user_input,
        })
    
    new_messages = messages + [ai_response]
    return {"messages": new_messages, "character_id": character_id, "system_prompt": system_prompt}

# --- NODE 2: EKSEKUSI ALAT ---
tool_node = ToolNode(tools)

# --- NODE 3 (PERBAIKAN FINAL): UBAH HASIL ALAT MENJADI JAWABAN ---
def tool_result_node(state: GraphState):
    """
    Node ini HANYA dipanggil setelah tool_node.
    PERBAIKAN: Node ini TIDAK memanggil LLM. Ia HANYA
    mengubah output ToolMessage menjadi AIMessage.
    Ini 100% menghindari error 'contents is not specified'.
    """
    print("Memasuki tool_result_node (Mengubah Tool ke AI Message)")
    messages = state["messages"]

    # Pesan terakhir HARUS ToolMessage
    if not messages or not isinstance(messages[-1], ToolMessage):
        print("Peringatan: tool_result_node dipanggil tanpa ToolMessage.")
        ai_response = AIMessage(content="Terjadi kesalahan saat memproses hasil alat.")
        return {"messages": messages + [ai_response]}

    # Ambil konten dari hasil alat
    tool_output = messages[-1].content
    
    # Buat AIMessage baru LANGSUNG dari output alat.
    # Kita tidak perlu persona di sini, yang penting datanya sampai.
    # Jika ingin persona, Anda bisa tambahkan string:
    # content=f"Hmph, ini hasil yang kutemukan:\n{tool_output}"
    # Tapi untuk stabilitas, kita kirim outputnya langsung:
    
    ai_response = AIMessage(content=tool_output)
    
    print(f"Mengubah ToolMessage menjadi AIMessage: {tool_output[:70]}...")

    new_messages = messages + [ai_response]
    # Hanya perlu update messages
    return {"messages": new_messages}


# --- FUNGSI KONDISI ---
def should_continue(state: GraphState) -> str:
    """Memutuskan alur selanjutnya setelah 'chat_node'."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print("Keputusan: Memanggil Alat (tools)")
        return "tools"
    else:
        print("Keputusan: Mengakhiri Alur (end)")
        return "end"

# --- DEFINISI WORKFLOW BARU ---
workflow = StateGraph(GraphState)

# 1. Tambahkan semua node
workflow.add_node("chat", chat_node)
workflow.add_node("tools", tool_node)
workflow.add_node("tool_result", tool_result_node) # <-- Node untuk hasil

# 2. Tentukan titik awal
workflow.set_entry_point("chat")

# 3. Tentukan alur kondisional dari 'chat'
workflow.add_conditional_edges(
    "chat",
    should_continue,
    {
        "tools": "tools", # Jika panggil alat, pergi ke 'tools'
        "end": END        # Jika tidak, selesai
    }
)

# 4. Tentukan alur baru setelah 'tools'
workflow.add_edge("tools", "tool_result") # <-- SETELAH 'tools', pergi ke 'tool_result'

# 5. Tentukan alur setelah 'tool_result'
workflow.add_edge("tool_result", END) # <-- SETELAH 'tool_result', alur selesai

# Compile agent
chat_agent = workflow.compile()
print("Workflow agent berhasil di-compile dengan arsitektur anti-error.")