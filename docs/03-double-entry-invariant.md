# Double-Entry & the Zero-Sum Invariant / Partie double & invariant somme nulle

## 🇬🇧 English

### Money is moved, never created

The core accounting truth: money does not appear or vanish — it only **moves**
from one place to another. When Alice sends $50 to Bob, $50 leaves Alice and the
*same* $50 arrives at Bob. Nothing is born; nothing dies.

Double-entry bookkeeping makes this physical. Every transaction writes **at least
two** ledger entries, and within each currency they must **sum to exactly zero**.

### Debit negative, credit positive

Each `LedgerEntry` has a signed `amount` (`wallet_ledger/models/ledger_entry.py:32`):

- a **debit** (money leaving) is **negative**;
- a **credit** (money arriving) is **positive**.

Alice → Bob, $50:

| account | amount  |
|---------|---------|
| Alice   | `-50`   |
| Bob     | `+50`   |
| **sum** | **`0`** |

The two halves cancel. That zero is the proof that no money was created.

### The invariant is enforced in code

This is not a convention you hope callers follow — it is *enforced*.
`LedgerService.assert_balanced` (`wallet_ledger/application/ledger.py:28`) groups
entries by currency and rejects any set whose total is not zero:

```python
# ledger.py:38
for currency, total in totals.items():
    if total != 0:
        raise LedgerNotBalancedError(currency, str(total))
```

And every write goes through `post_entries` (`ledger.py:42`), which calls
`assert_balanced` *before* touching the database:

```python
def post_entries(self, entries):
    self.assert_balanced(entries)   # gatekeeper
    db.session.add_all(entries)
```

So **no caller can create money**. A buggy or malicious caller that tries to
credit Bob without debiting anyone gets a `LedgerNotBalancedError`
(`wallet_ledger/domain/errors.py:94`) and the write never happens. The invariant
is a safety net welded to the only door into the ledger.

---

## 🇫🇷 Français

### L'argent se déplace, il ne se crée jamais

La vérité comptable fondamentale : l'argent n'apparaît ni ne disparaît — il ne
fait que **se déplacer** d'un endroit à un autre. Quand Alice envoie 50 $ à Bob,
50 $ quittent Alice et les *mêmes* 50 $ arrivent chez Bob. Rien ne naît, rien ne
meurt.

La comptabilité en partie double rend cela concret. Chaque transaction écrit **au
moins deux** écritures, et au sein de chaque devise leur **somme doit valoir
exactement zéro**.

### Débit négatif, crédit positif

Chaque `LedgerEntry` a un `amount` signé (`wallet_ledger/models/ledger_entry.py:32`) :

- un **débit** (argent qui part) est **négatif** ;
- un **crédit** (argent qui arrive) est **positif**.

Alice → Bob, 50 $ :

| compte  | amount  |
|---------|---------|
| Alice   | `-50`   |
| Bob     | `+50`   |
| **somme** | **`0`** |

Les deux moitiés s'annulent. Ce zéro est la preuve qu'aucune monnaie n'a été créée.

### L'invariant est garanti par le code

Ce n'est pas une convention que l'on espère voir respectée — elle est *imposée*.
`LedgerService.assert_balanced` (`wallet_ledger/application/ledger.py:28`) regroupe
les écritures par devise et rejette tout jeu dont le total n'est pas nul :

```python
# ledger.py:38
for currency, total in totals.items():
    if total != 0:
        raise LedgerNotBalancedError(currency, str(total))
```

Et toute écriture passe par `post_entries` (`ledger.py:42`), qui appelle
`assert_balanced` *avant* de toucher la base :

```python
def post_entries(self, entries):
    self.assert_balanced(entries)   # gardien
    db.session.add_all(entries)
```

Ainsi **aucun appelant ne peut créer de monnaie**. Un appelant bogué ou
malveillant qui tente de créditer Bob sans débiter personne reçoit une
`LedgerNotBalancedError` (`wallet_ledger/domain/errors.py:94`), et l'écriture
n'a jamais lieu. L'invariant est un filet de sécurité soudé à l'unique porte
d'entrée du grand livre.
