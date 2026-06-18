"""Écriture comptable : la brique élémentaire et IMMUABLE du grand livre.

Le solde d'un compte n'est jamais stocké : il se déduit de la somme des écritures.
C'est ce qui rend le système auditable — chaque centime a une ligne qui l'explique.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Identity

from wallet_ledger.domain.enums import EntryStatus, EntryType
from wallet_ledger.extensions import db
from wallet_ledger.models.base import MONEY_NUMERIC, enum_column, utcnow, uuid_pk


class LedgerEntry(db.Model):
    __tablename__ = "ledger_entries"

    id = uuid_pk()

    # Curseur strictement croissant attribué par la base. On l'utilise pour borner
    # les instantanés de solde : « toutes les écritures après le numéro N ». Contrairement
    # à un horodatage, deux écritures n'auront jamais le même numéro, donc aucun risque
    # d'en compter une deux fois ou de l'oublier à la frontière d'un instantané.
    seq = db.Column(BigInteger, Identity(), unique=True, nullable=False)

    account_id = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=False)
    transaction_id = db.Column(db.String(36), db.ForeignKey("transactions.id"), nullable=False)

    # Montant signé : négatif au débit, positif au crédit. La somme des écritures
    # d'une transaction (par devise) doit toujours valoir zéro.
    amount = db.Column(MONEY_NUMERIC, nullable=False)
    entry_type = enum_column(EntryType, nullable=False)
    status = enum_column(EntryStatus, nullable=False, default=EntryStatus.PENDING)
    currency = db.Column(db.String(3), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    transaction = db.relationship("Transaction", back_populates="entries")

    __table_args__ = (
        # Lecture de solde : on filtre par compte et statut SUCCESS.
        db.Index("ix_entry_account_status", "account_id", "status"),
        # Calcul du delta depuis un instantané : par compte, trié par curseur.
        db.Index("ix_entry_account_seq", "account_id", "seq"),
    )

    # Fabriques débit/crédit : un seul endroit décide qu'un débit est négatif et un
    # crédit positif. Les services demandent un montant (toujours positif) et le sens
    # comptable découle de la méthode appelée — impossible de se tromper de signe.
    @classmethod
    def debit(
        cls,
        account_id: str,
        transaction_id: str,
        amount,
        currency: str,
        status: EntryStatus = EntryStatus.SUCCESS,
    ) -> LedgerEntry:
        return cls(
            account_id=account_id,
            transaction_id=transaction_id,
            amount=-abs(amount),
            entry_type=EntryType.DEBIT,
            status=status,
            currency=currency,
        )

    @classmethod
    def credit(
        cls,
        account_id: str,
        transaction_id: str,
        amount,
        currency: str,
        status: EntryStatus = EntryStatus.SUCCESS,
    ) -> LedgerEntry:
        return cls(
            account_id=account_id,
            transaction_id=transaction_id,
            amount=abs(amount),
            entry_type=EntryType.CREDIT,
            status=status,
            currency=currency,
        )

    def __repr__(self) -> str:
        return f"<LedgerEntry {self.account_id} {self.amount} {self.entry_type}/{self.status}>"
