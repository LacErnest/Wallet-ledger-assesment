"""Endpoints transactions : annulation par contre-passation."""

from __future__ import annotations

from flask import Blueprint

from wallet_ledger.api.serializers import serialize_transaction
from wallet_ledger.application.reversals import ReversalService
from wallet_ledger.infrastructure.idempotency import idempotent
from wallet_ledger.infrastructure.tracing import get_correlation_id

bp = Blueprint("transactions", __name__)
_reversals = ReversalService()


@bp.post("/transactions/<transaction_id>/reverse")
@idempotent
def reverse_transaction(transaction_id: str):
    """Annule une transaction réussie via une transaction compensatoire (REVERSAL)."""
    reversal = _reversals.reverse(transaction_id, get_correlation_id())
    return serialize_transaction(reversal), 201
