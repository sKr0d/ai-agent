"""Chat model factory.

We talk to Ollama through its OpenAI-compatible endpoint with `ChatOpenAI`,
so the same code would work against a real OpenAI-compatible provider by only
changing `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY`.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import get_settings


@lru_cache
def get_llm() -> ChatOpenAI:
    """Return a cached chat model.

    Cached because the model is stateless and reused by every sub-agent;
    this avoids re-creating the HTTP client on each agent.
    """
    s = get_settings()
    return ChatOpenAI(
        model=s.model,
        base_url=s.base_url,
        api_key=s.api_key,
        temperature=s.temperature,
    )
