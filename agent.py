import os
from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

app = FastAPI()

# ── LLM ───────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "qwen3.7:27b"),
    base_url=os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1"),
    api_key=os.getenv("LLM_API_KEY", "ollama"),
    temperature=0,
)

# ── Tools ─────────────────────────────────────────────────────────
@tool
def search_web(query: str) -> str:
    """Search the web for a query."""
    return f"Results for: {query}"

tools = [search_web]

# ── Agent ─────────────────────────────────────────────────────────
# create_react_agent builds the prompt internally.
# Pass a SystemMessage if you want a custom system prompt.
agent = create_react_agent(
    model=llm,
    tools=tools,
    state_modifier="You are a senior engineer. Be concise.",
    prompt=SystemMessage(content="You are a helpful assistant. Use tools when needed."),
)

# ── API ───────────────────────────────────────────────────────────
@app.post("/chat")
def chat(payload: dict):
    result = agent.invoke(
        {"messages": [{"role": "user", "content": payload["message"]}]}
    )
    return {"response": result["messages"][-1].content}

