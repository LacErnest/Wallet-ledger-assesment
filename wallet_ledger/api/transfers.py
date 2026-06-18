"""Endpoints transferts : direct et deux phases (réserver / régler / annuler).

Tous les POST sont protégés par l'idempotence : un client qui rejoue sa requête ne
déclenche jamais deux mouvements d'argent.
"""

from __future__ import annotations

from flask import Blueprint, request

from wallet_ledger.api.schemas import TransferSchema
from wallet_ledger.api.serializers import serialize_transaction
from wallet_ledger.application.accounts import AccountService
from wallet_ledger.application.transfers import TransferService
from wallet_ledger.infrastructure.idempotency import idempotent
from wallet_ledger.infrastructure.tracing import get_correlation_id

bp = Blueprint("transfers", __name__)
_accounts = AccountService()
_transfers = TransferService()


def _resolve_pair(data: dict) -> tuple[str, str]:
    sender = _accounts.get_by_number(data["sender_account_number"])
    receiver = _accounts.get_by_number(data["receiver_account_number"])
    return sender.id, receiver.id


@bp.post("/transfers")
@idempotent
def execute_transfer():
    data = TransferSchema().load(request.get_json(silent=True) or {})
    sender_id, receiver_id = _resolve_pair(data)
    txn = _transfers.execute(sender_id, receiver_id, data["amount"], get_correlation_id())
    return serialize_transaction(txn), 201


@bp.post("/transfers/initiate")
@idempotent
def initiate_transfer():
    data = TransferSchema().load(request.get_json(silent=True) or {})
    sender_id, receiver_id = _resolve_pair(data)
    txn = _transfers.initiate(sender_id, receiver_id, data["amount"], get_correlation_id())
    return serialize_transaction(txn), 201


@bp.post("/transfers/<transaction_id>/commit")
@idempotent
def commit_transfer(transaction_id: str):
    return serialize_transaction(_transfers.commit(transaction_id))


@bp.post("/transfers/<transaction_id>/fail")
@idempotent
def fail_transfer(transaction_id: str):
    return serialize_transaction(_transfers.fail(transaction_id))
