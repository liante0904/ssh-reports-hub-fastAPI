SECRETS := python3 $(HOME)/secrets/generate_env.py private-hub
COMPOSE  := docker compose
UV_CACHE_DIR ?= /tmp/uv-cache
UV := UV_CACHE_DIR=$(UV_CACHE_DIR) uv

.PHONY: up down restart logs logs-api ps env test verify

up: env
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart: env
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f fastapi

ps:
	$(COMPOSE) ps

env:
	$(SECRETS)

test:
	$(UV) run pytest

verify: test
	PYTHONPYCACHEPREFIX=/tmp/pycache $(UV) run python -m compileall app tests

push:
	git push origin main

monitor:
	gh run watch $$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')

deploy: push monitor
