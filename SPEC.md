# SPEC — wallet-ledger

A FinTech double-entry **ledger engine** for a multi-currency digital wallet, built from
scratch for the Paysika Senior Backend technical test. This is the contract the
implementation and tests are written against.

> Status: **DRAFT — awaiting confirmation before implementation.**

---

## 1. Objective

Build the **core financial engine** of a digital wallet. It must guarantee three
properties above all else:

1. **Financial correctness** — money is never created or destroyed; every transaction's
   ledger entries sum to zero; a balance always equals the sum of its ledger entries.
2. **Auditability** — every movement is an immutable ledger entry, traceable end-to-end
   via a `correlation_id`.
3. **Concurrency safety** — simultaneous operations can never drive a balance negative or
   double-apply a request.

This is **not a CRUD app** — it is a ledger. Balances are *derived*, never stored as a
mutable column.

### Target users (of the API)
- **Wallet end-users** (Alice, Bob): hold money, deposit, transfer, see balance/history.
- **External payment providers** (Stripe, PayPal, MTN, Orange): confirm deposits via webhook.
- **Internal services**: risk approval (two-phase commit), notifications.

---

## 2. Functional scope

### Core (must-have)
| # | Capability | Acceptance criteria |
|---|-----------|---------------------|
| C1 | Double-entry ledger | Each transaction creates ≥2 entries; **Σ entries = 0** per currency. Enforced in code as an invariant. |
| C2 | No balance column | `Account` has **no** mutable balance field. Balance = `SUM(amount) WHERE status=SUCCESS`. |
| C3 | Atomic transfer | Both entries persisted in **one DB transaction**; partial failure rolls back fully. |
| C4 | Two-phase transfer | Phase 1 reserves funds (PENDING debit); Phase 2 commits after **Internal Risk Service** approval; can be failed/released. |
| C5 | Transaction states | `PENDING → SUCCESS / FAILED`; `SUCCESS → REVERSED`. Completed txns immutable; corrections via compensating entries. |
| C6 | Balance API | `GET /accounts/{id}/balance`, derived from ledger. |
| C7 | Deposits | initiate (PENDING txn carrying the **authorized amount**) → provider webhook confirms → ledger entries (clearing acct ↔ user). |
| C8 | Transaction history | `GET /accounts/{id}/transactions`, **paginated**. |
| C9 | Idempotency | `Idempotency-Key` on all POSTs; same key+body → same response, **no duplicate side-effects, safe under concurrency**. |
| C10 | Concurrency safety | Two simultaneous transfers cannot overspend; no negative balance. |
| C11 | Money value object | `Decimal` only (float forbidden); immutable; currency-aware arithmetic. |
| C12 | Domain events | `FundsReserved`, `TransferCompleted`, `TransferFailed`, `DepositCompleted` published on an in-process bus. |

### Bonus (all in scope per request)
| # | Capability |
|---|-----------|
| B1 | **Snapshot pattern** — periodic balance checkpoints; balance = snapshot + delta since. |
| B2 | **Payment provider integration** — Stripe / PayPal / MTN / Orange adapters + webhook signature verification. |
| B3 | **Notifications** — Email / SMS providers driven by domain events. |
| B4 | **FX** — third-party rate API + cross-currency transfer through an FX pool (per-currency Σ = 0). |
| B5 | **Distributed tracing** — `correlation_id` propagated: request → events → entries → notifications. |

---

## 3. Architecture & project structure

Clean, layered **DDD** with dependencies pointing **inward** (API → application → domain;
infrastructure plugs in via interfaces). The **domain layer has no Flask/SQLAlchemy imports**.

```
wallet_ledger/
├── domain/                  # Cœur métier pur — aucune dépendance framework
│   ├── money.py             # Value Object Money (Decimal)
│   ├── enums.py             # États & types (lifecycle)
│   ├── events.py            # Événements de domaine + bus
│   └── errors.py            # Exceptions métier
├── models/                  # Persistance SQLAlchemy (Account, Transaction, LedgerEntry, …)
├── application/             # Services applicatifs (orchestration des cas d'usage)
│   ├── ledger.py            # Calcul de solde (snapshot + delta) + invariant Σ=0
│   ├── transfers.py         # Transfert atomique + deux phases
│   ├── deposits.py          # Dépôts + réconciliation webhook
│   ├── fx.py                # Change + transfert multi-devises
│   ├── risk.py              # Service de risque interne (phase 2)
│   └── notifications.py     # Abonnés aux événements → Email/SMS
├── infrastructure/          # Détails techniques remplaçables (ports & adapters)
│   ├── idempotency.py       # Décorateur idempotence (claim-first, atomique)
│   ├── tracing.py           # correlation_id (entrée/sortie)
│   ├── fx_rates.py          # Client API de taux + repli hors-ligne
│   └── payments/            # Adaptateurs fournisseurs (Stripe/PayPal/MTN/Orange)
├── api/                     # Couche HTTP Flask (blueprints) + schémas marshmallow
├── config.py
├── extensions.py
└── __init__.py              # App factory
tests/                       # Tests orientés domaine (pytest, PostgreSQL)
docs/                        # Docs pédagogiques (une décision = un fichier)
```

**Design patterns used (and why):** Value Object (`Money`), Repository-ish via SQLAlchemy
session, **Ports & Adapters** (payment/FX/notification providers behind interfaces →
Open/Closed, Dependency Inversion), **Decorator** (idempotency, tracing), **Observer**
(domain event bus), **Strategy** (provider selection), **Optimistic Lock** (SQLAlchemy
`version_id_col`).

---

## 4. Tech stack & commands

- **Language/Framework:** Python 3.12, Flask 3.
- **DB:** PostgreSQL 16 (chosen for real row locks + serializable transactions → genuine
  concurrency guarantee, unlike SQLite).
- **Deps:** `uv` (lockfile-based, reproducible).
- **Validation/Serialization:** marshmallow.
- **Container:** Docker + docker-compose (app + db).
- **Tests:** pytest against a Postgres test database.

```bash
# Local dev
uv sync                              # install deps from lockfile
docker compose up -d db              # start Postgres
uv run flask --app wallet_ledger run --debug

# Everything in containers
docker compose up --build            # api + db

# Tests
docker compose up -d db
uv run pytest                        # domain-focused suite
uv run pytest --cov=wallet_ledger
```

---

## 5. Code style

- **Comments & docstrings in French**, expressing the **why** (business intent), not the
  *what*. Code identifiers stay in English (industry standard).
- SOLID, SRP, DRY, YAGNI. Don't reinvent the wheel (use marshmallow, SQLAlchemy native
  optimistic locking, stdlib hashing, etc.).
- Small, single-purpose functions; explicit names; no clever one-liners.
- Money is **always** `Decimal`; `float` is rejected at the `Money` boundary.
- Each public behavior has a test; tests assert **domain behavior**, not just HTTP wiring.

---

## 6. Testing strategy

Domain-first. Named tests required by the brief are first-class:
- `balance_computed_correctly_from_ledger`
- `transfer_fails_when_balance_insufficient`
- `transfer_creates_balanced_ledger_entries`
- `idempotent_transfer_does_not_duplicate_entries`
- `concurrent_transfers_do_not_create_negative_balance`

Plus: Money value-object laws, two-phase reserve/commit/fail, deposit reconciliation
(webhook amount ≠ authorized → rejected), snapshot correctness (snapshot + delta == full
sum), FX per-currency zero-sum, idempotency under concurrent duplicates, tracing propagation.

Concurrency test runs **real threads against Postgres** to prove the no-negative-balance
guarantee (the property only holds on a DB with true locking).

---

## 7. Boundaries

**Always**
- Keep the ledger the single source of truth; balances derived.
- Enforce Σ entries = 0 (per currency) before commit.
- Write all entries of a transaction in one DB transaction.
- Propagate `correlation_id` through every layer.
- French why-comments; teaching `docs/*.md` for each major decision.

**Ask first**
- Adding a new external dependency beyond the agreed stack.
- Changing the public API shape from the brief's examples.
- Trading off scope vs. the 16h deadline (which bonus to cut if time runs short).

**Never**
- Store a mutable balance column.
- Use `float` for money.
- Let a partial transaction persist (no unbalanced ledgers).
- Copy the reference repo's code — this is an original implementation.

---

## 8. Confirmed decisions

1. **Doc language: bilingual.** Code comments in **French** (business why). Teaching
   `docs/*.md` and README provided in **both English and French**.
2. **Migrations: Alembic** (via Flask-Migrate) — versioned, production-grade schema.
3. **No authentication layer** (out of brief scope); webhook signature verification
   **fails closed** (rejects unless a valid signature is presented).
4. **Cut order if time runs short:** Notifications → Tracing → FX. Core + snapshots +
   payment providers are non-negotiable.
5. **Git:** atomic commits, authored as Ernest Tsamo (no AI co-author trailer).

## 9. Infrastructure detail

- **PostgreSQL** is the source of truth (row locks + serializable retries → real
  concurrency guarantee).
- **Redis** is a read accelerator only (cache-aside for balances): lookup → compute from
  ledger on miss → cache with TTL → invalidate on new entry. Never a source of truth.
- **docker-compose** services: `api`, `db` (postgres), `redis`.
- **Credentials** for all external providers (DB, Redis, FX API, Stripe/PayPal/MTN/Orange,
  Email/SMS) come from env: `.env.example` is tracked (placeholders); `.env` is untracked.
