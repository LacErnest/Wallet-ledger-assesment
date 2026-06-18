"""Transaction : l'intention métier (un dépôt, un transfert) qui regroupe ses écritures."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB

from wallet_ledger.domain.enums import TransactionStatus, TransactionType
from wallet_ledger.extensions import db
from wallet_ledger.models.base import MONEY_NUMERIC, enum_column, utcnow, uuid_pk


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = uuid_pk()
    type = enum_column(TransactionType, nullable=False)
    status = enum_column(TransactionStatus, nullable=False, default=TransactionStatus.PENDING)

    # Montant « autorisé » de l'opération, conservé de bout en bout. Pour un dépôt,
    # c'est ce montant qui fait foi : la confirmation du fournisseur sera réconciliée
    # contre lui, jamais l'inverse (sinon un tiers pourrait créditer ce qu'il veut).
    amount = db.Column(MONEY_NUMERIC, nullable=False)
    currency = db.Column(db.String(3), nullable=False)

    # Données propres au type (contrepartie d'un transfert, fournisseur d'un dépôt,
    # taux de change…) en JSONB structuré, jamais en chaîne concaténée à la main.
    details = db.Column(JSONB, nullable=False, default=dict)

    # Référence externe (id côté fournisseur) pour le rapprochement et l'audit.
    reference = db.Column(db.String(128), nullable=True)

    # Identifiant de corrélation : relie requête, événements, écritures et notifications.
    correlation_id = db.Column(db.String(36), nullable=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    entries = db.relationship("LedgerEntry", back_populates="transaction", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Transaction {self.id} {self.type} {self.status}>"
