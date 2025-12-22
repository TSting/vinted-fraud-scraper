# adk_app/agent.py
import os
import pathlib

# --- .env vroeg laden (werkt ook bij `adk web`) ---
try:
    from dotenv import load_dotenv
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    ENV = ROOT / ".env"
    if ENV.exists():
        load_dotenv(str(ENV), override=False)
except ModuleNotFoundError:
    pass

# --- ADK imports ---
from google.adk.agents import LlmAgent, SequentialAgent

# --- Onze adapters, tools en subagents ---
from adapters.llm_provider import get_llm
from tools.inriver_api import lookup_entity_id, fetch_core_data, update_fields
from agents.vision_subagent import tool_vision_pipeline
from agents.copy_subagent import tool_copy_pipeline

# ------------------------------------------------------------
# InRiver Fetch Agent  (1 bolletje)
# - Doel: entity_id bepalen (via lookup als nodig) + kern­data ophalen
# - Tools: lookup_entity_id, fetch_core_data
# ------------------------------------------------------------
inriver_fetch_agent = LlmAgent(
    name="inriver_fetch",
    model=get_llm(),
    description=(
        "Bepaalt de 'entity_id' (via ProductCode → lookup indien nodig) en haalt kern­data op "
        "(item_data, product_data, product_ids) uit inRiver."
    ),
    instruction=(
        "1) Controleer of er een 'entity_id' beschikbaar is in de context; zo ja, gebruik die.\n"
        "2) Zo niet: controleer of er een ProductCode is en roep lookup_entity_id(product_code=<waarde>) aan.\n"
        "3) Roep fetch_core_data(entity_id=<bepaalde entity_id>) aan en bewaar 'item_data', 'product_data' en 'product_ids' voor vervolgstappen.\n"
        "4) Geef kort terug welke entity_id en hoeveel velden zijn opgehaald."
    ),
    tools=[lookup_entity_id, fetch_core_data],
)

# ------------------------------------------------------------
# Vision Subagent (ongewijzigd)
# - Verwacht: request='{\"entity_id\": <int>}'
# - Output: {'vision': {...}, 'debug': ...}
# ------------------------------------------------------------
vision_subagent = LlmAgent(
    name="vision_subagent",
    model=get_llm(),
    description="Analyseert meerdere productafbeeldingen en geeft feitelijke visuele beschrijving(en) van de huidige ProductGroup per afbeelding.",
    instruction=(
        "Ontvang JSON met {'entity_id': <int>} en roep de tool 'tool_vision_pipeline' aan. "
        "Het resultaat bevat een 'vision'-dict met beschrijvingen per afbeelding (per shot-type)."
    ),
    tools=[tool_vision_pipeline],
)

# ------------------------------------------------------------
# Copy Subagent (ongewijzigd)
# - Verwacht: request='{\"item_data\":..., \"product_data\":..., \"vision\":...}'
# - Haalt intern RAG op en retourneert de drie velden
# ------------------------------------------------------------
copy_subagent = LlmAgent(
    name="copy_subagent",
    model=get_llm(),
    description="Genereert productnaam op basis van de huidige ProductGroup en RAG (max. 5 woorden en alleen een hoofdletter bij het eerste woord) en genereert een korte HTML-beschrijving (max 50 woorden) "
    "op basis van data, visuele input en RAG, volgens Costes-richtlijnen met 1 interne link. Vermijd kleuren en benoem nooit de ProductBrandCode in de productnaam en ook nooit in de productomschrijving.",
    instruction=(
        "Gebruik tool_copy_pipeline(item_data=item_data, product_data=product_data, vision=vision) "
        "om productteksten te maken van de huidige ProductGroup. Deze tool haalt zelf RAG-examples op."
    ),
    tools=[tool_copy_pipeline],
)

# ------------------------------------------------------------
# InRiver Update Agent  (2e bolletje)
# - Doel: naam/beschrijving terugschrijven naar product_ids[0]
# - Tool: update_fields
# ------------------------------------------------------------
inriver_update_agent = LlmAgent(
    name="inriver_update",
    model=get_llm(),
    description="Schrijft ProductNameCommercial en ProductDescription terug naar inRiver (product_ids[0]) en vinkt ProductAgentChecked aan.",
    instruction=(
        "1) Lees uit de context:\n"
        "   - 'product_ids' (afkomstig van inriver_fetch)\n"
        "   - de drie outputvelden (afkomstig van copy_subagent): "
        "     ProductNameCommercial, ProductDescription, Toelichting\n"
        "2) Roep de tool `update_fields` aan met `product_entity_id=product_ids[0]` en een `updates` dictionary die de volgende velden bevat:\n"
        "     'ProductNameCommercial': <de waarde van ProductNameCommercial>,\n"
        "     'ProductSeoLabel': <dezelfde waarde als ProductNameCommercial>,\n"
        "     'ProductDescription': <...>,\n"
        "     'ProductAgentChecked': false\n"
        "   }) aan.\n"
        "3) Rapporteer kort welk product_entity_id is bijgewerkt en met welke waarden."
    ),
    tools=[update_fields],
)

# ------------------------------------------------------------
# Root: SequentialAgent (vaste pipeline)
# ------------------------------------------------------------
root_agent = SequentialAgent(
    name="orchestrator_root",
    sub_agents=[
        inriver_fetch_agent,  # lookup (indien nodig) + fetch_core_data
        vision_subagent,      # vision → 'vision' dict
        copy_subagent,        # copy → 3 velden (met RAG)
        inriver_update_agent, # wegschrijven naar inRiver
    ],
    description=(
        "Voert de orchestrator-pipeline stap-voor-stap uit: "
        "InRiver Fetch → Vision → Copy → InRiver Update."
    ),
)