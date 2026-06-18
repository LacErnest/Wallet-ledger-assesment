"""Exceptions métier.

On nomme chaque échec du domaine plutôt que de lever des `ValueError` génériques :
le code porteur de l'erreur permet à la couche HTTP de répondre le bon statut sans
que le domaine ait besoin de connaître HTTP (séparation des responsabilités).
"""

from __future__ import annotations


class DomainError(Exception):
    """Racine de toutes les erreurs métier."""

    code = "DOMAIN_ERROR"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class AccountNotFoundError(DomainError):
    code = "ACCOUNT_NOT_FOUND"

    def __init__(self, identifier: str):
        super().__init__(f"Compte introuvable : {identifier}")


class DuplicateAccountError(DomainError):
    code = "DUPLICATE_ACCOUNT"

    def __init__(self, owner_id: str, currency: str):
        super().__init__(
            f"Un compte existe déjà pour {owner_id} en {currency}"
        )


class InsufficientFundsError(DomainError):
    code = "INSUFFICIENT_FUNDS"

    def __init__(self, available: str, requested: str):
        super().__init__(
            f"Fonds insuffisants : disponible={available}, demandé={requested}"
        )


class InvalidAmountError(DomainError):
    code = "INVALID_AMOUNT"

    def __init__(self, message: str = "Le montant doit être strictement positif"):
        super().__init__(message)


class CurrencyMismatchError(DomainError):
    code = "CURRENCY_MISMATCH"

    def __init__(self, expected: str, actual: str):
        super().__init__(f"Devises incompatibles : {expected} vs {actual}")


class TransactionNotFoundError(DomainError):
    code = "TRANSACTION_NOT_FOUND"

    def __init__(self, transaction_id: str):
        super().__init__(f"Transaction introuvable : {transaction_id}")


class InvalidTransactionStateError(DomainError):
    code = "INVALID_TRANSACTION_STATE"

    def __init__(self, current: str, attempted: str):
        super().__init__(
            f"Transition d'état interdite : {current} -> {attempted}"
        )


class LedgerNotBalancedError(DomainError):
    """Filet de sécurité : on refuse d'écrire si la somme des écritures n'est pas nulle."""

    code = "LEDGER_NOT_BALANCED"

    def __init__(self, currency: str, total: str):
        super().__init__(
            f"Écritures non équilibrées en {currency} : somme={total} (attendu 0)"
        )


class DepositAmountMismatchError(DomainError):
    code = "DEPOSIT_AMOUNT_MISMATCH"

    def __init__(self, authorized: str, confirmed: str):
        super().__init__(
            f"Le montant confirmé ({confirmed}) ne correspond pas au montant "
            f"autorisé ({authorized})"
        )


class WebhookVerificationError(DomainError):
    code = "WEBHOOK_VERIFICATION_FAILED"

    def __init__(self, provider: str):
        super().__init__(f"Signature de webhook invalide pour {provider}")


class UnsupportedProviderError(DomainError):
    code = "UNSUPPORTED_PROVIDER"

    def __init__(self, provider: str):
        super().__init__(f"Fournisseur non supporté : {provider}")


class RiskRejectedError(DomainError):
    code = "RISK_REJECTED"

    def __init__(self, reason: str):
        super().__init__(f"Transfert refusé par le contrôle de risque : {reason}")


class IdempotencyConflictError(DomainError):
    code = "IDEMPOTENCY_CONFLICT"

    def __init__(self, message: str = "Clé d'idempotence réutilisée avec un corps différent"):
        super().__init__(message)
