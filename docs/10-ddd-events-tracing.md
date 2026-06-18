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

### Where are the "aggregates"? (a deliberate interpretation)
The brief names `AccountAggregate` / `TransactionAggregate` as aggregates that "enforce
domain invariants." We *do* enforce those invariants — we just don't wrap them in classical
aggregate-root objects. The reasoning:

- The **transaction** is the real consistency boundary: its entries must sum to zero per
  currency. That invariant is enforced at the single place every write goes through —
  `LedgerService.assert_balanced` (`application/ledger.py`) — and re-checked when a
  two-phase transfer settles (`transfers.py`). No caller can persist an unbalanced
  transaction.
- The **account** invariant ("never overdrawn") is guarded by a DB row lock on every debit
  (`AccountService.lock`) combined with the ledger-derived *available* balance — not by
  mutating an in-memory object.

So the aggregate **boundaries and invariants are real and guarded**; they live in the
application services and the database (the true arbiter under concurrency), rather than in
aggregate-root classes. This is a pragmatic trade: less ceremony, and correctness anchored
where concurrency is actually resolved. A stricter DDD style would add `Transaction` /
`Account` aggregate roots that own their entries and expose behaviour methods — a refactor
we could make **without changing any guarantee**. Worth naming the trade-off out loud
rather than claiming a textbook aggregate we didn't build.

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

### Où sont les « agrégats » ? (une interprétation assumée)
L'énoncé cite `AccountAggregate` / `TransactionAggregate` comme agrégats qui « imposent les
invariants du domaine ». Nous *imposons* bien ces invariants — sans les emballer dans des
objets racines d'agrégat classiques. Le raisonnement :

- La **transaction** est la vraie frontière de cohérence : la somme de ses écritures doit
  valoir zéro par devise. Cet invariant est imposé au seul endroit par lequel passe toute
  écriture — `LedgerService.assert_balanced` (`application/ledger.py`) — et revérifié au
  règlement d'un transfert en deux phases (`transfers.py`). Aucun appelant ne peut
  persister une transaction déséquilibrée.
- L'invariant du **compte** (« jamais à découvert ») est protégé par un verrou de ligne en
  base à chaque débit (`AccountService.lock`) combiné au solde *disponible* déduit du grand
  livre — pas par la mutation d'un objet en mémoire.

Les **frontières et invariants d'agrégat sont donc réels et protégés** ; ils vivent dans
les services applicatifs et la base (l'arbitre véritable sous concurrence), plutôt que dans
des classes racines d'agrégat. C'est un compromis pragmatique : moins de cérémonie, et la
justesse ancrée là où la concurrence se résout vraiment. Un style DDD plus strict
introduirait des racines `Transaction` / `Account` possédant leurs écritures — un
remaniement faisable **sans changer aucune garantie**. Mieux vaut nommer ce compromis que
de prétendre à un agrégat manuel que nous n'avons pas construit.

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
