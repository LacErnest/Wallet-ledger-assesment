"""Événements de domaine et bus en mémoire (patron Observateur).

Pourquoi : un transfert réussi doit pouvoir déclencher une notification sans que le
service de transfert connaisse l'email ou le SMS. On publie un événement, et les
abonnés réagissent. Cela respecte l'inversion de dépendances : le cœur métier ne
dépend pas des canaux de communication.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Noms d'événements (constantes pour éviter les fautes de frappe entre éditeur et abonné).
FUNDS_RESERVED = "FundsReserved"
TRANSFER_COMPLETED = "TransferCompleted"
TRANSFER_FAILED = "TransferFailed"
DEPOSIT_COMPLETED = "DepositCompleted"


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    payload: dict
    correlation_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Bus synchrone et en mémoire : suffisant ici, remplaçable par un courtier plus tard."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[DomainEvent], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._subscribers.get(event.event_type, []):
            # Un abonné qui échoue (ex. SMS indisponible) ne doit jamais annuler une
            # opération financière déjà validée : on isole et on journalise.
            try:
                handler(event)
            except Exception:  # noqa: BLE001 — on protège volontairement l'argent déjà engagé
                logger.exception("Échec d'un abonné pour l'événement %s", event.event_type)

    def clear(self) -> None:
        self._subscribers.clear()


# Singleton applicatif : un seul bus partagé par l'application.
event_bus = EventBus()
