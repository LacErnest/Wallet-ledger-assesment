"""Endpoints change : consultation de taux, conversion et transfert multi-devises."""

from __future__ import annotations

from flask import Blueprint, request

from wallet_ledger.api.schemas import FxConvertSchema, FxTransferSchema
from wallet_ledger.api.serializers import serialize_transaction
from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.fx import FxService
from wallet_ledger.domain.money import Money
from wallet_ledger.infrastructure.idempotency import idempotent
from wallet_ledger.infrastructure.tracing import get_correlation_id

bp = Blueprint("fx", __name__)
_accounts = AccountService()
_fx = FxService()


@bp.get("/fx/convert")
def convert():
    data = FxConvertSchema().load(request.args.to_dict())
    converted = _fx.convert(Money(data["amount"], data["from_currency"]), data["to_currency"])
    return {"converted_amount": str(converted.amount), "currency": converted.currency}


@bp.post("/fx/transfer")
@idempotent
def fx_transfer():
    data = FxTransferSchema().load(request.get_json(silent=True) or {})
    sender = _accounts.get_by_number(data["sender_account_number"])
    receiver = _accounts.get_by_number(data["receiver_account_number"])
    txn = _fx.execute_fx_transfer(sender.id, receiver.id, data["amount"], get_correlation_id())
    return serialize_transaction(txn), 201
