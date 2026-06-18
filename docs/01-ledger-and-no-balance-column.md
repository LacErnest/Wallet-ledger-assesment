# Ledger & No Balance Column / Grand livre & absence de colonne de solde

## 🇬🇧 English

### The sticky-note problem

Imagine a bank that keeps your balance on a sticky note: "you have $500". If
someone changes the note (a bug, a race, a fraud), the truth is gone — you have
no way to prove what the number *should* be. That is what a mutable `balance`
column is: a sticky note.

Now look at a real bank statement. It does **not** trust a single number. It
lists every transaction, and your balance is simply the **sum of that list**.
You believe the total because you can re-derive it line by line.

This project chooses the statement, not the sticky note.

### No balance column

Look at the `Account` model — there is deliberately no `balance` field:

```
# wallet_ledger/models/account.py
class Account(db.Model):
    id, number, owner_id, currency, version, created_at   # no balance!
```

The balance is **computed**, never stored. Each money movement is an immutable
row in `LedgerEntry` (`wallet_ledger/models/ledger_entry.py`), with a signed
`amount` (negative = debit, positive = credit) and a `status`.

### Balance = SUM of entries WHERE status = SUCCESS

The rule lives in `LedgerService.balance` (`wallet_ledger/application/ledger.py:47`):
it sums only `EntryStatus.SUCCESS` entries. Pending or failed entries do not
count toward what you actually own.

### Why this matters (the audit benefit)

Every cent is explained by a row you can point at. Nothing can drift, because
there is no second source of truth to drift *from*. An auditor re-runs the sum
and gets the same answer — always.

### Making it fast: the snapshot

Summing millions of rows on every read would be slow. So `maybe_snapshot`
(`ledger.py:73`) periodically freezes a checkpoint: a stored balance plus the
sequence number (`seq`) of the last entry it covered. Then `balance()` only sums
the *delta* — entries after that checkpoint — instead of all history. Fast reads,
but the ledger is still the source of truth; the snapshot is just a cache that can
always be rebuilt from the entries.

---

## 🇫🇷 Français

### Le problème du Post-it

Imaginez une banque qui garde votre solde sur un Post-it : « vous avez 500 $ ».
Si quelqu'un modifie le papier (un bug, une concurrence, une fraude), la vérité
est perdue — impossible de prouver ce que le nombre *devrait* être. Une colonne
`balance` modifiable, c'est exactement ce Post-it.

Regardez un vrai relevé bancaire. Il ne fait **pas** confiance à un seul nombre :
il liste chaque opération, et votre solde n'est que la **somme de cette liste**.
On croit au total parce qu'on peut le recalculer ligne par ligne.

Ce projet choisit le relevé, pas le Post-it.

### Pas de colonne de solde

Le modèle `Account` n'a volontairement aucun champ `balance` :

```
# wallet_ledger/models/account.py
class Account(db.Model):
    id, number, owner_id, currency, version, created_at   # pas de solde !
```

Le solde est **calculé**, jamais stocké. Chaque mouvement d'argent est une ligne
immuable dans `LedgerEntry` (`wallet_ledger/models/ledger_entry.py`), avec un
`amount` signé (négatif = débit, positif = crédit) et un `status`.

### Solde = SOMME des écritures OÙ status = SUCCESS

La règle vit dans `LedgerService.balance` (`wallet_ledger/application/ledger.py:47`) :
on ne somme que les écritures `EntryStatus.SUCCESS`. Les écritures en attente ou
échouées ne comptent pas dans ce que vous possédez réellement.

### Pourquoi c'est important (l'auditabilité)

Chaque centime est expliqué par une ligne que l'on peut désigner. Rien ne peut
diverger, car il n'existe pas de seconde source de vérité *avec laquelle*
diverger. Un auditeur rejoue la somme et obtient toujours le même résultat.

### Le rendre rapide : l'instantané

Sommer des millions de lignes à chaque lecture serait lent. `maybe_snapshot`
(`ledger.py:73`) fige donc périodiquement un point de contrôle : un solde stocké
plus le numéro de séquence (`seq`) de la dernière écriture couverte. Ensuite
`balance()` ne somme que le *delta* — les écritures postérieures — au lieu de tout
l'historique. Lectures rapides, mais le grand livre reste la source de vérité ;
l'instantané n'est qu'un cache, toujours reconstructible à partir des écritures.
