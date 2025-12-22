# tools/inriver_api.py
from typing import Any, Dict, List, Tuple
import os
import requests

REQUEST_TIMEOUT = (5, 30)  # (connect, read)

def _require_env() -> Tuple[str, str]:
    key = os.getenv("ECOM_INRIVER_API_KEY")
    base = os.getenv("IN_RIVER_BASE_URL")
    if not key or not base:
        raise RuntimeError("Missing ECOM_INRIVER_API_KEY or IN_RIVER_BASE_URL")
    return key, base

def _session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"X-inRiver-APIKey": api_key, "Accept": "application/json"})
    return s

def lookup_entity_id(product_code: str) -> Dict[str, int]:
    key, base = _require_env()
    url = f"{base}/api/v1.0.0/query"
    headers = {"accept": "text/plain", "Content-Type": "application/json-patch+json", "X-inRiver-APIKey": key}
    payload = {
        "dataCriteriaOperator": "And",
        "dataCriteria": [{"fieldTypeId": "ItemCodeURLFriendly", "operator": "Equal", "value": product_code}]
    }
    r = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    entity_ids = r.json().get("entityIds", [])
    if not entity_ids:
        raise ValueError(f"Geen entity gevonden met ItemCodeURLFriendly: {product_code}")
    return {"entity_id": entity_ids[0]}

def fetch_entity_fields(entity_id: int) -> Dict[str, Any]:
    key, base = _require_env()
    s = _session(key)
    url = f"{base}/api/v1.0.0/entities/{entity_id}/summary/fields"
    r = s.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return {f["fieldTypeId"]: f.get("value", "") for f in r.json()}

def fetch_entity_links(entity_id: int) -> List[Dict[str, Any]]:
    key, base = _require_env()
    s = _session(key)
    url = f"{base}/api/v1.0.0/entities/{entity_id}/links"
    r = s.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()

def fetch_related_entities_with_direction(entity_id: int, link_type_filter: str, direction: str = "target") -> List[int]:
    links = fetch_entity_links(entity_id)
    related_ids: List[int] = []
    for link in links:
        if link["linkTypeId"].lower() == link_type_filter.lower():
            if direction == "source" and link["sourceEntityId"] == int(entity_id):
                related_ids.append(link["targetEntityId"])
            elif direction == "target" and link["targetEntityId"] == int(entity_id):
                related_ids.append(link["sourceEntityId"])
    return related_ids

def fetch_core_data(entity_id: int) -> Dict[str, Any]:
    item_data = fetch_entity_fields(entity_id)
    product_ids = fetch_related_entities_with_direction(entity_id, "ProductItem", direction="target")
    product_data = fetch_entity_fields(product_ids[0]) if product_ids else {}
    return {"item_data": item_data, "product_ids": product_ids, "product_data": product_data}

def normalize_pmc_payload(ai_out: dict, lang: str = "nl-NL") -> dict:
    """
    Zet interne AI-keys -> PMC meertalige payload.
    Verwacht basis-IDs (ProductNameCommercial, ProductDescription).
    """
    def _v(key):
        return (ai_out.get(key) or "").strip()

    fields = []
    if _v("ProductNameCommercial"):
        fields.append({
            "fieldTypeId": "ProductNameCommercial",
            "values": [{"language": lang, "value": _v("ProductNameCommercial")}],
        })
    if _v("ProductDescription"):
        fields.append({
            "fieldTypeId": "ProductDescription",
            "values": [{"language": lang, "value": _v("ProductDescription")}],
        })
    return {"fields": fields}

def update_fields(product_entity_id: int, updates: Dict[str, Any]) -> Dict[str, str]:
    key, base = _require_env()
    s = _session(key)
    url = f"{base}/api/v1.0.0/entities/{product_entity_id}/fieldValues"

    payload = []
    for k, v in (updates or {}).items():
        if isinstance(v, dict):
            lang_map = {lang: (val or "").strip() for lang, val in v.items() if (val or "").strip()}
            if lang_map:
                payload.append({"fieldTypeId": k, "value": lang_map})
        elif isinstance(v, bool):
            # <-- boolean fields (zoals ProductAgentChecked)
            payload.append({"fieldTypeId": k, "value": v})
        else:
            val = (v or "").strip()
            if val:
                payload.append({"fieldTypeId": k, "value": {"nl-NL": val}})

    payload.append({
        "fieldTypeId": "ProductDescriptionCreatedBy",
        "value": "AI-agent-all-brands-V2"
    })

    r = s.put(url, json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return {"status": "updated"}