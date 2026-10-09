COMPOSE_DEV = docker compose -p yunesa --env-file .env -f docker-compose.yml
COMPOSE_PROD = docker compose -p yunesa-prod --env-file .env -f docker-compose.prod.yml

.PHONY: init config dev dev-etl down logs ps prod-config help

init:
	python scripts/init-env.py

config:
	$(COMPOSE_DEV) config --quiet

dev:
	$(COMPOSE_DEV) up -d --build

dev-etl:
	$(COMPOSE_DEV) --profile etl up -d --build

down:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f

ps:
	$(COMPOSE_DEV) ps

prod-config:
	$(COMPOSE_PROD) config --quiet

help:
	@echo "init config dev dev-etl down logs ps prod-config"

.DEFAULT_GOAL := help
