"""Canaux de notification (email, SMS).

Patron Ports & Adaptateurs : le service de notification ne connaît que l'interface
`NotificationChannel`. Brancher un vrai fournisseur (SendGrid, Twilio…) se fera en
ajoutant un adaptateur, sans toucher au cœur métier.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    name: str

    @abstractmethod
    def send(self, recipient: str, message: str) -> bool:
        """Envoie le message ; renvoie le succès. Un échec ne doit jamais casser l'opération financière."""


class EmailChannel(NotificationChannel):
    name = "EMAIL"

    def __init__(self, sender: str):
        self._sender = sender

    def send(self, recipient: str, message: str) -> bool:
        # Stub : en production, appel à l'API e-mail. Ici on journalise pour la traçabilité.
        logger.info("[EMAIL] de %s à %s : %s", self._sender, recipient, message)
        return True


class SmsChannel(NotificationChannel):
    name = "SMS"

    def __init__(self, sender: str):
        self._sender = sender

    def send(self, recipient: str, message: str) -> bool:
        logger.info("[SMS] de %s à %s : %s", self._sender, recipient, message)
        return True
