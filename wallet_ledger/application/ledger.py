"""Service du grand livre : calcul des soldes et garde-fou de la partie double.

C'est le cœur comptable. Deux responsabilités seulement :
  1. calculer un solde à partir des écritures (jamais d'une colonne stockée) ;
  2. refuser d'enregistrer un jeu d'écritures qui ne s'équilibre pas à zéro.
"""

from __future__ import annotations

from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from wallet_ledger.domain.aggregates import TransactionAggregate
from wallet_ledger.domain.enums import EntryStatus, EntryType
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account
from wallet_ledger.models.balance_snapshot import BalanceSnapshot
from wallet_ledger.models.ledger_entry import LedgerEntry


class LedgerService:
    """Opérations comptables pures (n'utilise que la base, jamais le cache)."""

    def post(self, transaction: TransactionAggregate, transaction_id: str) -> None:
        """Matérialise un agrégat Transaction en base après qu'IL a validé la partie double.

        C'est l'agrégat qui détient l'invariant ; le service ne fait que persister ce qu'il
        a autorisé. Aucun appelant ne peut donc créer de la monnaie par une écriture bancale.
        """
        transaction.assert_balanced()
        db.session.add_all(
            [
                LedgerEntry(
                    account_id=line.account_id,
                    transaction_id=transaction_id,
                    amount=line.amount,
                    entry_type=line.entry_type,
                    status=line.status,
                    currency=line.currency,
                    entry_metadata=line.metadata,
                )
                for line in transaction.lines
            ]
        )

    def assert_balanced(self, entries: list[LedgerEntry]) -> None:
        """Rejoue l'invariant de partie double sur des écritures existantes (ex. au règlement
        d'un transfert en deux phases). On délègue à l'agrégat, seul détenteur de la règle."""
        aggregate = TransactionAggregate(currency=entries[0].currency if entries else "")
        for entry in entries:
            aggregate.record(
                entry.account_id, entry.amount, entry.entry_type, entry.currency, entry.status
            )
        aggregate.assert_balanced()

    def post_entries(self, entries: list[LedgerEntry]) -> None:
        """Enregistre un jeu d'écritures déjà construit (utilisé par les fixtures de test)."""
        self.assert_balanced(entries)
        db.session.add_all(entries)

    def balance(self, account: Account) -> Money:
        """Solde soldé : instantané le plus récent + delta des écritures postérieures."""
        snapshot = self._latest_snapshot(account.id)
        base = snapshot.balance if snapshot else Decimal(0)
        cursor = snapshot.last_entry_seq if snapshot else 0

        delta = self._sum(account.id, after_seq=cursor, statuses=(EntryStatus.SUCCESS,))
        return Money(base + delta, account.currency)

    def available_balance(self, account: Account) -> Money:
        """Solde disponible : le soldé MOINS les débits réservés (PENDING).

        On retranche les réservations en cours pour qu'un même argent ne puisse pas
        être dépensé deux fois pendant un transfert en deux phases.
        """
        settled = self.balance(account).amount
        pending_debits = self._sum(
            account.id,
            after_seq=0,
            statuses=(EntryStatus.PENDING,),
            entry_type=EntryType.DEBIT,
        )
        return Money(settled + pending_debits, account.currency)

    def maybe_snapshot(self, account: Account) -> None:
        """Fige un instantané quand trop d'écritures se sont accumulées depuis le dernier.

        But : garder les lectures de solde rapides même sur des comptes à très gros
        historique, en ne resommant que le delta plutôt que toutes les lignes.
        """
        threshold = current_app.config["SNAPSHOT_EVERY_N_ENTRIES"]
        snapshot = self._latest_snapshot(account.id)
        cursor = snapshot.last_entry_seq if snapshot else 0
        previous_count = snapshot.entry_count if snapshot else 0

        new_entries = (
            db.session.query(LedgerEntry.seq, LedgerEntry.amount)
            .filter(
                LedgerEntry.account_id == account.id,
                LedgerEntry.status == EntryStatus.SUCCESS,
                LedgerEntry.seq > cursor,
            )
            .order_by(LedgerEntry.seq)
            .all()
        )
        if len(new_entries) < threshold:
            return

        base = snapshot.balance if snapshot else Decimal(0)
        new_balance = base + sum((row.amount for row in new_entries), Decimal(0))
        last_seq = new_entries[-1].seq

        db.session.add(
            BalanceSnapshot(
                account_id=account.id,
                balance=new_balance,
                last_entry_seq=last_seq,
                entry_count=previous_count + len(new_entries),
            )
        )

    # --- Aides privées ---------------------------------------------------------
    def _latest_snapshot(self, account_id: str) -> BalanceSnapshot | None:
        return (
            BalanceSnapshot.query.filter_by(account_id=account_id)
            .order_by(BalanceSnapshot.last_entry_seq.desc())
            .first()
        )

    def _sum(
        self,
        account_id: str,
        *,
        after_seq: int,
        statuses: tuple[EntryStatus, ...],
        entry_type: EntryType | None = None,
    ) -> Decimal:
        query = db.session.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).filter(
            LedgerEntry.account_id == account_id,
            LedgerEntry.status.in_(statuses),
            LedgerEntry.seq > after_seq,
        )
        if entry_type is not None:
            query = query.filter(LedgerEntry.entry_type == entry_type)
        return Decimal(query.scalar())
