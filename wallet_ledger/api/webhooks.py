"""Endpoints webhook : confirmation de paiement par le fournisseur.

On VÉRIFIE d'abord la signature : sans cette preuve d'authenticité, n'importe qui
pourrait appeler ce endpoint pour faire créditer un compte. La réconciliation du montant
est ensuite faite par le service de dépôt.

Deux formes coexistent : un endpoint par fournisseur (chaque fournisseur a sa propre URL
de webhook côté tableau de bord) et un endpoint unique `/payments/webhook` (forme de
l'énoncé) où le fournisseur est indiqué dans le corps.
"""

from __future__ import annotations

from flask import Blueprint, request

from wallet_ledger.application.deposits import DepositService
from wallet_ledger.domain.errors import UnsupportedProviderError, WebhookVerificationError
from wallet_ledger.infrastructure.payments import get_payment_provider

bp = Blueprint("webhooks", __name__)


def _process(provider_name: str):
    raw_body = request.get_data()
    # Stripe signe via « Stripe-Signature » ; les autres via un en-tête générique.
    signature = request.headers.get("Stripe-Signature") or request.headers.get("X-Signature", "")

    adapter = get_payment_provider(provider_name)
    if not adapter.verify_webhook(raw_body, signature):
        raise WebhookVerificationError(provider_name)

    result = adapter.parse_callback(request.get_json(silent=True) or {})
    if not result.is_success:
        # Échec/annulation côté fournisseur : rien à créditer.
        return {"status": "ignored"}

    txn = DepositService().settle(result.reference, result.amount, result.currency)
    return {"transaction_id": txn.id, "status": txn.status.value}


@bp.post("/payments/webhook/<provider>")
def payment_webhook(provider: str):
    return _process(provider)


@bp.post("/payments/webhook")
def payment_webhook_alias():
    # Endpoint unique : le fournisseur vient de l'en-tête X-Provider ou du corps.
    provider = request.headers.get("X-Provider") or (request.get_json(silent=True) or {}).get(
        "provider"
    )
    if not provider:
        raise UnsupportedProviderError("(absent du corps et de l'en-tête X-Provider)")
    return _process(provider)
