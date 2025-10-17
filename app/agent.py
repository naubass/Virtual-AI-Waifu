from typing import TypedDict, Annotated, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, BaseMessage
from langchain.chains import RetrievalQA
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
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

# Inisialisasi model embedding & muat Vector Store untuk Yuna
try:
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')
    yuna_vector_store = FAISS.load_local("faiss_index_all_subjects", embeddings, allow_dangerous_deserialization=True)
    yuna_retriever = yuna_vector_store.as_retriever(search_kwargs={"k": 3})
except Exception as e:
    print(f"Peringatan: Gagal memuat vector store untuk Yuna. Fitur e-learning tidak akan aktif. Error: {e}")
    yuna_retriever = None

class GraphState(TypedDict):
    character_id: str
    messages: Annotated[List[BaseMessage], "Daftar pesan dalam percakapan"]
    system_prompt: str

def chat_node(state: GraphState):
    """
    Node utama untuk memanggil LLM dan menghasilkan balasan, dengan logika RAG yang benar.
    """
    character_id = state["character_id"]
    messages = state["messages"]
    system_prompt = state["system_prompt"]
    
    current_user_input = messages[-1].content
    chat_history = messages[:-1]
    
    ai_response_content = ""

    # --- PERBAIKAN LOGIKA RAG DI SINI ---
    if character_id == "YUNA_CHAN" and yuna_retriever is not None:
        print("Mode E-Learning Yuna Aktif")
        
        # Buat chain RetrievalQA, yang lebih cocok untuk tugas ini
        yuna_qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff", # "stuff" akan memasukkan semua konteks ke dalam satu prompt
            retriever=yuna_retriever,
            return_source_documents=True # Untuk melihat sumber dokumen
        )
        
        # Panggil chain dengan query dari pengguna
        result = yuna_qa_chain.invoke(current_user_input)
        ai_response_content = result["result"]
        
        # Tampilkan sumber dokumen yang digunakan (opsional, untuk debugging)
        if result.get("source_documents"):
            print(f"Sumber Dokumen: {[doc.metadata.get('source', 'Tidak diketahui') for doc in result['source_documents']]}")

    else:
        # Untuk karakter lain, gunakan mode chat biasa
        print(f"Mode Chat Biasa untuk {character_id} Aktif")
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])
        chain = prompt_template | llm
        response = chain.invoke({
            "chat_history": chat_history,
            "input": current_user_input,
        })
        ai_response_content = response.content

    new_messages = messages + [AIMessage(content=ai_response_content)]
    
    return {
        "character_id": character_id,
        "messages": new_messages,
        "system_prompt": system_prompt,
    }

# Definisikan alur kerja (graph) - tidak ada perubahan
workflow = StateGraph(GraphState)
workflow.add_node("chat", chat_node)
workflow.set_entry_point("chat")
workflow.add_edge("chat", END)
chat_agent = workflow.compile()