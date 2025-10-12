from typing import TypedDict, Annotated, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, END

# ambil WAIFU
from app.waifu import WAIFU

# env
import os
from dotenv import load_dotenv

# initialisasi env
load_dotenv()

# llm
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
)

class GraphState(TypedDict):
    """
    Mendefinisikan state untuk graph kita.
    
    Args:
        character_id: ID karakter yang dipilih (misal: "aiko").
        messages: Daftar pesan dalam percakapan.
    """
    character_id: str
    messages: Annotated[List[BaseMessage], "Daftar pesan dalam percakapan"]

def chat_node(state: GraphState):
    """
    Node utama untuk memanggil LLM dan menghasilkan balasan.
    Fungsi ini sekarang dirancang untuk bekerja dengan benar.
    """
    character_id = state["character_id"]
    messages = state["messages"]

    character = WAIFU[character_id]
    if not character:
        raise ValueError(f"Tidak ada karakter dengan ID: {character_id}")
    
    current_user_input = messages[-1].content
    chat_history = messages[:-1]

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", character["system_prompt"]),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
    ])

    chain = prompt_template | llm

    # invoke
    response = chain.invoke({
        "chat_history": chat_history,
        "input": current_user_input,
    })

    new_messages = messages + [AIMessage(content=response.content)]

    return {
        "character_id": character_id,
        "messages": new_messages,
    }

# alur node workflow
workflow = StateGraph(GraphState)
workflow.add_node("chat", chat_node)
workflow.set_entry_point("chat")
workflow.add_edge("chat", END)

# compile graph
chat_agent = workflow.compile()

