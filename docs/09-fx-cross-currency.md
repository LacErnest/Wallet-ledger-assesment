# FX & Cross-Currency Transfers / Change & transferts multi-devises

## 🇬🇧 English

### Getting a rate
A cross-currency transfer needs a conversion rate. `FxRateProvider`
(`infrastructure/fx_rates.py`) calls an external rates API **if configured**, and
otherwise falls back to built-in reference rates (`fx_rates.py:20`, units per EUR).
This means the system stays usable and testable offline — a third-party outage can
slow us but never *block* an operation (`fx_rates.py:59`). Rates are computed through
EUR as a pivot: `rate(base→quote) = per_eur[quote] / per_eur[base]` (`:48`).

### The conservation problem
The golden rule of double-entry: **per currency, the sum of entries must be zero** —
money is moved, never created. But a cross-currency transfer touches *two* currencies.
If the sender loses 100 EUR and the receiver gains 108 USD, neither currency balances
to zero on its own. So how do we exchange without "printing" money?

### Solution: route through two FX pool accounts
We keep one internal **FX pool** account per currency, owned by `FX_POOL`
(`application/fx.py:25`, created on demand at `:58-59`). A transfer becomes **four
entries** (`fx.py:74-79`) — and crucially, *each currency stays balanced on its own*:

```
sender   DEBIT   -100 EUR   ┐ EUR side: -100 + 100 = 0
pool_A   CREDIT  +100 EUR   ┘
pool_B   DEBIT   -108 USD   ┐ USD side: -108 + 108 = 0
receiver CREDIT  +108 USD   ┘
```

The EUR the sender gave up lands in `pool_A`; the USD the receiver gets is drawn from
`pool_B`. The exchange happens *between the pools* (an accounting/treasury concern),
not inside the user-facing entries. Each currency's column still sums to zero, so the
`assert_balanced` invariant (`ledger.py:28`) holds per currency and no money is
conjured into existence.

### Wiring it together
`execute_fx_transfer` (`fx.py:43`) locks the sender, rejects a same-currency transfer
(`SameCurrencyError`), checks **available** balance (so reserved funds can't be double
spent), converts via the rate provider, posts the four entries, snapshots, commits,
then publishes `TransferCompleted` for notifications and cache invalidation.

**Lead takeaway:** when an invariant ("sum = 0 per currency") seems to block a feature,
don't weaken the invariant — introduce an internal account that absorbs the imbalance
and keeps it true.

## 🇫🇷 Français

### Obtenir un taux
Un transfert multi-devises a besoin d'un taux. `FxRateProvider`
(`infrastructure/fx_rates.py`) interroge une API externe **si configurée**, sinon il
retombe sur des taux de référence intégrés (`fx_rates.py:20`, unités par EUR). Le
système reste donc utilisable et testable hors-ligne : une panne d'un tiers peut nous
ralentir mais jamais *bloquer* une opération (`:59`). Les taux passent par l'EUR comme
pivot : `taux(base→quote) = par_eur[quote] / par_eur[base]` (`:48`).

### Le problème de conservation
La règle d'or de la partie double : **par devise, la somme des écritures doit être
nulle** — l'argent est déplacé, jamais créé. Mais un transfert multi-devises touche
*deux* devises. Si l'émetteur perd 100 EUR et le destinataire gagne 108 USD, aucune
des deux ne s'équilibre seule. Comment échanger sans « imprimer » de la monnaie ?

### Solution : router via deux comptes pool de change
On garde un compte **pool** interne par devise, détenu par `FX_POOL`
(`application/fx.py:25`, créé à la demande `:58-59`). Un transfert devient **quatre
écritures** (`fx.py:74-79`) — et surtout, *chaque devise reste équilibrée seule* :

```
émetteur     DÉBIT   -100 EUR   ┐ côté EUR : -100 + 100 = 0
pool_A       CRÉDIT  +100 EUR   ┘
pool_B       DÉBIT   -108 USD   ┐ côté USD : -108 + 108 = 0
destinataire CRÉDIT  +108 USD   ┘
```

Les EUR cédés atterrissent dans `pool_A` ; les USD reçus sont tirés de `pool_B`.
L'échange a lieu *entre les pools* (affaire de trésorerie), pas dans les écritures
côté client. La colonne de chaque devise somme toujours à zéro : l'invariant
`assert_balanced` (`ledger.py:28`) tient par devise, et aucune monnaie n'est créée.

### Le câblage
`execute_fx_transfer` (`fx.py:43`) verrouille l'émetteur, refuse un transfert
même-devise (`SameCurrencyError`), vérifie le solde **disponible** (les fonds réservés
ne peuvent être dépensés deux fois), convertit, poste les quatre écritures, fige un
instantané, commit, puis publie `TransferCompleted` pour les notifications et
l'invalidation du cache.

**À retenir comme lead :** quand un invariant (« somme = 0 par devise ») semble bloquer
une fonctionnalité, ne l'affaiblis pas — introduis un compte interne qui absorbe le
déséquilibre et le maintient vrai.
