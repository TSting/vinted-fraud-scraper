# adapters/llm_vertex.py
import pathlib, os
# .env laden vanuit projectroot (werkt ook bij `adk web`)
try:
    from dotenv import load_dotenv
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    ENV = ROOT / ".env"
    if ENV.exists():
        load_dotenv(str(ENV), override=False)
except ModuleNotFoundError:
    pass

from google.adk.models.lite_llm import LiteLlm

def get_vertex_llm(model_id: str | None = None):
    """
    Gemini via Vertex AI (LiteLlm).
    Vereist:
      - GOOGLE_CLOUD_PROJECT
      - VERTEX_LOCATION (bv. europe-west4)
      - Applicatie-credentials via ADC (GOOGLE_APPLICATION_CREDENTIALS of SA op Cloud Run)
    """
    model_id = model_id or os.getenv("LLM_MODEL_VERTEX", "gemini-1.5-pro-002")
    # ADK/LiteLlm gebruikt het model als "vertex/<id>"
    return LiteLlm(model=f"vertex_ai/gemini-2.5-flash")