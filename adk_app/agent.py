import os
import pathlib

# --- Monkeypatch google-genai Client for Vertex AI ---
# This MUST happen before ADK imports to ensure it uses the patched version
import google.genai
import google.adk.models.google_llm

_original_client = google.genai.Client

class VertexClient(_original_client):
    def __init__(self, *args, **kwargs):
        # Force Vertex AI if no API key is provided
        if not kwargs.get("api_key"):
            kwargs["vertexai"] = True
            kwargs["project"] = kwargs.get("project") or os.getenv("GOOGLE_CLOUD_PROJECT") or "ecom-agents"
            kwargs["location"] = kwargs.get("location") or os.getenv("VERTEX_LOCATION") or "europe-west1"
        super().__init__(*args, **kwargs)

# Overwrite the class in the module and specifically in ADK model file
google.genai.Client = VertexClient
google.adk.models.google_llm.Client = VertexClient

# --- ADK imports ---
from google.adk.agents import LlmAgent
from google.adk.models import Gemini

# Load env variables (if not already set in environment)
try:
    from dotenv import load_dotenv
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    ENV = ROOT / ".env"
    if ENV.exists():
        load_dotenv(str(ENV), override=False)
except ModuleNotFoundError:
    pass

from tools.search_tools import search_similar_products

def tool_find_similar_items(query: str) -> str:
    """
    Looks for the uploaded image in the session and finds similar products in the database.
    Use this when a user uploads an image and asks to find similar items.
    """
    return "Vector search functionality is being integrated. Please ensure the Firestore Index is created."

# Configure Model
# Note: config parameters are handled by the VertexClient monkeypatch
visual_search_agent = LlmAgent(
    name="visual_search_agent",
    model=Gemini(model="gemini-2.5-flash"),
    description="An agent that helps users find products by uploading images.",
    instruction=(
        "You are a Visual Product Search assistant for The Sting. "
        "When a user uploads an image, you can analyze it and find similar products in our database. "
        "Use the tools available to perform vector similarity search."
    ),
    tools=[tool_find_similar_items]
)

root_agent = visual_search_agent