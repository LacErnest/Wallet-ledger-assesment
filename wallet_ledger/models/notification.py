"""Notification : trace d'un message (email/SMS) déclenché par un événement métier.

On la persiste pour l'audit : pouvoir prouver qu'un client a bien été averti d'un
mouvement sur son argent fait partie des obligations d'un service financier.
"""

from __future__ import annotations

from wallet_ledger.extensions import db
from wallet_ledger.models.base import utcnow, uuid_pk


class Notification(db.Model):
    __tablename__ = "notifications"

    id = uuid_pk()
    channel = db.Column(db.String(10), nullable=False)  # EMAIL / SMS
    recipient = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    event_type = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # SENT / FAILED
    correlation_id = db.Column(db.String(36), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return f"<Notification {self.channel} -> {self.recipient} ({self.status})>"
