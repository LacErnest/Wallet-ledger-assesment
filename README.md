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
make fund acc=<number> amt=<amount>   # top up any account (demo helper)
```

`make seed` creates `alice`/`bob` (USD), `kamga` (XAF) and `claire` (EUR, funded) — so a
**cross-currency transfer** works out of the box (note: use `/fx/transfer`, not `/transfers`):

```bash
# claire (EUR) -> alice (USD): 30 EUR is converted to USD via the FX pool
curl -X POST localhost:8000/api/v1/fx/transfer -H 'Content-Type: application/json' \
  -d '{"sender_account_number":"<claire>","receiver_account_number":"<alice>","amount":"30"}'
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

### How this scales

The implementation here keeps the balance **strictly derived** (snapshot + delta + cache) to
honour *"no mutable balance column"* literally. To scale to real Stripe/bank volume (1M users,
10M+ entries, 1000+ reads/s), the next step is **CQRS** — split the immutable ledger (write
side, the source of truth) from a **maintained balance read model** updated *in the same ACID
transaction* as the entries:

- **O(1) reads.** A balance becomes a single indexed point-lookup on an `account_balance`
  projection — no summing, independent of history size. The ledger stays authoritative and
  the projection is fully rebuildable from it (it's the PDF's own *"Projection / Read Model"*
  optimization, not a source of truth).
- **No-overdraft as one atomic statement** — the database enforces it, not the app:
  ```sql
  UPDATE account_balance SET balance = balance - :amount
   WHERE account_id = :id AND balance >= :amount;   -- 0 rows ⇒ insufficient funds
  ```
  Race-free, no `SELECT FOR UPDATE`, no lock-then-check window; a `CHECK (balance >= 0)` makes
  a negative balance physically impossible. The entire concurrency bug class disappears.
- **Snapshots become async rebuild tooling** (background job), off the write path — used to
  bootstrap/rebuild a projection from a checkpoint + delta, not to serve reads.
- **Shard by `account_id`** so entries and the balance row co-locate; reads stay O(1) point
  lookups on a sharded key → horizontal scale. *Available-balance decisions* use the strongly
  consistent projection; *display reads* tolerate the cache.
- **Extreme scale:** move hot money movements to a purpose-built ledger engine like
  **[TigerBeetle](https://tigerbeetle.com)** — double-entry as the native primitive,
  no-overdraft enforced atomically, millions of transfers/sec — and keep PostgreSQL for the rest.

Throughout, the **ledger remains the immutable, rebuildable source of truth**; everything else
is a derived, disposable acceleration layer.

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

> **Single-phase vs two-phase transfers (deliberate design).** The brief describes two
> distinct capabilities: an **atomic transfer** (§2A — *"both entries in the same database
> transaction"*) and a separate **two-phase reservation system** (§3 — reserve, then commit
> after the Risk Service approves). They are mapped to two flows:
> - **`POST /transfers`** → the §2A **single-phase** transfer: debit + credit both written
>   `SUCCESS` in one transaction, immediately.
> - **`POST /transfers/initiate` → `/{id}/commit` (or `/{id}/fail`)** → the §3 **two-phase**
>   flow: a `PENDING` reservation, then settlement after `RiskService.assess`, or release.
>
> A successful `initiate`+`commit` yields the same ledger result as one `execute`, but adds
> the held reservation and the risk-approval gate. The brief only prescribes `POST /transfers`
> as an endpoint; the two-phase endpoint names are our design choice.

**Interactive API reference:** Swagger UI (try-it-out) at `/api/v1/docs` and ReDoc
(clean reference) at `/api/v1/redoc`, both off the OpenAPI 3 spec at `/api/v1/openapi.json`.
Every endpoint documents its parameters, responses, error codes and examples.

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

> **Transfert simple vs deux phases (choix assumé).** L'énoncé décrit deux capacités
> distinctes : un **transfert atomique** (§2A — *« les deux écritures dans la même transaction »*)
> et un **système de réservation en deux phases** (§3 — réserver, puis régler après accord du
> service de risque). On les expose en deux flux :
> - **`POST /transfers`** → le transfert **simple** (§2A) : débit + crédit écrits `SUCCESS`
>   d'un coup, immédiatement.
> - **`POST /transfers/initiate` → `/{id}/commit` (ou `/{id}/fail`)** → le flux **deux phases**
>   (§3) : réservation `PENDING`, puis règlement après `RiskService.assess`, ou libération.
>
> Un `initiate`+`commit` réussi donne le même résultat comptable qu'un `execute`, mais ajoute
> la réservation et le contrôle de risque. L'énoncé ne nomme que `POST /transfers` comme
> endpoint ; les noms des endpoints deux phases sont notre choix de conception.

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

### Passage à l'échelle

Ici, le solde reste **strictement déduit** (instantané + delta + cache) pour respecter
*« pas de colonne de solde mutable »* à la lettre. Pour monter à l'échelle d'une vraie
plateforme (1M utilisateurs, 10M+ écritures, 1000+ lectures/s), l'étape suivante est le
**CQRS** : séparer le grand livre immuable (côté écriture, source de vérité) d'un **modèle de
lecture de solde maintenu** dans la *même transaction ACID* que les écritures :

- **Lectures en O(1).** Le solde devient un simple point-lookup indexé sur une projection
  `account_balance` — plus aucune somme, indépendamment de la taille de l'historique. Le grand
  livre reste la référence et la projection est entièrement reconstructible à partir de lui
  (c'est l'option *« Projection / Read Model »* citée par l'énoncé, pas une source de vérité).
- **Non-découvert en une seule instruction atomique** — c'est la base qui l'impose, pas le code :
  ```sql
  UPDATE account_balance SET balance = balance - :montant
   WHERE account_id = :id AND balance >= :montant;   -- 0 ligne ⇒ fonds insuffisants
  ```
  Sans course, sans `SELECT FOR UPDATE` ni fenêtre « lire puis vérifier » ; un
  `CHECK (balance >= 0)` rend un solde négatif physiquement impossible.
- **Les instantanés deviennent un outil de reconstruction asynchrone** (tâche de fond), hors du
  chemin d'écriture.
- **Partitionnement par `account_id`** pour que écritures et ligne de solde soient co-localisées
  → lectures O(1) et passage à l'échelle horizontal. Les décisions de *solde disponible*
  s'appuient sur la projection fortement cohérente ; les lectures d'*affichage* tolèrent le cache.
- **Échelle extrême :** confier les mouvements à un moteur de grand livre dédié comme
  **[TigerBeetle](https://tigerbeetle.com)** (partie double native, non-découvert atomique,
  millions de transferts/s), et garder PostgreSQL pour le reste.

Dans tous les cas, le **grand livre reste la source de vérité immuable et reconstructible** ;
tout le reste n'est qu'une couche d'accélération dérivée et jetable.

### Compromis

- **`db.create_all()` non utilisé** — schéma versionné avec Alembic, migrations au démarrage.
- **Appels HTTP fournisseurs simulés hors-ligne** — réels dès que les clés sont fournies.
- **Pas de couche d'authentification** — hors périmètre ; webhooks vérifiés par signature.
- **Bus d'événements en mémoire** — simple et synchrone ; deviendrait un courtier à grande
  échelle, avec les notifications déportées dans un outbox.
