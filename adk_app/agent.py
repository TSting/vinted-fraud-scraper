import os
import pathlib
import sys
import logging
import base64

# Set up logging for easier debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("visual_search_agent")

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

from tools.search_tools import search_similar_products
from image_utils import detect_clothing_items, crop_to_box

def find_similar_items(query: str, tool_context=None) -> str:
    """
    Analyzes the uploaded image and searches for similar products in Firestore.
    Use this tool when a user has provided an image and wants to find matches.
    
    Args:
        query: The user's search query/description
        tool_context: ADK ToolContext containing session data and uploaded images
    """
    logger.info(f"Tool called with query: {query}")
    logger.info(f"Tool context type: {type(tool_context)}")
    
    # Check if we have a valid tool context
    if not tool_context:
        logger.error("No tool_context provided to find_similar_items")
        return "Internal Error: Geen tool context ontvangen. Probeer het opnieuw."

    try:
        image_bytes = None
        
        # 1. Check direct user_content first (ADK exposes this directly on ToolContext)
        if hasattr(tool_context, 'user_content') and tool_context.user_content and tool_context.user_content.parts:
            logger.info(f"Checking direct user_content ({len(tool_context.user_content.parts)} parts)")
            for part in tool_context.user_content.parts:
                if hasattr(part, 'inline_data') and part.inline_data and hasattr(part.inline_data, 'data') and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    logger.info("✓ Found image in direct user_content.")
                    break
        
        # 2. If not found, check via _invocation_context (private attribute)
        if not image_bytes and hasattr(tool_context, '_invocation_context'):
            invocation_ctx = tool_context._invocation_context
            logger.info(f"Checking _invocation_context: {type(invocation_ctx)}")
            
            # Check user_content in invocation context
            if hasattr(invocation_ctx, 'user_content') and invocation_ctx.user_content and invocation_ctx.user_content.parts:
                logger.info(f"Checking invocation user_content ({len(invocation_ctx.user_content.parts)} parts)")
                for part in invocation_ctx.user_content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data and hasattr(part.inline_data, 'data') and part.inline_data.data:
                        image_bytes = part.inline_data.data
                        logger.info("✓ Found image in invocation user_content.")
                        break
            
            # Check session history
            if not image_bytes and hasattr(invocation_ctx, 'session') and invocation_ctx.session:
                events = invocation_ctx.session.events
                logger.info(f"Checking session history ({len(events)} events)")
                for event in reversed(events):
                    if event.author and event.author.lower() == "user" and event.content and event.content.parts:
                        logger.info(f"Checking event from {event.author} with {len(event.content.parts)} parts")
                        for part in event.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data and hasattr(part.inline_data, 'data') and part.inline_data.data:
                                image_bytes = part.inline_data.data
                                logger.info(f"✓ Found image in event authored by {event.author}")
                                break
                    if image_bytes:
                        break
                    
        if not image_bytes:
            logger.warning(f"No image found anywhere in tool_context")
            return f"Ik kon geen geüploade afbeelding vinden. Upload a.u.b. een foto en probeer het opnieuw."
        
        # Convert image_bytes to proper bytes format if needed
        logger.info(f"Image data type: {type(image_bytes)}")
        if isinstance(image_bytes, str):
            # If it's a base64 string, decode it
            try:
                logger.info("Decoding base64 string...")
                image_bytes = base64.b64decode(image_bytes)
            except Exception as e:
                logger.error(f"Failed to decode base64: {e}")
                return f"Fout bij het decoderen van de afbeelding. Type: {type(image_bytes)}"
        elif not isinstance(image_bytes, bytes):
            # Convert to bytes if it's a bytearray or similar
            try:
                image_bytes = bytes(image_bytes)
            except Exception as e:
                logger.error(f"Failed to convert to bytes: {e}")
                return f"Fout bij het converteren van de afbeelding naar bytes. Type: {type(image_bytes)}"
        
        logger.info(f"✓ Image ready ({len(image_bytes)} bytes). Starting Firestore search...")
        
        # Perform Vector Search with query context
        results, was_cropped = search_similar_products(image_bytes, query=query, limit=5, auto_crop=False)
        
        # --- NEW: Smart Detection Flow ---
        # We only run detection if the user hasn't already specified what they want in the query
        # or if we want to be proactive about screenshots/multi-items.
        
        # Check if we should run detection (heuristic: tall aspect ratio or empty query)
        img_outline = []
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            if h / w > 1.25 or not query:
                logger.info("Tall image or empty query detected. Running object detection...")
                detected_items = detect_clothing_items(image_bytes)
                
                if len(detected_items) > 1:
                    logger.info(f"Found {len(detected_items)} items. Checking for clarification...")
                    
                    # Try to see if query matches one of the labels or descriptions
                    matched_item = None
                    if query:
                        query_lower = query.lower()
                        # Simple synonym map for better Dutch/English matching if Gemini slips up
                        synonyms = {
                            "trui": ["sweater", "pullover", "knitwear", "trui", "vest"],
                            "rok": ["skirt", "rok"],
                            "broek": ["pants", "trousers", "jeans", "broek", "shorts"],
                            "blouse": ["blouse", "shirt", "top"],
                            "schoenen": ["shoes", "boots", "laarzen", "schoenen", "sneakers"]
                        }
                        
                        for item in detected_items:
                            label = item['label'].lower()
                            description = item['description'].lower()
                            
                            # 1. Direct label match
                            if label in query_lower or query_lower in label:
                                matched_item = item
                                logger.info(f"Direct label match: {label}")
                                break
                            
                            # 2. Description match
                            if query_lower in description:
                                matched_item = item
                                logger.info(f"Description match: {description}")
                                break
                                
                            # 3. Synonym match
                            for Dutch, eng_list in synonyms.items():
                                if Dutch in query_lower:
                                    if any(s in label for s in eng_list):
                                        matched_item = item
                                        logger.info(f"Synonym match: {label} via {Dutch}")
                                        break
                            if matched_item:
                                break
                    
                    if not matched_item:
                        # Return clarification message
                        item_list = "\n".join([f"- **{item['label']}** ({item['description']})" for item in detected_items])
                        logger.info("No clear match found, asking for clarification.")
                        return (
                            f"Ik zie meerdere kledingstukken op deze afbeelding:\n{item_list}\n\n"
                            "Om je de beste resultaten te geven: **welk van deze items wil je dat ik zoek?**"
                        )
                    else:
                        logger.info(f"✓ Match confirmed for item '{matched_item['label']}'. Cropping...")
                        image_bytes = crop_to_box(image_bytes, matched_item['box_2d'])
                        was_cropped = True
                elif len(detected_items) == 1:
                    logger.info(f"Found 1 item: {detected_items[0]['label']}. Cropping...")
                    image_bytes = crop_to_box(image_bytes, detected_items[0]['box_2d'])
                    was_cropped = True
                else:
                    logger.info("No items detected by Gemini. Proceeding with full image.")
        except Exception as detection_err:
            logger.error(f"Detection/Cropping failed: {detection_err}")
            # Fallback to original image if detection fails

        # Perform Search (with potentially cropped image)
        logger.info(f"Starting final search with {len(image_bytes)} bytes...")
        results, _ = search_similar_products(image_bytes, query=query, limit=5, auto_crop=False)
            
        logger.info(f"✓ Found {len(results)} similar products")
        
        crop_msg = ""
        if was_cropped:
            crop_msg = "*(We hebben de afbeelding automatisch bijgesneden om UI-elementen te verwijderen voor een beter resultaat.)*\n\n"
            
        output = f"{crop_msg}We hebben het volgende item gevonden dat overeenkomt met je geüploade afbeelding:\n\n"
        for item in results:
            # Resolve name from nested dictionary
            names = item.get("name", {})
            if isinstance(names, dict):
                name = names.get("nl-NL") or names.get("en-GB") or "Naamloos Product"
            else:
                name = str(names) or "Naamloos Product"
                
            item_code = item.get("item_code", "N/A")
            item_id = item.get("item_id", "N/A")
            image_url = item.get("image_url", "Geen URL")
            
            # Calculate confidence percentage (1.0 distance = 0%, 0.0 distance = 100%)
            distance = item.get("vector_distance", 0.5)
            confidence = max(0, min(100, (1.0 - distance) * 100))
            
            output += f"**{name}** (Match: {confidence:.1f}%)\n"
            output += f"Itemcode: {item_code}\n"
            output += f"Entity ID: {item_id}\n"
            if image_url != "Geen URL":
                output += f'<a href="{image_url}" target="_blank"><img src="{image_url}" width="250" alt="{name}"></a>\n\n'
            else:
                output += "\n"
        
        output += "Laat het me weten als je nog iets anders wilt zien!"
        return output
        
    except Exception as e:
        logger.exception("Error in find_similar_items")
        return f"Er is een fout opgetreden tijdens het zoeken: {str(e)}"

# Configure Agent
visual_search_agent = LlmAgent(
    name="visual_search_agent",
    model=Gemini(model="gemini-2.5-flash"),
    description="Finds similar products based on uploaded images.",
    instruction=(
        "Je bent een Visuele Zoekassistent voor The Sting. Wanneer een gebruiker een afbeelding uploadt: "
        "1. De tool 'find_similar_items' detecteert automatisch alle kledingstukken. "
        "2. Als er meerdere items zijn en de gebruiker heeft niet specifiek aangegeven wat ze zoeken, "
        "zal de tool je vragen om verduidelijking. "
        "3. Zodra het item duidelijk is, wordt de afbeelding bijgesneden om tekst/knoppen te verwijderen "
        "en wordt de zoekopdracht uitgevoerd. "
        "Reageer altijd VOLLEDIG in het Nederlands. Gebruik de output van de tool en wees behulpzaam bij het vragen naar verduidelijking."
    ),
    tools=[find_similar_items]
)

root_agent = visual_search_agent