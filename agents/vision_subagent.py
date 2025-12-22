# agents/vision_subagent.py

import os
import base64
import requests
from typing import Dict, List, Any
# Remove: from openai import OpenAI
from litellm import completion  # Add this import

from adapters.llm_provider import get_llm
from google.adk.agents import LlmAgent

from tools.inriver_api import fetch_related_entities_with_direction, fetch_entity_fields

# Remove: client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def vision_agent(image_b64: str) -> str:
    response = completion(  # Replace client.chat.completions.create with this
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": (
                "Je bent VisueleStylist, een ervaren visuele mode-expert voor een kledingwinkel. "
                "Jouw taak is om nauwkeurig te beschrijven wat er op een aangeleverde mode-afbeelding te zien is specifiek over het kledingstuk met betrekking tot de ProductGroup. "
                "Je let op kledingtype, pasvorm (zoals skinny, wide, cropped), stijl (zoals casual, chique, minimalistisch), "
                "details (zoals zakken, knopen, prints), accessoires en de algemene uitstraling van het kledingstuk. "
                "Gebruik een natuurlijke en heldere schrijfstijl, alsof je het kledingstuk mondeling zou omschrijven aan een collega in een modeteam. "
                "Je beschrijving is objectief en feitelijk, zonder commerciële en kleur bijvoegingen. Antwoord altijd in het NEDERLANDS."
            )},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Analyseer deze modefoto en beschrijf zo nauwkeurig mogelijk wat je ziet alleen over de huidige ProductGroup. "
                        "Focus op:\n- Het soort kledingstuk\n- De pasvorm en stijl\n- Details\n- De algemene uitstraling van de outfit\n\n"
                        "Wees feitelijk en objectief. Gebruik geen commerciële termen en geen kleuren. "
                        "Beschrijf het beeld alsof je het uitlegt aan een mode-inkoper of collega. Antwoord in het Nederlands."
                    )},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        temperature=0.5,
    )
    return response.choices[0].message.content.strip()

# The rest of the file (tool_vision_pipeline, etc.) remains unchanged

def tool_vision_pipeline(entity_id: int) -> Dict[str, Any]:
    vision = {}
    resources = fetch_related_entities_with_direction(entity_id, "ItemResource", direction="source")

    # Haal alle relevante metadata op
    available_images = []
    for rid in resources:
        fields = fetch_entity_fields(rid)
        available_images.append({
            "resource_id": rid,
            "shot_type": (fields.get("ResourceShotType") or "").lower(),
            "filename": fields.get("ResourceFilename"),
        })

    # Definitie van gewenste shots per positie
    shot_preferences = {
        "front": ["mdfront3", "psfront1"],
        "back": ["mdback4", "psback2"],
    }

    for position, preferred_shots in shot_preferences.items():
        for shot_type in preferred_shots:
            for img in available_images:
                print(f"🔍 Controleren afbeelding: ResourceID={rid}, ShotType='{...}', Filename='{...}'")
                if img["shot_type"] == shot_type and img["filename"]:
                    try:
                        image_url = f"https://thesting.xcdn.nl/{img['filename']}"
                        resp = requests.get(image_url); resp.raise_for_status()
                        image_b64 = base64.b64encode(resp.content).decode("utf-8")

                        description = vision_agent(image_b64)
                        vision[shot_type] = {
                            "description": description,
                            "image_url": image_url,
                            "position": position,
                        }
                        # ✅ Stop na eerste succesvolle match per positie
                        break
                    except Exception as e:
                        continue
            if position in [v["position"] for v in vision.values()]:
                break  # ✅ We hebben al een match voor deze positie, ga door naar volgende

    return {
        "vision": vision,
        "debug": {
            "resources_checked": available_images,
            "shots_used": list(vision.keys())
        }
    }