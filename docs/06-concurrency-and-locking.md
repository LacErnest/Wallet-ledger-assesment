# Concurrency & Locking / Concurrence & verrouillage

## 🇬🇧 English

### The classic race: lost update

Alice has **100**. Two transfers of **80** arrive at the *same instant*, on two
threads. Each reads the balance, sees "100 available", concludes "80 ≤ 100, fine",
and settles. Result: both succeed, Alice is at **−60**. Money was created from thin
air. This is the **lost-update** race, and it is the single most dangerous bug a
ledger can have.

The window is between *reading* the balance and *writing* the debit. If two
operations interleave inside that window, the check is worthless.

### The fix: a row lock serializes the sender

We close the window with a PostgreSQL `SELECT ... FOR UPDATE` row lock.
`AccountService.lock` (`wallet_ledger/application/accounts.py:40`):

```python
# accounts.py:43
account = db.session.query(Account).filter_by(id=account_id).with_for_update().first()
```

Every transfer locks the **sender** first (`transfers.py:74`, `transfers.py:50`).
The first thread grabs the lock; the second **blocks** until the first commits.
Now they run strictly one-after-another: thread A settles 80 (balance → 20),
thread B then re-reads 20, sees 80 > 20, and is correctly rejected. The race is
gone because the two operations can no longer overlap on the same row.

### Why PostgreSQL, not SQLite

SQLite has no real row-level `FOR UPDATE` — it serializes with a coarse
database-wide lock and can't give us this fine-grained, per-account blocking under
true concurrency. That is precisely why production runs on **PostgreSQL**: the row
lock is the cornerstone of the no-negative-balance guarantee.

### Defense in depth: optimistic locking

As a second line, `Account` uses SQLAlchemy's `version_id_col`
(`wallet_ledger/models/account.py:33`):

```python
version = db.Column(db.Integer, nullable=False, default=0)
__mapper_args__ = {"version_id_col": version}
```

Every write checks and increments `version`. If two updates somehow race, one
gets a `StaleDataError` instead of silently overwriting the other. The row lock
*prevents* the race; optimistic locking is the seatbelt if the lock is ever missing.

### The test that proves it

`test_concurrent_transfers_do_not_create_negative_balance`
(`tests/test_transfers.py:75`) is not a mock — it spawns **two real threads**,
each in its own app context and session, both attempting an 80 transfer from a
100 balance. It asserts exactly one `"ok"`, one `"rejected"`, and a final balance
of **20**. Real threads, real locks, real proof.

---

## 🇫🇷 Français

### La course classique : la mise à jour perdue

Alice a **100**. Deux transferts de **80** arrivent au *même instant*, sur deux
threads. Chacun lit le solde, voit « 100 disponible », conclut « 80 ≤ 100, ok » et
règle. Résultat : les deux passent, Alice est à **−60**. De la monnaie créée à
partir de rien. C'est la course de la **mise à jour perdue**, le bug le plus
dangereux qu'un grand livre puisse avoir.

La fenêtre se situe entre la *lecture* du solde et l'*écriture* du débit. Si deux
opérations s'entrelacent dans cette fenêtre, la vérification ne vaut rien.

### La solution : un verrou de ligne sérialise l'émetteur

On ferme la fenêtre avec un verrou de ligne PostgreSQL `SELECT ... FOR UPDATE`.
`AccountService.lock` (`wallet_ledger/application/accounts.py:40`) :

```python
# accounts.py:43
account = db.session.query(Account).filter_by(id=account_id).with_for_update().first()
```

Chaque transfert verrouille d'abord l'**émetteur** (`transfers.py:74`,
`transfers.py:50`). Le premier thread prend le verrou ; le second **attend** que le
premier valide. Ils s'exécutent dès lors strictement l'un après l'autre : le
thread A règle 80 (solde → 20), le thread B relit 20, voit 80 > 20, et est
correctement rejeté. La course disparaît car les deux opérations ne peuvent plus
se chevaucher sur la même ligne.

### Pourquoi PostgreSQL, pas SQLite

SQLite n'a pas de vrai `FOR UPDATE` par ligne — il sérialise via un verrou global
grossier et ne peut pas offrir ce blocage fin, par compte, sous vraie concurrence.
C'est exactement pour cela que la production tourne sur **PostgreSQL** : le verrou
de ligne est la pierre angulaire de la garantie « pas de solde négatif ».

### Défense en profondeur : verrou optimiste

En seconde ligne, `Account` utilise le `version_id_col` de SQLAlchemy
(`wallet_ledger/models/account.py:33`) :

```python
version = db.Column(db.Integer, nullable=False, default=0)
__mapper_args__ = {"version_id_col": version}
```

Chaque écriture vérifie et incrémente `version`. Si deux mises à jour se
télescopent malgré tout, l'une reçoit une `StaleDataError` au lieu d'écraser
l'autre en silence. Le verrou de ligne *empêche* la course ; le verrou optimiste
est la ceinture de sécurité si jamais le verrou venait à manquer.

### Le test qui le prouve

`test_concurrent_transfers_do_not_create_negative_balance`
(`tests/test_transfers.py:75`) n'est pas un mock — il lance **deux vrais
threads**, chacun dans son propre contexte d'application et sa session, tentant
tous deux un transfert de 80 depuis un solde de 100. Il vérifie exactement un
`"ok"`, un `"rejected"`, et un solde final de **20**. Vrais threads, vrais
verrous, vraie preuve.
