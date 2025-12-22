# adapters/llm_openai.py
import pathlib, os
# Laad .env uit projectroot, ook als ADK elders draait
try:
    from dotenv import load_dotenv
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    ENV = ROOT / ".env"
    if ENV.exists():
        load_dotenv(str(ENV), override=False)
except ModuleNotFoundError:
    pass

from google.adk.models.lite_llm import LiteLlm

def get_openai_llm():
    """
    OpenAI via LiteLLM. Gebruikt OPENAI_API_KEY uit env/.env.
    """
    return LiteLlm(model="openai/gpt-4o")
