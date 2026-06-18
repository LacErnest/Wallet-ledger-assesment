"""Service de notification : informer le client à chaque mouvement sur son argent.

Il s'abonne aux événements de domaine. Le service de transfert n'a donc rien à savoir
des emails ou des SMS : il publie « transfert effectué », et c'est ici qu'on prévient
le client. On persiste chaque envoi pour pouvoir prouver, plus tard, qu'il a eu lieu.
"""

from __future__ import annotations

import logging

from wallet_ledger.application.accounts import AccountService
from wallet_ledger.domain.events import (
    DEPOSIT_COMPLETED,
    DomainEvent,
    EventBus,
    TRANSFER_COMPLETED,
    TRANSFER_FAILED,
)
from wallet_ledger.extensions import db
from wallet_ledger.infrastructure.notifications import NotificationChannel
from wallet_ledger.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, channels: list[NotificationChannel], accounts: AccountService | None = None):
        self._channels = channels
        self._accounts = accounts or AccountService()

    def register(self, bus: EventBus) -> None:
        """Branche le service sur les événements qui méritent d'avertir le client."""
        bus.subscribe(TRANSFER_COMPLETED, self.on_transfer_completed)
        bus.subscribe(TRANSFER_FAILED, self.on_transfer_failed)
        bus.subscribe(DEPOSIT_COMPLETED, self.on_deposit_completed)

    def on_transfer_completed(self, event: DomainEvent) -> None:
        payload = event.payload
        message = f"Transfert de {payload['amount']} {payload['currency']} effectué."
        self._notify(payload["sender_id"], message, event)

    def on_transfer_failed(self, event: DomainEvent) -> None:
        self._notify_transaction_party(event, "Votre transfert a échoué ; les fonds réservés ont été libérés.")

    def on_deposit_completed(self, event: DomainEvent) -> None:
        payload = event.payload
        message = f"Dépôt de {payload['amount']} {payload['currency']} crédité sur votre compte."
        self._notify(payload["account_id"], message, event)

    def _notify_transaction_party(self, event: DomainEvent, message: str) -> None:
        # Certains événements (échec) ne portent qu'un identifiant de transaction :
        # on reste robuste si le destinataire n'est pas déductible.
        recipient_account = event.payload.get("sender_id") or event.payload.get("account_id")
        if recipient_account:
            self._notify(recipient_account, message, event)

    def _notify(self, account_id: str, message: str, event: DomainEvent) -> None:
        recipient = self._recipient_for(account_id)
        for channel in self._channels:
            sent = channel.send(recipient, message)
            db.session.add(Notification(
                channel=channel.name, recipient=recipient, message=message,
                event_type=event.event_type, status="SENT" if sent else "FAILED",
                correlation_id=event.correlation_id,
            ))
        db.session.commit()

    def _recipient_for(self, account_id: str) -> str:
        # En l'absence de carnet de contacts, on adresse au propriétaire du compte.
        try:
            return self._accounts.get(account_id).owner_id
        except Exception:  # noqa: BLE001 — une notification ne doit jamais faire échouer un paiement
            return account_id
