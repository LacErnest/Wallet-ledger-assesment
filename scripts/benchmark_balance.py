"""Micro-benchmark de lecture de solde.

But : étayer par une mesure l'objectif de l'énoncé (« lecture de solde < 10 ms » même
avec des millions d'écritures). On insère beaucoup d'écritures sur un compte, on coupe
un instantané, puis on chronomètre la lecture du solde — par le grand livre (instantané
+ delta) puis par le cache Redis.

Usage : uv run python scripts/benchmark_balance.py [--entries N] [--reads M]
"""

from __future__ import annotations

import argparse
import statistics
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

from sqlalchemy import func

from wallet_ledger import create_app
from wallet_ledger.application.balance_query import BalanceQuery
from wallet_ledger.application.ledger import LedgerService
from wallet_ledger.extensions import db
from wallet_ledger.infrastructure.cache import BalanceCache
from wallet_ledger.models.account import Account
from wallet_ledger.models.balance_snapshot import BalanceSnapshot
from wallet_ledger.models.ledger_entry import LedgerEntry
from wallet_ledger.models.transaction import Transaction

_BENCH_OWNER = "BENCHMARK"


def _percentile(samples: list[float], pct: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(pct * len(ordered)))]


def _report(label: str, samples_ms: list[float]) -> None:
    print(
        f"  {label:<22} mean={statistics.mean(samples_ms):.3f} ms  "
        f"p50={_percentile(samples_ms, 0.50):.3f} ms  "
        f"p95={_percentile(samples_ms, 0.95):.3f} ms  "
        f"max={max(samples_ms):.3f} ms"
    )


def _seed_entries(account: Account, n: int) -> Transaction:
    txn = Transaction(type="DEPOSIT", status="SUCCESS", amount=Decimal(n), currency="USD")
    db.session.add(txn)
    db.session.flush()
    now = datetime.now(UTC)
    # Insertion en masse (une écriture = 1.00) : on mesure la LECTURE, pas l'écriture.
    db.session.bulk_insert_mappings(
        LedgerEntry,
        [
            {
                "id": str(uuid.uuid4()),
                "account_id": account.id,
                "transaction_id": txn.id,
                "amount": Decimal("1"),
                "entry_type": "CREDIT",
                "status": "SUCCESS",
                "currency": "USD",
                "created_at": now,
            }
            for _ in range(n)
        ],
    )
    db.session.commit()
    return txn


def _full_scan(account_id: str):
    """Solde par balayage complet (sans instantané) : la baseline qu'on cherche à battre."""
    return (
        db.session.query(func.coalesce(func.sum(LedgerEntry.amount), 0))
        .filter(LedgerEntry.account_id == account_id, LedgerEntry.status == "SUCCESS")
        .scalar()
    )


def _cleanup(account: Account, txn: Transaction) -> None:
    LedgerEntry.query.filter_by(account_id=account.id).delete()
    BalanceSnapshot.query.filter_by(account_id=account.id).delete()
    db.session.delete(txn)
    db.session.delete(account)
    db.session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries", type=int, default=50_000)
    parser.add_argument("--reads", type=int, default=1_000)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        ledger = LedgerService()
        cache = BalanceCache(app.extensions["redis"], app.config["BALANCE_CACHE_TTL_SECONDS"])
        balance_query = BalanceQuery(ledger, cache)

        account = Account(owner_id=_BENCH_OWNER, currency="USD")
        db.session.add(account)
        db.session.commit()

        print(f"Insertion de {args.entries:,} écritures...")
        txn = _seed_entries(account, args.entries)
        ledger.maybe_snapshot(account)
        db.session.commit()
        cache.invalidate(account.id)

        print(f"Solde = {ledger.balance(account)} | {args.reads:,} lectures chronométrées :\n")

        scan_samples = []
        for _ in range(args.reads):
            start = perf_counter()
            _full_scan(account.id)
            scan_samples.append((perf_counter() - start) * 1000)

        ledger_samples = []
        for _ in range(args.reads):
            start = perf_counter()
            ledger.balance(account)
            ledger_samples.append((perf_counter() - start) * 1000)

        cached_samples = []
        for _ in range(args.reads):
            start = perf_counter()
            balance_query.get(account)
            cached_samples.append((perf_counter() - start) * 1000)

        _report("balayage complet (baseline)", scan_samples)
        _report("grand livre (snapshot+delta)", ledger_samples)
        _report("cache Redis", cached_samples)

        _cleanup(account, txn)
        print("\nNettoyage effectué.")


if __name__ == "__main__":
    main()
