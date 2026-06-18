"""Instantané de solde : point de contrôle pour ne pas resommer tout l'historique.

Solde = solde de l'instantané + somme des écritures dont le curseur dépasse celui
de l'instantané. Sur un compte à des millions de lignes, on ne lit ainsi que le delta.
"""

from __future__ import annotations

from sqlalchemy import BigInteger

from wallet_ledger.extensions import db
from wallet_ledger.models.base import MONEY_NUMERIC, utcnow, uuid_pk


class BalanceSnapshot(db.Model):
    __tablename__ = "balance_snapshots"

    id = uuid_pk()
    account_id = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=False)

    balance = db.Column(MONEY_NUMERIC, nullable=False)

    # Curseur de la dernière écriture incluse : la frontière exacte du delta à ajouter.
    last_entry_seq = db.Column(BigInteger, nullable=False)
    # Nombre d'écritures soldées incluses : sert à décider quand couper le prochain instantané.
    entry_count = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        # Récupération rapide du dernier instantané d'un compte.
        db.Index("ix_snapshot_account_seq", "account_id", "last_entry_seq"),
    )

    def __repr__(self) -> str:
        return f"<BalanceSnapshot {self.account_id} {self.balance} @seq={self.last_entry_seq}>"
