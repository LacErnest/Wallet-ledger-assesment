"""Endpoint webhook : confirmation de paiement par le fournisseur.

On VÉRIFIE d'abord la signature : sans cette preuve d'authenticité, n'importe qui
pourrait appeler ce endpoint pour faire créditer un compte. La réconciliation du montant
est ensuite faite par le service de dépôt.
"""

from __future__ import annotations

from flask import Blueprint, request

from wallet_ledger.application.deposits import DepositService
from wallet_ledger.domain.errors import WebhookVerificationError
from wallet_ledger.infrastructure.payments import get_payment_provider

bp = Blueprint("webhooks", __name__)


@bp.post("/payments/webhook/<provider>")
def payment_webhook(provider: str):
    raw_body = request.get_data()
    # Stripe signe via « Stripe-Signature » ; les autres via un en-tête générique.
    signature = request.headers.get("Stripe-Signature") or request.headers.get("X-Signature", "")

    adapter = get_payment_provider(provider)
    if not adapter.verify_webhook(raw_body, signature):
        raise WebhookVerificationError(provider)

    result = adapter.parse_callback(request.get_json(silent=True) or {})
    if not result.is_success:
        # Échec/annulation côté fournisseur : rien à créditer.
        return {"status": "ignored"}

    txn = DepositService().settle(result.reference, result.amount)
    return {"transaction_id": txn.id, "status": txn.status.value}
