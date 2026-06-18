# Performance: Snapshots & Cache / Performance : instantanés & cache

## 🇬🇧 English

### The problem
A balance is never a stored column — it is the **sum of ledger entries** (see
`wallet_ledger/application/ledger.py:47`). That is correct and auditable, but naïve:
at 1M users, 10M entries, 1000 reads/s with a <10ms target, re-summing millions of
rows on every read would melt the database. We need reads to stay cheap *without*
giving up "balance derived from entries" as the single source of truth.

Two complementary tools solve this. They attack different costs: snapshots make the
*computation* cheap; the cache makes the *repeat read* free.

### (a) Snapshot pattern — checkpoint the math
Periodically we store a balance checkpoint keyed on a monotonic cursor `seq`
(`balance_snapshot.py:24`, a `BigInteger` strictly-increasing per entry). Then:

```
balance = snapshot.balance + sum(entries WHERE seq > snapshot.last_entry_seq)
```

See `ledger.py:47-56`. Instead of summing 10M rows we sum only the **delta** since
the last checkpoint. `maybe_snapshot` (`ledger.py:73`) cuts a new snapshot once
`SNAPSHOT_EVERY_N_ENTRIES` entries have piled up, so the delta stays bounded.

**Why `seq` and not a timestamp?** Two entries can share the same millisecond, and
clocks drift. A timestamp boundary (`> snapshot_time`) risks double-counting or
skipping an entry written on the boundary. A strictly-increasing integer gives an
*exact, gap-free* cursor: "everything after entry N" is unambiguous. This is the
quiet bug-killer of the whole design.

### (b) Redis cache — accelerate the repeat read
`BalanceCache` (`infrastructure/cache.py`) and `BalanceQuery`
(`application/balance_query.py`) implement **cache-aside**: read cache → on miss,
compute from the ledger → store back with a short TTL.

Three rules that make this safe:
- **Never the source of truth.** Money decisions (`available_balance`, transfers)
  always recompute from the ledger under lock; only display-style reads use cache.
- **Fail-open.** If Redis is down, `get`/`set` swallow the error and fall back to the
  ledger (`cache.py:31`). A cache outage must never break a read.
- **Invalidate on every movement.** Every deposit/transfer event purges the key
  (`__init__.py:92`). A *stale* balance is worse than no cache at all.

**Takeaway as a future lead:** keep one authoritative source, then layer derived
accelerators that are always safe to throw away.

## 🇫🇷 Français

### Le problème
Un solde n'est jamais une colonne stockée — c'est la **somme des écritures** (voir
`wallet_ledger/application/ledger.py:47`). C'est correct et auditable, mais naïf : à
1M d'utilisateurs, 10M d'écritures, 1000 lectures/s et une cible <10ms, resommer des
millions de lignes à chaque lecture ferait fondre la base. Il faut des lectures peu
coûteuses *sans* abandonner « le solde dérive des écritures » comme seule vérité.

Deux outils complémentaires : l'instantané rend le *calcul* peu coûteux, le cache rend
la *lecture répétée* gratuite.

### (a) Instantané — figer le calcul
On stocke périodiquement un point de contrôle indexé sur un curseur monotone `seq`
(`balance_snapshot.py:24`, un `BigInteger` strictement croissant). Puis :

```
solde = instantané.balance + somme(écritures WHERE seq > instantané.last_entry_seq)
```

Voir `ledger.py:47-56`. On ne somme que le **delta** depuis le dernier point.
`maybe_snapshot` (`ledger.py:73`) coupe un nouvel instantané dès que
`SNAPSHOT_EVERY_N_ENTRIES` écritures se sont accumulées : le delta reste borné.

**Pourquoi `seq` et pas un horodatage ?** Deux écritures peuvent partager la même
milliseconde, et les horloges dérivent. Une frontière temporelle risque de
double-compter ou d'oublier une écriture posée sur la frontière. Un entier strictement
croissant donne un curseur *exact, sans trou* : « tout ce qui suit l'écriture N » est
sans ambiguïté. C'est le tueur de bug discret de tout le design.

### (b) Cache Redis — accélérer la lecture répétée
`BalanceCache` (`infrastructure/cache.py`) et `BalanceQuery`
(`application/balance_query.py`) implémentent le **cache-aside** : lire le cache → en
cas de miss, calculer depuis le grand livre → réécrire avec un TTL court.

Trois règles qui rendent cela sûr :
- **Jamais la source de vérité.** Les décisions financières recalculent toujours sous
  verrou ; seules les lectures d'affichage passent par le cache.
- **Tolérant aux pannes.** Si Redis tombe, on retombe sur le grand livre (`cache.py:31`).
- **Invalider à chaque mouvement.** Chaque événement purge la clé (`__init__.py:92`) :
  un solde périmé vaut pire que pas de cache.

**À retenir comme futur lead :** une seule source faisant autorité, puis des
accélérateurs dérivés qu'on peut toujours jeter sans risque.
