# adapters/llm_provider.py
import os
from adapters.llm_openai import get_openai_llm
from adapters.llm_vertex import get_vertex_llm

def get_llm():
    """
    Router op basis van LLM_PROVIDER:
      - openai  -> openai/gpt-4o (of wat je in env zet)
      - vertex  -> vertex/gemini-1.5-pro-002 (of wat je in env zet)
    """
    provider = (os.getenv("LLM_PROVIDER") or "openai").lower()
    if provider == "vertex":
        return get_vertex_llm()
    return get_openai_llm()