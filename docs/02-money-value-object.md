# The Money Value Object / Le value object Money

## 🇬🇧 English

### Never use float for money

Open a Python prompt and type `0.1 + 0.2`. You get `0.30000000000000004`.
Floating-point numbers are binary approximations; some decimal fractions simply
cannot be represented exactly. In a ledger, those tiny errors accumulate into
real, unexplainable discrepancies. So `Money` flatly **rejects floats**:

```python
# wallet_ledger/domain/money.py:44
if isinstance(self.amount, float):
    raise TypeError("Le flottant est interdit pour Money : utiliser Decimal, int ou str.")
```

We use `Decimal`, which stores exact base-10 numbers — what you'd write on paper.

### Immutable and currency-aware

`Money` is a frozen dataclass (`money.py:36`): once created it cannot be mutated,
so an amount can be shared freely without anyone changing it underneath you.

It also carries its currency. You can never accidentally add dollars to euros —
the guard `_ensure_same_currency` raises `CurrencyMismatchError`:

```python
# money.py:62
def __add__(self, other):
    self._ensure_same_currency(other)   # USD + EUR -> error
    return Money(self.amount + other.amount, self.currency)
```

A bare number could never protect you from this; a value object can.

### Per-currency decimals

Different currencies have different smallest units. `_CURRENCY_DECIMALS`
(`money.py:22`) encodes this:

- `USD` / `EUR` → 2 decimals (cents).
- `JPY` (Japanese Yen), `XAF` / `XOF` (CFA francs) → 0 decimals.

The Yen has **no sub-unit** — there is no "Japanese cent". Storing ¥100.00 would
invent decimals that do not exist in real life, so amounts are quantized to 0
places for these currencies.

### Banker's rounding (HALF_EVEN)

When rounding is needed, `Money` uses `ROUND_HALF_EVEN` (`money.py:51`). Normal
"round half up" always pushes `.5` upward, which over millions of operations
biases totals consistently high. Banker's rounding sends `.5` to the nearest
*even* digit — sometimes up, sometimes down — so the errors cancel out and the
bias disappears. Example: `2.5 → 2`, `3.5 → 4`.

### Tiny example

```python
Money(Decimal("10.00"), "USD") + Money(Decimal("0.10"), "USD")  # 10.10 USD
Money(Decimal("10"), "USD") + Money(Decimal("10"), "EUR")       # CurrencyMismatchError
Money(0.1, "USD")                                               # TypeError (no floats)
```

---

## 🇫🇷 Français

### Ne jamais utiliser de float pour l'argent

Dans un interpréteur Python, tapez `0.1 + 0.2`. Vous obtenez
`0.30000000000000004`. Les flottants sont des approximations binaires ; certaines
fractions décimales ne se représentent pas exactement. Dans un grand livre, ces
minuscules erreurs s'accumulent en écarts réels et inexplicables. `Money` **refuse
donc les floats** :

```python
# wallet_ledger/domain/money.py:44
if isinstance(self.amount, float):
    raise TypeError("Le flottant est interdit pour Money : utiliser Decimal, int ou str.")
```

On utilise `Decimal`, qui stocke des nombres base-10 exacts — ceux qu'on écrirait
sur papier.

### Immuable et conscient de sa devise

`Money` est une dataclass figée (`money.py:36`) : une fois créée, elle ne peut
plus être modifiée ; on peut donc la partager sans craindre qu'on la change dans
notre dos.

Elle porte aussi sa devise. Impossible d'additionner par erreur des dollars et
des euros — le garde-fou `_ensure_same_currency` lève `CurrencyMismatchError` :

```python
# money.py:62
def __add__(self, other):
    self._ensure_same_currency(other)   # USD + EUR -> erreur
    return Money(self.amount + other.amount, self.currency)
```

Un simple nombre ne pourrait jamais vous protéger ; un value object, si.

### Décimales par devise

Chaque devise a sa plus petite unité. `_CURRENCY_DECIMALS` (`money.py:22`) l'encode :

- `USD` / `EUR` → 2 décimales (les centimes).
- `JPY` (yen japonais), `XAF` / `XOF` (francs CFA) → 0 décimale.

Le yen n'a **pas de sous-unité** — il n'existe pas de « centime japonais ».
Stocker ¥100,00 inventerait des décimales qui n'existent pas, donc les montants
sont quantifiés à 0 décimale pour ces devises.

### Arrondi du banquier (HALF_EVEN)

Quand un arrondi est nécessaire, `Money` utilise `ROUND_HALF_EVEN` (`money.py:51`).
L'arrondi classique « à la moitié supérieure » pousse toujours `.5` vers le haut,
ce qui, sur des millions d'opérations, biaise systématiquement les totaux à la
hausse. L'arrondi du banquier envoie `.5` vers le chiffre *pair* le plus proche —
parfois en haut, parfois en bas — donc les erreurs se compensent et le biais
disparaît. Exemple : `2,5 → 2`, `3,5 → 4`.

### Petit exemple

```python
Money(Decimal("10.00"), "USD") + Money(Decimal("0.10"), "USD")  # 10.10 USD
Money(Decimal("10"), "USD") + Money(Decimal("10"), "EUR")       # CurrencyMismatchError
Money(0.1, "USD")                                               # TypeError (pas de float)
```
