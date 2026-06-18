"""Endpoint dépôts : l'utilisateur initie un dépôt via un fournisseur de paiement."""

from __future__ import annotations

from flask import Blueprint, request

from wallet_ledger.api.schemas import DepositSchema
from wallet_ledger.api.serializers import serialize_transaction
from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.deposits import DepositService
from wallet_ledger.infrastructure.idempotency import idempotent
from wallet_ledger.infrastructure.tracing import get_correlation_id

bp = Blueprint("deposits", __name__)
_accounts = AccountService()


@bp.post("/deposits")
@idempotent
def create_deposit():
    data = DepositSchema().load(request.get_json(silent=True) or {})
    account = _accounts.get_by_number(data["account_number"])

    # Contexte propre au mobile money : on ne transmet que ce qui est fourni.
    context = {k: data[k] for k in ("operator", "phone_number") if k in data}

    txn = DepositService().initiate(
        account.id, data["amount"], data["provider"], context, get_correlation_id()
    )
    return serialize_transaction(txn), 201
