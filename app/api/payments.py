from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlmodel import Session, select
from ..schemas import PaymentCreate, PaymentOut, ConfirmResponse, RefundRequest
from ..db import get_session
from ..crud import create_payment, get_payment, list_payments, update_payment_status, add_event
from ..gateway import get_gateway
from typing import List, Optional
import json

router = APIRouter(prefix="/payments", tags=["payments"])

IDEMPOTENCY_HEADER = "Idempotency-Key"

@router.post("", response_model=PaymentOut)
def create_payment_endpoint(payload: PaymentCreate, request: Request, session: Session = Depends(get_session), idempotency_key: Optional[str] = Header(None, alias=IDEMPOTENCY_HEADER)):
    # idempotency: if client passes Idempotency-Key and a payment exists with same key, return it
    if idempotency_key:
        from ..models import Payment as PaymentModel
        q = select(PaymentModel).where(PaymentModel.idempotency_key == idempotency_key)
        res = session.exec(q).first()
        if res:
            return PaymentOut(
                id=res.id,
                external_id=res.external_id,
                amount_cents=res.amount_cents,
                currency=res.currency,
                status=res.status,
                metadata=json.loads(res.metadata) if res.metadata else None,
                created_at=res.created_at.isoformat(),
                updated_at=res.updated_at.isoformat(),
            )

    p = create_payment(session, payload.amount_cents, payload.currency, payload.metadata)
    # store idempotency key if provided
    if idempotency_key:
        p.idempotency_key = idempotency_key
        session.add(p)
        session.commit()
        session.refresh(p)

    gateway = get_gateway()
    try:
        external_id, info = gateway.create_intent(p.amount_cents, p.currency, idempotency_key)
    except TypeError:
        external_id, info = gateway.create_intent(p.amount_cents, p.currency)
    # store stripe payment intent id if using stripe adapter
    try:
        from ..models import Payment as PaymentModel
        PaymentModel.stripe_payment_intent_id  # reference to avoid linter errors
        # if adapter returned external id, store in stripe_payment_intent_id
    except Exception:
        pass
    update_payment_status(session, p, "created", external_id)
    add_event(session, p.id, "created", {"gateway_info": info})
    return PaymentOut(
        id=p.id,
        external_id=p.external_id,
        amount_cents=p.amount_cents,
        currency=p.currency,
        status=p.status,
        metadata=json.loads(p.metadata) if p.metadata else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )

@router.post("/{payment_id}/confirm", response_model=ConfirmResponse)
def confirm_payment(payment_id: int, session: Session = Depends(get_session)):
    p = get_payment(session, payment_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    gateway = get_gateway()
    res = gateway.confirm_payment(p.external_id or "")
    if res.get("status") in ("succeeded", "requires_capture", "captured"):
        try:
            charge_id = res.get("charge_id")
            if charge_id:
                p.gateway_charge_id = charge_id
        except Exception:
            pass
        update_payment_status(session, p, "captured")
        add_event(session, p.id, "captured", res)
        return ConfirmResponse(success=True, message="Payment captured")
    update_payment_status(session, p, "failed")
    add_event(session, p.id, "failed", res)
    return ConfirmResponse(success=False, message="Failed to capture")

@router.post("/{payment_id}/refund")
def refund_payment(payment_id: int, refund: RefundRequest, session: Session = Depends(get_session)):
    p = get_payment(session, payment_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.status not in ("captured",):
        raise HTTPException(status_code=400, detail="Only captured payments can be refunded")
    gateway = get_gateway()
    res = gateway.refund(p.external_id or "", refund.amount_cents)
    update_payment_status(session, p, "refunded")
    add_event(session, p.id, "refunded", res)
    return {"success": True, "refund": res}

@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment_endpoint(payment_id: int, session: Session = Depends(get_session)):
    p = get_payment(session, payment_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentOut(
        id=p.id,
        external_id=p.external_id,
        amount_cents=p.amount_cents,
        currency=p.currency,
        status=p.status,
        metadata=json.loads(p.metadata) if p.metadata else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )

@router.get("", response_model=List[PaymentOut])
def list_payments_endpoint(limit: int = 100, session: Session = Depends(get_session)):
    payments = list_payments(session, limit)
    out = []
    for p in payments:
        out.append(PaymentOut(
            id=p.id,
            external_id=p.external_id,
            amount_cents=p.amount_cents,
            currency=p.currency,
            status=p.status,
            metadata=json.loads(p.metadata) if p.metadata else None,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        ))
    return out
