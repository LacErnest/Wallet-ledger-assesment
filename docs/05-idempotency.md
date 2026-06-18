# Idempotency / Idempotence

## 🇬🇧 English

### Why retries happen — and why they're dangerous

The client sends `POST /transfers`, the money moves, but the response is lost to a
network blip or a timeout. The client has no idea it worked, so it **retries**.
Without protection, the transfer runs *twice* — Alice pays Bob $50 two times. In
money systems, an accidental double-execution is a real loss.

**Idempotency** means: the same request, replayed any number of times, has the
**same effect as running it once**. The client sends an `Idempotency-Key` header,
and we guarantee the work behind that key happens at most once.

### The naive trap: check-then-act

The obvious approach is "look up the key; if absent, run the work; then save it":

```text
if key not in table:   # request A and request B both read "absent"
    run_transfer()     # ... so BOTH run it. Double spend.
    save(key)
```

Two concurrent retries both pass the check before either writes. The gap between
*check* and *act* is a race window. Don't do this.

### The fix: claim-first, with the DB as the single gate

We let the **database unique constraint** be the only arbiter. `idempotent`
(`wallet_ledger/infrastructure/idempotency.py:52`) inserts the key in its **own
committed transaction, before** running the view:

```python
# idempotency.py:63
db.session.add(IdempotencyKey(key=key, request_hash=request_hash))
try:
    db.session.commit()          # the unique constraint decides the winner
except IntegrityError:
    db.session.rollback()
    return _resolve_duplicate(key, request_hash)
```

`IdempotencyKey.key` is `unique=True` (`wallet_ledger/models/idempotency.py:18`),
so exactly **one** concurrent insert succeeds. There is no check-then-act gap —
the claim *is* the check.

### What the loser sees

`_resolve_duplicate` (`idempotency.py:40`) handles every duplicate:

- **completed** key → replay the stored `response_body` / `response_status`
  (same answer, no re-run);
- **in progress** (response still `NULL`, `is_completed` false) → `409` "a request
  with this key is already in progress";
- **same key, different body** → `409` (key reuse is a client bug).

### Completing and recovering

On success the claim is filled in with the response so future retries can replay
it (`idempotency.py:81`). On an **unexpected failure** the claim is *released* so
a genuine retry can proceed (`idempotency.py:72`):

```python
except Exception:
    db.session.rollback()
    claim = IdempotencyKey.query.filter_by(key=key).first()
    if claim is not None and not claim.is_completed:
        db.session.delete(claim); db.session.commit()
    raise
```

---

## 🇫🇷 Français

### Pourquoi des rejeux — et pourquoi c'est dangereux

Le client envoie `POST /transfers`, l'argent bouge, mais la réponse se perd dans
un aléa réseau ou un timeout. Le client ignore que ça a marché : il **rejoue**.
Sans protection, le transfert s'exécute *deux fois* — Alice paie Bob 50 $ deux
fois. En finance, une double exécution accidentelle est une perte réelle.

L'**idempotence** signifie : la même requête, rejouée autant de fois qu'on veut, a
le **même effet qu'une seule exécution**. Le client envoie un en-tête
`Idempotency-Key`, et on garantit que le travail derrière cette clé n'a lieu qu'une fois.

### Le piège naïf : vérifier-puis-agir

L'approche évidente est « chercher la clé ; absente → exécuter ; puis l'enregistrer » :

```text
si clé absente:        # A et B lisent tous deux « absente »
    exécuter_transfert()  # ... donc les DEUX l'exécutent. Double dépense.
    enregistrer(clé)
```

Deux rejeux simultanés passent la vérification avant que l'un n'écrive. L'écart
entre *vérifier* et *agir* est une fenêtre de course. À éviter.

### La solution : réserver d'abord, la base comme unique arbitre

On laisse la **contrainte d'unicité** trancher seule. `idempotent`
(`wallet_ledger/infrastructure/idempotency.py:52`) insère la clé dans sa **propre
transaction validée, avant** d'exécuter la vue :

```python
# idempotency.py:63
db.session.add(IdempotencyKey(key=key, request_hash=request_hash))
try:
    db.session.commit()          # la contrainte d'unicité désigne le gagnant
except IntegrityError:
    db.session.rollback()
    return _resolve_duplicate(key, request_hash)
```

`IdempotencyKey.key` est `unique=True` (`wallet_ledger/models/idempotency.py:18`),
donc une **seule** insertion concurrente réussit. Pas d'écart vérifier-puis-agir :
la réservation *est* la vérification.

### Ce que voit le perdant

`_resolve_duplicate` (`idempotency.py:40`) traite tout doublon :

- clé **terminée** → on rejoue le `response_body` / `response_status` stocké
  (même réponse, pas de réexécution) ;
- clé **en cours** (réponse encore `NULL`, `is_completed` faux) → `409` « une
  requête avec cette clé est déjà en cours » ;
- même clé, **corps différent** → `409` (réutilisation = bug client).

### Achever et récupérer

En cas de succès, la réservation est complétée avec la réponse pour permettre les
rejeux (`idempotency.py:81`). En cas d'**échec inattendu**, elle est *libérée*
pour qu'un vrai nouvel essai puisse passer (`idempotency.py:72`) :

```python
except Exception:
    db.session.rollback()
    claim = IdempotencyKey.query.filter_by(key=key).first()
    if claim is not None and not claim.is_completed:
        db.session.delete(claim); db.session.commit()
    raise
```
