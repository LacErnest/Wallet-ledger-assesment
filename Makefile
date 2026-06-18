# Commandes du projet. `make` ou `make help` liste les cibles disponibles.
# Pré-requis : Docker + docker compose, et uv (https://docs.astral.sh/uv/).

FLASK := uv run flask --app wallet_ledger
COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help install up down logs dev migrate migration seed test test-down lint fmt shell clean

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Installe les dépendances (uv)
	uv sync

up: ## Démarre TOUTE la pile (api + db + redis). API sur http://localhost:8000
	$(COMPOSE) up -d --build
	@echo "API prête sur http://localhost:8000  —  docs : http://localhost:8000/api/v1/docs"

down: ## Arrête la pile (les données sont conservées)
	$(COMPOSE) down

logs: ## Suit les logs de l'API
	$(COMPOSE) logs -f api

dev: ## Lance l'API en local (db + redis dans Docker, rechargement à chaud)
	$(COMPOSE) up -d db redis
	$(FLASK) db upgrade
	$(FLASK) run --debug

migrate: ## Applique les migrations à la base de développement
	$(COMPOSE) up -d db
	$(FLASK) db upgrade

migration: ## Génère une migration : make migration m="message"
	$(FLASK) db migrate -m "$(m)"

seed: ## Insère des comptes et transactions de démonstration
	$(FLASK) seed

test: ## Lance les tests sur des conteneurs jetables isolés (db + redis de test)
	$(COMPOSE) --profile test up -d test-db test-redis
	@echo "Attente des conteneurs de test..."
	@until docker compose exec -T test-db pg_isready -U wallet -d wallet_test >/dev/null 2>&1; do sleep 1; done
	uv run pytest

test-down: ## Arrête les conteneurs de test
	$(COMPOSE) --profile test down

lint: ## Vérifie le style et les erreurs sans rien modifier (ruff)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Corrige et formate le code automatiquement (ruff)
	uv run ruff check --fix .
	uv run ruff format .

shell: ## Ouvre un shell Flask (contexte applicatif)
	$(FLASK) shell

clean: ## Arrête tout et supprime les volumes (données effacées)
	$(COMPOSE) --profile test down -v
