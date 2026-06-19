"""Fabrique de fournisseurs de paiement (patron Fabrique).

Chaque fournisseur (Stripe, PawaPay, PayPal) est un *adaptateur* derrière le port
`PaymentProvider` (Ports & Adaptateurs) : il traduit une API externe vers notre interface.
Cette fabrique en choisit un par son nom et l'instancie avec sa configuration. Ajouter un
fournisseur = une classe d'adaptateur + une branche ici, sans rien changer ailleurs.
"""

from __future__ import annotations

from flask import current_app

from wallet_ledger.domain.errors import UnsupportedProviderError
from wallet_ledger.infrastructure.payments.base import PaymentProvider
from wallet_ledger.infrastructure.payments.pawapay_provider import PawaPayProvider
from wallet_ledger.infrastructure.payments.paypal_provider import PayPalProvider
from wallet_ledger.infrastructure.payments.stripe_provider import StripeProvider

__all__ = ["PaymentProvider", "get_payment_provider"]


def get_payment_provider(name: str) -> PaymentProvider:
    config = current_app.config
    key = name.lower()
    if key == "stripe":
        return StripeProvider(config["STRIPE_API_KEY"], config["STRIPE_WEBHOOK_SECRET"])
    if key == "pawapay":
        return PawaPayProvider(
            config["PAWAPAY_BASE_URL"],
            config["PAWAPAY_API_TOKEN"],
            config["PAWAPAY_WEBHOOK_SECRET"],
        )
    if key == "paypal":
        return PayPalProvider(
            config["PAYPAL_API_BASE"],
            config["PAYPAL_CLIENT_ID"],
            config["PAYPAL_SECRET"],
            config["PAYPAL_WEBHOOK_SECRET"],
        )
    raise UnsupportedProviderError(name)
