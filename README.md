# wallet-ledger

> A double-entry **ledger engine** for a multi-currency digital wallet — built for the
> Paysika Senior Backend technical test.
> Moteur de **grand livre en partie double** pour un portefeuille multi-devises.

*(English first — version française plus bas.)*

---

## 🇬🇧 English

### What it is

This is **not a CRUD app** — it is a financial ledger. Its three non-negotiable
guarantees are:

1. **Financial correctness** — money is never created or destroyed. Every transaction
   writes ledger entries that **sum to zero per currency**, and a balance is *always*
   the sum of an account's entries (there is **no mutable balance column**).
2. **Auditability** — every movement is an immutable ledger line, traceable end-to-end by
   a `correlation_id`.
3. **Concurrency safety** — simultaneous operations can never overdraw an account or
   double-apply a request.

### Architecture at a glance

Layered Domain-Driven Design, dependencies pointing **inward**. The domain has **no
framework imports**.

```
API (Flask)            → HTTP, validation (marshmallow), idempotency, tracing
  │
Application            → use cases: ledger, transfers, deposits, fx, risk, notifications
  │
Domain                 → Money (value object), enums, domain events, errors  ← pure
  │
Infrastructure         → PostgreSQL, Redis, payment & FX adapters (Ports & Adapters)
```

**Design patterns used:** Value Object (`Money`), **Aggregate roots** (`TransactionAggregate`,
`AccountAggregate` — own the double-entry and no-overdraft invariants), Ports & Adapters
(payment/FX/notification providers, balance cache), Factory (provider selection), Observer
(domain event bus), Decorator (idempotency, tracing), Optimistic Lock (SQLAlchemy
`version_id_col`) + row locks.

### Key design decisions (the *why*)

| Decision | Why |
|----------|-----|
| **No balance column** | A stored balance can drift from reality and can't be audited. The ledger is the single source of truth. |
| **`Money` value object, `Decimal` only** | Floats lose cents (`0.1+0.2≠0.3`). Money is immutable, currency-aware, and rejects floats. |
| **Σ entries = 0 enforced in code** | The double-entry rule is the law that prevents money being created by accident. |
| **PostgreSQL, not SQLite** | Real row locks (`SELECT FOR UPDATE`) + serializable retries give a genuine no-negative-balance guarantee. |
| **Snapshot keyed on a monotonic `seq`** | Cursor-based snapshots avoid the timestamp-boundary bugs of time-based ones; balance = snapshot + delta. |
| **Redis = read cache only** | Fast balance reads; never a source of truth; invalidated on every money movement. |
| **Idempotency = claim-first** | The unique key is reserved *before* the work runs, so concurrent retries can't double-spend. |
| **Two-phase transfers + Risk Service** | Funds are reserved, then settled after a risk check — how "in-flight money" is handled. |
| **Webhooks verified, fail-closed** | A deposit is only credited if the provider signature is valid *and* the amount matches what was authorized. |

### Tech stack

Python 3.12 · Flask 3 · PostgreSQL 16 · Redis 7 · SQLAlchemy 2 + Alembic · marshmallow ·
**uv** (deps) · Docker + docker-compose.

### Run it

`make help` lists every command. The quickest start:

```bash
cp .env.example .env          # then fill credentials (optional — see offline mode below)
make up                       # builds & starts api + postgres + redis; runs migrations on boot
make seed                     # (optional) sample accounts + a funded transfer to explore
```

After `make up` the **API is live at http://localhost:8000** — no extra step. Useful targets:

```bash
make dev      # run the API locally with hot reload (db + redis in Docker)
make logs     # tail the API logs
make down     # stop the stack (data kept)
```

Copy `.env.example` to `.env`. Without external keys the system runs in **offline mode**
(stubbed providers, built-in FX rates) so it is fully usable and testable.

### Tests

```bash
make test     # spins up isolated test-db + test-redis containers, then runs pytest
```

Integration tests run against **dedicated throwaway containers** (`test-db` on :5434,
`test-redis` on :6381, started via the compose `test` profile) — they never touch dev data
and each test starts from a clean state. The concurrency tests spawn **real threads against
PostgreSQL** to prove that two simultaneous transfers (and two replayed webhooks) can never
produce a negative balance or a double-credit.

### Operations

- **Liveness:** `GET /health` (process up). **Readiness:** `GET /health/ready` —
  checks PostgreSQL + Redis connectivity and returns `503` until both answer.
- **Structured logging:** every log line is JSON and carries the request's
  `correlation_id`, so an incident on a payment is traceable end-to-end.
- **Quality gate:** `make lint` (ruff check + format check) and `make fmt`; a
  `.pre-commit-config.yaml` runs ruff on every commit.
- **Reversals:** `POST /api/v1/transactions/{id}/reverse` records a compensating
  REVERSAL (the original is never mutated, only marked `REVERSED`).

### Performance (measured)

`make bench` runs a micro-benchmark (50k entries on one account, 1000 reads). Indicative
numbers on a laptop against the dockerized Postgres:

| Read path | p50 | p95 |
|-----------|-----|-----|
| Full ledger scan (baseline) | ~12 ms | ~14 ms |
| Snapshot + delta | ~12 ms | ~15 ms |
| **Redis cache** | **~0.5 ms** | **~0.9 ms** |

The **cache** is what meets the brief's `<10ms` @ 1000 q/s target for balance reads. At
50k entries the snapshot doesn't beat the full scan yet (both are round-trip-bound); its
advantage is *asymptotic* — the scan grows linearly with ledger size while snapshot+delta
stays flat, so at the brief's 10M-entry scale the snapshot keeps a cache-miss recompute
bounded. Honest takeaway: **cache for latency, snapshot for scale.**

### API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/accounts` | Create an account |
| GET | `/api/v1/accounts/{number}` | Account details |
| GET | `/api/v1/accounts/{number}/balance` | Balance (derived from ledger) |
| GET | `/api/v1/accounts/{number}/transactions` | History (paginated) |
| POST | `/api/v1/transfers` | Atomic transfer |
| POST | `/api/v1/transfers/initiate` | Phase 1 — reserve funds |
| POST | `/api/v1/transfers/{id}/commit` | Phase 2 — settle (after risk check) |
| POST | `/api/v1/transfers/{id}/fail` | Release a reservation |
| POST | `/api/v1/transactions/{id}/reverse` | Reverse a transaction (compensating entry) |
| POST | `/api/v1/deposits` | Initiate a deposit (Stripe / PawaPay / PayPal) |
| POST | `/api/v1/payments/webhook/{provider}` | Provider confirmation (signature-verified) |
| POST | `/api/v1/payments/webhook` | Same, single endpoint (provider in body / `X-Provider`) |
| GET | `/api/v1/fx/rate` | Get the exchange rate between two currencies |
| GET | `/api/v1/fx/convert` | Convert an amount |
| POST | `/api/v1/fx/transfer` | Cross-currency transfer (via FX pool) |

All `POST`s accept an `Idempotency-Key` header. Every request carries an
`X-Correlation-ID` (provided or generated) echoed on the response.

**Interactive API reference:** Swagger UI (try-it-out) at `/api/v1/docs` and ReDoc
(clean reference) at `/api/v1/redoc`, both off the OpenAPI 3 spec at `/api/v1/openapi.json`.
Every endpoint documents its parameters, responses, error codes and examples.

### Teaching docs

Each major decision is explained simply in [`docs/`](docs/) (bilingual):

1. [Ledger & no balance column](docs/01-ledger-and-no-balance-column.md)
2. [The `Money` value object](docs/02-money-value-object.md)
3. [Double-entry invariant](docs/03-double-entry-invariant.md)
4. [Two-phase transfers](docs/04-two-phase-transfers.md)
5. [Idempotency](docs/05-idempotency.md)
6. [Concurrency & locking](docs/06-concurrency-and-locking.md)
7. [Performance: snapshots & cache](docs/07-performance-snapshots-and-cache.md)
8. [Deposits, webhooks & providers](docs/08-deposits-webhooks-providers.md)
9. [FX & cross-currency](docs/09-fx-cross-currency.md)
10. [DDD, events & tracing](docs/10-ddd-events-tracing.md)

### Tradeoffs

- **`db.create_all()` is not used** — schema is versioned with Alembic. Migrations run on
  container boot.
- **Provider HTTP calls are stubbed offline** — real calls happen when API keys are set.
- **No auth layer** — out of the brief's scope; webhooks are signature-verified fail-closed.
- **In-process event bus** — simple and synchronous; would become a broker (Kafka/RabbitMQ)
  at scale, with notifications moved to an outbox.

---

## 🇫🇷 Français

### De quoi s'agit-il

Ce n'est **pas une application CRUD** — c'est un grand livre financier. Trois garanties
non négociables :

1. **Exactitude financière** — l'argent n'est jamais créé ni détruit. Chaque transaction
   écrit des écritures dont la **somme par devise vaut zéro**, et un solde est *toujours*
   la somme des écritures d'un compte (**aucune colonne de solde mutable**).
2. **Auditabilité** — chaque mouvement est une ligne immuable, traçable de bout en bout
   par un `correlation_id`.
3. **Sûreté concurrentielle** — deux opérations simultanées ne peuvent ni rendre un solde
   négatif ni appliquer deux fois la même requête.

### Architecture en un coup d'œil

Conception pilotée par le domaine (DDD), en couches, dépendances tournées vers
l'**intérieur**. Le domaine n'importe **aucun framework**.

```
API (Flask)            → HTTP, validation (marshmallow), idempotence, traçabilité
  │
Application            → cas d'usage : grand livre, transferts, dépôts, change, risque, notifications
  │
Domaine                → Money (value object), énumérations, événements, erreurs  ← pur
  │
Infrastructure         → PostgreSQL, Redis, adaptateurs paiement & change (Ports & Adaptateurs)
```

**Patrons utilisés :** Value Object (`Money`), **Racines d'agrégat** (`TransactionAggregate`,
`AccountAggregate` — portent les invariants de partie double et de non-découvert), Ports &
Adaptateurs (fournisseurs de paiement/change/notification, cache de solde), Fabrique (choix
du fournisseur), Observateur (bus d'événements), Décorateur (idempotence, traçabilité),
Verrou optimiste (`version_id_col`) + verrous de ligne.

### Décisions de conception clés (le *pourquoi*)

| Décision | Pourquoi |
|----------|----------|
| **Pas de colonne de solde** | Un solde stocké peut diverger de la réalité et n'est pas auditable. Le grand livre fait foi. |
| **Value object `Money`, `Decimal` uniquement** | Le flottant perd des centimes (`0.1+0.2≠0.3`). Money est immuable, lié à sa devise, et refuse les flottants. |
| **Σ écritures = 0 imposée en code** | La partie double est la loi qui empêche de créer de l'argent par erreur. |
| **PostgreSQL, pas SQLite** | De vrais verrous de ligne (`SELECT FOR UPDATE`) garantissent l'absence de solde négatif. |
| **Instantané indexé sur un `seq` monotone** | Le curseur évite les bugs de frontière temporelle ; solde = instantané + delta. |
| **Redis = cache de lecture seulement** | Lectures de solde rapides ; jamais source de vérité ; invalidé à chaque mouvement. |
| **Idempotence : réserver d'abord** | La clé unique est posée *avant* l'exécution, donc deux requêtes concurrentes ne peuvent pas doubler un débit. |
| **Transferts deux phases + service de risque** | Les fonds sont réservés puis réglés après contrôle — la gestion de l'« argent en vol ». |
| **Webhooks vérifiés, fail-closed** | Un dépôt n'est crédité que si la signature est valide *et* le montant correspond à l'autorisé. |

### Pile technique

Python 3.12 · Flask 3 · PostgreSQL 16 · Redis 7 · SQLAlchemy 2 + Alembic · marshmallow ·
**uv** · Docker + docker-compose.

### Lancer le projet

`make help` liste toutes les commandes. Démarrage le plus rapide :

```bash
cp .env.example .env          # puis renseigner les identifiants (optionnel, cf. mode hors-ligne)
make up                       # build + démarre api + postgres + redis ; migrations au boot
make seed                     # (optionnel) comptes de démo + un transfert financé
```

Après `make up`, l'**API tourne sur http://localhost:8000** — aucune étape supplémentaire.
Autres cibles utiles : `make dev` (API en local, rechargement à chaud), `make logs`, `make down`.

Sans clés externes, le système tourne en **mode hors-ligne** (fournisseurs simulés, taux
de change intégrés) : pleinement utilisable et testable.

### Tests

```bash
make test     # démarre des conteneurs de test isolés (test-db, test-redis) puis pytest
```

Les tests d'intégration s'exécutent sur des **conteneurs jetables dédiés** (jamais les
données de dev). Les tests de concurrence lancent de **vrais threads sur PostgreSQL** pour
prouver que deux transferts simultanés — ou deux webhooks rejoués — ne peuvent jamais
produire un solde négatif ni un double crédit.

### Compromis

- **`db.create_all()` non utilisé** — schéma versionné avec Alembic, migrations au démarrage.
- **Appels HTTP fournisseurs simulés hors-ligne** — réels dès que les clés sont fournies.
- **Pas de couche d'authentification** — hors périmètre ; webhooks vérifiés par signature.
- **Bus d'événements en mémoire** — simple et synchrone ; deviendrait un courtier à grande
  échelle, avec les notifications déportées dans un outbox.

Voir [`SPEC.md`](SPEC.md) pour la spécification complète et [`docs/`](docs/) pour les
explications pédagogiques de chaque décision.
