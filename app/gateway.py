import uuid
from typing import Tuple, Optional
from .config import settings

class MockGateway:
    def create_intent(self, amount_cents: int, currency: str, idempotency_key: Optional[str] = None) -> Tuple[str, dict]:
        external_id = f"mock_{uuid.uuid4()}"
        return external_id, {"status": "requires_confirmation", "client_secret": None}

    def confirm_payment(self, external_id: str) -> dict:
        return {"status": "succeeded", "external_id": external_id, "charge_id": f"ch_{uuid.uuid4()}"}

    def refund(self, external_id: str, amount_cents: int | None = None) -> dict:
        return {"status": "refunded", "external_id": external_id, "amount_refunded": amount_cents}

try:
    import stripe
except Exception:
    stripe = None

class StripeAdapter:
    def __init__(self, api_key: str):
        if stripe is None:
            raise RuntimeError("stripe package not installed")
        stripe.api_key = api_key

    def create_intent(self, amount_cents: int, currency: str, idempotency_key: Optional[str] = None) -> Tuple[str, dict]:
        kwargs = {
            "amount": amount_cents,
            "currency": currency.lower(),
            "automatic_payment_methods": {"enabled": True},
        }
        if idempotency_key and stripe:
            intent = stripe.PaymentIntent.create(**kwargs, idempotency_key=idempotency_key)
        else:
            intent = stripe.PaymentIntent.create(**kwargs)
        return intent.id, {"status": intent.status, "client_secret": getattr(intent, 'client_secret', None)}

    def confirm_payment(self, external_id: str) -> dict:
        intent = stripe.PaymentIntent.retrieve(external_id)
        if intent.status in ("requires_confirmation", "requires_payment_method"):
            intent = stripe.PaymentIntent.confirm(external_id)
        charge_id = None
        try:
            charge_id = intent.charges.data[0].id if intent.charges and intent.charges.data else None
        except Exception:
            charge_id = None
        return {"status": intent.status, "external_id": intent.id, "charge_id": charge_id}

    def refund(self, external_id: str, amount_cents: int | None = None) -> dict:
        refund_args = {"payment_intent": external_id}
        if amount_cents:
            refund_args["amount"] = amount_cents
        r = stripe.Refund.create(**refund_args)
        return {"status": r.status, "refund_id": r.id, "amount": getattr(r, "amount", None)}

def get_gateway():
    if settings.MOCK_GATEWAY:
        return MockGateway()
    if settings.STRIPE_API_KEY:
        return StripeAdapter(settings.STRIPE_API_KEY)
    return MockGateway()
