# DDD, Events & Tracing / DDD, événements & traçabilité

## 🇬🇧 English

### Layered architecture (and why the domain imports no framework)
The code is split into layers: `domain/` (pure rules: `Money`, events, errors), then
`application/` (use cases: transfers, deposits, FX), then `infrastructure/` and `api/`
(Flask, Redis, HTTP). The rule: **the domain never imports a framework.** Check
`domain/events.py` — no Flask, no SQLAlchemy. Why does this matter? The part most
expensive to get wrong (the money rules) stays testable in isolation, survives a
framework swap, and can't accidentally depend on a request context. Dependencies point
*inward*: outer layers know the domain, never the reverse (Ports & Adapters).

### Aggregate roots that own their invariants
The brief names `AccountAggregate` / `TransactionAggregate` as aggregates that "enforce
domain invariants." We model both as **explicit aggregate roots** — pure-domain classes in
`domain/aggregates.py`, no framework imports:

- **`TransactionAggregate`** *owns its entries* and enforces the double-entry rule. You add
  `debit()` / `credit()` lines, and `assert_balanced()` guarantees the entries sum to zero
  **per currency** (`domain/aggregates.py`). The services build this aggregate; the ledger
  only persists what the aggregate has already validated (`LedgerService.post`). No caller
  can materialise an unbalanced transaction.
- **`AccountAggregate`** enforces "never overdrawn": `ensure_can_debit(amount, available)`
  raises `InsufficientFundsError` if the available balance can't cover the debit. Transfers
  and FX delegate the funds check to it.

So the business rules live **on the domain aggregates** (tested in isolation,
`tests/test_aggregates.py`), not scattered through services. The services orchestrate
(load, lock, persist) and delegate the *invariants* to the aggregate roots — the model is
no longer anemic. Concurrency is still resolved at the database (row locks); the aggregate
owns the *accounting* invariants, the DB owns the *isolation* guarantee. The two are
complementary.

### The domain event bus (Observer)
A transfer's job is to move money correctly — not to send email, SMS, or talk to Redis.
So instead of calling those directly, it **publishes** a `DomainEvent`:

```python
self.events.publish(DomainEvent(TRANSFER_COMPLETED, {...}, correlation_id=...))
```

(`application/fx.py:84`). Subscribers react independently. The `EventBus`
(`events.py:33`) is a simple in-memory dict of `event_type → handlers`. At startup
`_wire_event_subscribers` (`__init__.py:70`) registers two unrelated reactions to the
same events: the `NotificationService` (`application/notifications.py:32`) and a cache
invalidator (`__init__.py:92`). The transfer service knows about **neither**. Add a new
side-effect tomorrow (analytics, fraud scoring) by subscribing — no core change.

### Failure isolation — why a notification can't undo a payment
`publish` wraps each handler in try/except and only **logs** failures
(`events.py:42-49`). This is deliberate: the money is already committed before the
event fires (`fx.py:82` commits, *then* `:84` publishes). If the SMS gateway is down,
we must not roll back a valid, settled payment. The subscriber's problem stays the
subscriber's problem.

### Distributed tracing via `correlation_id`
One id follows the whole chain: it is assigned per request in `init_tracing`
(`infrastructure/tracing.py:16`, honoring an inbound `X-Correlation-ID` or minting one),
threaded into the transaction and the `DomainEvent` (`fx.py:91`), and persisted on each
`Notification` row (`notifications.py:64`). In a dispute you can replay
request → entries → events → notifications under a single id. **For auditable money,
traceability is not optional.**

**Lead takeaway:** decouple *what happened* (an event) from *who cares* (subscribers),
isolate their failures, and stamp everything with one id so the system can explain
itself after the fact.

## 🇫🇷 Français

### Architecture en couches (et pourquoi le domaine n'importe aucun framework)
Le code est en couches : `domain/` (règles pures : `Money`, événements, erreurs), puis
`application/` (cas d'usage), puis `infrastructure/` et `api/` (Flask, Redis, HTTP). La
règle : **le domaine n'importe jamais de framework.** Voir `domain/events.py` — ni
Flask, ni SQLAlchemy. Pourquoi ? La partie la plus coûteuse à rater (les règles d'argent)
reste testable isolément, survit à un changement de framework, et ne dépend pas par
accident d'un contexte de requête. Les dépendances pointent *vers l'intérieur* : les
couches externes connaissent le domaine, jamais l'inverse (Ports & Adaptateurs).

### Des racines d'agrégat qui possèdent leurs invariants
L'énoncé cite `AccountAggregate` / `TransactionAggregate` comme agrégats qui « imposent les
invariants du domaine ». Nous modélisons les deux comme de **vraies racines d'agrégat** —
des classes purement domaine dans `domain/aggregates.py`, sans aucun framework :

- **`TransactionAggregate`** *possède ses écritures* et impose la partie double. On ajoute
  des lignes `debit()` / `credit()`, et `assert_balanced()` garantit que la somme vaut zéro
  **par devise** (`domain/aggregates.py`). Les services construisent l'agrégat ; le grand
  livre ne fait que persister ce qu'il a déjà validé (`LedgerService.post`). Aucun appelant
  ne peut matérialiser une transaction déséquilibrée.
- **`AccountAggregate`** impose « jamais à découvert » : `ensure_can_debit(montant,
  disponible)` lève `InsufficientFundsError` si le disponible ne couvre pas le débit. Les
  transferts et le change lui délèguent ce contrôle.

Les règles métier vivent donc **sur les agrégats du domaine** (testés en isolation,
`tests/test_aggregates.py`), au lieu d'être éparpillées dans les services. Les services
orchestrent (charger, verrouiller, persister) et délèguent les *invariants* aux racines
d'agrégat — le modèle n'est plus anémique. La concurrence reste résolue par la base
(verrous de ligne) ; l'agrégat porte les invariants *comptables*, la base la garantie
d'*isolation*. Les deux sont complémentaires.

### Le bus d'événements de domaine (Observateur)
Le rôle d'un transfert est de déplacer l'argent correctement — pas d'envoyer un email,
un SMS, ni de parler à Redis. Plutôt que d'appeler ces canaux, il **publie** un
`DomainEvent` :

```python
self.events.publish(DomainEvent(TRANSFER_COMPLETED, {...}, correlation_id=...))
```

(`application/fx.py:84`). Les abonnés réagissent indépendamment. L'`EventBus`
(`events.py:33`) est un simple dict en mémoire `event_type → handlers`. Au démarrage,
`_wire_event_subscribers` (`__init__.py:70`) branche deux réactions sans rapport sur les
mêmes événements : le `NotificationService` (`notifications.py:32`) et l'invalidateur de
cache (`__init__.py:92`). Le service de transfert n'en connaît **aucun**. Ajouter demain
un effet de bord (analytics, scoring de fraude) se fait en s'abonnant — sans toucher au
cœur.

### Isolation des pannes — pourquoi une notification ne défait pas un paiement
`publish` enveloppe chaque handler dans try/except et **journalise** seulement les
échecs (`events.py:42-49`). C'est délibéré : l'argent est déjà commité avant l'événement
(`fx.py:82` commit, *puis* `:84` publie). Si la passerelle SMS tombe, on ne doit pas
annuler un paiement valide et réglé. Le problème de l'abonné reste celui de l'abonné.

### Traçabilité distribuée via `correlation_id`
Un seul id suit toute la chaîne : assigné par requête dans `init_tracing`
(`infrastructure/tracing.py:16`, en respectant un `X-Correlation-ID` entrant ou en en
générant un), propagé dans la transaction et le `DomainEvent` (`fx.py:91`), et persisté
sur chaque ligne `Notification` (`notifications.py:64`). En cas de litige, on rejoue
requête → écritures → événements → notifications sous un id unique. **Pour de l'argent
auditable, la traçabilité n'est pas optionnelle.**

**À retenir comme lead :** découpler *ce qui s'est passé* (un événement) de *qui s'y
intéresse* (les abonnés), isoler leurs pannes, et estampiller tout avec un id unique
pour que le système puisse s'expliquer après coup.
