"""Service de risque interne (phase 2 d'un transfert).

Pourquoi une étape dédiée : entre la réservation des fonds et leur règlement, une
plateforme financière veut pouvoir dire « non » (montant anormal, compte suspect…).
On isole cette décision derrière une interface pour pouvoir, demain, brancher un vrai
moteur anti-fraude sans toucher au service de transfert (inversion de dépendances).
"""

from __future__ import annotations

from decimal import Decimal

from wallet_ledger.domain.errors import RiskRejectedError
from wallet_ledger.domain.money import Money


class RiskService:
    """Politique de risque minimale mais réaliste, remplaçable par un moteur externe."""

    # Au-delà de ce seuil, un transfert demande une vérification humaine : on préfère
    # bloquer et laisser un humain trancher plutôt que régler un montant aberrant.
    def __init__(self, auto_approval_limit: Decimal = Decimal("1000000")):
        self._auto_approval_limit = auto_approval_limit

    def assess(self, amount: Money) -> None:
        """Valide le règlement ou lève RiskRejectedError. Le silence vaut approbation."""
        if amount.amount > self._auto_approval_limit:
            raise RiskRejectedError(
                f"montant {amount} supérieur au plafond d'approbation automatique"
            )
