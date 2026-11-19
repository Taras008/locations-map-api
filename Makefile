COMPOSE ?= docker compose
EXEC    = $(COMPOSE) exec web

.DEFAULT_GOAL := help
.PHONY: help env up down logs ps test lint fmt migrate makemigrations shell seed

help: ## Показати доступні команди
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

env: ## Створити .env для локальних перевизначень (необов'язково)
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

up: ## Зібрати й запустити всі сервіси, дочекатися healthchecks
	$(COMPOSE) up -d --build --wait

down: ## Зупинити сервіси
	$(COMPOSE) down

logs: ## Логи всіх сервісів
	$(COMPOSE) logs -f --tail=100

ps: ## Стан сервісів
	$(COMPOSE) ps

test: ## Тести з покриттям
	$(EXEC) pytest --cov

lint: ## ruff: лінтер і перевірка форматування
	$(EXEC) ruff check .
	$(EXEC) ruff format --check .

fmt: ## ruff: автовиправлення й форматування
	$(EXEC) ruff check --fix .
	$(EXEC) ruff format .

migrate: ## Застосувати міграції
	$(EXEC) python manage.py migrate

makemigrations: ## Створити міграції
	$(EXEC) python manage.py makemigrations

shell: ## Django shell
	$(EXEC) python manage.py shell

seed: ## Демо-дані
	$(EXEC) python manage.py seed_demo
