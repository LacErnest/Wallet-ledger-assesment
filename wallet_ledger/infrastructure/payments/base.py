"""Port « fournisseur de paiement » (patron Ports & Adaptateurs).

Le service de dépôt ne connaît que cette interface : il ignore si l'argent arrive
par carte (Stripe) ou par mobile money (PawaPay). On peut donc ajouter un fournisseur
sans toucher au cœur métier (principe ouvert/fermé).
"""

from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


def hmac_sha256_hex(secret: str, message: bytes) -> str:
    """Signature HMAC-SHA256 : preuve qu'un message vient bien d'un détenteur du secret."""
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ProviderCharge:
    """Résultat d'une demande de paiement. La référence relie le futur webhook à notre transaction."""

    reference: str
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CallbackResult:
    """Données d'un webhook, normalisées pour que le service de dépôt soit agnostique."""

    reference: str
    is_success: bool
    amount: Decimal | None = None
    currency: str | None = None


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def create_deposit(self, *, amount: Decimal, currency: str, reference: str, context: dict) -> ProviderCharge:
        """Demande au fournisseur d'encaisser le paiement (la confirmation arrive plus tard, par webhook)."""

    @abstractmethod
    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        """Vrai seulement si la signature prouve l'authenticité. Toujours refuser en cas de doute."""

    @abstractmethod
    def parse_callback(self, payload: dict) -> CallbackResult:
        """Extrait référence, succès et montant du corps du webhook propre au fournisseur."""
