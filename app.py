import os, hmac, hashlib, json, asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from adk_app.agent import root_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from tools.inriver_api import lookup_entity_id, fetch_core_data

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # zet je secret hier

app = FastAPI()

class WebhookPayload(BaseModel):
    StepName: str
    Action: str
    StepStatusName: str
    ProductCode: str
    ClientName: str  # bijv. costes, cotton club, the sting

def compute_cf_signature(secret: str, body: bytes) -> str:
    """
    Creative Force: HMAC-SHA256(key=secret, msg=raw_json_body).hexdigest()
    Geeft een 64-karakter hex string terug.
    """
    if secret is None:
        raise RuntimeError("WEBHOOK_SECRET is niet gezet")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

@app.post("/webhook")
async def webhook(request: Request, x_cf_signature: str = Header(None)):
    # --- 1) Lees RUWE body & verifieer signature ---
    raw_body: bytes = await request.body()
    try:
        expected = compute_cf_signature(WEBHOOK_SECRET, raw_body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config error: {e}")

    if not x_cf_signature:
        raise HTTPException(status_code=400, detail="Missing X-CF-Signature header")

    # Constant-time compare tegen timing attacks
    if not hmac.compare_digest(expected, x_cf_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # --- 2) Parse JSON naar jouw payload model ---
    try:
        payload = WebhookPayload.model_validate_json(raw_body)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {ve}")

    # --- 3) JOUW bestaande logica ---
    if payload.StepName != "Asset Delivery":
        return {"message": "Webhook received but StepName is not 'Asset Delivery'. No action taken."}
    if payload.Action != "Completed":
        return {"message": "Webhook received but Action is not 'Completed'. No action taken."}
    if payload.StepStatusName != "Done":
        return {"message": "Webhook received but StepStatusName is not 'Done'. No action taken."}
    client = (payload.ClientName or "").casefold()
    if client not in {"costes", "cotton club", "the sting"}:
        return {"message": f"Webhook received but ClientName '{client}' is not supported. No action taken."}

    # --- Preflight skip-check op ProductAgentChecked ---
    try:
        ent = lookup_entity_id(product_code=payload.ProductCode)
        entity_id = ent.get("entity_id")
        if entity_id:
            core = fetch_core_data(entity_id)
            product_checked_value = core.get("product_data", {}).get("ProductAgentChecked")

            # Converteer string "true"/"false" naar boolean, anders None
            is_checked = None
            if isinstance(product_checked_value, bool):
                is_checked = product_checked_value
            elif isinstance(product_checked_value, str):
                val_lower = product_checked_value.strip().lower()
                if val_lower == "true": is_checked = True
                elif val_lower == "false": is_checked = False

            if is_checked is not None:
                return {
                    "message": f"Overgeslagen: ProductAgentChecked={is_checked} op product-level.",
                    "product_entity_id": core.get("product_ids", [None])[0],
                    "reason": "Product reeds gecontroleerd (ProductAgentChecked)."
                }
    except Exception:
        pass

    # --- ADK sessie/runner voorbereiden (ongewijzigd) ---
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    user_id = "creativeForce"
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="orchestrator_app",
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(
        agent=root_agent,
        app_name="orchestrator_app",
        session_service=session_service,
    )

    input_data = {"ProductCode": payload.ProductCode}
    content = types.Content(role="user", parts=[types.Part(text=json.dumps(input_data))])

    result = {"final_response": None, "error": None, "session_state": {}}

    async def run_job():
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                is_final = hasattr(event, "is_final_response") and event.is_final_response()
                if is_final and getattr(event, "content", None) and getattr(event.content, "parts", None):
                    parts = event.content.parts
                    if parts and getattr(parts[0], "text", None):
                        result["final_response"] = parts[0].text
            try:
                result["session_state"] = getattr(session, "state", {})
            except Exception as e:
                result["session_state"] = {"error": str(e)}
        except Exception as e:
            result["error"] = str(e)

    async def gen():
        yield ": connected\n\n"
        task = asyncio.create_task(run_job())
        while not task.done():
            yield ": heartbeat\n\n"
            await asyncio.sleep(15)
        await task
        if result["error"]:
            err = {"error": result["error"], "session_id": session_id}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
        else:
            done = {
                "message": "Root agent executed successfully",
                "result": result["final_response"] or "No response received.",
                "session_id": session_id,
                "session_state": result["session_state"],
            }
            yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")