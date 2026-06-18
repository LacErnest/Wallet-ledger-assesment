"""Clé d'idempotence : garantit qu'une même requête rejouée ne s'applique qu'une fois.

La clé est posée AVANT d'exécuter l'opération (réservation), grâce à la contrainte
d'unicité. Deux requêtes simultanées portant la même clé ne peuvent donc pas exécuter
le transfert deux fois : la seconde butte sur la clé déjà prise.
"""

from __future__ import annotations

from wallet_ledger.extensions import db
from wallet_ledger.models.base import utcnow, uuid_pk


class IdempotencyKey(db.Model):
    __tablename__ = "idempotency_keys"

    id = uuid_pk()
    key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    request_hash = db.Column(db.String(64), nullable=False)

    # Nuls tant que l'opération n'est pas terminée : un enregistrement « réservé »
    # signale qu'une requête est en cours, et permet de rejouer la réponse une fois finie.
    response_status = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    @property
    def is_completed(self) -> bool:
        return self.response_body is not None

    def __repr__(self) -> str:
        return f"<IdempotencyKey {self.key} completed={self.is_completed}>"
