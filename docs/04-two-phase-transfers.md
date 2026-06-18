# Two-Phase Transfers / Transferts en deux phases

## 🇬🇧 English

### The problem: money "in flight"

In a real payment platform, money is often *committed but not yet settled*. You
want to put a hold on funds, let a Risk Service look at the transfer, and only
then move the money — or release the hold. A single all-at-once write can't model
that pause. So we split a transfer into two phases.

### Available vs settled balance

The trick is two different balances (`wallet_ledger/application/ledger.py`):

- **settled** (`balance`, `ledger.py:47`) — only `SUCCESS` entries. The money
  that has truly moved.
- **available** (`available_balance`, `ledger.py:58`) — settled **minus** the
  `PENDING` debits already reserved.

```python
# ledger.py:64
settled = self.balance(account).amount
pending_debits = self._sum(..., statuses=(EntryStatus.PENDING,), entry_type=EntryType.DEBIT)
return Money(settled + pending_debits, account.currency)
```

Reserving money lowers *available* immediately but leaves *settled* untouched.
That gap is what stops the same dollar being spent twice while in flight.

### Phase 1 — `initiate`: reserve the funds

`initiate` (`transfers.py:71`) locks the sender, checks **available** funds, then
writes a **single** `PENDING` debit — no credit yet, so the transaction is
deliberately unbalanced until it settles:

```python
# transfers.py:86
db.session.add(self._entry(sender.id, txn.id, -money.amount,
                           EntryType.DEBIT, EntryStatus.PENDING, money.currency))
```

The transaction is now `PENDING`. Available balance drops; settled does not.

### Between phases — the Risk Service can say no

`commit` calls `self.risk.assess(money)` (`transfers.py:100`). `RiskService`
(`wallet_ledger/application/risk.py:25`) approves silently or raises
`RiskRejectedError` above its auto-approval limit. This decision point is the
*whole reason* two phases exist — and it lives behind an interface so a real
anti-fraud engine can be plugged in later without touching transfers.

### Phase 2 — `commit` or `fail`

`commit` (`transfers.py:94`) flips the reserved debit to `SUCCESS`, creates the
matching `SUCCESS` credit, re-checks the zero-sum invariant, and marks the
transaction `SUCCESS`. Now settled balance moves too.

`fail` (`transfers.py:127`) flips every `PENDING` entry to `FAILED` and the
transaction to `FAILED` — the reservation is released and available balance is
restored. No money ever moved.

---

## 🇫🇷 Français

### Le problème : l'argent « en vol »

Sur une vraie plateforme de paiement, l'argent est souvent *engagé mais pas
encore réglé*. On veut bloquer des fonds, laisser un service de risque examiner le
transfert, puis seulement déplacer l'argent — ou libérer le blocage. Une écriture
unique ne sait pas modéliser cette pause. On découpe donc le transfert en deux phases.

### Solde disponible vs soldé

L'astuce : deux soldes distincts (`wallet_ledger/application/ledger.py`) :

- **soldé** (`balance`, `ledger.py:47`) — uniquement les écritures `SUCCESS`.
  L'argent réellement déplacé.
- **disponible** (`available_balance`, `ledger.py:58`) — le soldé **moins** les
  débits `PENDING` déjà réservés.

Réserver de l'argent baisse aussitôt le *disponible* mais laisse le *soldé*
intact. Cet écart empêche de dépenser deux fois le même euro pendant qu'il est en vol.

### Phase 1 — `initiate` : réserver les fonds

`initiate` (`transfers.py:71`) verrouille l'émetteur, vérifie le **disponible**,
puis écrit un **seul** débit `PENDING` — pas encore de crédit, la transaction
reste donc volontairement déséquilibrée jusqu'au règlement :

```python
# transfers.py:86
db.session.add(self._entry(sender.id, txn.id, -money.amount,
                           EntryType.DEBIT, EntryStatus.PENDING, money.currency))
```

La transaction est `PENDING`. Le disponible chute ; le soldé non.

### Entre les phases — le service de risque peut refuser

`commit` appelle `self.risk.assess(money)` (`transfers.py:100`). `RiskService`
(`wallet_ledger/application/risk.py:25`) approuve en silence ou lève
`RiskRejectedError` au-delà de son plafond. Ce point de décision est *toute la
raison d'être* des deux phases — et il vit derrière une interface, pour brancher
demain un vrai moteur anti-fraude sans toucher aux transferts.

### Phase 2 — `commit` ou `fail`

`commit` (`transfers.py:94`) passe le débit réservé à `SUCCESS`, crée le crédit
`SUCCESS` correspondant, revérifie l'invariant somme nulle, et passe la
transaction à `SUCCESS`. Le soldé bouge enfin.

`fail` (`transfers.py:127`) passe chaque écriture `PENDING` à `FAILED` et la
transaction à `FAILED` — la réservation est libérée, le disponible restauré.
Aucun argent n'a bougé.
