"""Compte : porteur d'une devise unique. Volontairement SANS colonne de solde."""

from __future__ import annotations

import secrets

from wallet_ledger.extensions import db
from wallet_ledger.models.base import utcnow, uuid_pk


def _generate_account_number() -> str:
    # Numéro lisible par un humain, distinct de l'identifiant technique. La contrainte
    # d'unicité en base reste le garde-fou ; en production on l'adosserait à une
    # séquence dédiée pour éliminer tout risque de collision.
    return "2" + str(secrets.randbelow(10**9)).zfill(9)


class Account(db.Model):
    __tablename__ = "accounts"

    id = uuid_pk()
    number = db.Column(db.String(10), unique=True, nullable=False, default=_generate_account_number)
    owner_id = db.Column(db.String(64), nullable=False, index=True)
    currency = db.Column(db.String(3), nullable=False)

    # Verrou optimiste géré nativement par SQLAlchemy : à chaque écriture la version
    # est vérifiée et incrémentée. Deux modifications concurrentes du même compte ne
    # peuvent donc pas s'écraser silencieusement (une lèvera StaleDataError).
    version = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __mapper_args__ = {"version_id_col": version}

    # Un seul compte par (propriétaire, devise) : empêche les doublons de comptes
    # internes (pool de change, compte de compensation) sous forte concurrence.
    __table_args__ = (
        db.UniqueConstraint("owner_id", "currency", name="uq_account_owner_currency"),
    )

    def __repr__(self) -> str:
        return f"<Account {self.number} {self.owner_id} {self.currency}>"
