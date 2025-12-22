from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import re
import pathlib
import pandas as pd
from litellm import completion

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Mapping van business codes naar merknaam
BUSINESS_FORMULA_MAPPING = {
    "C": "Costes",
    "CC": "CottonClub",
    "TS": "TheSting",
}

SYSTEM_PROMPT_DEBUG: Dict[str, Any] = {}

# -----------------------------
# Helpers: paths dynamisch (aangepast voor TheSting + gender)
# -----------------------------
def get_rag_path(business_code: str, product_data: Optional[Dict[str, Any]] = None) -> pathlib.Path:
    """
    Bepaal dynamisch het juiste RAG-bestand op basis van business_code.
    Voor The Sting (TS) wordt ook gekeken naar ProductGender.
    """
    brand_name = BUSINESS_FORMULA_MAPPING.get(business_code)

    if business_code == "TS":
        # Strikte lookup van ProductGender in root, PRODUCTS of ITEM
        gender = (
            (product_data or {}).get("ProductGender") or
            (product_data or {}).get("PRODUCTS", {}).get("ProductGender")
        )
        gender = str(gender).strip().capitalize()  # wordt lege string als niet aanwezig
        file_name = f"InRiverExport2025online_items_{brand_name}_{gender}_Current.xlsx"
    else:
        file_name = f"InRiverExport2025online_items_{brand_name}_Current.xlsx"

    path = ROOT / "rag_data" / file_name
    logger.debug(f"📄 Gekozen RAG-pad: {path}")
    return path


def get_system_prompt_path(business_code: str, product_data: Optional[Dict[str, Any]] = None) -> pathlib.Path:
    """
    Bepaal dynamisch het juiste system prompt-bestand op basis van business_code.
    Voor The Sting (TS) wordt ook gekeken naar ProductGender.
    """
    brand_name = BUSINESS_FORMULA_MAPPING.get(business_code)

    if business_code == "TS":
        # Strikte lookup van ProductGender in root, PRODUCTS of ITEM
        gender = (
            (product_data or {}).get("ProductGender") or
            (product_data or {}).get("PRODUCTS", {}).get("ProductGender")
        )
        gender = str(gender).strip().capitalize()  # wordt lege string als niet aanwezig
        file_name = f"System_Prompt_Productomschrijvingen_{brand_name}_{gender}_Current.docx"
    else:
        file_name = f"System_Prompt_Productomschrijvingen_{brand_name}_Current.docx"

    path = ROOT / "prompts" / file_name
    logger.debug(f"🧠 Gekozen system prompt-pad: {path}")
    return path

# -----------------------------
# Helpers: RAG
# -----------------------------
def get_rag_examples(product_data: Dict[str, Any], max_examples: int = 5) -> List[Dict[str, str]]:
    # business code ophalen
    business_code = (
        product_data.get("ItemBusinessFormula") or
        product_data.get("ITEM", {}).get("ItemBusinessFormula") or
        product_data.get("PRODUCTS", {}).get("ProductBusinessFormula")
    )
    if not business_code:
        logger.warning("Geen business code gevonden in product_data")
        return []

    rag_path = get_rag_path(business_code, product_data)

    try:
        df = pd.read_excel(rag_path)
    except Exception as e:
        logger.warning("⚠️ RAG laden mislukt (%s): %s", rag_path, e)
        return []

    # ProductGroup en ProductBrandCode ophalen
    pgroup = (
        product_data.get("ProductGroup") or
        product_data.get("ITEM", {}).get("ProductGroup") or
        product_data.get("PRODUCTS", {}).get("ProductGroup") or ""
    )
    bbrandcode = (
        product_data.get("ProductBrandCode") or
        product_data.get("ITEM", {}).get("ProductBrandCode") or
        product_data.get("PRODUCTS", {}).get("ProductBrandCode") or ""
    )
    if isinstance(pgroup, list):
        pgroup = pgroup[0] if pgroup else ""
    if isinstance(bbrandcode, list):
        bbrandcode = bbrandcode[0] if bbrandcode else ""
    pgroup = str(pgroup).strip()
    bbrandcode = str(bbrandcode).strip()

    if not pgroup:
        logger.info("ℹ️ Geen ProductGroup aanwezig → geen RAG-voorbeelden.")
        return []

    # Check benodigde kolommen
    cols_needed = ["ProductNameCommercial_nl-NL", "ProductDescription_nl-NL"]
    for col in ["ProductGroup", "ProductBrandCode", *cols_needed]:
        if col not in df.columns:
            logger.warning("⚠️ Kolom ontbreekt in RAG: %s", col)
            return []

    gcol = df["ProductGroup"].fillna("").astype(str).str.strip()
    bcol = df["ProductBrandCode"].fillna("").astype(str).str.strip()

    # Filteren
    sub = pd.DataFrame()
    try:
        if bbrandcode:
            mask_both = (gcol == pgroup) & (bcol == bbrandcode)
            sub = df.loc[mask_both, cols_needed].dropna(how="any")
            if sub.empty:
                # fallback: alleen op group filteren
                sub = df.loc[gcol == pgroup, cols_needed].dropna(how="any")
        else:
            sub = df.loc[gcol == pgroup, cols_needed].dropna(how="any")

        sub = sub.head(max_examples)

    except Exception as e:
        logger.warning("⚠️ RAG filter mislukt: %s", e)
        return []

    # Teruggeven als lijst van dicts
    return [
        {
            "name": str(row["ProductNameCommercial_nl-NL"]),
            "description": str(row["ProductDescription_nl-NL"]),
        }
        for _, row in sub.iterrows()
    ]

# -----------------------------
# Helpers: system prompt
# -----------------------------
def _load_system_prompt(business_code: str, product_data: Optional[Dict[str, Any]] = None) -> str:
    system_prompt_path = get_system_prompt_path(business_code, product_data)
    default_prompt = (
        f"Je bent PimContentManager, een creatieve NL product-schrijver voor {BUSINESS_FORMULA_MAPPING.get(business_code)}. "
        "Je schrijft vlot, commercieel en consistent met eerdere teksten en volgt strikt: "
        "maximaal 50 woorden, een productnaam en een productomschrijving met 1 styling-URL (interne link), "
        "geen kleur, tone-of-voice per ProductBrandCode. "
        "Houd je aan de richtlijnen: maximaal 50 woorden in HTML met interne link, stylingadvies alleen over de huidige productgroep, "
        "vermijd kleuren en benoem nooit de ProductBrandCode in de productomschrijving."
    )

    SYSTEM_PROMPT_DEBUG.update({
        "ok": False,
        "source": str(system_prompt_path),
        "used_fallback": None,
        "chars": None,
    })

    try:
        import docx
    except Exception as e:
        logger.error("python-docx niet beschikbaar: %s", e)
        SYSTEM_PROMPT_DEBUG.update({"ok": False, "used_fallback": True, "chars": len(default_prompt)})
        return default_prompt

    try:
        if not system_prompt_path.exists():
            logger.warning("System prompt niet gevonden: %s. Fallback.", system_prompt_path)
            SYSTEM_PROMPT_DEBUG.update({"ok": False, "used_fallback": True, "chars": len(default_prompt)})
            return default_prompt

        doc = docx.Document(str(system_prompt_path))
        text = "\n".join(p.text for p in doc.paragraphs).strip()
        if not text:
            SYSTEM_PROMPT_DEBUG.update({"ok": False, "used_fallback": True, "chars": len(default_prompt)})
            return default_prompt

        SYSTEM_PROMPT_DEBUG.update({"ok": True, "used_fallback": False, "chars": len(text)})
        return text

    except Exception:
        SYSTEM_PROMPT_DEBUG.update({"ok": False, "used_fallback": True, "chars": len(default_prompt)})
        return default_prompt

# -----------------------------
# Helpers: vision description
# -----------------------------
def _build_visual_description(vision: Dict[str, Any]) -> str:
    if not isinstance(vision, dict):
        return str(vision).strip()
    parts = []
    for shot, info in vision.items():
        desc = (info or {}).get("description", "")
        if desc:
            parts.append(f"[{shot}] {desc}")
    return "\n".join(parts).strip()

# -----------------------------
# Robust JSON extraction / validation
# -----------------------------
def _strip_code_fences(s: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip(), flags=re.IGNORECASE | re.MULTILINE)

def _find_first_json(s: str) -> Optional[dict]:
    s = _strip_code_fences(s)
    try:
        return json.loads(s)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", s)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

def _limit_words(text: str, max_words: int = 50) -> str:
    words = re.findall(r"\S+", text or "")
    if len(words) <= max_words:
        return text or ""
    return " ".join(words[:max_words]).rstrip(",.;:!?””)\"'") + "…"

def _validate_output(d: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing = []
    for key in ("ProductNameCommercial", "ProductDescription", "Toelichting"):
        val = (d or {}).get(key, "") or ""
        if not isinstance(val, str) or not val.strip():
            missing.append(key)
    return (len(missing) == 0, missing)

# -----------------------------
# LLM call
# -----------------------------
def _build_user_prompt(product_data: Dict[str, Any], visual_description: str,
                       examples: Optional[List[Dict[str, str]]] = None) -> str:
    prompt = "[PRODUCTDATA]\n"
    for section, fields in product_data.items():
        prompt += f"\n[{section.upper()}]\n"
        for k, v in fields.items():
            prompt += f"{k}: {v}\n"

    if examples:
        prompt += "\n[VOORBEELDEN UIT EERDERE PRODUCTEN]\n"
        for ex in examples:
            prompt += f"Productnaam: {ex.get('name','')}\nBeschrijving: {ex.get('description','')}\n\n"

    prompt += "\n[VISUELE BESCHRIJVING]\n" + (visual_description or "") + "\n\n"
    prompt += (
        "Schrijf een commerciële productnaam en een korte productbeschrijving.\n"
        "Formaat:\n"
        "ProductNameCommercial: ...\n"
        "ProductDescription: ...\n"
        "Toelichting: ...\n"
        "Toelichting: 1–5 zinnen waarin je je keuzes uitlegt en of je visuele input, RAG en system prompt hebt gebruikt.\n"
        "Antwoord in het Nederlands.\n"
        "BELANGRIJK: Geef uitsluitend een JSON-object terug met exact deze keys: "
        '{"ProductNameCommercial":"","ProductDescription":"","Toelichting":""}\n'
        "Geen extra tekst, geen uitleg buiten het JSON-object."
    )
    return prompt

def _llm_generate(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
    resp = completion(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

# -----------------------------
# High-level AI call + parse
# -----------------------------
def _copy_agent_call(product_data: Dict[str, Any], visual_description: str,
                     examples: Optional[List[Dict[str, str]]] = None,
                     max_retries: int = 2) -> Tuple[Dict[str, str], Dict[str, Any]]:
    business_code = (
    product_data.get("ItemBusinessFormula") or
    product_data.get("ITEM", {}).get("ItemBusinessFormula") or
    product_data.get("PRODUCTS", {}).get("ProductBusinessFormula")
)
    system_prompt = _load_system_prompt(business_code, product_data)
    user_prompt = _build_user_prompt(product_data, visual_description, examples)

    attempts: List[Dict[str, Any]] = []
    last_parsed: Dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        raw = _llm_generate(system_prompt, user_prompt)
        parsed = _find_first_json(raw) or {}
        result = {
            "ProductNameCommercial": str(parsed.get("ProductNameCommercial", "")).strip(),
            "ProductDescription": str(parsed.get("ProductDescription", "")).strip(),
            "Toelichting": str(parsed.get("Toelichting", "")).strip(),
        }
        ok, missing = _validate_output(result)
        attempts.append({
            "attempt": attempt + 1,
            "raw_len": len(raw or ""),
            "raw_preview": (raw or "")[:240],
            "parsed_keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
            "ok": ok,
            "missing": missing,
        })
        last_parsed = result

        if ok:
            result["ProductDescription"] = _limit_words(result["ProductDescription"], 50)
            return result, {"attempts": attempts, "from_fallback": False}

        user_prompt += (
            "\n\nLET OP: In je vorige antwoord ontbraken deze verplichte velden: "
            + ", ".join(missing)
            + ". Antwoord opnieuw en geef ALLEEN het JSON-object met exact de drie keys. "
              "Geen uitleg, geen code fences."
        )

    fb = _fallback_copy(last_parsed, product_data)
    return fb, {"attempts": attempts, "from_fallback": True}

# -----------------------------
# Fallback generator
# -----------------------------
def _fallback_copy(current: Dict[str, str], product_data: Dict[str, Any]) -> Dict[str, str]:
    pd_flat = product_data.get("PRODUCTS") or product_data.get("PRODUCT") or product_data
    name = (
        current.get("ProductNameCommercial")
        or str(pd_flat.get("ProductNameCommercial") or pd_flat.get("Name") or pd_flat.get("Title") or "Nieuw item")
    ).strip()

    base_desc = (
        pd_flat.get("ShortDescription")
        or pd_flat.get("ProductDescription")
        or pd_flat.get("Description")
        or ""
    )
    if isinstance(base_desc, list):
        base_desc = " ".join(str(x) for x in base_desc if x)

    desc = (current.get("ProductDescription") or str(base_desc) or "Korte productbeschrijving volgt.").strip()
    desc = _limit_words(desc, 50)

    toel = (current.get("Toelichting") or
            "Automatische fallback: naam en beschrijving samengesteld uit beschikbare productvelden. "
            "Controleer tone-of-voice en voeg styling-URL toe.").strip()

    return {
        "ProductNameCommercial": name,
        "ProductDescription": desc,
        "Toelichting": toel,
    }

# -----------------------------
# Coercion
# -----------------------------
def _coerce_dict(x) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            obj = json.loads(x)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}

# -----------------------------
# ADK-tool: pipeline
# -----------------------------
def tool_copy_pipeline(item_data: Dict[str, Any], product_data: Dict[str, Any], vision: Dict[str, Any]) -> Dict[str, Any]:
    logger.debug("🧩 tool_copy_pipeline gestart")

    item_data = _coerce_dict(item_data)
    product_data = _coerce_dict(product_data)
    vision = _coerce_dict(vision)

    visual_description = _build_visual_description(vision)

    examples = get_rag_examples({"ITEM": item_data, "PRODUCTS": product_data}, max_examples=5)
    logger.debug("📦 %d RAG-voorbeelden opgehaald", len(examples))

    payload, telemetry = _copy_agent_call({"ITEM": item_data, "PRODUCTS": product_data}, visual_description, examples)

    debug_block = {
        "rag_examples_count": len(examples),
        "used_filters": {
            "ProductGroup": product_data.get("ProductGroup"),
            "ProductBrandCode": product_data.get("ProductBrandCode"),
        },
        "examples_used": examples,
        "system_prompt": SYSTEM_PROMPT_DEBUG,
        "generation": telemetry,
    }

    result: Dict[str, Any] = {
        "ProductNameCommercial": payload["ProductNameCommercial"],
        "ProductDescription": payload["ProductDescription"],
        "Toelichting": payload["Toelichting"],
        "copy_subagent": {
            "ProductNameCommercial": payload["ProductNameCommercial"],
            "ProductDescription": payload["ProductDescription"],
            "Toelichting": payload["Toelichting"],
        },
        "debug": debug_block,
    }

    ok, missing = _validate_output(payload)
    if not ok:
        logger.warning("❗ copy_subagent output incompleet: %s", missing)
        result.setdefault("debug", {}).update({"final_missing": missing})

    return result