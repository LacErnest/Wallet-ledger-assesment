# Deposits, Webhooks & Providers / Dépôts, webhooks & fournisseurs

## 🇬🇧 English

### The deposit flow
Funding a wallet is asynchronous: we ask a third party to collect money, and they tell
us *later* whether it worked. The flow (`application/deposits.py`):

1. **Initiate** — user requests a deposit. We create a `PENDING` transaction that
   **stores the authorized amount** (`deposits.py:51`) and call the provider's
   `create_deposit`. We save the provider's `reference` — the webhook will carry it.
2. **Provider charges** the card / mobile-money account out-of-band.
3. **Webhook confirms** — the provider POSTs a callback. After we verify it, `settle`
   (`deposits.py:71`) posts two balanced ledger entries: **clearing → user**
   (`deposits.py:88-93`), then marks the transaction `SUCCESS`.

### Three providers, one port (Ports & Adapters + Factory)
The deposit service only knows the abstract `PaymentProvider` port
(`payments/base.py:40`); each provider is an **adapter** wrapping an external API. The
concrete adapter is chosen by name in a **factory** — `get_payment_provider`
(`payments/__init__.py`). (It's *not* the Strategy pattern: these are adapters to
different systems, not interchangeable algorithms injected into a context.) Adding a
provider = one new adapter class + one branch, with zero change to the core — PayPal
below was added in exactly that way.

- **Stripe** (`stripe_provider.py`) — cards. Amounts in **minor units / cents**
  (`amount * 100`, except zero-decimal currencies, `stripe_provider.py:40`). Webhook
  signed via the `Stripe-Signature` header `t=...,v1=...`; we HMAC
  `"{timestamp}.{raw_body}"` and compare (`stripe_provider.py:55-64`).
- **PawaPay** (`pawapay_provider.py`) — mobile money for MTN & Orange. Amounts as
  **decimal strings** (`pawapay_provider.py:54`), operator mapped to a *correspondent*
  code like `MTN_MOMO_CMR` / `ORANGE_CMR` (`:26`). `depositId` = our transaction id,
  giving **idempotency** on PawaPay's side (`:55`).
- **PayPal** (`paypal_provider.py`) — Orders API v2; amounts as decimal strings, our
  transaction id carried in `custom_id` so the capture webhook
  (`PAYMENT.CAPTURE.COMPLETED`) maps back to our deposit. Same fail-closed verification.

A single endpoint `POST /payments/webhook` also exists (provider read from the body /
`X-Provider`) for the brief's shape, alongside the per-provider `…/webhook/{provider}`.

### Two security points you must never skip
1. **Verify the webhook signature, fail-closed.** `verify_webhook` returns `False` on
   missing secret or missing signature (`stripe_provider.py:56`, `pawapay_provider.py:77`).
   An unverified webhook would let anyone credit any account for free. Default to *deny*.
2. **Reconcile confirmed vs. authorized amount.** In `settle`, the confirmed amount is
   compared to the amount we stored at initiation; a mismatch raises
   `DepositAmountMismatchError` (`deposits.py:80-83`). A provider can therefore **never
   credit more than the user asked for**. We also reject non-`PENDING` transactions
   (`:77`) so a *replayed* webhook can't credit twice.

**Lead takeaway:** trust boundaries are where security lives. Treat every external
callback as hostile until a signature and an amount both check out.

## 🇫🇷 Français

### Le flux de dépôt
Alimenter un portefeuille est asynchrone : on demande à un tiers d'encaisser, il nous
dit *plus tard* si ça a marché. Le flux (`application/deposits.py`) :

1. **Initier** — l'utilisateur demande un dépôt. On crée une transaction `PENDING` qui
   **mémorise le montant autorisé** (`deposits.py:51`) et on appelle `create_deposit`.
   On garde la `reference` du fournisseur : le webhook la portera.
2. **Le fournisseur encaisse** la carte / le compte mobile money hors-bande.
3. **Le webhook confirme** — après vérification, `settle` (`deposits.py:71`) poste deux
   écritures équilibrées : **compensation → utilisateur** (`:88-93`), puis passe la
   transaction à `SUCCESS`.

### Trois fournisseurs, un seul port (Ports & Adaptateurs + Fabrique)
Le service ne connaît que le port abstrait `PaymentProvider` (`payments/base.py:40`) ;
chaque fournisseur est un **adaptateur** d'une API externe. L'adaptateur concret est
choisi par nom dans une **fabrique** — `get_payment_provider` (`payments/__init__.py`).
(Ce n'est *pas* le patron Stratégie : ce sont des adaptateurs vers des systèmes
différents, pas des algorithmes interchangeables injectés dans un contexte.) Ajouter un
fournisseur = une classe d'adaptateur + une branche, sans toucher au cœur — PayPal a été
ajouté exactement ainsi.

- **Stripe** (`stripe_provider.py`) — cartes. Montants en **sous-unités / centimes**
  (`amount * 100`, `:40`). Webhook signé via l'en-tête `Stripe-Signature` `t=...,v1=...` ;
  on calcule le HMAC de `"{timestamp}.{corps}"` et on compare (`:55-64`).
- **PawaPay** (`pawapay_provider.py`) — mobile money MTN & Orange. Montants en **chaînes
  décimales** (`:54`), opérateur traduit en code *correspondant* `MTN_MOMO_CMR` /
  `ORANGE_CMR` (`:26`). `depositId` = notre id de transaction → **idempotence** côté
  PawaPay (`:55`).
- **PayPal** (`paypal_provider.py`) — API Orders v2 ; notre id de transaction porté dans
  `custom_id`, si bien que le webhook de capture (`PAYMENT.CAPTURE.COMPLETED`) se relie à
  notre dépôt. Même vérification fail-closed.

Un endpoint unique `POST /payments/webhook` existe aussi (fournisseur lu dans le corps /
`X-Provider`), à côté du `…/webhook/{provider}` par fournisseur.

### Deux points de sécurité à ne jamais sauter
1. **Vérifier la signature du webhook, fail-closed.** `verify_webhook` renvoie `False`
   si secret ou signature manquent (`stripe_provider.py:56`, `pawapay_provider.py:77`).
   Un webhook non vérifié laisserait n'importe qui créditer un compte gratuitement. Par
   défaut, on *refuse*.
2. **Réconcilier montant confirmé vs. autorisé.** Dans `settle`, on compare le montant
   confirmé à celui mémorisé à l'initiation ; un écart lève `DepositAmountMismatchError`
   (`deposits.py:80-83`). Un fournisseur ne peut donc **jamais créditer plus que demandé**.
   On rejette aussi les transactions non-`PENDING` (`:77`) : un webhook rejoué ne
   crédite pas deux fois.

**À retenir comme lead :** la sécurité vit aux frontières de confiance. Traiter chaque
callback externe comme hostile tant que signature *et* montant ne sont pas validés.
