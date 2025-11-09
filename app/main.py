from fastapi import FastAPI, Request, HTTPException
from .db import init_db
from .api.payments import router as payments_router
from .config import settings
import json

app = FastAPI(title="Payment Microservice", version="0.3.0")

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(payments_router)

@app.post("/webhooks")
async def webhook(request: Request):
    payload_bytes = await request.body()
    payload_text = payload_bytes.decode('utf-8')
    # If Stripe webhook secret is configured, verify signature
    if settings.STRIPE_WEBHOOK_SECRET:
        try:
            import stripe
            sig_header = request.headers.get("stripe-signature")
            event = stripe.Webhook.construct_event(payload=payload_text, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Webhook verification failed: {str(e)}")
        evt = event
        # Example handling for payment_intent.succeeded and charge.refunded
        if evt["type"] == "payment_intent.succeeded":
            pi = evt["data"]["object"]
            # TODO: lookup payment by stripe_payment_intent_id and update status in DB
            return {"received": True, "type": evt["type"], "id": pi.get("id")}
        if evt["type"] == "charge.refunded":
            ch = evt["data"]["object"]
            return {"received": True, "type": evt["type"], "id": ch.get("id")}
        return {"received": True, "type": evt["type"]}
    else:
        try:
            data = json.loads(payload_text)
        except Exception:
            data = {"raw": payload_text}
        return {"received": True, "event": data}
