SECRETS := python3 $(HOME)/secrets/generate_env.py hub
COMPOSE  := docker compose

.PHONY: up down restart logs ps env

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

push:
	git push origin main

monitor:
	gh run watch $$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')

deploy: push monitor
