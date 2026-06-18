"""Spécification OpenAPI 3 de l'API.

On documente l'API au niveau d'un fournisseur comme Stripe : chaque endpoint décrit
son intention, ses paramètres, ses réponses ET ses erreurs, avec des exemples. La
spec est servie en JSON et explorable via Swagger UI (voir `docs.py`).

Descriptions en anglais (standard de l'industrie pour une référence d'API).
"""

from __future__ import annotations

# --- Briques réutilisables (DRY) ----------------------------------------------

_IDEMPOTENCY_HEADER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": False,
    "schema": {"type": "string"},
    "description": (
        "Safely retry a POST without risk of the operation being applied twice. "
        "The same key + same body replays the original response; the same key + a "
        "different body returns 409."
    ),
}

_CORRELATION_HEADER = {
    "name": "X-Correlation-ID",
    "in": "header",
    "required": False,
    "schema": {"type": "string"},
    "description": "Trace id propagated across the request, events, ledger and notifications. Auto-generated if omitted.",
}


def _json(ref: str, example: dict | list) -> dict:
    return {"content": {"application/json": {"schema": {"$ref": ref}, "example": example}}}


def _error_response(description: str, code: str, message: str) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Error"},
                "example": {"error": message, "code": code},
            }
        },
    }


_TXN_EXAMPLE = {
    "transaction_id": "0d4f9b2e-2b8a-4f1e-9c33-2a1b6c5d4e3f",
    "type": "TRANSFER",
    "status": "SUCCESS",
    "amount": "30.00",
    "currency": "USD",
    "correlation_id": "c0ffee00-0000-0000-0000-000000000000",
    "created_at": "2026-06-18T12:00:00+00:00",
}


def build_spec() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "wallet-ledger API",
            "version": "1.0.0",
            "description": (
                "Double-entry ledger engine for a multi-currency digital wallet.\n\n"
                "**Money is never created or destroyed**: every transaction writes ledger "
                "entries that sum to zero per currency, and a balance is always derived from "
                "the ledger (there is no stored balance). All POSTs accept an `Idempotency-Key`; "
                "every response carries an `X-Correlation-ID`."
            ),
        },
        "servers": [{"url": "/api/v1"}],
        "tags": [
            {
                "name": "Accounts",
                "description": "Create accounts and read ledger-derived balances and history.",
            },
            {
                "name": "Transfers",
                "description": "Move funds between accounts — atomic or two-phase (reserve/settle).",
            },
            {
                "name": "Deposits",
                "description": "Fund a wallet from an external provider (Stripe, PawaPay).",
            },
            {"name": "Webhooks", "description": "Signed provider callbacks that confirm deposits."},
            {"name": "FX", "description": "Currency conversion and cross-currency transfers."},
        ],
        "paths": _paths(),
        "components": _components(),
    }


def _paths() -> dict:
    return {
        "/accounts": {
            "post": {
                "tags": ["Accounts"],
                "summary": "Create an account",
                "description": "Creates a wallet account for an owner in a single currency. One account per (owner, currency).",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CreateAccountRequest"},
                            "example": {"owner_id": "alice", "currency": "USD"},
                        }
                    },
                },
                "responses": {
                    "201": _json(
                        "#/components/schemas/Account",
                        {
                            "id": "3d1a93e3-bac5-4bc0-ba10-e0d267444e7d",
                            "number": "2104077793",
                            "owner_id": "alice",
                            "currency": "USD",
                            "created_at": "2026-06-18T12:00:00+00:00",
                        },
                    )
                    | {"description": "Account created"},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "409": _error_response(
                        "An account already exists for this owner and currency",
                        "DUPLICATE_ACCOUNT",
                        "Un compte existe déjà pour alice en USD",
                    ),
                },
            }
        },
        "/accounts/{number}": {
            "get": {
                "tags": ["Accounts"],
                "summary": "Retrieve an account",
                "parameters": [_path_param("number", "Account number")],
                "responses": {
                    "200": _json(
                        "#/components/schemas/Account",
                        {
                            "id": "3d1a93e3-bac5-4bc0-ba10-e0d267444e7d",
                            "number": "2104077793",
                            "owner_id": "alice",
                            "currency": "USD",
                            "created_at": "2026-06-18T12:00:00+00:00",
                        },
                    )
                    | {"description": "The account"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/accounts/{number}/balance": {
            "get": {
                "tags": ["Accounts"],
                "summary": "Get balance (derived from the ledger)",
                "description": "Returns the balance computed as the sum of SUCCESS ledger entries (snapshot + delta), served via a Redis read-cache.",
                "parameters": [_path_param("number", "Account number")],
                "responses": {
                    "200": _json(
                        "#/components/schemas/Balance",
                        {"account_number": "2104077793", "balance": "170.00", "currency": "USD"},
                    )
                    | {"description": "Current balance"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/accounts/{number}/transactions": {
            "get": {
                "tags": ["Accounts"],
                "summary": "List transaction history (paginated)",
                "parameters": [
                    _path_param("number", "Account number"),
                    {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                    {
                        "name": "per_page",
                        "in": "query",
                        "schema": {"type": "integer", "default": 20},
                    },
                ],
                "responses": {
                    "200": _json(
                        "#/components/schemas/TransactionList",
                        {
                            "items": [_TXN_EXAMPLE],
                            "page": 1,
                            "per_page": 20,
                            "total": 1,
                            "pages": 1,
                        },
                    )
                    | {"description": "Paginated transactions"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/transfers": {
            "post": _transfer_op(
                "Execute an atomic transfer",
                "Debits the sender and credits the receiver in one database transaction. The sender row is locked to prevent overdraft under concurrency.",
            )
        },
        "/transfers/initiate": {
            "post": _transfer_op(
                "Initiate a two-phase transfer (reserve funds)",
                "Phase 1: reserves the amount as a PENDING debit (reduces available balance, not settled balance). Settle with /commit or release with /fail.",
            )
        },
        "/transfers/{transaction_id}/commit": {
            "post": _two_phase_op(
                "Commit a reserved transfer",
                "Phase 2: after the internal risk check approves, settles the debit and creates the credit.",
            )
        },
        "/transfers/{transaction_id}/fail": {
            "post": _two_phase_op(
                "Fail a reserved transfer",
                "Releases a reservation: PENDING entries become FAILED and the reserved funds are returned.",
            )
        },
        "/transactions/{transaction_id}/reverse": {
            "post": {
                "tags": ["Transfers"],
                "summary": "Reverse a transaction (compensating entry)",
                "description": "Reverses a SUCCESS transaction by recording a new REVERSAL transaction whose entries mirror the original. The original is never mutated; it is marked REVERSED.",
                "parameters": [
                    _path_param("transaction_id", "Transaction id to reverse"),
                    _IDEMPOTENCY_HEADER,
                ],
                "responses": {
                    "201": _json(
                        "#/components/schemas/Transaction", _TXN_EXAMPLE | {"type": "REVERSAL"}
                    )
                    | {"description": "Compensating transaction created"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": _error_response(
                        "Only a SUCCESS transaction can be reversed",
                        "INVALID_TRANSACTION_STATE",
                        "Transition d'état interdite",
                    ),
                },
            }
        },
        "/deposits": {
            "post": {
                "tags": ["Deposits"],
                "summary": "Initiate a deposit",
                "description": "Creates a PENDING deposit that records the authorized amount, and asks the provider (stripe / pawapay) to charge. The amount is credited only after a signed webhook confirms it (see /payments/webhook).",
                "parameters": [_IDEMPOTENCY_HEADER, _CORRELATION_HEADER],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/DepositRequest"},
                            "examples": {
                                "stripe": {
                                    "value": {
                                        "account_number": "2104077793",
                                        "amount": "200.00",
                                        "provider": "stripe",
                                    }
                                },
                                "pawapay_mtn": {
                                    "value": {
                                        "account_number": "2104077793",
                                        "amount": "5000",
                                        "provider": "pawapay",
                                        "operator": "mtn",
                                        "phone_number": "237650000000",
                                    }
                                },
                            },
                        }
                    },
                },
                "responses": {
                    "201": _json(
                        "#/components/schemas/Transaction",
                        _TXN_EXAMPLE | {"type": "DEPOSIT", "status": "PENDING"},
                    )
                    | {"description": "Deposit initiated (PENDING)"},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/payments/webhook/{provider}": {
            "post": {
                "tags": ["Webhooks"],
                "summary": "Provider deposit confirmation",
                "description": (
                    "Called by the payment provider. The signature is **verified (fail-closed)** "
                    "and the confirmed amount and currency are **reconciled** against the authorized "
                    "deposit — a provider can never credit more, less, or a different currency than authorized."
                ),
                "parameters": [
                    _path_param("provider", "Provider name", enum=["stripe", "pawapay"]),
                    {
                        "name": "Stripe-Signature",
                        "in": "header",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Stripe signature header (t=,v1=).",
                    },
                    {
                        "name": "X-Signature",
                        "in": "header",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "HMAC-SHA256 of the raw body (PawaPay).",
                    },
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "example": {
                                "depositId": "0d4f9b2e-2b8a-4f1e-9c33-2a1b6c5d4e3f",
                                "status": "COMPLETED",
                                "amount": "5000",
                                "currency": "XAF",
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Deposit settled or ignored",
                        "content": {
                            "application/json": {
                                "example": {"transaction_id": "0d4f9b2e-...", "status": "SUCCESS"}
                            }
                        },
                    },
                    "401": _error_response(
                        "Signature verification failed",
                        "WEBHOOK_VERIFICATION_FAILED",
                        "Signature de webhook invalide pour pawapay",
                    ),
                    "409": _error_response(
                        "Deposit already settled (replayed webhook)",
                        "INVALID_TRANSACTION_STATE",
                        "Transition d'état interdite",
                    ),
                    "422": _error_response(
                        "Confirmed amount/currency does not match the authorized deposit",
                        "DEPOSIT_AMOUNT_MISMATCH",
                        "Le montant confirmé ne correspond pas au montant autorisé",
                    ),
                },
            }
        },
        "/fx/rate": {
            "get": {
                "tags": ["FX"],
                "summary": "Get the exchange rate between two currencies",
                "parameters": [
                    {
                        "name": "from",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "USD",
                    },
                    {
                        "name": "to",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "EUR",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Exchange rate",
                        "content": {
                            "application/json": {
                                "example": {"from": "USD", "to": "EUR", "rate": "0.92592593"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                },
            }
        },
        "/fx/convert": {
            "get": {
                "tags": ["FX"],
                "summary": "Convert an amount between currencies",
                "parameters": [
                    {
                        "name": "from",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "USD",
                    },
                    {
                        "name": "to",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "EUR",
                    },
                    {
                        "name": "amount",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "108",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Converted amount",
                        "content": {
                            "application/json": {
                                "example": {"converted_amount": "100.00", "currency": "EUR"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/ValidationError"},
                },
            }
        },
        "/fx/transfer": {
            "post": {
                "tags": ["FX"],
                "summary": "Cross-currency transfer",
                "description": "Transfers between accounts of different currencies, routing through internal FX pool accounts so the ledger still sums to zero per currency.",
                "parameters": [_IDEMPOTENCY_HEADER, _CORRELATION_HEADER],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/TransferRequest"},
                            "example": {
                                "sender_account_number": "2104077793",
                                "receiver_account_number": "2511399945",
                                "amount": "108",
                            },
                        }
                    },
                },
                "responses": {
                    "201": _json(
                        "#/components/schemas/Transaction", _TXN_EXAMPLE | {"type": "FX_TRANSFER"}
                    )
                    | {"description": "FX transfer completed"},
                    "400": {"$ref": "#/components/responses/ValidationError"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "422": _error_response(
                        "Same currency, or insufficient funds",
                        "SAME_CURRENCY",
                        "Transfert FX inutile : les deux comptes sont en USD",
                    ),
                },
            }
        },
    }


def _transfer_op(summary: str, description: str) -> dict:
    return {
        "tags": ["Transfers"],
        "summary": summary,
        "description": description,
        "parameters": [_IDEMPOTENCY_HEADER, _CORRELATION_HEADER],
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/TransferRequest"},
                    "example": {
                        "sender_account_number": "2104077793",
                        "receiver_account_number": "2511399945",
                        "amount": "30.00",
                    },
                }
            },
        },
        "responses": {
            "201": _json("#/components/schemas/Transaction", _TXN_EXAMPLE)
            | {"description": "Transfer created"},
            "400": {"$ref": "#/components/responses/ValidationError"},
            "404": {"$ref": "#/components/responses/NotFound"},
            "422": _error_response(
                "Insufficient funds or currency mismatch",
                "INSUFFICIENT_FUNDS",
                "Fonds insuffisants : disponible=20, demandé=50",
            ),
        },
    }


def _two_phase_op(summary: str, description: str) -> dict:
    return {
        "tags": ["Transfers"],
        "summary": summary,
        "description": description,
        "parameters": [_path_param("transaction_id", "Transaction id"), _IDEMPOTENCY_HEADER],
        "responses": {
            "200": _json("#/components/schemas/Transaction", _TXN_EXAMPLE)
            | {"description": "Updated transaction"},
            "404": {"$ref": "#/components/responses/NotFound"},
            "409": _error_response(
                "Transaction is not in a state that allows this transition",
                "INVALID_TRANSACTION_STATE",
                "Transition d'état interdite",
            ),
            "422": _error_response(
                "Rejected by the internal risk service",
                "RISK_REJECTED",
                "Transfert refusé par le contrôle de risque",
            ),
        },
    }


def _path_param(name: str, description: str, enum: list | None = None) -> dict:
    schema = {"type": "string"}
    if enum:
        schema["enum"] = enum
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": schema,
        "description": description,
    }


def _components() -> dict:
    return {
        "schemas": {
            "CreateAccountRequest": {
                "type": "object",
                "required": ["owner_id", "currency"],
                "properties": {
                    "owner_id": {"type": "string", "example": "alice"},
                    "currency": {
                        "type": "string",
                        "minLength": 3,
                        "maxLength": 3,
                        "example": "USD",
                    },
                },
            },
            "TransferRequest": {
                "type": "object",
                "required": ["sender_account_number", "receiver_account_number", "amount"],
                "properties": {
                    "sender_account_number": {"type": "string", "example": "2104077793"},
                    "receiver_account_number": {"type": "string", "example": "2511399945"},
                    "amount": {
                        "type": "string",
                        "description": "Decimal string (never a float)",
                        "example": "30.00",
                    },
                },
            },
            "DepositRequest": {
                "type": "object",
                "required": ["account_number", "amount", "provider"],
                "properties": {
                    "account_number": {"type": "string", "example": "2104077793"},
                    "amount": {"type": "string", "example": "200.00"},
                    "provider": {"type": "string", "enum": ["stripe", "pawapay"]},
                    "operator": {
                        "type": "string",
                        "enum": ["mtn", "orange"],
                        "description": "PawaPay only",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "PawaPay only",
                        "example": "237650000000",
                    },
                },
            },
            "Account": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "number": {"type": "string"},
                    "owner_id": {"type": "string"},
                    "currency": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Balance": {
                "type": "object",
                "properties": {
                    "account_number": {"type": "string"},
                    "balance": {
                        "type": "string",
                        "description": "Decimal string at the currency's precision",
                    },
                    "currency": {"type": "string"},
                },
            },
            "Transaction": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["DEPOSIT", "TRANSFER", "FX_TRANSFER", "REVERSAL"],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["PENDING", "SUCCESS", "FAILED", "REVERSED"],
                    },
                    "amount": {"type": "string"},
                    "currency": {"type": "string"},
                    "correlation_id": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "TransactionList": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Transaction"},
                    },
                    "page": {"type": "integer"},
                    "per_page": {"type": "integer"},
                    "total": {"type": "integer"},
                    "pages": {"type": "integer"},
                },
            },
            "Error": {
                "type": "object",
                "properties": {"error": {"type": "string"}, "code": {"type": "string"}},
            },
        },
        "responses": {
            "NotFound": _error_response(
                "Resource not found", "ACCOUNT_NOT_FOUND", "Compte introuvable : 0000000000"
            ),
            "ValidationError": {
                "description": "Request failed validation",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                        "example": {
                            "error": "Requête invalide",
                            "code": "VALIDATION_ERROR",
                            "details": {"currency": ["Missing data for required field."]},
                        },
                    }
                },
            },
        },
    }
