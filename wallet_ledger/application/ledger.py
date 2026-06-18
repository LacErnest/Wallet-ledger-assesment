"""Service du grand livre : calcul des soldes et garde-fou de la partie double.

C'est le cœur comptable. Deux responsabilités seulement :
  1. calculer un solde à partir des écritures (jamais d'une colonne stockée) ;
  2. refuser d'enregistrer un jeu d'écritures qui ne s'équilibre pas à zéro.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from wallet_ledger.domain.enums import EntryStatus, EntryType
from wallet_ledger.domain.errors import LedgerNotBalancedError
from wallet_ledger.domain.money import Money
from wallet_ledger.extensions import db
from wallet_ledger.models.account import Account
from wallet_ledger.models.balance_snapshot import BalanceSnapshot
from wallet_ledger.models.ledger_entry import LedgerEntry


class LedgerService:
    """Opérations comptables pures (n'utilise que la base, jamais le cache)."""

    def assert_balanced(self, entries: list[LedgerEntry]) -> None:
        """Vérifie l'invariant « somme = 0 par devise », la règle d'or de la partie double.

        On l'isole pour pouvoir aussi la rejouer au moment de solder un transfert en
        deux phases (où débit et crédit sont écrits à des instants différents).
        """
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for entry in entries:
            totals[entry.currency] += entry.amount

        for currency, total in totals.items():
            if total != 0:
                raise LedgerNotBalancedError(currency, str(total))

    def post_entries(self, entries: list[LedgerEntry]) -> None:
        """Enregistre un jeu d'écritures équilibré (aucun appelant ne peut créer de monnaie)."""
        self.assert_balanced(entries)
        db.session.add_all(entries)

    def balance(self, account: Account) -> Money:
        """Solde soldé : instantané le plus récent + delta des écritures postérieures."""
        snapshot = self._latest_snapshot(account.id)
        base = snapshot.balance if snapshot else Decimal(0)
        cursor = snapshot.last_entry_seq if snapshot else 0

        delta = self._sum(
            account.id, after_seq=cursor, statuses=(EntryStatus.SUCCESS,)
        )
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
