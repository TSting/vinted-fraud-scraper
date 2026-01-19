import os
import pathlib
import sys
import logging
import base64
import asyncio
import glob

# Set up logging for easier debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vinted_fraud_agent")

# --- Robust Path Fix ---
# Add local venv site-packages to sys.path to ensure local dependencies (like playwright) 
# are found even if adk is running from a different environment.
_project_root = pathlib.Path(__file__).resolve().parents[1]
_site_pkg_patterns = [
    os.path.join(_project_root, "venv", "lib", "python*", "site-packages"),
]
for pattern in _site_pkg_patterns:
    for sp in glob.glob(pattern):
        if os.path.exists(sp) and sp not in sys.path:
            logger.info(f"Injecting local site-packages: {sp}")
            sys.path.insert(0, sp)

# --- Monkeypatch google-genai Client for Vertex AI ---
import google.genai
import google.adk.models.google_llm

_original_client = google.genai.Client

class VertexClient(_original_client):
    def __init__(self, *args, **kwargs):
        if not kwargs.get("api_key"):
            kwargs["vertexai"] = True
            kwargs["project"] = kwargs.get("project") or os.getenv("GOOGLE_CLOUD_PROJECT") or "ecom-agents"
            kwargs["location"] = kwargs.get("location") or os.getenv("VERTEX_LOCATION") or "europe-west1"
        super().__init__(*args, **kwargs)

google.genai.Client = VertexClient
google.adk.models.google_llm.Client = VertexClient

# --- ADK imports ---
from google.adk.agents import LlmAgent
from google.adk.models import Gemini

# --- Pathing & Env ---
ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.append(ROOT)

try:
    from dotenv import load_dotenv
    ENV = os.path.join(ROOT, ".env")
    if os.path.exists(ENV):
        load_dotenv(ENV, override=False)
except ImportError:
    pass

from vinted_scraper import capture_newest_vinted_item_screenshot

def get_vinted_newest_item_screenshot(tool_context=None) -> str:
    """
    Gaat naar Vinted, opent het nieuwste item en maakt een screenshot.
    Gebruik deze tool wanneer de gebruiker vraagt om te controleren op nieuwe Costes producten op Vinted.
    """
    logger.info("Tool called: get_vinted_newest_item_screenshot")
    try:
        # Run the scraper in a way that works whether we have a loop or not
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If we are already in a loop (like ADK's), run it in a separate thread
            import threading
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, capture_newest_vinted_item_screenshot())
                try:
                    # Set a 120 second timeout to prevent indefinite waiting
                    screenshot_path, item_url = future.result(timeout=120)
                except FutureTimeoutError:
                    return "De actie kon niet worden voltooid vanwege een time-out. De seller validatie duurt langer dan verwacht. Probeer het later nog eens."
        else:
            screenshot_path, item_url = asyncio.run(capture_newest_vinted_item_screenshot())
        
        if screenshot_path is None or item_url is None:
            return "Ik heb alle 'Nieuw met prijskaartje' Costes items van de afgelopen 24 uur gecontroleerd, maar helaas: geen enkele verkoper van deze items heeft voldoende andere nieuwe Costes items te koop staan (minimaal 2 vereist). Er is daarom geen screenshot gemaakt."
        
        return f"Ik heb het nieuwste Costes item op Vinted geopend: {item_url}\n\nDe screenshot is opgeslagen in de map `vinted_screenshots` met de naam `{os.path.basename(screenshot_path)}`.\n\n*(Opmerking: Vanwege lokale beperkingen kan ik de afbeelding hier niet direct tonen, maar ik heb de actie succesvol uitgevoerd.)*"
    except Exception as e:
        error_msg = f"Er is een fout opgetreden bij het scrapen van Vinted: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        return error_msg

# Configure Agent
vinted_fraud_agent = LlmAgent(
    name="vinted_fraud_agent",
    model=Gemini(model="gemini-2.0-flash"),
    description="Vinted Fraud Scraper Agent - Controleert op nieuwe Costes producten op Vinted.",
    instruction=(
        "Je bent de Vinted Fraud Scraper Agent voor Costes. Je hoofddoel is het opsporen van potentiële fraude op Vinted.\n\n"
        "BELANGRIJK: Wanneer de gebruiker vraagt om te kijken of er nieuwe producten zijn, MOET je ALTIJD de tool 'get_vinted_newest_item_screenshot' aanroepen. "
        "Ga NOOIT zelf antwoorden dat je bezig bent of dat de actie is voltooid zonder de tool ECHT aan te roepen.\n\n"
        "Als je de tool aanroept, wacht dan op het resultaat. Gebruik NOOIT placeholders zoals '[insert URL here]'. "
        "Geef alleen de URL en informatie door die je van de tool terugkrijgt.\n\n"
        "Reageer altijd in het Nederlands. Bevestig wanneer de actie is voltooid en geef de URL van het item door."
    ),
    tools=[get_vinted_newest_item_screenshot]
)

root_agent = vinted_fraud_agent